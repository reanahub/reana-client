# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2017, 2018 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""REANA client ping tests."""

from click.testing import CliRunner

from reana_client.cli import Config, cli


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


def test_ping_ok(mock_base_api_client):
    """Test ping server is set and reachable."""
    env = {'REANA_SERVER_URL': 'localhost'}
    status_code = 200
    response = {"status": 200, "message": "OK"}
    mocked_api_client = mock_base_api_client(status_code,
                                             response,
                                             'reana-server')
    config = Config(mocked_api_client)
    runner = CliRunner(env=env)
    result = runner.invoke(cli, ['ping'], obj=config)
    message = 'Server is running'
    assert message in result.output
