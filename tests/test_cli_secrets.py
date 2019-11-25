# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2019 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""REANA client secrets tests."""

import pytest
from bravado.exception import HTTPError
from click.testing import CliRunner
from mock import Mock, patch
from pytest_reana.test_utils import make_mock_api_client

from reana_client.cli import cli


def test_secrets_list_server_not_reachable():
    """Test list secrets when not connected to any cluster."""
    message = 'REANA client is not connected to any REANA cluster.'
    reana_token = '000000'
    runner = CliRunner()
    result = runner.invoke(cli, ['secrets-list', '-t', reana_token])
    assert result.exit_code == 1
    assert message in result.output


def test_secrets_list_server_no_token():
    """Test list secrets when access token is not set."""
    message = 'Please provide your access token'
    env = {'REANA_SERVER_URL': 'localhost'}
    runner = CliRunner(env=env)
    result = runner.invoke(cli, ['secrets-list'])
    assert result.exit_code == 1
    assert message in result.output


def test_secrets_list_ok():
    """Test list secrets successfull."""
    status_code = 200
    response = [
        {
            "name": "password",
            "type": "env"
        }
    ]
    env = {'REANA_SERVER_URL': 'localhost'}
    mock_http_response, mock_response = Mock(), Mock()
    mock_http_response.status_code = status_code
    mock_response = response
    reana_token = '000000'
    runner = CliRunner(env=env)
    with runner.isolation():
        with patch(
            "reana_client.api.client.current_rs_api_client",
                make_mock_api_client('reana-server')(mock_response,
                                                     mock_http_response)):
            result = runner.invoke(
                cli, ['secrets-list', '-t', reana_token])
            assert result.exit_code == 0
            assert "password" in result.output
            assert "env" in result.output


@pytest.mark.parametrize(
    'secret',
    ['USER=reanauser', 'USER=reana=user'])
def test_secrets_add(secret):
    """Test secrets add."""
    status_code = 201
    reana_token = '000000'
    secret_file = 'file.txt'
    response = [secret_file]
    env = {'REANA_SERVER_URL': 'localhost'}
    message = 'were successfully uploaded.'
    mock_http_response = Mock()
    mock_http_response.status_code = status_code
    mock_http_response.raw_bytes = str(response).encode()
    mock_response = response
    runner = CliRunner(env=env)
    with runner.isolation():
        with patch(
                "reana_client.api.client.current_rs_api_client",
                make_mock_api_client('reana-server')(mock_response,
                                                     mock_http_response)):
            with runner.isolated_filesystem():
                with open(secret_file, 'w') as f:
                    f.write('test')
                result = runner.invoke(
                    cli, ['secrets-add',
                          '-t', reana_token,
                          '--file', secret_file,
                          '--env', secret]
                )
                assert result.exit_code == 0
                assert message in result.output


@pytest.mark.parametrize(
    'secret',
    ['wrongformat', 'PASS:123'])
def test_secrets_add_wrong_format(secret):
    """Test adding secrets with wrong format."""
    reana_token = '000000'
    env = {'REANA_SERVER_URL': 'localhost'}
    runner = CliRunner(env=env)
    message = 'For literal strings use "SECRET_NAME=VALUE" format'

    result = runner.invoke(
        cli, ['secrets-add', '-t', reana_token,
              '--env', secret]
    )
    assert result.exit_code == 1
    assert message in result.output


def test_secrets_add_already_exist():
    """Test adding secrets when they already exist."""
    status_code = 409
    reana_token = '000000'
    env = {'REANA_SERVER_URL': 'localhost'}
    message = 'One of the secrets already exists. No secrets were added.'
    mock_http_response = Mock(
        status_code=status_code,
        reason='Conflict',
        json=Mock(return_value={'message': 'Conflict'}))
    rs_api_client_mock = Mock()
    rs_api_client_mock.api.add_secrets = Mock(
        side_effect=HTTPError(mock_http_response))
    runner = CliRunner(env=env)
    with runner.isolation():
        with patch(
                "reana_client.api.client.current_rs_api_client",
                rs_api_client_mock):
                result = runner.invoke(
                    cli, ['secrets-add',
                          '-t', reana_token,
                          '--env', 'USER=reanauser']
                )
                assert message in result.output
                assert result.exit_code == 1


def test_secrets_delete():
    """Test secrets delete."""
    status_code = 200
    reana_token = '000000'
    secret_file = 'file.txt'
    response = ['file.txt']
    message = 'were successfully deleted.'
    mock_http_response = Mock()
    mock_http_response.status_code = status_code
    mock_response = response
    env = {'REANA_SERVER_URL': 'localhost'}
    runner = CliRunner(env=env)
    with runner.isolation():
        with patch(
                "reana_client.api.client.current_rs_api_client",
                make_mock_api_client('reana-server')(mock_response,
                                                     mock_http_response)):
                result = runner.invoke(
                    cli, ['secrets-delete', '-t', reana_token, secret_file]
                )
                assert result.exit_code == 0
                assert message in result.output
