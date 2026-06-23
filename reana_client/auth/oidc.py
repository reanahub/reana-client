# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2026 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
"""OIDC login (loopback PKCE and device flow) and token refresh helpers."""

import base64
import hashlib
import json
import secrets
import time
import webbrowser
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Callable, Dict, Optional, Tuple
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

import requests

from reana_client.auth.storage import (
    clear_token_material,
    get_active_server,
    get_server_entry,
    normalize_server_url,
    upsert_server_entry,
)

DEFAULT_SCOPES = "openid profile email offline_access"
EXPIRY_LEEWAY_SECONDS = 60
DISCOVERY_PATH = "/api/.well-known/openid-configuration"
PKCE_CODE_CHALLENGE_METHOD = "S256"

LOOPBACK_HOST = "127.0.0.1"
LOOPBACK_CALLBACK_PATH = "/callback"
LOOPBACK_TIMEOUT_SECONDS = 300

_CALLBACK_SUCCESS_HTML = (
    b"<html><body><h1>REANA login complete.</h1>"
    b"<p>You can close this tab and return to the terminal.</p></body></html>"
)
_CALLBACK_ERROR_HTML = (
    b"<html><body><h1>REANA login failed.</h1>"
    b"<p>Return to the terminal for details.</p></body></html>"
)


class AuthenticationError(Exception):
    """Authentication failure visible to CLI users."""


def utcnow() -> datetime:
    """Return timezone-aware current UTC time."""
    return datetime.now(timezone.utc)


def parse_timestamp(value: Optional[str]) -> Optional[datetime]:
    """Parse ISO timestamp stored in credential file."""
    if not value:
        return None
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def format_timestamp(value: datetime) -> str:
    """Format timestamp for credential file."""
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _decode_jwt_exp(token: Optional[str]) -> Optional[datetime]:
    """Decode JWT exp claim without validating the token."""
    if not token or token.count(".") < 2:
        return None
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    try:
        claims = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
        exp = claims.get("exp")
        return datetime.fromtimestamp(exp, timezone.utc) if exp else None
    except Exception:
        return None


def _token_expires_at(token_response: Dict) -> Optional[str]:
    """Return access token expiry timestamp from token response."""
    expires_in = token_response.get("expires_in")
    if expires_in is not None:
        return format_timestamp(utcnow() + timedelta(seconds=int(expires_in)))
    jwt_exp = _decode_jwt_exp(token_response.get("access_token"))
    return format_timestamp(jwt_exp) if jwt_exp else None


def _refresh_token_expires_at(token_response: Dict) -> Optional[str]:
    """Return refresh token expiry timestamp if issuer exposes it."""
    refresh_expires_in = token_response.get("refresh_expires_in")
    if refresh_expires_in is None:
        return None
    return format_timestamp(utcnow() + timedelta(seconds=int(refresh_expires_in)))


def _response_json(response: requests.Response) -> Dict:
    """Return JSON response or raise a readable authentication error."""
    try:
        return response.json()
    except ValueError as exc:
        raise AuthenticationError(
            f"Authentication server returned a non-JSON response: {response.text}"
        ) from exc


def _base64url_encode(value: bytes) -> str:
    """Return unpadded base64url-encoded value."""
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def generate_pkce_pair() -> Dict[str, str]:
    """Generate PKCE verifier and S256 challenge."""
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = _base64url_encode(
        hashlib.sha256(code_verifier.encode("ascii")).digest()
    )
    return {
        "code_verifier": code_verifier,
        "code_challenge": code_challenge,
        "code_challenge_method": PKCE_CODE_CHALLENGE_METHOD,
    }


def discover(server_url: str) -> Dict:
    """Discover OIDC endpoints relayed by REANA server."""
    normalized_url = normalize_server_url(server_url)
    response = requests.get(
        urljoin(normalized_url + "/", DISCOVERY_PATH.lstrip("/")),
        timeout=30,
        verify=False,
    )
    if not response.ok:
        raise AuthenticationError(
            "Could not discover authentication metadata from "
            f"{normalized_url}: HTTP {response.status_code}"
        )
    metadata = _response_json(response)
    required_fields = [
        "issuer",
        "authorization_endpoint",
        "token_endpoint",
        "reana_cli_client_id",
    ]
    missing_fields = [field for field in required_fields if not metadata.get(field)]
    if missing_fields:
        raise AuthenticationError(
            "Authentication metadata is missing required field(s): "
            + ", ".join(missing_fields)
        )
    return metadata


def _store_token_response(
    server_url: str, metadata: Dict, token_response: Dict
) -> Dict:
    """Persist token response for a server."""
    refresh_token = token_response.get("refresh_token")
    if not refresh_token:
        raise AuthenticationError(
            "Authentication server did not return a refresh token. "
            "Please enable refresh/offline tokens for the REANA CLI client."
        )
    entry = {
        "issuer": metadata["issuer"],
        "client_id": metadata["reana_cli_client_id"],
        "token_endpoint": metadata["token_endpoint"],
        "authorization_endpoint": metadata.get("authorization_endpoint"),
        "device_authorization_endpoint": metadata.get("device_authorization_endpoint"),
        "revocation_endpoint": metadata.get("revocation_endpoint"),
        "access_token": token_response.get("access_token"),
        "access_token_expires_at": _token_expires_at(token_response),
        "refresh_token": refresh_token,
        "refresh_token_expires_at": _refresh_token_expires_at(token_response),
    }
    return upsert_server_entry(server_url, entry)


def _build_authorization_url(
    metadata: Dict, scopes: str, pkce: Dict, state: str, redirect_uri: str
) -> str:
    """Build the OIDC authorization endpoint URL for the loopback flow."""
    params = {
        "response_type": "code",
        "client_id": metadata["reana_cli_client_id"],
        "redirect_uri": redirect_uri,
        "scope": scopes,
        "state": state,
        "code_challenge": pkce["code_challenge"],
        "code_challenge_method": pkce["code_challenge_method"],
    }
    return metadata["authorization_endpoint"] + "?" + urlencode(params)


class _CallbackHandler(BaseHTTPRequestHandler):
    """Capture the single authorization-code redirect on the loopback server."""

    def do_GET(self):  # noqa: N802
        """Record callback query parameters and acknowledge the browser."""
        parsed = urlparse(self.path)
        if parsed.path != LOOPBACK_CALLBACK_PATH:
            self.send_response(404)
            self.end_headers()
            return
        query = {key: values[0] for key, values in parse_qs(parsed.query).items()}
        self.server.callback_query = query
        body = _CALLBACK_SUCCESS_HTML if "code" in query else _CALLBACK_ERROR_HTML
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        """Silence the default stderr request logging."""


def _start_callback_server() -> Tuple[HTTPServer, str]:
    """Start a loopback HTTP server and return it with its redirect URI."""
    httpd = HTTPServer((LOOPBACK_HOST, 0), _CallbackHandler)
    httpd.callback_query = None
    port = httpd.server_address[1]
    redirect_uri = f"http://{LOOPBACK_HOST}:{port}{LOOPBACK_CALLBACK_PATH}"
    return httpd, redirect_uri


def _wait_for_callback(httpd: HTTPServer, timeout: int) -> Optional[Dict]:
    """Serve requests until the authorization callback arrives or times out."""
    deadline = time.monotonic() + timeout
    httpd.callback_query = None
    while httpd.callback_query is None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        httpd.timeout = remaining
        httpd.handle_request()
    return httpd.callback_query


def _exchange_authorization_code(
    metadata: Dict, code: str, pkce: Dict, redirect_uri: str
) -> Dict:
    """Exchange an authorization code for tokens using the PKCE verifier."""
    response = requests.post(
        metadata["token_endpoint"],
        data={
            "grant_type": "authorization_code",
            "client_id": metadata["reana_cli_client_id"],
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": pkce["code_verifier"],
        },
        timeout=30,
        verify=False,
    )
    payload = _response_json(response)
    if not response.ok:
        raise AuthenticationError(
            "Browser login failed: "
            f"{payload.get('error_description') or payload.get('error') or response.text}"
        )
    return payload


def login_with_loopback(
    server_url: str,
    display_url: Callable[[str], None],
    open_browser: Callable[[str], bool] = webbrowser.open,
    timeout: int = LOOPBACK_TIMEOUT_SECONDS,
) -> Dict:
    """Perform the loopback authorization-code + PKCE flow and store credentials."""
    normalized_url = normalize_server_url(server_url)
    metadata = discover(normalized_url)
    pkce = generate_pkce_pair()
    state = secrets.token_urlsafe(32)

    httpd, redirect_uri = _start_callback_server()
    try:
        authorization_url = _build_authorization_url(
            metadata, DEFAULT_SCOPES, pkce, state, redirect_uri
        )
        display_url(authorization_url)
        try:
            open_browser(authorization_url)
        except Exception:
            pass
        query = _wait_for_callback(httpd, timeout)
    finally:
        httpd.server_close()

    if query is None:
        raise AuthenticationError("Browser login timed out. Please run login again.")
    if query.get("error"):
        raise AuthenticationError(
            "Browser login failed: "
            f"{query.get('error_description') or query.get('error')}"
        )
    returned_state = query.get("state")
    if not returned_state or not secrets.compare_digest(returned_state, state):
        raise AuthenticationError(
            "Browser login failed: state parameter mismatch (possible CSRF)."
        )
    code = query.get("code")
    if not code:
        raise AuthenticationError(
            "Browser login failed: no authorization code was returned."
        )

    token_response = _exchange_authorization_code(metadata, code, pkce, redirect_uri)
    return _store_token_response(normalized_url, metadata, token_response)


def _start_device_authorization(metadata: Dict, pkce: Dict) -> Dict:
    """Start OIDC device authorization flow."""
    response = requests.post(
        metadata["device_authorization_endpoint"],
        data={
            "client_id": metadata["reana_cli_client_id"],
            "scope": DEFAULT_SCOPES,
            "code_challenge": pkce["code_challenge"],
            "code_challenge_method": pkce["code_challenge_method"],
        },
        timeout=30,
        verify=False,
    )
    payload = _response_json(response)
    if response.ok:
        return payload
    raise AuthenticationError(
        "Could not start device login: "
        f"{payload.get('error_description') or payload.get('error') or response.text}"
    )


def login_with_device_flow(
    server_url: str,
    display_callback: Callable[[Dict], None],
    sleep: Callable[[int], None] = time.sleep,
) -> Dict:
    """Perform OIDC device flow (headless fallback) and store credentials."""
    normalized_url = normalize_server_url(server_url)
    metadata = discover(normalized_url)
    if not metadata.get("device_authorization_endpoint"):
        raise AuthenticationError(
            "This REANA server does not advertise a device authorization endpoint."
        )
    pkce = generate_pkce_pair()
    device_response = _start_device_authorization(metadata, pkce)
    display_callback(device_response)

    interval = int(device_response.get("interval", 5))
    device_code = device_response["device_code"]
    while True:
        sleep(interval)
        response = requests.post(
            metadata["token_endpoint"],
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device_code,
                "client_id": metadata["reana_cli_client_id"],
                "code_verifier": pkce["code_verifier"],
            },
            timeout=30,
            verify=False,
        )
        payload = _response_json(response)
        if response.ok:
            return _store_token_response(normalized_url, metadata, payload)

        error = payload.get("error")
        if error == "authorization_pending":
            continue
        if error == "slow_down":
            interval += 5
            continue
        if error == "expired_token":
            raise AuthenticationError("Device login expired. Please run login again.")
        if error == "access_denied":
            raise AuthenticationError("Device login was denied.")
        raise AuthenticationError(
            "Device login failed: "
            f"{payload.get('error_description') or error or response.text}"
        )


def _access_token_valid(server_entry: Dict) -> bool:
    """Return whether stored access token can be used now."""
    access_token = server_entry.get("access_token")
    expires_at = parse_timestamp(server_entry.get("access_token_expires_at"))
    if not access_token or not expires_at:
        return False
    return expires_at - timedelta(seconds=EXPIRY_LEEWAY_SECONDS) > utcnow()


def refresh_credentials(server_url: str, server_entry: Optional[Dict] = None) -> Dict:
    """Refresh credentials for a server."""
    normalized_url = normalize_server_url(server_url)
    server_entry = server_entry or get_server_entry(normalized_url)
    refresh_token = server_entry.get("refresh_token")
    if not refresh_token:
        raise AuthenticationError("Please run `reana-client login`.")

    response = requests.post(
        server_entry["token_endpoint"],
        data={
            "grant_type": "refresh_token",
            "client_id": server_entry["client_id"],
            "refresh_token": refresh_token,
        },
        timeout=30,
        verify=False,
    )
    payload = _response_json(response)
    if not response.ok:
        clear_token_material(normalized_url)
        raise AuthenticationError("Please run `reana-client login`.")

    metadata = {
        "issuer": server_entry["issuer"],
        "reana_cli_client_id": server_entry["client_id"],
        "token_endpoint": server_entry["token_endpoint"],
        "authorization_endpoint": server_entry.get("authorization_endpoint"),
        "device_authorization_endpoint": server_entry.get(
            "device_authorization_endpoint"
        ),
        "revocation_endpoint": server_entry.get("revocation_endpoint"),
    }
    if "refresh_token" not in payload:
        payload["refresh_token"] = refresh_token
    return _store_token_response(normalized_url, metadata, payload)


def get_access_token() -> str:
    """Return valid access token for the active server, refreshing as needed."""
    server_url = get_active_server()
    if not server_url:
        raise AuthenticationError("REANA client is not connected to any REANA cluster.")
    server_entry = get_server_entry(server_url)
    if _access_token_valid(server_entry):
        return server_entry["access_token"]
    return refresh_credentials(server_url, server_entry)["access_token"]


def logout(server_url: Optional[str] = None) -> Optional[str]:
    """Logout from active server and return remote revocation warning if any."""
    server_url = server_url or get_active_server()
    if not server_url:
        raise AuthenticationError("REANA client is not connected to any REANA cluster.")
    server_entry = get_server_entry(server_url)
    refresh_token = server_entry.get("refresh_token")
    revocation_endpoint = server_entry.get("revocation_endpoint")
    warning = None
    if refresh_token and revocation_endpoint:
        try:
            response = requests.post(
                revocation_endpoint,
                data={
                    "client_id": server_entry["client_id"],
                    "token": refresh_token,
                    "token_type_hint": "refresh_token",
                },
                timeout=30,
                verify=False,
            )
            if not response.ok:
                warning = (
                    "Remote token revocation failed with "
                    f"HTTP {response.status_code}."
                )
        except requests.RequestException as exc:
            warning = f"Remote token revocation failed: {exc}"
    clear_token_material(server_url)
    return warning
