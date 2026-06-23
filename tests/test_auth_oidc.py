# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2026 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
"""REANA client OIDC authentication tests."""

from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import pytest

from reana_client.auth import oidc
from reana_client.auth.storage import (
    get_server_entry,
    load_config,
    normalize_server_url,
    upsert_server_entry,
)


class MockResponse:
    """Small requests response double."""

    def __init__(self, payload, ok=True, status_code=200):
        """Initialize response double."""
        self._payload = payload
        self.ok = ok
        self.status_code = status_code
        self.text = str(payload)

    def json(self):
        """Return response payload."""
        return self._payload


def test_credentials_are_stored_with_restrictive_permissions(tmp_path, monkeypatch):
    """Test credential store path, server normalization, and file permissions."""
    config_path = tmp_path / "reana-client.json"
    monkeypatch.setenv("REANA_CLIENT_CONFIG", str(config_path))

    upsert_server_entry(
        "HTTPS://reana.example.org/",
        {
            "issuer": "https://issuer.example.org",
            "client_id": "reana-cli",
            "access_token": "access",
        },
    )

    assert normalize_server_url("HTTPS://reana.example.org/") == (
        "https://reana.example.org"
    )
    assert normalize_server_url("localhost:5000/") == "http://localhost:5000"
    assert load_config()["active_server"] == "https://reana.example.org"
    assert get_server_entry("https://reana.example.org")["access_token"] == "access"
    assert oct(config_path.stat().st_mode & 0o777) == "0o600"
    assert oct(config_path.parent.stat().st_mode & 0o777) == "0o700"


def test_get_access_token_refreshes_expiring_token(tmp_path, monkeypatch):
    """Test refresh-token grant updates stored credentials."""
    config_path = tmp_path / "reana-client.json"
    monkeypatch.setenv("REANA_CLIENT_CONFIG", str(config_path))
    monkeypatch.setenv("REANA_SERVER_URL", "https://reana.example.org")
    upsert_server_entry(
        "https://reana.example.org",
        {
            "issuer": "https://issuer.example.org",
            "client_id": "reana-cli",
            "token_endpoint": "https://issuer.example.org/token",
            "device_authorization_endpoint": "https://issuer.example.org/device",
            "access_token": "old-access",
            "access_token_expires_at": oidc.format_timestamp(
                oidc.utcnow() + timedelta(seconds=10)
            ),
            "refresh_token": "old-refresh",
        },
    )

    def fake_post(url, data, timeout, verify):
        assert url == "https://issuer.example.org/token"
        assert data["grant_type"] == "refresh_token"
        assert data["refresh_token"] == "old-refresh"
        return MockResponse(
            {
                "access_token": "new-access",
                "refresh_token": "new-refresh",
                "expires_in": 3600,
            }
        )

    monkeypatch.setattr(oidc.requests, "post", fake_post)

    assert oidc.get_access_token() == "new-access"
    server_entry = get_server_entry("https://reana.example.org")
    assert server_entry["access_token"] == "new-access"
    assert server_entry["refresh_token"] == "new-refresh"


METADATA = {
    "issuer": "https://issuer.example.org",
    "authorization_endpoint": "https://issuer.example.org/auth",
    "token_endpoint": "https://issuer.example.org/token",
    "device_authorization_endpoint": "https://issuer.example.org/device",
    "reana_cli_client_id": "reana-cli",
}


class FakeLoopbackServer:
    """Loopback HTTP server double exposing a no-op ``server_close``."""

    def server_close(self):
        """Match the HTTPServer interface used in the ``finally`` block."""


def test_login_with_loopback_exchanges_code_with_pkce(tmp_path, monkeypatch):
    """Test the browser loopback flow exchanges the code using the verifier."""
    config_path = tmp_path / "reana-client.json"
    monkeypatch.setenv("REANA_CLIENT_CONFIG", str(config_path))
    redirect_uri = "http://127.0.0.1:5555/callback"
    captured = {}

    monkeypatch.setattr(oidc, "discover", lambda server_url: dict(METADATA))
    monkeypatch.setattr(
        oidc, "_start_callback_server", lambda: (FakeLoopbackServer(), redirect_uri)
    )

    def fake_wait(httpd, timeout):
        query = parse_qs(urlparse(captured["url"]).query)
        return {"code": "auth-code", "state": query["state"][0]}

    monkeypatch.setattr(oidc, "_wait_for_callback", fake_wait)

    def fake_post(url, data, timeout, verify):
        assert url == METADATA["token_endpoint"]
        assert data["grant_type"] == "authorization_code"
        assert data["code"] == "auth-code"
        assert data["redirect_uri"] == redirect_uri
        assert data["code_verifier"]
        return MockResponse(
            {"access_token": "access", "refresh_token": "refresh", "expires_in": 3600}
        )

    monkeypatch.setattr(oidc.requests, "post", fake_post)

    oidc.login_with_loopback(
        "https://reana.example.org",
        lambda url: captured.__setitem__("url", url),
        open_browser=lambda url: True,
    )

    params = parse_qs(urlparse(captured["url"]).query)
    assert params["response_type"] == ["code"]
    assert params["redirect_uri"] == [redirect_uri]
    assert params["code_challenge_method"] == ["S256"]
    assert params["code_challenge"]
    assert params["scope"] == [oidc.DEFAULT_SCOPES]
    entry = get_server_entry("https://reana.example.org")
    assert entry["access_token"] == "access"
    assert entry["refresh_token"] == "refresh"


def test_login_with_loopback_rejects_state_mismatch(tmp_path, monkeypatch):
    """Test the loopback flow fails closed on a mismatched state (CSRF guard)."""
    config_path = tmp_path / "reana-client.json"
    monkeypatch.setenv("REANA_CLIENT_CONFIG", str(config_path))

    monkeypatch.setattr(oidc, "discover", lambda server_url: dict(METADATA))
    monkeypatch.setattr(
        oidc,
        "_start_callback_server",
        lambda: (FakeLoopbackServer(), "http://127.0.0.1:5555/callback"),
    )
    monkeypatch.setattr(
        oidc,
        "_wait_for_callback",
        lambda httpd, timeout: {"code": "auth-code", "state": "forged-state"},
    )

    def fail_post(url, data, timeout, verify):
        raise AssertionError("token endpoint must not be called on state mismatch")

    monkeypatch.setattr(oidc.requests, "post", fail_post)

    with pytest.raises(oidc.AuthenticationError, match="state parameter mismatch"):
        oidc.login_with_loopback(
            "https://reana.example.org",
            lambda url: None,
            open_browser=lambda url: True,
        )


def test_device_flow_stores_credentials_with_pkce(tmp_path, monkeypatch):
    """Test the headless device flow uses offline scope and PKCE."""
    config_path = tmp_path / "reana-client.json"
    monkeypatch.setenv("REANA_CLIENT_CONFIG", str(config_path))
    posts = []

    monkeypatch.setattr(oidc, "discover", lambda server_url: dict(METADATA))

    def fake_post(url, data, timeout, verify):
        posts.append(data.copy())
        if url == METADATA["device_authorization_endpoint"]:
            assert data["scope"] == oidc.DEFAULT_SCOPES
            assert data["code_challenge"]
            assert data["code_challenge_method"] == "S256"
            return MockResponse(
                {
                    "device_code": "device-code",
                    "verification_uri": "https://issuer.example.org/device",
                    "user_code": "1234",
                    "interval": 0,
                }
            )
        assert data["grant_type"] == "urn:ietf:params:oauth:grant-type:device_code"
        assert data["code_verifier"]
        return MockResponse(
            {"access_token": "access", "refresh_token": "refresh", "expires_in": 3600}
        )

    monkeypatch.setattr(oidc.requests, "post", fake_post)

    prompts = []
    oidc.login_with_device_flow(
        "https://reana.example.org",
        prompts.append,
        sleep=lambda interval: None,
    )

    assert prompts[0]["device_code"] == "device-code"
    assert get_server_entry("https://reana.example.org")["refresh_token"] == "refresh"


def test_pkce_pair_uses_s256_challenge():
    """Test PKCE verifier/challenge generation."""
    pkce = oidc.generate_pkce_pair()

    assert len(pkce["code_verifier"]) >= 43
    assert pkce["code_challenge"]
    assert "=" not in pkce["code_challenge"]
    assert pkce["code_challenge_method"] == "S256"
