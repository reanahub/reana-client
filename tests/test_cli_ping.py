# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2017, 2018 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""REANA client ping tests."""

from click.testing import CliRunner
from mock import Mock, patch
from pytest_reana.test_utils import make_mock_api_client

from reana_client.cli import cli
from reana_client.config import ERROR_MESSAGES


def test_ping_token_not_set():
    """Test ping when token is not set."""
    env = {"REANA_SERVER_URL": "localhost"}
    runner = CliRunner(env=env)
    result = runner.invoke(cli, ["ping"])
    message = ERROR_MESSAGES["missing_access_token"]
    assert message in result.output


def test_ping_server_not_set():
    """Test ping when server is not set."""
    reana_token = "000000"
    runner = CliRunner()
    result = runner.invoke(cli, ["ping", "-t", reana_token])
    message = "REANA client is not connected to any REANA cluster."
    assert message in result.output


def test_ping_server_not_reachable():
    """Test ping when server is set, but unreachable."""
    reana_token = "000000"
    env = {"REANA_SERVER_URL": "localhost"}
    runner = CliRunner(env=env)
    result = runner.invoke(cli, ["ping", "-t", reana_token])
    message = "ERROR: INVALID SERVER"
    assert message in result.output


def test_ping_ok():
    """Test ping server is set and reachable."""
    reana_token = "000000"
    env = {"REANA_SERVER_URL": "localhost"}
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
