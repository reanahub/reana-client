# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2017, 2018 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""REANA client files tests."""

import hashlib
import json
import os

from click.testing import CliRunner
from mock import Mock, patch
from pytest_reana.test_utils import make_mock_api_client

from reana_client.cli import cli


def test_list_files_server_not_reachable():
    """Test list workflow workspace files when not connected to any cluster."""
    message = 'REANA client is not connected to any REANA cluster.'
    runner = CliRunner()
    result = runner.invoke(cli, ['ls'])
    assert result.exit_code == 1
    assert message in result.output


def test_list_files_server_no_token():
    """Test list workflow workspace files when access token is not set."""
    message = 'Please provide your access token'
    env = {'REANA_SERVER_URL': 'localhost'}
    runner = CliRunner(env=env)
    result = runner.invoke(cli, ['ls'])
    assert result.exit_code == 1
    assert message in result.output


def test_list_files_ok():
    """Test list workflow workspace files successfull."""
    status_code = 200
    response = [
        {
            "last-modified": "string",
            "name": "string",
            "size": 0
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
                cli, ['ls', '-t', reana_token, '--workflow', 'mytest.1',
                      '--json'])
            json_response = json.loads(result.output)
            assert result.exit_code == 0
            assert isinstance(json_response, list)
            assert len(json_response) == 1
            assert json_response[0]['name'] in response[0]['name']


def test_download_file():
    """Test file downloading."""
    status_code = 200
    response = 'Content of file to download'
    env = {'REANA_SERVER_URL': 'localhost'}
    mock_http_response = Mock()
    mock_http_response.status_code = status_code
    mock_http_response.raw_bytes = str(response).encode()
    mock_response = response
    reana_token = '000000'
    response_md5 = hashlib.md5(mock_response.encode('utf-8')).hexdigest()
    file = 'dummy_file.txt'
    message = 'File {0} downloaded to'.format(file)
    runner = CliRunner(env=env)
    with runner.isolation():
        with patch(
                "reana_client.api.client.current_rs_api_client",
                make_mock_api_client('reana-server')(mock_response,
                                                     mock_http_response)):
            result = runner.invoke(
                cli, ['download', '-t', reana_token, '--workflow', 'mytest.1',
                      file]
            )
            assert result.exit_code == 0
            assert os.path.isfile(file) is True
            file_md5 = hashlib.md5(open(file, 'rb').read()).hexdigest()
            assert file_md5 == response_md5
            assert message in result.output
            os.remove(file)


def test_upload_file(create_yaml_workflow_schema):
    """Test upload file."""
    status_code = 200
    reana_token = '000000'
    file = 'file.txt'
    response = [file]
    env = {'REANA_SERVER_URL': 'localhost'}
    message = 'was successfully uploaded.'
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
                with open(file, 'w') as f:
                    f.write('test')
                with open('reana.yaml', 'w') as reana_schema:
                    reana_schema.write(create_yaml_workflow_schema)
                result = runner.invoke(
                    cli, ['upload', '-t', reana_token, '--workflow',
                          'mytest.1', file]
                )
                assert result.exit_code == 0
                assert message in result.output


def test_delete_file():
    """Test delete file."""
    status_code = 200
    reana_token = '000000'
    filename1 = 'file1'
    filename2 = 'problematic_file'
    filename2_error_message = '{} could not be deleted.'.format(filename2)
    response = {'deleted': {filename1: {'size': 19}},
                'failed': {filename2: {'error': filename2_error_message}}}
    message1 = 'file1 was successfully deleted'
    mock_http_response = Mock()
    mock_http_response.status_code = status_code
    mock_http_response.raw_bytes = str(response).encode()
    mock_response = response
    env = {'REANA_SERVER_URL': 'localhost'}
    runner = CliRunner(env=env)
    with runner.isolation():
        with patch(
                "reana_client.api.client.current_rs_api_client",
                make_mock_api_client('reana-server')(mock_response,
                                                     mock_http_response)):
            with runner.isolated_filesystem():
                result = runner.invoke(
                    cli,
                    ['rm', '-t', reana_token,
                     '--workflow', 'mytest.1', filename1]
                )
                assert result.exit_code == 0
                assert message1 in result.output
                assert filename2_error_message in result.output


def test_delete_non_existing_file():
    """Test delete non existing file."""
    status_code = 200
    reana_token = '000000'
    filename = 'file11'
    response = {'deleted': {}, 'failed': {}}
    message = '{} did not match any existing file.'.format(filename)
    mock_http_response = Mock()
    mock_http_response.status_code = status_code
    mock_http_response.raw_bytes = str(response).encode()
    mock_response = response
    env = {'REANA_SERVER_URL': 'localhost'}
    runner = CliRunner(env=env)
    with runner.isolation():
        with patch(
                "reana_client.api.client.current_rs_api_client",
                make_mock_api_client('reana-server')(mock_response,
                                                     mock_http_response)):
            with runner.isolated_filesystem():
                result = runner.invoke(
                    cli,
                    ['rm', '-t', reana_token, '--workflow', 'mytest.1',
                     filename]
                )
                assert result.exit_code == 0
                assert message in result.output


def test_move_file_running_workflow():
    """Test move files when workflow is running."""
    status_code = 200
    reana_token = '000000'
    src_file = 'file11'
    target = 'file2'
    response = {"status": "running",
                "logs": "",
                "name": "mytest.1"}
    message = 'File(s) could not be moved for running workflow'
    mock_http_response = Mock()
    mock_http_response.status_code = status_code
    mock_http_response.raw_bytes = str(response).encode()
    mock_response = response
    env = {'REANA_SERVER_URL': 'localhost'}
    runner = CliRunner(env=env)
    with runner.isolation():
        with patch(
                "reana_client.api.client.current_rs_api_client",
                make_mock_api_client('reana-server')(mock_response,
                                                     mock_http_response)):
            result = runner.invoke(
                cli,
                ['mv', '-t', reana_token, '--workflow', 'mytest.1',
                 src_file, target]
            )
            assert result.exit_code == 1
            assert message in result.output
