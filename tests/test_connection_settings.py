# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2026 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
"""Saved connection policy, login transactions and safe diagnostics."""

import ssl

import pytest
import requests
from click.testing import CliRunner

from reana_client import config
from reana_client.auth import oidc, storage
from reana_client.auth.diagnostics import connection_error
from reana_client.cli import cli
from reana_client.cli import ping as commands

SERVER = "https://reana.example.org"
OTHER = "https://other.example.org"
METADATA = {
    "issuer": SERVER,
    "reana_cli_client_id": "cli",
    "token_endpoint": SERVER + "/token",
}


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    """Use a disposable store independent of the developer's credentials."""
    monkeypatch.setenv("REANA_CLIENT_CONFIG", str(tmp_path / "client.json"))
    for name in (
        "REANA_SERVER_URL",
        "REANA_SERVER_TLS_VERIFY",
        "REANA_SERVER_CA_CERTS",
        "REANA_ACCESS_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize("server_flag", ["--server", "--server-url"])
def test_login_saves_tls_only_on_success(server_flag, monkeypatch):
    """The first request sees the override, which becomes the later default."""

    def login(server):
        assert config.tls_verify(server) is False
        return oidc._store_token_response(
            server, METADATA, {"access_token": "a.b.c", "refresh_token": "r"}
        )

    monkeypatch.setattr(commands, "_browser_login", login)
    result = CliRunner().invoke(cli, ["login", server_flag, SERVER, "--no-tls-verify"])
    assert result.exit_code == 0, result.output
    assert "TLS verification: disabled" in result.output
    assert storage.get_active_server() == SERVER
    assert storage.get_server_entry(SERVER)["tls"]["verify"] is False
    assert config.tls_verify(SERVER) is False
    assert config.tls_verify_for_url(SERVER, OTHER + "/token") is True
    # No flag on re-login inherits the saved setting.
    assert CliRunner().invoke(cli, ["login"]).exit_code == 0


def test_failed_login_preserves_selection_and_tls_with_rotated_token(monkeypatch):
    """Recovery may save a rotated token, never the requested TLS policy or selection."""
    storage.upsert_server_entry(SERVER, {"tls": {"verify": False}})
    storage.upsert_server_entry(OTHER, {"tls": {"verify": True}}, make_active=False)

    def fail(server):
        assert config.tls_verify(server) is False
        oidc._store_token_response(server, METADATA, {"refresh_token": "rotated"})

    monkeypatch.setattr(commands, "_browser_login", fail)
    result = CliRunner().invoke(cli, ["login", "--server", OTHER, "--no-tls-verify"])
    assert result.exit_code == 1
    assert storage.get_active_server() == SERVER
    entry = storage.get_server_entry(OTHER)
    assert entry["refresh_token"] == "rotated"
    assert entry["tls"]["verify"] is True


@pytest.mark.parametrize(
    "args",
    [
        ["--server", SERVER, "--server-url", OTHER],
        ["--server", SERVER, "--tls-verify", "--no-tls-verify"],
    ],
)
def test_conflicting_flags_do_not_start_login(args, monkeypatch):
    """Reject contradictory settings before opening a browser or writing a store."""
    monkeypatch.setattr(
        commands, "_browser_login", lambda _: pytest.fail("unexpected login")
    )
    result = CliRunner().invoke(cli, ["login", *args])
    assert result.exit_code == 1
    assert storage.get_active_server() is None


def test_ca_precedence_and_explicit_conflict(monkeypatch, caplog):
    """A CA override enables verification and suppresses bypass diagnostics."""
    storage.upsert_server_entry(SERVER, {"tls": {"verify": False}})
    monkeypatch.setenv(config.CA_CERTS_ENV, "/trusted/ca.pem")
    with config.connection_scope(SERVER):
        assert config.tls_verify() == "/trusted/ca.pem"
        assert config.tls_status() == "enabled"
    assert not caplog.records
    result = CliRunner().invoke(cli, ["login", "--no-tls-verify"])
    assert result.exit_code == 1
    assert "conflicts with REANA_SERVER_CA_CERTS" in result.output


def test_invocation_keeps_server_when_store_selection_changes():
    """API calls and notebook URLs share the destination selected at CLI startup."""
    storage.upsert_server_entry(SERVER, {"tls": {"verify": False}})
    with config.connection_scope():
        assert storage.get_active_server() == SERVER
        assert config.tls_verify() is False
        storage.upsert_server_entry(OTHER, {})
        assert storage.get_active_server() == SERVER
        assert config.tls_verify() is False
    assert storage.get_active_server() == OTHER


@pytest.mark.parametrize(
    "code, wording",
    [(18, "self-signed"), (20, "not trusted"), (10, "expired"), (62, "hostname")],
)
def test_certificate_diagnostics_are_specific_and_sanitised(code, wording, caplog):
    """Classify structured verification errors without printing secret request data."""
    cause = ssl.SSLCertVerificationError("secret-code-and-token")
    cause.verify_code = code
    error = requests.exceptions.SSLError(cause)
    with caplog.at_level("DEBUG"):
        message = connection_error(SERVER, SERVER + "/token?secret=abc", error)
    assert wording in message
    assert "secret-code-and-token" not in message + caplog.text
    assert "secret=abc" not in message + caplog.text
    assert ("--no-tls-verify" in message) == (code in (18, 20))
    if code in (18, 20):
        assert "--no-tls-verify" not in connection_error(
            SERVER, OTHER + "/token", error
        )


@pytest.mark.parametrize(
    "variables",
    [
        {"REANA_SERVER_URL": "https://old.example.org"},
        {"REANA_SERVER_TLS_VERIFY": "0"},
        {"REANA_SERVER_URL": "https://old.example.org", "REANA_SERVER_TLS_VERIFY": "1"},
    ],
)
def test_retired_exports_fail_cli_and_api_with_migration_guidance(
    variables, monkeypatch
):
    """Stale exports must never silently select a different server or TLS policy."""
    from reana_client.api import client

    storage.upsert_server_entry(SERVER, {})
    for name, value in variables.items():
        monkeypatch.setenv(name, value)
    runner = CliRunner()
    for arguments in (["ping", "-t", "a.b.c"], ["login", "--server", SERVER]):
        result = runner.invoke(cli, arguments)
        assert result.exit_code == 1
        for name in variables:
            assert name in result.output
        assert "Unset them, then run" in result.output
    with pytest.raises(ValueError, match="no longer client inputs"):
        client._get_current_reana_server_api_client()
    for arguments in (["--help"], ["login", "--help"], ["version"]):
        assert runner.invoke(cli, arguments).exit_code == 0


def test_empty_exports_and_missing_server_do_not_reopen_commons_fallback(monkeypatch):
    """Fail before passing an empty URL to the lower-level API client."""
    from reana_client.api import client

    for name in ("REANA_SERVER_URL", "REANA_SERVER_TLS_VERIFY"):
        monkeypatch.setenv(name, "")
    monkeypatch.setattr(
        client,
        "get_current_api_client",
        lambda **_: pytest.fail("commons fallback reached"),
    )
    with pytest.raises(ValueError, match="No REANA server is configured"):
        client._get_current_reana_server_api_client()


def test_notebook_open_keeps_destination_after_concurrent_selection_change(monkeypatch):
    """Session creation, secret lookup and printed link use one server selection."""
    from reana_client.api import client

    storage.upsert_server_entry(SERVER, {"tls": {"verify": False}})

    def open_session(*args, **kwargs):
        assert storage.get_active_server() == SERVER
        storage.upsert_server_entry(OTHER, {})
        return "/sessions/notebook"

    def session_secret(*args, **kwargs):
        assert storage.get_active_server() == SERVER
        assert config.tls_verify() is False
        return {"session_secret": "secret"}

    monkeypatch.setattr(client, "open_interactive_session", open_session)
    monkeypatch.setattr(client, "get_interactive_session_secret", session_secret)
    monkeypatch.setattr(client, "info", lambda *_: {})
    result = CliRunner().invoke(
        cli, ["open", "-t", "a.b.c", "-w", "analysis.1", "jupyter"]
    )
    assert result.exit_code == 0, result.output
    assert SERVER + "/sessions/notebook?token=secret" in result.output
    assert OTHER not in result.output
    assert storage.get_active_server() == OTHER
