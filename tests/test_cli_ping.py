# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2017, 2018, 2020, 2021, 2023, 2026 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""REANA client ping tests."""

import logging
import socket
import ssl

import pytest
import requests
from bravado.exception import HTTPError
from bravado.http_future import HttpFuture
from bravado.requests_client import RequestsClient
from click.testing import CliRunner
from mock import Mock, patch
from reana_commons.testing import make_mock_api_client

from reana_client.cli import cli
from reana_client.auth.storage import CredentialStoreError
from reana_client.config import ERROR_MESSAGES


def test_ping_token_not_set(monkeypatch, client_config):
    """Test ping when token is not set."""
    env = client_config("localhost")
    runner = CliRunner(env=env)
    monkeypatch.setattr(
        "reana_client.cli.utils.get_access_token",
        lambda: (_ for _ in ()).throw(
            Exception(ERROR_MESSAGES["missing_access_token"])
        ),
    )
    result = runner.invoke(cli, ["ping"])
    message = ERROR_MESSAGES["missing_access_token"]
    assert message in result.output


def test_ping_server_not_set(tmp_path, monkeypatch):
    """Test ping when server is not set."""
    monkeypatch.setenv(
        "REANA_CLIENT_CONFIG", str(tmp_path / "missing-client-config.json")
    )
    monkeypatch.delenv("REANA_SERVER_URL", raising=False)
    reana_token = "000000"
    runner = CliRunner()
    result = runner.invoke(cli, ["ping", "-t", reana_token])
    message = "No REANA server is configured."
    assert message in result.output


@pytest.mark.parametrize(
    "command, operation",
    [("ping", "get_you"), ("list", "get_workflows"), ("info", "info")],
)
@pytest.mark.parametrize("failure", ["certificate", "dns", "refused", "timeout"])
def test_commands_report_transport_failures(
    command, operation, failure, client_config, monkeypatch, caplog
):
    """Bravado transport failures reach the CLI with safe, actionable diagnostics."""
    server = "https://reana.example.org"
    env = client_config(server)
    certificate = ssl.SSLCertVerificationError("secret-request-data")
    certificate.verify_code = 18
    failures = {
        "certificate": (requests.exceptions.SSLError(certificate), "not trusted"),
        "dns": (
            requests.exceptions.ConnectionError(socket.gaierror("secret-request-data")),
            "hostname could not be resolved",
        ),
        "refused": (
            requests.exceptions.ConnectionError(
                ConnectionRefusedError("secret-request-data")
            ),
            "connection was refused",
        ),
        "timeout": (
            requests.exceptions.ReadTimeout("secret-request-data"),
            "connection timed out",
        ),
    }
    error, expected = failures[failure]
    transport = RequestsClient()
    monkeypatch.setattr(transport.session, "send", Mock(side_effect=error))
    future = transport.request({"method": "GET", "url": server + "/api?secret=query"})
    assert isinstance(future, HttpFuture)
    runner = CliRunner(env=env)
    with patch("reana_client.api.client.current_rs_api_client") as api_client:
        getattr(api_client.api, operation).return_value = future
        with caplog.at_level("DEBUG"):
            result = runner.invoke(cli, [command, "-t", "synthetic.jwt.token"])
    assert result.exit_code == 1
    assert f"Could not connect to {server} (from saved login)" in result.output
    assert expected in result.output
    assert ("--no-tls-verify" in result.output) == (failure == "certificate")
    for unwanted in (
        "INVALID SERVER",
        "Authenticated as:",
        "REANA server version:",
        "secret-request-data",
        "secret=query",
        "synthetic.jwt.token",
    ):
        assert unwanted not in result.output + caplog.text


@pytest.mark.parametrize(
    "status, message", [(403, "INVALID ACCESS TOKEN"), (404, "INVALID SERVER")]
)
def test_ping_preserves_http_status_errors(status, message, client_config):
    """Transport classification does not intercept Bravado HTTP responses."""
    client_config("https://reana.example.org")
    with patch("reana_client.api.client.current_rs_api_client") as api_client:
        api_client.api.get_you.return_value.result.side_effect = HTTPError(
            response=Mock(status_code=status)
        )
        result = CliRunner().invoke(cli, ["ping", "-t", "synthetic.jwt.token"])
    assert result.exit_code == 1
    assert f"ERROR: {message}" in result.output


def test_ping_ok(client_config):
    """Test ping server is set and reachable."""
    reana_token = "000000"
    env = client_config("localhost")
    status_code = 200
    response = {
        "email": "johndoe@example.org",
        "reana_token": "000000",
        "full_name": "John Doe",
        "username": "jdoe",
    }
    mock_http_response, mock_response = Mock(), Mock()
    mock_http_response.status_code = status_code
    mock_response = response
    runner = CliRunner(env=env)
    with runner.isolation():
        with patch(
            "reana_client.api.client.current_rs_api_client",
            make_mock_api_client("reana-server")(mock_response, mock_http_response),
        ):
            result = runner.invoke(cli, ["ping", "-t", reana_token])
            message = "Authenticated as: John Doe <johndoe@example.org>"
            assert message in result.output
            message = "Connected"
            assert message in result.output


def test_login_redirect_error_omits_location(caplog, monkeypatch):
    """A refused authentication redirect never reveals its destination."""
    caplog.set_level(logging.DEBUG)
    monkeypatch.setattr(
        "reana_client.auth.oidc.requests.get",
        Mock(
            return_value=Mock(
                is_redirect=True,
                status_code=302,
                headers={"location": "https://evil.example/cb?token=secret"},
            )
        ),
    )
    result = CliRunner().invoke(
        cli, ["--loglevel", "DEBUG", "login", "--server", "https://reana.example.org"]
    )
    assert result.exit_code == 1
    assert "failed with HTTP 302" in result.output
    assert "Refusing to follow a redirect" in result.output
    for leaked in ("evil.example", "secret"):
        assert leaked not in result.output
        assert leaked not in caplog.text


def test_login_reports_credential_lock_timeout(monkeypatch):
    """A wedged credential writer becomes a concise CLI error, not a traceback."""
    monkeypatch.setattr(
        "reana_client.cli.ping._browser_login",
        Mock(side_effect=CredentialStoreError("credential lock timed out")),
    )
    result = CliRunner().invoke(
        cli, ["login", "--server-url", "https://reana.example.org"]
    )
    assert result.exit_code == 1
    assert "credential lock timed out" in result.output
    assert "Traceback" not in result.output


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        ([], None),
        (["--callback-port", "8899"], 8899),
        (["--callback-port", "0"], 0),
        (["--callback-port", "65535"], 65535),
    ],
)
def test_login_passes_callback_port_to_browser_login(monkeypatch, arguments, expected):
    """The option reaches the port selection, and an omitted option is ``None``."""
    monkeypatch.delenv("REANA_CLIENT_LOGIN_LOOPBACK_PORT", raising=False)
    login_with_loopback = Mock()
    monkeypatch.setattr(
        "reana_client.cli.ping.login_with_loopback", login_with_loopback
    )
    result = CliRunner().invoke(
        cli, ["login", "--server-url", "https://reana.example.org", *arguments]
    )
    assert result.exit_code == 0, result.output
    assert login_with_loopback.call_args.kwargs["callback_port"] == expected
    assert login_with_loopback.call_args.args[0] == "https://reana.example.org"


@pytest.mark.parametrize("value", ["-1", "65536", "abc", "88.5"])
def test_login_rejects_invalid_callback_port(monkeypatch, value):
    """Values outside 0-65535 are a usage error."""
    login_with_loopback = Mock()
    monkeypatch.setattr(
        "reana_client.cli.ping.login_with_loopback", login_with_loopback
    )
    result = CliRunner().invoke(
        cli,
        [
            "login",
            "--server-url",
            "https://reana.example.org",
            "--callback-port",
            value,
        ],
    )
    assert result.exit_code == 2
    assert "--callback-port" in result.output
    login_with_loopback.assert_not_called()


@pytest.mark.parametrize("port", ["0", "8899"])
def test_login_rejects_headless_with_callback_port(monkeypatch, port):
    """Device login uses no callback, so an explicit port is refused early."""
    device_login = Mock()
    monkeypatch.setattr("reana_client.cli.ping._device_login", device_login)
    monkeypatch.setattr(
        "reana_client.cli.ping.connection_scope",
        Mock(side_effect=AssertionError("the login was started")),
    )
    result = CliRunner().invoke(
        cli,
        [
            "login",
            "--server-url",
            "https://reana.example.org",
            "--headless",
            "--callback-port",
            port,
        ],
    )
    assert result.exit_code == 1
    assert "--headless and --callback-port cannot be used together" in result.output
    device_login.assert_not_called()


@pytest.mark.parametrize("arguments", [[], ["--callback-port", "8899"]])
def test_browser_login_stops_on_retired_port_variable(monkeypatch, arguments):
    """A stale export is reported, also together with ``--callback-port``."""
    login_with_loopback = Mock()
    monkeypatch.setattr(
        "reana_client.cli.ping.login_with_loopback", login_with_loopback
    )
    result = CliRunner(env={"REANA_CLIENT_LOGIN_LOOPBACK_PORT": "8899"}).invoke(
        cli, ["login", "--server-url", "https://reana.example.org", *arguments]
    )
    assert result.exit_code == 1
    assert "REANA_CLIENT_LOGIN_LOOPBACK_PORT is no longer a client input" in (
        result.output
    )
    assert "reana-client login --callback-port PORT" in result.output
    login_with_loopback.assert_not_called()


@pytest.mark.parametrize("value", ["", "   "])
def test_blank_retired_port_variable_does_not_stop_browser_login(monkeypatch, value):
    """Empty and whitespace-only values do not trigger the guidance."""
    login_with_loopback = Mock()
    monkeypatch.setattr(
        "reana_client.cli.ping.login_with_loopback", login_with_loopback
    )
    result = CliRunner(env={"REANA_CLIENT_LOGIN_LOOPBACK_PORT": value}).invoke(
        cli, ["login", "--server-url", "https://reana.example.org"]
    )
    assert result.exit_code == 0, result.output
    login_with_loopback.assert_called_once()


def test_retired_port_variable_does_not_affect_other_commands(monkeypatch):
    """Device login and unrelated commands ignore a stale export."""
    device_login = Mock()
    monkeypatch.setattr("reana_client.cli.ping._device_login", device_login)
    runner = CliRunner(env={"REANA_CLIENT_LOGIN_LOOPBACK_PORT": "8899"})
    result = runner.invoke(
        cli, ["login", "--server-url", "https://reana.example.org", "--headless"]
    )
    assert result.exit_code == 0, result.output
    device_login.assert_called_once()

    result = runner.invoke(cli, ["version"])
    assert result.exit_code == 0, result.output
    assert "REANA_CLIENT_LOGIN_LOOPBACK_PORT" not in result.output


def test_logout_reports_credential_lock_timeout(monkeypatch):
    """Logout handles the same storage boundary consistently."""
    monkeypatch.setattr(
        "reana_client.cli.ping.get_active_server",
        Mock(return_value="https://reana.example.org"),
    )
    monkeypatch.setattr(
        "reana_client.cli.ping.oidc_logout",
        Mock(side_effect=CredentialStoreError("credential lock timed out")),
    )
    result = CliRunner().invoke(cli, ["logout"])
    assert result.exit_code == 1
    assert "credential lock timed out" in result.output
