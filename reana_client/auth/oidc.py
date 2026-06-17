# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2026 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
"""OIDC device-flow and token refresh helpers."""

import base64
import hashlib
import json
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, Optional
from urllib.parse import urljoin

import requests

from reana_client.auth.storage import (
    clear_token_material,
    get_active_server,
    get_server_entry,
    normalize_server_url,
    upsert_server_entry,
)


DEFAULT_SCOPES = "openid profile email offline_access"
FALLBACK_SCOPES = "openid profile email"
EXPIRY_LEEWAY_SECONDS = 60
DISCOVERY_PATH = "/api/.well-known/openid-configuration"
PKCE_CODE_CHALLENGE_METHOD = "S256"


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
        "token_endpoint",
        "device_authorization_endpoint",
        "reana_cli_client_id",
    ]
    missing_fields = [field for field in required_fields if not metadata.get(field)]
    if missing_fields:
        raise AuthenticationError(
            "Authentication metadata is missing required field(s): "
            + ", ".join(missing_fields)
        )
    return metadata


def _start_device_authorization(metadata: Dict, scopes: str, pkce: Dict) -> Dict:
    """Start OIDC device authorization flow."""
    response = requests.post(
        metadata["device_authorization_endpoint"],
        data={
            "client_id": metadata["reana_cli_client_id"],
            "scope": scopes,
            "code_challenge": pkce["code_challenge"],
            "code_challenge_method": pkce["code_challenge_method"],
        },
        timeout=30,
        verify=False,
    )
    payload = _response_json(response)
    if response.ok:
        return payload
    if payload.get("error") == "invalid_scope" and scopes == DEFAULT_SCOPES:
        return _start_device_authorization(metadata, FALLBACK_SCOPES, pkce)
    raise AuthenticationError(
        "Could not start device login: "
        f"{payload.get('error_description') or payload.get('error') or response.text}"
    )


def _offline_access_not_allowed(payload: Dict) -> bool:
    """Return whether token response refused offline access."""
    error = (payload.get("error") or "").lower()
    description = (payload.get("error_description") or "").lower()
    return "offline" in description and (
        "not allowed" in description or error in {"invalid_grant", "invalid_scope"}
    )


def _store_token_response(server_url: str, metadata: Dict, token_response: Dict) -> Dict:
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
        "device_authorization_endpoint": metadata["device_authorization_endpoint"],
        "revocation_endpoint": metadata.get("revocation_endpoint"),
        "access_token": token_response.get("access_token"),
        "access_token_expires_at": _token_expires_at(token_response),
        "refresh_token": refresh_token,
        "refresh_token_expires_at": _refresh_token_expires_at(token_response),
    }
    return upsert_server_entry(server_url, entry)


def login_with_device_flow(
    server_url: str,
    display_callback: Callable[[Dict], None],
    sleep: Callable[[int], None] = time.sleep,
) -> Dict:
    """Perform OIDC device flow and store resulting credentials."""
    normalized_url = normalize_server_url(server_url)
    metadata = discover(normalized_url)
    scopes_to_try = [DEFAULT_SCOPES, FALLBACK_SCOPES]
    for scopes in scopes_to_try:
        pkce = generate_pkce_pair()
        device_response = _start_device_authorization(metadata, scopes, pkce)
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
                raise AuthenticationError(
                    "Device login expired. Please run login again."
                )
            if error == "access_denied":
                raise AuthenticationError("Device login was denied.")
            if scopes == DEFAULT_SCOPES and _offline_access_not_allowed(payload):
                break
            raise AuthenticationError(
                "Device login failed: "
                f"{payload.get('error_description') or error or response.text}"
            )
    raise AuthenticationError("Device login failed: offline access is not allowed.")


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
        "device_authorization_endpoint": server_entry[
            "device_authorization_endpoint"
        ],
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
