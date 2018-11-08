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

from reana_client.cli import Config, cli


def test_list_files_server_not_reachable():
    """Test list workflow workspace files when not connected to any cluster."""
    message = 'REANA client is not connected to any REANA cluster.'
    runner = CliRunner()
    result = runner.invoke(cli, ['list'])
    assert result.exit_code == 1
    assert message in result.output


def test_list_files_server_no_token():
    """Test list workflow workspace files when access token is not set."""
    message = 'Please provide your access token'
    env = {'REANA_SERVER_URL': 'localhost'}
    runner = CliRunner(env=env)
    result = runner.invoke(cli, ['list'])
    assert result.exit_code == 1
    assert message in result.output


def test_list_files_ok(mock_base_api_client):
    """Test list workflow workspace files successfull."""
    status_code = 200
    response = [
        {
            "last-modified": "string",
            "name": "string",
            "size": 0
        }
    ]
    reana_token = '000000'
    env = {'REANA_SERVER_URL': 'localhost'}
    mocked_api_client = mock_base_api_client(status_code,
                                             response,
                                             'reana-server')
    config = Config(mocked_api_client)
    runner = CliRunner(env=env)
    result = runner.invoke(
        cli,
        ['list', '-at', reana_token, '--workflow', 'mytest.1', '--json'],
        obj=config
    )
    json_response = json.loads(result.output)
    assert result.exit_code == 0
    assert isinstance(json_response, list)
    assert len(json_response) == 1
    assert json_response[0]['name'] in response[0]['name']


def test_download_file(mock_base_api_client):
    """Test file downloading."""
    status_code = 200
    reana_token = '000000'
    env = {'REANA_SERVER_URL': 'localhost'}
    response = 'Content of file to download'
    response_md5 = hashlib.md5(response.encode('utf-8')).hexdigest()
    file = 'dummy_file.txt'
    message = 'File {0} downloaded to'.format(file)
    mocked_api_client = mock_base_api_client(status_code,
                                             response,
                                             'reana-server')
    config = Config(mocked_api_client)
    runner = CliRunner(env=env)
    result = runner.invoke(
        cli,
        ['download', '-at', reana_token, '--workflow', 'mytest.1', file],
        obj=config
    )
    assert result.exit_code == 0
    assert os.path.isfile(file) is True
    file_md5 = hashlib.md5(open(file, 'rb').read()).hexdigest()
    assert file_md5 == response_md5
    assert message in result.output
    os.remove(file)


def test_upload_file(mock_base_api_client, create_yaml_workflow_schema):
    """Test upload file."""
    status_code = 200
    reana_token = '000000'
    env = {'REANA_SERVER_URL': 'localhost'}
    file = 'file.txt'
    response = [file]
    message = 'was successfully uploaded.'
    mocked_api_client = mock_base_api_client(status_code,
                                             response,
                                             'reana-server')
    config = Config(mocked_api_client)
    runner = CliRunner(env=env)
    with runner.isolated_filesystem():
        with open(file, 'w') as f:
            f.write('test')
        with open('reana.yaml', 'w') as reana_schema:
            reana_schema.write(create_yaml_workflow_schema)
        result = runner.invoke(
            cli,
            ['upload', '-at', reana_token, '--workflow', 'mytest.1', file],
            obj=config
        )
        assert result.exit_code == 0
        assert message in result.output
