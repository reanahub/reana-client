# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2026 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
"""REANA client OIDC authentication tests."""

from datetime import timedelta

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


def test_device_flow_retries_without_offline_access(tmp_path, monkeypatch):
    """Test invalid offline_access scope fallback."""
    config_path = tmp_path / "reana-client.json"
    monkeypatch.setenv("REANA_CLIENT_CONFIG", str(config_path))
    metadata = {
        "issuer": "https://issuer.example.org",
        "token_endpoint": "https://issuer.example.org/token",
        "device_authorization_endpoint": "https://issuer.example.org/device",
        "reana_cli_client_id": "reana-cli",
    }
    posts = []

    def fake_discover(server_url):
        return metadata

    def fake_post(url, data, timeout, verify):
        posts.append(data.copy())
        if data.get("scope") == oidc.DEFAULT_SCOPES:
            assert data["code_challenge"]
            assert data["code_challenge_method"] == "S256"
            return MockResponse({"error": "invalid_scope"}, ok=False, status_code=400)
        if data.get("scope") == oidc.FALLBACK_SCOPES:
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
        assert data["code_verifier"]
        return MockResponse(
            {
                "access_token": "access",
                "refresh_token": "refresh",
                "expires_in": 3600,
            }
        )

    monkeypatch.setattr(oidc, "discover", fake_discover)
    monkeypatch.setattr(oidc.requests, "post", fake_post)

    prompts = []
    oidc.login_with_device_flow(
        "https://reana.example.org",
        prompts.append,
        sleep=lambda interval: None,
    )

    assert posts[0]["scope"] == oidc.DEFAULT_SCOPES
    assert posts[1]["scope"] == oidc.FALLBACK_SCOPES
    assert prompts[0]["device_code"] == "device-code"
    assert get_server_entry("https://reana.example.org")["refresh_token"] == "refresh"


def test_device_flow_restarts_without_offline_access_when_token_endpoint_refuses_it(
    tmp_path, monkeypatch
):
    """Test fallback when token endpoint refuses offline tokens."""
    config_path = tmp_path / "reana-client.json"
    monkeypatch.setenv("REANA_CLIENT_CONFIG", str(config_path))
    metadata = {
        "issuer": "https://issuer.example.org",
        "token_endpoint": "https://issuer.example.org/token",
        "device_authorization_endpoint": "https://issuer.example.org/device",
        "reana_cli_client_id": "reana-cli",
    }
    posts = []
    token_attempts = []

    def fake_discover(server_url):
        return metadata

    def fake_post(url, data, timeout, verify):
        posts.append(data.copy())
        if data.get("scope") == oidc.DEFAULT_SCOPES:
            return MockResponse(
                {
                    "device_code": "offline-device-code",
                    "verification_uri": "https://issuer.example.org/device",
                    "user_code": "1111",
                    "interval": 0,
                }
            )
        if data.get("scope") == oidc.FALLBACK_SCOPES:
            return MockResponse(
                {
                    "device_code": "refresh-device-code",
                    "verification_uri": "https://issuer.example.org/device",
                    "user_code": "2222",
                    "interval": 0,
                }
            )

        token_attempts.append(data.copy())
        if data["device_code"] == "offline-device-code":
            return MockResponse(
                {
                    "error": "invalid_grant",
                    "error_description": (
                        "Offline tokens not allowed for the user or client"
                    ),
                },
                ok=False,
                status_code=400,
            )
        return MockResponse(
            {
                "access_token": "access",
                "refresh_token": "refresh",
                "expires_in": 3600,
            }
        )

    monkeypatch.setattr(oidc, "discover", fake_discover)
    monkeypatch.setattr(oidc.requests, "post", fake_post)

    prompts = []
    oidc.login_with_device_flow(
        "https://reana.example.org",
        prompts.append,
        sleep=lambda interval: None,
    )

    assert posts[0]["scope"] == oidc.DEFAULT_SCOPES
    assert posts[2]["scope"] == oidc.FALLBACK_SCOPES
    assert prompts[0]["device_code"] == "offline-device-code"
    assert prompts[1]["device_code"] == "refresh-device-code"
    assert token_attempts[0]["device_code"] == "offline-device-code"
    assert token_attempts[1]["device_code"] == "refresh-device-code"
    assert get_server_entry("https://reana.example.org")["refresh_token"] == "refresh"


def test_pkce_pair_uses_s256_challenge():
    """Test PKCE verifier/challenge generation."""
    pkce = oidc.generate_pkce_pair()

    assert len(pkce["code_verifier"]) >= 43
    assert pkce["code_challenge"]
    assert "=" not in pkce["code_challenge"]
    assert pkce["code_challenge_method"] == "S256"
