# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2026 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
"""Saved server commands and their credential-store boundaries."""

import ssl
import threading
from pathlib import Path
from unittest.mock import Mock

import pytest
import requests
from click.testing import CliRunner

from reana_client.auth import oidc, servers, storage
from reana_client.cli import cli


@pytest.fixture()
def offline(monkeypatch):
    """Fail any unexpected HTTP request."""
    request = Mock(side_effect=AssertionError("Unexpected network request"))
    monkeypatch.setattr("requests.sessions.Session.request", request)
    return request


def invoke(*args):
    """Execute one invocation and require success."""
    result = CliRunner().invoke(cli, list(args))
    assert result.exit_code == 0, (result.output, result.exception)
    return result.output


def test_offline_server_lifecycle(offline):
    """Add/list/select/remove never authenticate or implicitly select a server."""
    assert "No saved REANA servers" in invoke("server-list")
    invoke("server-add", "B.EXAMPLE/", "--no-tls-verify")
    invoke("server-add", "a.example")
    config = storage.load_config()
    assert config["active_server"] is None
    assert config["servers"]["https://b.example"] == {"tls": {"verify": False}}
    storage.upsert_server_entry(
        "https://a.example",
        {"access_token": "secret", "future": "hidden"},
        make_active=False,
    )
    before = storage.load_config()["servers"]
    invoke("server-use", "B.EXAMPLE/")
    output = invoke("server-list")
    assert "* https://b.example  TLS verification: disabled" in output
    assert "https://a.example  TLS verification: enabled" in output
    assert output.index("a.example") < output.index("b.example")
    assert "secret" not in output and "hidden" not in output
    invoke("server-use", "a.example")
    assert storage.load_config()["servers"] == before
    invoke("server-remove", "b.example")
    assert storage.load_config()["active_server"] == "https://a.example"
    invoke("server-remove", "a.example", "--local-only")
    assert storage.load_config() == storage.empty_config()
    offline.assert_not_called()


@pytest.mark.parametrize("command", ["server-use", "server-remove"])
def test_unknown_server_preserves_selection(command, offline):
    """Unknown URLs cannot replace the current selection or create records."""
    invoke("server-add", "known.example")
    invoke("server-use", "known.example")
    before = storage.load_config()
    result = CliRunner().invoke(cli, [command, "unknown.example"])
    assert result.exit_code == 1
    assert "No saved REANA server" in result.output
    assert storage.load_config() == before


def test_add_rejects_duplicate_and_conflicting_tls(monkeypatch, offline):
    """Adding never overwrites credentials, and rejects ineffective TLS choices."""
    invoke("server-add", "a.example")
    before = storage.load_config()
    result = CliRunner().invoke(cli, ["server-add", "a.example", "--no-tls-verify"])
    assert result.exit_code == 1 and "already saved" in result.output
    result = CliRunner().invoke(
        cli, ["server-add", "b.example", "--tls-verify", "--no-tls-verify"]
    )
    assert result.exit_code == 1
    monkeypatch.setenv("REANA_SERVER_CA_CERTS", "bundle.pem")
    result = CliRunner().invoke(cli, ["server-add", "b.example", "--no-tls-verify"])
    assert result.exit_code == 1 and "conflicts" in result.output
    assert storage.load_config() == before


def test_list_effective_ca_policy(monkeypatch, offline):
    """A bundle overrides saved bypass in the displayed effective policy."""
    invoke("server-add", "a.example", "--no-tls-verify")
    monkeypatch.setenv("REANA_SERVER_CA_CERTS", "bundle.pem")
    assert "TLS verification: enabled" in invoke("server-list")
    assert storage.get_server_entry("a.example")["tls"]["verify"] is False


def seed_revocation():
    """Save credentials for exercising revocation without a login flow."""
    storage.upsert_server_entry(
        "https://a.example",
        {
            "refresh_token": "refresh-secret",
            "client_id": "reana-client",
            "revocation_endpoint": "https://a.example/revoke",
            "tls": {"verify": False},
        },
    )


@pytest.mark.parametrize("status", [200, 307, 503])
@pytest.mark.parametrize("external", [False, True])
def test_remove_revokes_before_forgetting(monkeypatch, status, external):
    """Failed revocation preserves the full entry; success removes selection."""
    seed_revocation()
    endpoint = "https://iam.example/revoke" if external else "https://a.example/revoke"
    storage.upsert_server_entry("a.example", {"revocation_endpoint": endpoint})
    before = storage.load_config()

    def post(url, **kwargs):
        assert storage.load_config() == before
        assert url == endpoint
        assert kwargs["data"]["token"] == "refresh-secret"
        assert kwargs["verify"] is external
        return Mock(
            ok=status < 400,
            status_code=status,
            is_redirect=status == 307,
            headers={"location": "https://iam.example/revoke?secret=redirect"},
        )

    monkeypatch.setattr(oidc.requests, "post", post)
    result = CliRunner().invoke(cli, ["server-remove", "a.example"])
    if status != 200:
        assert result.exit_code == 1 and "--local-only" in result.output
        assert f"HTTP {status}" in result.output
        assert "https://a.example (from server-remove argument)" in result.output
        assert "secret=redirect" not in result.output
        if status == 307:
            assert "Refusing to follow a redirect" in result.output
        assert "refresh-secret" not in result.output
        assert storage.load_config() == before
    else:
        assert result.exit_code == 0, result.output
        assert storage.load_config() == storage.empty_config()


@pytest.mark.parametrize(
    "failure, external",
    [("certificate", False), ("certificate", True), ("refused", False)],
)
def test_remove_explains_transport_failure_without_changing_store(
    monkeypatch, caplog, failure, external
):
    """Classify revocation before discarding its cause, using the argument's origin."""
    seed_revocation()
    target = "https://a.example"
    endpoint = (
        "https://iam.example" if external else target
    ) + "/revoke?secret=endpoint"
    storage.upsert_server_entry(
        target, {"revocation_endpoint": endpoint, "tls": {"verify": not external}}
    )
    storage.upsert_server_entry("https://selected.example", {})
    path = Path(storage.get_config_path())
    before = path.read_bytes()
    certificate = ssl.SSLCertVerificationError("refresh-secret")
    certificate.verify_code = 18
    error = (
        requests.exceptions.SSLError(certificate)
        if failure == "certificate"
        else requests.exceptions.ConnectionError(
            ConnectionRefusedError("refresh-secret")
        )
    )
    post = Mock(side_effect=error)
    monkeypatch.setattr(oidc.requests, "post", post)
    with caplog.at_level("DEBUG"):
        result = CliRunner().invoke(cli, ["server-remove", target])
    assert result.exit_code == 1
    assert f"{target} (from server-remove argument)" in result.output
    assert (
        "not trusted" in result.output
        if failure == "certificate"
        else "connection was refused" in result.output
    )
    assert ("--no-tls-verify" in result.output) == (
        failure == "certificate" and not external
    )
    if external:
        assert "does not apply to this identity provider" in result.output
    assert "Resolve the reported problem before retrying" in result.output
    assert "--local-only" in result.output
    for value in ("selected.example", "secret=endpoint", "refresh-secret"):
        assert value not in result.output + caplog.text
    assert path.read_bytes() == before
    assert post.call_args.kwargs["verify"] is True


def test_remove_missing_metadata_and_local_escape(offline):
    """No revocation endpoint requires deliberate local-only removal."""
    storage.upsert_server_entry("a.example", {"refresh_token": "secret"})
    before = storage.load_config()
    result = CliRunner().invoke(cli, ["server-remove", "a.example"])
    assert result.exit_code == 1 and "metadata is missing" in result.output
    assert storage.load_config() == before
    assert "not revoked" in invoke("server-remove", "a.example", "--local-only")
    assert storage.load_config() == storage.empty_config()


def test_remove_waits_for_rotated_token(monkeypatch):
    """Removal revokes the new token after a concurrent refresh finishes."""
    seed_revocation()
    lock = storage.try_acquire_refresh_lock("a.example")
    waiting = threading.Event()
    errors = []
    real_acquire = storage._acquire_file_lock

    def acquire(handle, *args, **kwargs):
        waiting.set()
        return real_acquire(handle, *args, **kwargs)

    monkeypatch.setattr(storage, "_acquire_file_lock", acquire)
    revoked = []
    monkeypatch.setattr(
        servers,
        "revoke_credentials",
        lambda server, entry, **kwargs: revoked.append(entry["refresh_token"]),
    )

    def remove():
        try:
            servers.remove_server("a.example")
        except Exception as error:
            errors.append(error)

    worker = threading.Thread(target=remove)
    worker.start()
    try:
        assert waiting.wait(2)
        storage.upsert_server_entry(
            "a.example", {"refresh_token": "rotated"}, make_active=False
        )
    finally:
        storage.release_refresh_lock(lock)
        worker.join(timeout=5)
    assert not worker.is_alive() and not errors
    assert revoked == ["rotated"]
    assert storage.load_config() == storage.empty_config()


def test_refresh_does_not_reuse_deleted_record(monkeypatch, offline):
    """A stale caller cannot refresh a record removed while it was waiting."""
    seed_revocation()
    stale = storage.get_server_entry("a.example")
    servers.remove_server("a.example", local_only=True)
    with pytest.raises(oidc.AuthenticationError, match="No usable credentials"):
        oidc.refresh_credentials("a.example", stale)
    assert storage.load_config() == storage.empty_config()


def test_selection_survives_background_refresh(offline):
    """A background credential write retains a user's newer selection."""
    storage.upsert_server_entry("a.example", {"refresh_token": "old"})
    invoke("server-add", "b.example")
    invoke("server-use", "b.example")
    storage.upsert_server_entry(
        "a.example", {"refresh_token": "new"}, make_active=False
    )
    assert storage.load_config()["active_server"] == "https://b.example"


def test_stale_exports_do_not_block_server_commands(monkeypatch, offline):
    """Retired exports neither block local management nor influence settings."""
    monkeypatch.setenv("REANA_SERVER_URL", "https://wrong.example")
    monkeypatch.setenv("REANA_SERVER_TLS_VERIFY", "0")
    invoke("server-add", "a.example")
    assert storage.get_server_entry("a.example") == {}
    invoke("server-use", "a.example")
    assert "* https://a.example  TLS verification: enabled" in invoke("server-list")
    result = CliRunner().invoke(cli, ["ping"])
    assert result.exit_code == 1 and "no longer client inputs" in result.output
    invoke("server-remove", "a.example")
    assert storage.load_config() == storage.empty_config()


def test_remove_revokes_with_stale_exports(monkeypatch):
    """Removal uses saved origin and TLS even while legacy exports remain."""
    seed_revocation()
    monkeypatch.setenv("REANA_SERVER_URL", "https://wrong.example")
    monkeypatch.setenv("REANA_SERVER_TLS_VERIFY", "1")
    post = Mock(return_value=Mock(ok=True, status_code=200, is_redirect=False))
    monkeypatch.setattr(oidc.requests, "post", post)
    invoke("server-remove", "a.example")
    assert post.call_args.args == ("https://a.example/revoke",)
    assert post.call_args.kwargs["verify"] is False


def test_list_reads_one_snapshot_and_reports_invalid_tls(monkeypatch, offline):
    """One broken TLS setting must not hide the remaining saved connections."""
    storage.save_config(
        {
            "active_server": None,
            "servers": {
                "https://a.example": {"tls": {"verify": "bad"}},
                "https://b.example": {"tls": {"verify": False}},
                "https://c.example": {},
            },
        }
    )
    load = Mock(wraps=storage.load_config)
    monkeypatch.setattr(storage, "load_config", load)
    entries = servers.list_servers()
    load.assert_called_once()
    assert [entry["tls_verification"] for entry in entries] == [
        "invalid",
        "disabled",
        "enabled",
    ]


def test_local_removal_warning_requires_refresh_token(offline):
    """Configuration-only removal has no remote credentials to warn about."""
    invoke("server-add", "a.example")
    assert "not revoked" not in invoke("server-remove", "a.example", "--local-only")
    storage.upsert_server_entry("a.example", {"refresh_token": "secret"})
    assert "not revoked" in invoke("server-remove", "a.example", "--local-only")


def test_add_preserves_explicit_tls_choice(offline):
    """Implicit default and explicit verification remain distinguishable."""
    invoke("server-add", "a.example")
    invoke("server-add", "b.example", "--tls-verify")
    assert storage.get_server_entry("a.example") == {}
    assert storage.get_server_entry("b.example") == {"tls": {"verify": True}}
