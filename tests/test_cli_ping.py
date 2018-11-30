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


def test_ping_server_not_set():
    """Test ping when server is not set."""
    runner = CliRunner()
    result = runner.invoke(cli, ['ping'])
    message = 'REANA client is not connected to any REANA cluster.'
    assert message in result.output


def test_ping_server_not_reachable():
    """Test ping when server is set, but unreachable."""
    env = {'REANA_SERVER_URL': 'localhot'}
    runner = CliRunner(env=env)
    result = runner.invoke(cli, ['ping'])
    message = 'Could not connect to the selected'
    assert message in result.output


def test_ping_ok():
    """Test ping server is set and reachable."""
    env = {'REANA_SERVER_URL': 'localhost'}
    status_code = 200
    response = {"status": 200, "message": "OK"}
    mock_http_response, mock_response = Mock(), Mock()
    mock_http_response.status_code = status_code
    mock_response = response
    runner = CliRunner(env=env)
    with runner.isolation():
        with patch(
                "reana_client.api.client.current_rs_api_client",
                make_mock_api_client('reana-server')(mock_response,
                                                     mock_http_response)):

            result = runner.invoke(cli, ['ping'])
            message = 'Server is running'
            assert message in result.output
