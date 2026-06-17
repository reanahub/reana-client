# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2026 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
"""Exercise authentication TLS policy with a self-signed HTTPS issuer."""

import json
import shutil
import ssl
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest
import requests

from reana_client import config
from reana_client.auth import oidc, storage


@pytest.fixture(scope="module")
def certificate(tmp_path_factory):
    """Generate a short-lived certificate valid for the test server address."""
    openssl = shutil.which("openssl")
    if not openssl:
        pytest.skip("OpenSSL is needed to generate the HTTPS test certificate")
    directory = tmp_path_factory.mktemp("auth-tls")
    cert, key = directory / "cert.pem", directory / "key.pem"
    subprocess.run(
        [
            openssl,
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "1",
            "-subj",
            "/CN=localhost",
            "-addext",
            "subjectAltName=IP:127.0.0.1",
            "-keyout",
            str(key),
            "-out",
            str(cert),
        ],
        check=True,
        capture_output=True,
    )
    return str(cert), str(key)


@pytest.fixture
def issuer(certificate):
    """Serve discovery and token endpoints through one self-signed ingress."""
    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            self.reply(metadata)

        def do_POST(self):  # noqa: N802
            data = parse_qs(
                self.rfile.read(int(self.headers["Content-Length"])).decode()
            )
            received.append((self.path, data))
            if self.path.endswith("/device"):
                self.reply(
                    {
                        "device_code": "device",
                        "user_code": "ABCD",
                        "verification_uri": base + "/verify",
                        "expires_in": 60,
                        "interval": 1,
                    }
                )
            else:
                self.reply(
                    {
                        "access_token": "access",
                        "refresh_token": "refresh",
                        "expires_in": 0,
                    }
                )

        def reply(self, payload):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(payload).encode())

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(*certificate)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    base = f"https://127.0.0.1:{server.server_port}"
    metadata = {
        "issuer": base + "/keycloak",
        "authorization_endpoint": base + "/keycloak/authorize",
        "token_endpoint": base + "/keycloak/token",
        "device_authorization_endpoint": base + "/keycloak/device",
        "revocation_endpoint": base + "/keycloak/revoke",
        "reana_cli_client_id": "reana-client",
    }
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield base, metadata, received
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch, tmp_path):
    """Keep credentials and certificate trust independent of the developer."""
    monkeypatch.setenv("REANA_CLIENT_CONFIG", str(tmp_path / "credentials.json"))
    monkeypatch.setenv(config.TLS_VERIFY_ENV, "no")
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    for name in (config.CA_CERTS_ENV, "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"):
        monkeypatch.delenv(name, raising=False)


def test_bundled_issuer_login_refresh_and_logout(issuer, monkeypatch):
    """Browser and device grants, refresh and revocation honour the bypass."""
    base, metadata, received = issuer
    query = {}

    def display(url):
        query.update(parse_qs(urlparse(url).query))

    monkeypatch.setattr(
        oidc,
        "_wait_for_callback",
        lambda *_args: {"code": "code", "state": query["state"][0]},
    )
    entry = oidc.login_with_loopback(base, display, open_browser=lambda _url: False)
    assert entry["access_token"] == "access"
    assert oidc.refresh_credentials(base)["access_token"] == "access"
    assert oidc.logout(base) is None
    entry = oidc.login_with_device_flow(
        base, lambda _prompt: None, sleep=lambda _: None
    )
    assert entry["access_token"] == "access"
    oidc._revoke_discarded_tokens(base, metadata, {"refresh_token": "discarded"})
    assert [data.get("grant_type", [None])[0] for _, data in received] == [
        "authorization_code",
        "refresh_token",
        None,
        None,
        "urn:ietf:params:oauth:grant-type:device_code",
        None,
    ]
    assert [path for path, _ in received].count("/keycloak/revoke") == 2


@pytest.mark.parametrize("trusted", [False, True])
def test_external_issuer_requires_trust(issuer, certificate, monkeypatch, trusted):
    """An issuer on another port stays strict unless its CA is supplied."""
    _, metadata, received = issuer
    server_url = "https://127.0.0.1:1"
    if trusted:
        monkeypatch.setenv(config.CA_CERTS_ENV, certificate[0])
    pkce = oidc.generate_pkce_pair()
    entry = {
        "issuer": metadata["issuer"],
        "client_id": "reana-client",
        "token_endpoint": metadata["token_endpoint"],
        "revocation_endpoint": metadata["revocation_endpoint"],
        "refresh_token": "refresh",
    }
    storage.upsert_server_entry(server_url, entry)
    operations = [
        lambda: oidc._exchange_authorization_code(
            server_url, metadata, "code", pkce, "http://localhost/callback"
        ),
        lambda: oidc._start_device_authorization(server_url, metadata, pkce),
        lambda: oidc.refresh_credentials(server_url),
    ]
    for operation in operations:
        if trusted:
            operation()
        else:
            with pytest.raises(oidc.AuthenticationError) as error:
                operation()
            assert isinstance(error.value.__cause__, requests.exceptions.SSLError)
    oidc._revoke_discarded_tokens(server_url, metadata, {"refresh_token": "discarded"})
    warning = oidc.logout(server_url)
    assert (warning is None) == trusted
    assert len(received) == (5 if trusted else 0)


@pytest.mark.parametrize(
    ("server", "endpoint", "same"),
    [
        ("https://localhost:30443", "https://localhost:30443/keycloak/token", True),
        ("https://LOCALHOST", "https://localhost:443/keycloak", True),
        ("https://localhost:0443", "https://localhost/keycloak", True),
        ("https://[::1]:30443", "https://[::1]:30443/keycloak", True),
        ("https://localhost", "https://localhost:30443/keycloak", False),
        ("https://localhost", "https://127.0.0.1/keycloak", False),
        ("https://localhost", "https://localhost.example.org/keycloak", False),
        ("https://localhost", "http://localhost/keycloak", False),
        ("http://localhost", "https://localhost/keycloak", False),
        ("https://localhost", "https://localhost@evil.example/keycloak", False),
        ("https://localhost", "https://user@localhost/keycloak", False),
        ("https://localhost:0", "https://localhost:0/keycloak", False),
        ("https://localhost:65536", "https://localhost:65536/keycloak", False),
        ("https://localhost:bad", "https://localhost:bad/keycloak", False),
        ("", "https://localhost/keycloak", False),
    ],
)
def test_endpoint_origin_boundary(server, endpoint, same):
    """Only an exact HTTPS origin match can inherit disabled verification."""
    assert config.tls_verify_for_url(server, endpoint) is (not same)
