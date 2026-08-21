# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2026 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
"""REANA client OIDC authentication tests."""

import logging
import time
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import pytest

from reana_client import config
from reana_client.auth import oidc
from reana_client.auth import storage
from reana_client.auth.storage import (
    get_server_entry,
    load_config,
    normalize_server_url,
    upsert_server_entry,
)


class MockResponse:
    """Small requests response double."""

    _REDIRECT_STATI = (301, 302, 303, 307, 308)

    def __init__(self, payload, ok=True, status_code=200, headers=None):
        """Initialize response double."""
        self._payload = payload
        self.ok = ok
        self.status_code = status_code
        self.text = str(payload)
        self.headers = headers or {}

    def json(self):
        """Return response payload."""
        return self._payload

    @property
    def is_redirect(self):
        """Mirror ``requests.Response.is_redirect``."""
        return "location" in self.headers and self.status_code in self._REDIRECT_STATI

    @property
    def is_permanent_redirect(self):
        """Mirror ``requests.Response.is_permanent_redirect``."""
        return "location" in self.headers and self.status_code in (301, 308)


def test_credentials_are_stored_with_restrictive_permissions(tmp_path, monkeypatch):
    """Test credential store path, server normalization, and file permissions."""
    config_path = tmp_path / "reana-client.json"
    tmp_path.chmod(0o755)
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
    assert normalize_server_url("localhost:5000/") == "https://localhost:5000"
    with pytest.raises(ValueError, match="must use HTTPS"):
        normalize_server_url("http://localhost:5000/")
    with pytest.raises(ValueError, match="must use HTTPS"):
        normalize_server_url("ftp://localhost/")
    assert load_config()["active_server"] == "https://reana.example.org"
    assert get_server_entry("https://reana.example.org")["access_token"] == "access"
    assert oct(config_path.stat().st_mode & 0o777) == "0o600"
    assert oct(config_path.parent.stat().st_mode & 0o777) == "0o755"


def test_default_config_directory_has_restrictive_permissions(tmp_path, monkeypatch):
    """Test the dedicated default config directory is restricted."""
    config_path = tmp_path / ".config" / "reana" / "reana-client.json"
    monkeypatch.delenv("REANA_CLIENT_CONFIG", raising=False)
    monkeypatch.setattr(storage, "DEFAULT_CONFIG_PATH", str(config_path))

    storage.save_config(storage.empty_config())

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

    def fake_post(url, data, timeout, allow_redirects, verify):
        assert url == "https://issuer.example.org/token"
        assert data["grant_type"] == "refresh_token"
        assert data["refresh_token"] == "old-refresh"
        assert verify is True
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


def test_refresh_credentials_releases_lock_before_network_call(tmp_path, monkeypatch):
    """The credential-store lock must not be held across the token request.

    A slow or unresponsive issuer would otherwise block every other
    concurrent ``reana-client`` invocation on the machine for the full
    request timeout, since ``get_access_token()`` takes the same lock
    before delegating here. Verified directly against the real OS-level
    lock file (not a mock), from inside the mocked network call itself.
    """
    import fcntl

    config_path = tmp_path / "reana-client.json"
    monkeypatch.setenv("REANA_CLIENT_CONFIG", str(config_path))
    monkeypatch.setenv("REANA_SERVER_URL", "https://reana.example.org")
    upsert_server_entry(
        "https://reana.example.org",
        {
            "issuer": "https://issuer.example.org",
            "client_id": "reana-cli",
            "token_endpoint": "https://issuer.example.org/token",
            "access_token": "old-access",
            "access_token_expires_at": oidc.format_timestamp(
                oidc.utcnow() + timedelta(seconds=10)
            ),
            "refresh_token": "old-refresh",
        },
    )

    lock_path = str(config_path) + ".lock"

    def fake_post(url, data, timeout, allow_redirects, verify):
        # A second, independent file handle on the same lock file must be
        # able to acquire it *right now*, non-blocking, proving
        # get_access_token()/refresh_credentials() released it before
        # making this request rather than holding it for the duration.
        probe = open(lock_path, "a+", encoding="utf-8")
        try:
            fcntl.flock(probe.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(probe.fileno(), fcntl.LOCK_UN)
        except BlockingIOError:
            pytest.fail("credential store lock is still held during the network call")
        finally:
            probe.close()
        return MockResponse(
            {"access_token": "new-access", "refresh_token": "new-refresh"}
        )

    monkeypatch.setattr(oidc.requests, "post", fake_post)

    assert oidc.get_access_token() == "new-access"


def test_logout_holds_lock_across_revocation_request(tmp_path, monkeypatch):
    """logout() must hold the credential-store lock for its whole duration.

    Unlike refresh (a hot path, fixed to release the lock around its
    network call), logout is a rare, one-shot action -- holding the lock
    across its revocation request has no throughput cost and prevents a
    concurrent refresh from rotating the token between logout's read and
    its final clear, which would otherwise revoke a stale token while
    wiping a live, newly-rotated one from local disk without ever
    revoking it at the issuer. Verified directly against the real
    OS-level lock file (not a mock), from inside the mocked network call.
    """
    import fcntl

    config_path = tmp_path / "reana-client.json"
    monkeypatch.setenv("REANA_CLIENT_CONFIG", str(config_path))
    server_url = "https://reana.example.org"
    upsert_server_entry(
        server_url,
        {
            "client_id": "reana-cli",
            "revocation_endpoint": "https://issuer.example.org/revoke",
            "access_token": "old-access",
            "refresh_token": "old-refresh",
        },
    )

    lock_path = str(config_path) + ".lock"

    def fake_post(url, data, timeout, allow_redirects, verify):
        probe = open(lock_path, "a+", encoding="utf-8")
        try:
            fcntl.flock(probe.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(probe.fileno(), fcntl.LOCK_UN)
            pytest.fail(
                "credential store lock was NOT held during logout's "
                "revocation request"
            )
        except BlockingIOError:
            pass  # expected: the lock is held, as it should be.
        finally:
            probe.close()
        return MockResponse({}, ok=True)

    monkeypatch.setattr(oidc.requests, "post", fake_post)

    warning = oidc.logout(server_url)

    assert warning is None
    server_entry = get_server_entry(server_url)
    assert "access_token" not in server_entry
    assert "refresh_token" not in server_entry


@pytest.mark.parametrize("status_code", [429, 500, 503])
def test_refresh_transient_http_error_preserves_credentials(
    status_code, tmp_path, monkeypatch
):
    """Test retryable refresh failures do not erase stored credentials."""
    config_path = tmp_path / "reana-client.json"
    monkeypatch.setenv("REANA_CLIENT_CONFIG", str(config_path))
    server_url = "https://reana.example.org"
    entry = {
        "issuer": "https://issuer.example.org",
        "client_id": "reana-cli",
        "token_endpoint": "https://issuer.example.org/token",
        "access_token": "old-access",
        "refresh_token": "old-refresh",
    }
    upsert_server_entry(server_url, entry)
    monkeypatch.setattr(
        oidc.requests,
        "post",
        lambda *args, **kwargs: MockResponse(
            {"error": "temporarily_unavailable"},
            ok=False,
            status_code=status_code,
        ),
    )

    with pytest.raises(oidc.AuthenticationError, match="Could not refresh"):
        oidc.refresh_credentials(server_url)

    assert get_server_entry(server_url)["refresh_token"] == "old-refresh"


def test_refresh_network_error_preserves_credentials(tmp_path, monkeypatch):
    """Test a network error leaves credentials available for a retry."""
    config_path = tmp_path / "reana-client.json"
    monkeypatch.setenv("REANA_CLIENT_CONFIG", str(config_path))
    server_url = "https://reana.example.org"
    upsert_server_entry(
        server_url,
        {
            "issuer": "https://issuer.example.org",
            "client_id": "reana-cli",
            "token_endpoint": "https://issuer.example.org/token",
            "access_token": "old-access",
            "refresh_token": "old-refresh",
        },
    )

    def raise_connection_error(*args, **kwargs):
        raise oidc.requests.ConnectionError("issuer unavailable")

    monkeypatch.setattr(oidc.requests, "post", raise_connection_error)

    with pytest.raises(
        oidc.AuthenticationError,
        match="Could not refresh authentication credentials. Please try again.",
    ):
        oidc.refresh_credentials(server_url)

    assert get_server_entry(server_url)["refresh_token"] == "old-refresh"


def test_refresh_rejects_stored_cleartext_token_endpoint(tmp_path, monkeypatch):
    """Credentials saved by an older client cannot trigger a cleartext refresh."""
    config_path = tmp_path / "reana-client.json"
    monkeypatch.setenv("REANA_CLIENT_CONFIG", str(config_path))
    server_url = "https://reana.example.org"
    upsert_server_entry(
        server_url,
        {
            "issuer": "https://issuer.example.org",
            "client_id": "reana-cli",
            "token_endpoint": "http://issuer.example.org/token",
            "access_token": "old-access",
            "refresh_token": "old-refresh",
        },
    )
    monkeypatch.setattr(
        oidc.requests,
        "post",
        lambda *args, **kwargs: pytest.fail("cleartext endpoint must not be called"),
    )

    with pytest.raises(oidc.AuthenticationError, match="token_endpoint.*HTTPS"):
        oidc.refresh_credentials(server_url)

    assert get_server_entry(server_url)["refresh_token"] == "old-refresh"


def test_invalid_refresh_grant_clears_credentials(tmp_path, monkeypatch):
    """Test an invalid refresh grant requires a clean login."""
    config_path = tmp_path / "reana-client.json"
    monkeypatch.setenv("REANA_CLIENT_CONFIG", str(config_path))
    server_url = "https://reana.example.org"
    upsert_server_entry(
        server_url,
        {
            "issuer": "https://issuer.example.org",
            "client_id": "reana-cli",
            "token_endpoint": "https://issuer.example.org/token",
            "access_token": "old-access",
            "refresh_token": "invalid-refresh",
        },
    )
    monkeypatch.setattr(
        oidc.requests,
        "post",
        lambda *args, **kwargs: MockResponse(
            {"error": "invalid_grant"}, ok=False, status_code=400
        ),
    )

    with pytest.raises(oidc.AuthenticationError, match="reana-client login"):
        oidc.refresh_credentials(server_url)

    server_entry = get_server_entry(server_url)
    assert "access_token" not in server_entry
    assert "refresh_token" not in server_entry


def test_invalid_grant_does_not_clobber_a_concurrently_rotated_token(
    tmp_path, monkeypatch
):
    """A losing process's invalid_grant must not destroy a winner's fresh token.

    refresh_credentials() no longer holds the credential-store lock across
    the token-endpoint request (fixed for the same reason as PR789-32),
    so two processes can now both read the same stale refresh token before
    either rotates it. One succeeds and stores a new token; the other's
    request is rejected as invalid_grant. The loser's cleanup must only
    clear token material if it's still the exact rejected token on disk --
    not unconditionally, or it would wipe out the winner's valid one too.
    """
    config_path = tmp_path / "reana-client.json"
    monkeypatch.setenv("REANA_CLIENT_CONFIG", str(config_path))
    server_url = "https://reana.example.org"
    upsert_server_entry(
        server_url,
        {
            "issuer": "https://issuer.example.org",
            "client_id": "reana-cli",
            "token_endpoint": "https://issuer.example.org/token",
            "access_token": "old-access",
            "refresh_token": "stale-refresh",
        },
    )

    def fake_post(url, data, timeout, allow_redirects, verify):
        # Simulate a winning concurrent process having already rotated the
        # token on disk while this ("losing") request was in flight.
        upsert_server_entry(
            server_url,
            {
                "access_token": "winner-access",
                "refresh_token": "winner-refresh",
            },
        )
        return MockResponse({"error": "invalid_grant"}, ok=False, status_code=400)

    monkeypatch.setattr(oidc.requests, "post", fake_post)

    with pytest.raises(oidc.AuthenticationError, match="changed by another process"):
        oidc.refresh_credentials(server_url)


def test_refresh_discards_result_after_a_concurrent_logout(tmp_path, monkeypatch):
    """An in-flight refresh must not resurrect credentials cleared by logout.

    refresh_credentials() releases the credential-store lock for the
    duration of its network call. If a concurrent logout() clears the store
    while that call is in flight, the refresh must detect this (via the
    credential epoch bumped by both logout and every successful write) and
    discard its result instead of writing fresh tokens back -- otherwise a
    slow refresh could silently undo an explicit logout.
    """
    config_path = tmp_path / "reana-client.json"
    monkeypatch.setenv("REANA_CLIENT_CONFIG", str(config_path))
    server_url = "https://reana.example.org"
    upsert_server_entry(
        server_url,
        {
            "issuer": "https://issuer.example.org",
            "client_id": "reana-cli",
            "token_endpoint": "https://issuer.example.org/token",
            "revocation_endpoint": "https://issuer.example.org/revoke",
            "access_token": "old-access",
            "refresh_token": "stale-refresh",
        },
    )

    revoke_calls = []

    def fake_post(url, data, timeout, allow_redirects, verify):
        if url == "https://issuer.example.org/token":
            # Simulate a concurrent logout clearing the store while this
            # refresh's network request is still in flight.
            storage.clear_token_material(server_url)
            return MockResponse(
                {
                    "access_token": "new-access",
                    "refresh_token": "new-refresh",
                    "expires_in": 3600,
                }
            )
        if url == "https://issuer.example.org/revoke":
            revoke_calls.append(data)
            return MockResponse({}, ok=True)
        raise AssertionError(f"unexpected POST to {url}")

    monkeypatch.setattr(oidc.requests, "post", fake_post)

    with pytest.raises(oidc.AuthenticationError, match="login"):
        oidc.refresh_credentials(server_url)

    entry = get_server_entry(server_url)
    assert "access_token" not in entry
    assert "refresh_token" not in entry
    assert revoke_calls and revoke_calls[0]["token"] == "new-refresh"


def test_concurrent_refresh_does_not_undo_an_explicit_switch_to_another_server(
    tmp_path, monkeypatch
):
    """PR777-19: a slow background refresh must not undo a concurrent login.

    Scenario: server A is active and its token is being refreshed in the
    background (e.g. from ``get_access_token()``); while that refresh's
    network request is still in flight, the user runs ``login`` to switch
    to server B. Once the refresh completes, its write-back must not flip
    ``active_server`` back to A -- the user's explicit switch to B must win.
    Drives the real ``refresh_credentials()``/``upsert_server_entry()``
    machinery from two real threads, using the same waiter-thread pattern
    as ``test_loopback_callback_ignores_a_bare_request_and_waits_for_the_real_one``.
    """
    import threading

    config_path = tmp_path / "reana-client.json"
    monkeypatch.setenv("REANA_CLIENT_CONFIG", str(config_path))
    server_a = "https://a.example.org"
    server_b = "https://b.example.org"

    upsert_server_entry(
        server_a,
        {
            "issuer": "https://issuer.example.org",
            "client_id": "reana-cli",
            "token_endpoint": "https://issuer.example.org/token",
            "access_token": "a-old-access",
            "refresh_token": "a-old-refresh",
        },
    )
    assert load_config()["active_server"] == server_a

    login_started = threading.Event()
    login_done = threading.Event()

    def fake_post(url, data, timeout, allow_redirects, verify):
        # Simulate a slow issuer: block the refresh's network call until the
        # concurrent "login" below has switched the active server to B.
        login_started.set()
        assert login_done.wait(timeout=5)
        return MockResponse(
            {
                "access_token": "a-new-access",
                "refresh_token": "a-new-refresh",
                "expires_in": 3600,
            }
        )

    monkeypatch.setattr(oidc.requests, "post", fake_post)

    refresh_result = {}

    def do_refresh():
        refresh_result["entry"] = oidc.refresh_credentials(server_a)

    refresher = threading.Thread(target=do_refresh)
    refresher.start()

    assert login_started.wait(timeout=5)
    # The user explicitly switches to server B while A's refresh is in
    # flight -- equivalent to what login_with_loopback()/
    # login_with_device_flow() do via _store_token_response().
    upsert_server_entry(
        server_b,
        {
            "issuer": "https://issuer.example.org",
            "client_id": "reana-cli",
            "token_endpoint": "https://issuer.example.org/token",
            "access_token": "b-access",
            "refresh_token": "b-refresh",
        },
    )
    assert load_config()["active_server"] == server_b
    login_done.set()

    refresher.join(timeout=5)
    assert not refresher.is_alive()
    assert refresh_result["entry"]["access_token"] == "a-new-access"

    # The background refresh's write-back must not have clobbered the
    # user's explicit switch to server B.
    assert load_config()["active_server"] == server_b
    assert get_server_entry(server_a)["access_token"] == "a-new-access"


def test_concurrent_refresh_reuses_winners_result_without_a_redundant_request(
    tmp_path, monkeypatch
):
    """A process that loses the refresh-lock race must not also hit the network.

    ``refresh_credentials()`` serialises the token-endpoint request itself via
    a refresh-scoped advisory lock, separate from the general credential-store
    lock, so that two concurrent CLI processes refreshing the same server
    don't both pay a round-trip against the same refresh token. A process
    that can't acquire the lock should wait for the winner and reuse its
    freshly written access token instead of making its own request.
    """
    config_path = tmp_path / "reana-client.json"
    monkeypatch.setenv("REANA_CLIENT_CONFIG", str(config_path))
    server_url = "https://reana.example.org"
    upsert_server_entry(
        server_url,
        {
            "issuer": "https://issuer.example.org",
            "client_id": "reana-cli",
            "token_endpoint": "https://issuer.example.org/token",
            "access_token": "old-access",
            "refresh_token": "stale-refresh",
        },
    )

    monkeypatch.setattr(oidc, "try_acquire_refresh_lock", lambda server_url: None)

    def fake_wait(server_url, timeout):
        # Simulate the winning process finishing its refresh while we waited.
        upsert_server_entry(
            server_url,
            {
                "access_token": "winner-access",
                "access_token_expires_at": None,
                "refresh_token": "winner-refresh",
            },
        )
        return True

    monkeypatch.setattr(oidc, "wait_for_refresh_lock", fake_wait)

    def fake_post(*args, **kwargs):
        raise AssertionError(
            "refresh_credentials() should not perform its own network "
            "request after reusing a concurrent winner's result"
        )

    monkeypatch.setattr(oidc.requests, "post", fake_post)

    result = oidc.refresh_credentials(server_url)
    assert result["access_token"] == "winner-access"


def test_refresh_lock_is_reentrant_across_independent_opens(tmp_path, monkeypatch):
    """The refresh lock genuinely serialises across independent file handles.

    ``try_acquire_refresh_lock``/``wait_for_refresh_lock`` open the lock file
    fresh each call (modeling separate OS processes) rather than sharing a
    handle -- confirms the lock actually contends with itself rather than
    being a no-op that always reports success.
    """
    config_path = tmp_path / "reana-client.json"
    monkeypatch.setenv("REANA_CLIENT_CONFIG", str(config_path))
    server_url = "https://reana.example.org"

    held = storage.try_acquire_refresh_lock(server_url)
    assert held is not None
    assert storage.try_acquire_refresh_lock(server_url) is None
    assert storage.wait_for_refresh_lock(server_url, timeout=0.2) is False

    storage.release_refresh_lock(held)
    assert storage.wait_for_refresh_lock(server_url, timeout=1) is True


def test_refresh_lock_path_differs_per_server(tmp_path, monkeypatch):
    """The refresh lock file is scoped per-server, not shared across servers.

    PR777-20: previously ``_refresh_lock_path()`` was derived purely from
    the config file path, so refreshing server A's tokens could serialise a
    concurrent command against a completely unrelated server B for up to
    ``REFRESH_LOCK_WAIT_SECONDS``, even though nothing about B's credentials
    is affected by A's refresh.
    """
    config_path = tmp_path / "reana-client.json"
    monkeypatch.setenv("REANA_CLIENT_CONFIG", str(config_path))

    path_a = storage._refresh_lock_path("https://a.example.org")
    path_b = storage._refresh_lock_path("https://b.example.org")

    assert path_a != path_b
    # Deterministic: the same server always maps to the same lock file.
    assert path_a == storage._refresh_lock_path("https://a.example.org")


def test_refresh_lock_does_not_block_a_different_server(tmp_path, monkeypatch):
    """Holding server A's refresh lock must not block acquiring server B's.

    Regression test for PR777-20, using the same waiter-thread pattern as
    ``test_loopback_callback_ignores_a_bare_request_and_waits_for_the_real_one``.
    """
    import threading

    config_path = tmp_path / "reana-client.json"
    monkeypatch.setenv("REANA_CLIENT_CONFIG", str(config_path))

    server_a = "https://a.example.org"
    server_b = "https://b.example.org"

    held_a = storage.try_acquire_refresh_lock(server_a)
    assert held_a is not None
    try:
        result = {}

        def try_b():
            result["lock"] = storage.try_acquire_refresh_lock(server_b)

        waiter = threading.Thread(target=try_b)
        waiter.start()
        waiter.join(timeout=5)

        assert not waiter.is_alive()
        assert result["lock"] is not None
        storage.release_refresh_lock(result["lock"])
    finally:
        storage.release_refresh_lock(held_a)


METADATA = {
    "issuer": "https://issuer.example.org",
    "authorization_endpoint": "https://issuer.example.org/auth",
    "token_endpoint": "https://issuer.example.org/token",
    "device_authorization_endpoint": "https://issuer.example.org/device",
    "reana_cli_client_id": "reana-cli",
}


def test_discover_verifies_tls(monkeypatch):
    """Test OIDC discovery verifies TLS by default."""

    def fake_get(url, timeout, allow_redirects, verify):
        assert url == ("https://reana.example.org/api/.well-known/openid-configuration")
        assert timeout == 30
        assert verify is True
        return MockResponse(dict(METADATA))

    monkeypatch.setattr(oidc.requests, "get", fake_get)

    assert oidc.discover("https://reana.example.org") == METADATA


@pytest.mark.parametrize(
    "field",
    [
        "issuer",
        "authorization_endpoint",
        "token_endpoint",
        "device_authorization_endpoint",
        "revocation_endpoint",
    ],
)
@pytest.mark.parametrize(
    "url",
    [
        "http://issuer.example.org/path",
        "ftp://issuer.example.org/path",
        "issuer.example.org/path",
    ],
)
def test_discover_rejects_non_https_oidc_metadata(field, url, monkeypatch):
    """Relayed credential-bearing endpoints must independently require HTTPS."""
    metadata = {**METADATA, "revocation_endpoint": "https://issuer.example.org/revoke"}
    metadata[field] = url
    monkeypatch.setattr(
        oidc.requests, "get", lambda *args, **kwargs: MockResponse(metadata)
    )

    with pytest.raises(oidc.AuthenticationError, match=rf"{field}.*HTTPS"):
        oidc.discover("https://reana.example.org")


@pytest.mark.parametrize("status_code", [301, 302, 303, 307, 308])
def test_discover_rejects_redirect_response(status_code, monkeypatch):
    """Discovery refuses to follow a redirect rather than trusting its target."""

    def fake_get(url, timeout, allow_redirects, verify):
        assert allow_redirects is False
        return MockResponse(
            {},
            status_code=status_code,
            headers={"location": "http://attacker.example.org/"},
        )

    monkeypatch.setattr(oidc.requests, "get", fake_get)

    with pytest.raises(oidc.AuthenticationError, match="redirect"):
        oidc.discover("https://reana.example.org")


def test_refresh_credentials_rejects_redirect_response(tmp_path, monkeypatch):
    """A redirected token-endpoint response must not be treated as a token grant.

    Regression test: ``requests`` follows 307/308 redirects by resending the
    original POST body -- including the refresh token -- to the redirect
    target. The refresh must instead refuse to follow it.
    """
    config_path = tmp_path / "reana-client.json"
    monkeypatch.setenv("REANA_CLIENT_CONFIG", str(config_path))
    upsert_server_entry(
        "https://reana.example.org",
        {
            "issuer": "https://issuer.example.org",
            "client_id": "reana-cli",
            "token_endpoint": "https://issuer.example.org/token",
            "refresh_token": "refresh-token",
        },
    )

    def fake_post(url, data, timeout, allow_redirects, verify):
        assert allow_redirects is False
        return MockResponse(
            {},
            status_code=307,
            headers={"location": "http://attacker.example.org/token"},
        )

    monkeypatch.setattr(oidc.requests, "post", fake_post)

    with pytest.raises(oidc.AuthenticationError, match="redirect"):
        oidc.refresh_credentials("https://reana.example.org")


def test_discover_reports_network_failure_as_authentication_error(monkeypatch):
    """Connection failures should be concise CLI errors, not tracebacks."""
    monkeypatch.setattr(
        oidc.requests,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            oidc.requests.ConnectionError("unavailable")
        ),
    )

    with pytest.raises(oidc.AuthenticationError, match="Could not connect"):
        oidc.discover("https://reana.example.org")


def test_tls_verify_defaults_to_enabled(monkeypatch):
    """Test TLS verification is enabled when no override is set."""
    monkeypatch.delenv(config.CA_CERTS_ENV, raising=False)
    monkeypatch.delenv(config.INSECURE_ENV, raising=False)

    assert config.tls_verify() is True


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "Yes", "on", "  true  "])
def test_tls_verify_disabled_by_insecure_env(value, monkeypatch):
    """Test REANA_INSECURE disables TLS verification for local testing."""
    monkeypatch.delenv(config.CA_CERTS_ENV, raising=False)
    monkeypatch.setenv(config.INSECURE_ENV, value)

    assert config.tls_verify() is False


@pytest.mark.parametrize("value", ["0", "false", "no", ""])
def test_tls_verify_ignores_falsey_insecure_env(value, monkeypatch):
    """Test non-truthy REANA_INSECURE values keep verification enabled."""
    monkeypatch.delenv(config.CA_CERTS_ENV, raising=False)
    monkeypatch.setenv(config.INSECURE_ENV, value)

    assert config.tls_verify() is True


def test_tls_verify_uses_ca_bundle_over_insecure(monkeypatch):
    """Test REANA_SERVER_CA_CERTS trusts a CA bundle and wins over insecure."""
    monkeypatch.setenv(config.INSECURE_ENV, "true")
    monkeypatch.setenv(config.CA_CERTS_ENV, "/etc/reana/ca.pem")

    assert config.tls_verify() == "/etc/reana/ca.pem"


class FakeLoopbackServer:
    """Loopback HTTP server double exposing a no-op ``server_close``."""

    def server_close(self):
        """Match the HTTPServer interface used in the ``finally`` block."""


def test_loopback_callback_ignores_a_bare_request_and_waits_for_the_real_one():
    """A GET with no code/error must not pre-empt the real OAuth redirect.

    Any other local process reaching the loopback port during the login
    window (its port number is printed in the displayed authorization URL)
    could otherwise send a bare request first and end the wait loop before
    the real browser callback arrives -- a trivial local denial of service.
    Drives the real ``_CallbackHandler``/``_wait_for_callback`` machinery
    with real HTTP requests, not mocks.
    """
    import threading
    import urllib.error
    import urllib.request

    httpd, redirect_uri = oidc._start_callback_server()
    try:
        result = {}

        def wait():
            result["query"] = oidc._wait_for_callback(httpd, timeout=5)

        waiter = threading.Thread(target=wait)
        waiter.start()

        # A bare request from an unrelated local process: no code, no error.
        with pytest.raises(urllib.error.HTTPError) as excinfo:
            urllib.request.urlopen(redirect_uri, timeout=5)
        assert excinfo.value.code == 400

        # The real browser redirect arrives shortly after.
        real_response = urllib.request.urlopen(
            f"{redirect_uri}?code=real-code", timeout=5
        )
        assert real_response.status == 200

        waiter.join(timeout=5)
        assert not waiter.is_alive()
        assert result["query"] == {"code": "real-code"}
    finally:
        httpd.server_close()


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

    def fake_post(url, data, timeout, allow_redirects, verify):
        assert url == METADATA["token_endpoint"]
        assert data["grant_type"] == "authorization_code"
        assert data["code"] == "auth-code"
        assert data["redirect_uri"] == redirect_uri
        assert data["code_verifier"]
        assert verify is True
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


def test_login_accepts_access_token_without_refresh_token(tmp_path, monkeypatch):
    """Test issuers may return an access token without offline credentials."""
    config_path = tmp_path / "reana-client.json"
    monkeypatch.setenv("REANA_CLIENT_CONFIG", str(config_path))
    monkeypatch.setenv("REANA_SERVER_URL", "https://reana.example.org")

    entry = oidc._store_token_response(
        "https://reana.example.org",
        METADATA,
        {"access_token": "access-only"},
    )

    assert entry["refresh_token"] is None
    assert oidc.get_access_token() == "access-only"


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

    def fake_post(url, data, timeout, allow_redirects, verify):
        assert verify is True
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
                    "expires_in": 600,
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


def test_device_flow_stops_at_local_expiry(monkeypatch):
    """A provider cannot keep device polling alive past ``expires_in``."""
    monkeypatch.setattr(oidc, "discover", lambda server_url: dict(METADATA))
    token_endpoint_calls = []

    def fake_post(url, data, timeout, allow_redirects, verify):
        if url == METADATA["device_authorization_endpoint"]:
            return MockResponse(
                {
                    "device_code": "device-code",
                    "verification_uri": "https://issuer.example.org/device",
                    "user_code": "1234",
                    "interval": 5,
                    "expires_in": 5,
                }
            )
        token_endpoint_calls.append(data)
        return MockResponse(
            {"error": "authorization_pending"}, ok=False, status_code=400
        )

    times = iter([0, 0, 5])
    monkeypatch.setattr(oidc.requests, "post", fake_post)

    with pytest.raises(oidc.AuthenticationError, match="Device login expired"):
        oidc.login_with_device_flow(
            "https://reana.example.org",
            lambda response: None,
            sleep=lambda interval: None,
            monotonic=lambda: next(times),
        )

    assert token_endpoint_calls == []


def test_device_flow_accepts_success_returned_after_local_expiry(monkeypatch):
    """A successful token response is accepted even if the poll crossed the deadline."""
    monkeypatch.setattr(oidc, "discover", lambda server_url: dict(METADATA))

    def fake_post(url, data, timeout, allow_redirects, verify):
        if url == METADATA["device_authorization_endpoint"]:
            return MockResponse(
                {
                    "device_code": "device-code",
                    "verification_uri": "https://issuer.example.org/device",
                    "user_code": "1234",
                    "interval": 0,
                    "expires_in": 5,
                }
            )
        assert timeout == 1
        return MockResponse(
            {"access_token": "late-access", "refresh_token": "late-refresh"}
        )

    times = iter([0, 0, 4, 6])
    monkeypatch.setattr(oidc.requests, "post", fake_post)

    monkeypatch.setattr(
        oidc, "_store_token_response", lambda url, metadata, payload: payload
    )
    result = oidc.login_with_device_flow(
        "https://reana.example.org",
        lambda response: None,
        sleep=lambda interval: None,
        monotonic=lambda: next(times),
    )
    assert result["access_token"] == "late-access"


def test_get_access_token_rechecks_credentials_after_lock(tmp_path, monkeypatch):
    """A process waiting on refresh reuses the winner's access token."""
    config_path = tmp_path / "reana-client.json"
    server_url = "https://reana.example.org"
    monkeypatch.setenv("REANA_CLIENT_CONFIG", str(config_path))
    monkeypatch.setenv("REANA_SERVER_URL", server_url)
    upsert_server_entry(
        server_url,
        {
            "access_token": "old-access",
            "access_token_expires_at": oidc.format_timestamp(
                oidc.utcnow() + timedelta(seconds=10)
            ),
            "refresh_token": "old-refresh",
        },
    )

    class RefreshWinnerLock:
        """Simulate another process finishing while this one waits."""

        def __enter__(self):
            upsert_server_entry(
                server_url,
                {
                    "access_token": "winner-access",
                    "access_token_expires_at": oidc.format_timestamp(
                        oidc.utcnow() + timedelta(hours=1)
                    ),
                    "refresh_token": "winner-refresh",
                },
            )

        def __exit__(self, exc_type, exc_value, traceback):
            return False

    monkeypatch.setattr(oidc, "credential_store_lock", RefreshWinnerLock)
    monkeypatch.setattr(
        oidc.requests,
        "post",
        lambda *args, **kwargs: pytest.fail("refresh endpoint must not be called"),
    )

    assert oidc.get_access_token() == "winner-access"


def test_pkce_pair_uses_s256_challenge():
    """Test PKCE verifier/challenge generation."""
    pkce = oidc.generate_pkce_pair()

    assert len(pkce["code_verifier"]) >= 43
    assert pkce["code_challenge"]
    assert "=" not in pkce["code_challenge"]
    assert pkce["code_challenge_method"] == "S256"


def test_acquire_file_lock_times_out_instead_of_blocking_forever(tmp_path, caplog):
    """PR777-09: a wedged lock holder must produce a bounded, loud failure.

    Regression test for the general credential-store lock primitive
    (distinct from the refresh-specific lock covered by PR777-20 above):
    previously POSIX blocked forever on ``fcntl.flock(LOCK_EX)`` with no
    timeout and no message, and Windows silently swallowed the ``OSError``
    from a contended ``msvcrt.locking`` and proceeded as if it had acquired
    the lock. ``_acquire_file_lock`` now polls the same non-blocking
    primitive on both platforms and must raise within a short, bounded
    ``timeout`` instead of hanging, logging a "waiting" message first.
    """
    lock_path = tmp_path / "test.lock"
    holder = open(lock_path, "a+", encoding="utf-8")
    storage._acquire_file_lock(holder)  # uncontended: succeeds immediately.

    contender = open(lock_path, "a+", encoding="utf-8")
    try:
        start = time.monotonic()
        with caplog.at_level(logging.WARNING, logger="reana_client.auth.storage"):
            with pytest.raises(TimeoutError, match="credential lock"):
                storage._acquire_file_lock(contender, timeout=0.3)
        elapsed = time.monotonic() - start

        # Bounded: never blocks anywhere near forever.
        assert elapsed < 5
        assert any(
            "Waiting for credential lock" in record.message for record in caplog.records
        )
    finally:
        storage._release_file_lock(holder)
        holder.close()
        contender.close()


def test_acquire_file_lock_succeeds_after_a_bounded_wait_once_released(tmp_path):
    """A contended lock that clears before the timeout is acquired, not lost.

    Complements the timeout test above: the bounded retry loop must not
    just fail fast on first contention -- it must keep polling and succeed
    once the holder releases, as long as that happens within ``timeout``.
    """
    import threading

    lock_path = tmp_path / "test.lock"
    holder = open(lock_path, "a+", encoding="utf-8")
    storage._acquire_file_lock(holder)

    def release_after_delay():
        time.sleep(0.2)
        storage._release_file_lock(holder)
        holder.close()

    releaser = threading.Thread(target=release_after_delay)
    releaser.start()

    contender = open(lock_path, "a+", encoding="utf-8")
    try:
        start = time.monotonic()
        storage._acquire_file_lock(contender, timeout=5)
        elapsed = time.monotonic() - start

        # Actually waited for the release rather than failing immediately,
        # but nowhere near the full timeout.
        assert 0.15 < elapsed < 4
    finally:
        storage._release_file_lock(contender)
        contender.close()
        releaser.join(timeout=5)
