# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2017, 2018, 2020, 2021, 2023, 2026 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""REANA client ping tests."""

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


TRANSPORT_FAILURE_COMMANDS = [
    ["ping"],
    ["info"],
    ["list"],
    ["create", "-f", "REANA_YAML"],
    ["validate", "-f", "REANA_YAML"],
    ["run", "-f", "REANA_YAML"],
    ["start", "-w", "wf"],
    ["start", "-w", "wf", "-p", "x=1"],
    ["restart", "-w", "wf"],
    ["restart", "-w", "wf", "-p", "x=1"],
    ["status", "-w", "wf"],
    ["logs", "-w", "wf"],
    ["logs", "-w", "wf", "--follow"],
    ["stop", "-w", "wf", "--force"],
    ["delete", "-w", "wf"],
    ["delete", "-w", "wf", "--include-all-runs"],
    ["diff", "wf.1", "wf.2"],
    ["open", "-w", "wf"],
    ["close", "-w", "wf"],
    ["share-add", "-w", "wf", "-u", "jane@example.org"],
    ["share-remove", "-w", "wf", "-u", "jane@example.org"],
    ["share-status", "-w", "wf"],
    ["ls", "-w", "wf"],
    ["du", "-w", "wf"],
    ["download", "-w", "wf"],
    ["download", "-w", "wf", "results.txt"],
    ["upload", "-w", "wf"],
    ["upload", "-w", "wf", "REANA_YAML"],
    ["rm", "-w", "wf", "results.txt"],
    ["mv", "-w", "wf", "a.txt", "b.txt"],
    ["prune", "-w", "wf"],
    ["secrets-add", "--env", "NAME=value"],
    ["secrets-delete", "NAME"],
    ["secrets-list"],
    ["quota-show", "--resources"],
    ["retention-rules-list", "-w", "wf"],
    ["test", "-w", "wf"],
]


@pytest.mark.parametrize(
    "arguments", TRANSPORT_FAILURE_COMMANDS, ids=lambda arguments: " ".join(arguments)
)
@pytest.mark.parametrize("failure", ["certificate", "dns", "refused", "timeout"])
def test_commands_report_transport_failures(
    arguments, failure, client_config, monkeypatch, caplog, tmp_path
):
    """Transport failures reach the CLI with safe, actionable diagnostics."""
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

    class FailingOperations:
        """Generated API whose every operation fails in the transport."""

        def __getattr__(self, name):
            operation = Mock(return_value=future)
            operation.operation.path_name = "/api/" + name
            return operation

    reana_yaml = tmp_path / "reana.yaml"
    reana_yaml.write_text(
        "workflow:\n"
        "  type: serial\n"
        "  specification:\n"
        "    steps:\n"
        "      - environment: docker.io/library/python:3.12\n"
        "        commands:\n"
        "          - echo secret-request-data\n"
    )
    arguments = [
        str(reana_yaml) if item == "REANA_YAML" else item for item in arguments
    ]
    arguments.insert(1, "-t")
    arguments.insert(2, "synthetic.jwt.token")
    runner = CliRunner(env=env)
    # Workspace uploads bypass the generated client.
    monkeypatch.setattr(
        "reana_client.api.client.requests.post", Mock(side_effect=error)
    )
    with patch("reana_client.api.client.current_rs_api_client") as api_client:
        api_client.api = FailingOperations()
        with caplog.at_level("DEBUG"):
            result = runner.invoke(cli, arguments)
    assert result.exit_code == 1
    assert f"Could not connect to {server} (from saved login)" in result.output
    assert expected in result.output
    assert ("--no-tls-verify" in result.output) == (failure == "certificate")
    for unwanted in (
        "INVALID SERVER",
        "Authenticated as:",
        "REANA server version:",
        "Something went wrong",
        "Traceback",
        "secret-request-data",
        "secret=query",
        "synthetic.jwt.token",
    ):
        assert unwanted not in result.output + caplog.text


@pytest.mark.parametrize(
    "arguments",
    [["status", "-w", "wf"], ["secrets-add", "--env", "NAME=secret-request-data"]],
)
def test_debug_logs_do_not_expose_credentials(
    arguments, client_config, monkeypatch, caplog
):
    """The generated client's own DEBUG output stays free of tokens and bodies."""
    env = client_config("https://reana.example.org")
    monkeypatch.setattr(
        "requests.Session.send",
        Mock(side_effect=requests.exceptions.ConnectionError(ConnectionRefusedError())),
    )
    with caplog.at_level("DEBUG"):
        result = CliRunner(env=env).invoke(
            cli, ["-l", "DEBUG"] + arguments + ["-t", "synthetic.jwt.token"]
        )
    assert result.exit_code == 1
    assert "connection was refused" in result.output
    for unwanted in ("synthetic.jwt.token", "secret-request-data"):
        assert unwanted not in result.output + caplog.text


def test_cwl_runner_reports_transport_failures(client_config, monkeypatch, tmp_path):
    """The CWL runner entrypoint explains a failed connection and exits non-zero."""
    from reana_client.cli.cwl_runner import cwl_runner

    env = client_config("https://reana.example.org")
    monkeypatch.setattr(
        "reana_client.cli.cwl_runner._create_cwl_workflow",
        Mock(side_effect=requests.exceptions.ConnectionError(ConnectionRefusedError())),
    )
    result = CliRunner(env=env).invoke(
        cwl_runner, ["-t", "synthetic.jwt.token", str(tmp_path / "workflow.cwl")]
    )
    assert result.exit_code == 1
    assert "connection was refused" in result.output
    assert "Traceback" not in result.output


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
