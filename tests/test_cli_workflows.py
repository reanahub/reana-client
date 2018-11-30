# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2017, 2018 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""REANA client workflow tests."""

import json

from click.testing import CliRunner
from mock import Mock, patch
from pytest_reana.test_utils import make_mock_api_client

from reana_client.cli import cli


def test_workflows_server_not_connected():
    """Test workflows command when server is not connected."""
    runner = CliRunner()
    result = runner.invoke(cli, ['workflows'])
    message = 'REANA client is not connected to any REANA cluster.'
    assert message in result.output
    assert result.exit_code == 1


def test_workflows_no_token():
    """Test workflows command when token is not set."""
    env = {'REANA_SERVER_URL': 'localhost'}
    runner = CliRunner(env=env)
    result = runner.invoke(cli, ['workflows'])
    message = 'Please provide your access token by using the -at'
    assert result.exit_code == 1
    assert message in result.output


def test_workflows_server_ok():
    """Test workflows command when server is reachable."""
    response = [
        {
            "status": "running",
            "created": "2018-06-13T09:47:35.66097",
            "user": "00000000-0000-0000-0000-000000000000",
            "name": "mytest.1",
            "id": "256b25f4-4cfb-4684-b7a8-73872ef455a1",
        }
    ]
    status_code = 200
    mock_http_response, mock_response = Mock(), Mock()
    mock_http_response.status_code = status_code
    mock_response = response
    env = {'REANA_SERVER_URL': 'localhost', 'REANA_WORKON': 'mytest.1'}
    reana_token = '000000'
    runner = CliRunner(env=env)
    with runner.isolation():
        with patch(
                "reana_client.api.client.current_rs_api_client",
                make_mock_api_client('reana-server')(mock_response,
                                                     mock_http_response)):
            result = runner.invoke(cli, ['workflows', '-at', reana_token])
            message = 'RUN_NUMBER'
            assert result.exit_code == 0
            assert message in result.output


def test_workflows_valid_json():
    """Test workflows command with --json and -v flags."""
    response = [
        {
            "status": "running",
            "created": "2018-06-13T09:47:35.66097",
            "user": "00000000-0000-0000-0000-000000000000",
            "name": "mytest.1",
            "id": "256b25f4-4cfb-4684-b7a8-73872ef455a1",
        }
    ]
    status_code = 200
    mock_http_response, mock_response = Mock(), Mock()
    mock_http_response.status_code = status_code
    mock_response = response
    env = {'REANA_SERVER_URL': 'localhost'}
    reana_token = '000000'
    runner = CliRunner(env=env)
    with runner.isolation():
        with patch(
                "reana_client.api.client.current_rs_api_client",
                make_mock_api_client('reana-server')(mock_response,
                                                     mock_http_response)):
            result = runner.invoke(cli,
                                   ['workflows', '-v', '-at',
                                    reana_token, '--json'])
            json_response = json.loads(result.output)
            assert result.exit_code == 0
            assert isinstance(json_response, list)
            assert len(json_response) == 1
            assert 'name' in json_response[0]
            assert 'run_number' in json_response[0]
            assert 'created' in json_response[0]
            assert 'status' in json_response[0]
            assert 'id' in json_response[0]
            assert 'user' in json_response[0]


def test_workflow_create_failed():
    """Test workflow create when creation fails."""
    runner = CliRunner()
    result = runner.invoke(cli, ['create'])
    message = 'Error: Invalid value for "-f"'
    assert message in result.output
    assert result.exit_code == 2


def test_workflow_create_successful(create_yaml_workflow_schema):
    """Test workflow create when creation is successfull."""
    status_code = 201
    response = {
        "message": "The workflow has been successfully created.",
        "workflow_id": "cdcf48b1-c2f3-4693-8230-b066e088c6ac",
        "workflow_name": "mytest.1"
    }
    env = {'REANA_SERVER_URL': 'localhost'}
    reana_token = '000000'
    mock_http_response, mock_response = Mock(), Mock()
    mock_http_response.status_code = status_code
    mock_response = response
    runner = CliRunner(env=env)
    with runner.isolation():
        with patch(
                "reana_client.api.client.current_rs_api_client",
                make_mock_api_client('reana-server')(mock_response,
                                                     mock_http_response)):
            with runner.isolated_filesystem():
                with open('reana.yaml', 'w') as f:
                    f.write(create_yaml_workflow_schema)
                result = runner.invoke(
                    cli,
                    ['create', '-at', reana_token, '--skip-validation']
                )
                assert result.exit_code == 0
                assert response["workflow_name"] in result.output


def test_workflow_start_successful():
    """Test workflow start when creation is successfull."""
    response = {
        "status": "created",
        "message": "Workflow successfully launched",
        "id": "256b25f4-4cfb-4684-b7a8-73872ef455a1",
        "workflow_name": "mytest.1",
        "user": "00000000-0000-0000-0000-000000000000"
    }
    status_code = 200
    reana_token = '000000'
    message = 'mytest.1 has been started'
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
                cli,
                ['start', '-at', reana_token, '-w', response["workflow_name"]]
            )
            assert result.exit_code == 0
            assert message in result.output


def test_workflows_validate(create_yaml_workflow_schema):
    """Test validation of REANA specifications file."""
    message = "is a valid REANA specification file"
    runner = CliRunner()
    with runner.isolated_filesystem():
        with open('reana.yaml', 'w') as f:
            f.write(create_yaml_workflow_schema)
        result = runner.invoke(
            cli,
            ['validate', '--file', 'reana.yaml'],
        )
        assert result.exit_code == 0
        assert message in result.output


def test_get_workflow_status_ok():
    """Test workflow status."""
    status_code = 200
    response = {
        'created': '2018-10-29T12:50:12',
        'id': '4e576cf9-a946-4346-9cde-7712f8dcbb3f',
        'logs': '',
        'name': 'workflow.5',
        'progress': {
            'current_command': None,
            'current_step_name': None,
            'failed': {'job_ids': [], 'total': 0},
            'finished': {'job_ids': [], 'total': 0},
            'run_started_at': '2018-10-29T12:51:04',
            'running': {'job_ids': [], 'total': 0},
            'total': {'job_ids': [], 'total': 1}
        },
        'status': 'running',
        'user': '00000000-0000-0000-0000-000000000000'
    }
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
                cli,
                ['status', '-at', reana_token, '--json', '-v', '-w',
                 response['name']]
            )
            json_response = json.loads(result.output)
            assert result.exit_code == 0
            assert isinstance(json_response, list)
            assert len(json_response) == 1
            assert json_response[0]['name'] in response['name']


@patch('reana_client.cli.workflow.workflow_create')
@patch('reana_client.cli.workflow.upload_files')
@patch('reana_client.cli.workflow.workflow_start')
def test_run(workflow_start_mock,
             upload_file_mock,
             workflow_create_mock,
             create_yaml_workflow_schema):
    """Test run command, if wrapped commands are called."""
    reana_workflow_schema = "reana.yaml"
    runner = CliRunner()
    with runner.isolated_filesystem():
        with open(reana_workflow_schema, 'w') as f:
            f.write(create_yaml_workflow_schema)
        result = runner.invoke(
            cli,
            ['run', '-f', reana_workflow_schema],
        )
    assert workflow_create_mock.called is True
    assert upload_file_mock.called is True
    assert workflow_start_mock.called is True


def test_workflow_input_parameters():
    """Test if not existing input parameters from CLI are applied."""
    status_code = 200
    response = {'id': 'd9304bdf-0d19-45d9-ae87-d5fd18059193',
                'name': 'workflow.19',
                'type': 'serial',
                'parameters': {'helloworld': 'code/helloworld.py',
                               'inputfile': 'data/names.txt',
                               'outputfile': 'results/greetings.txt',
                               'sleeptime': 2}}
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
            parameter = "Debug"
            expected_message = '{0}, is not in reana.yaml'.format(parameter)
            result = runner.invoke(
                cli,
                ['start', '-at', reana_token, '-w workflow.19',
                 '-p {0}=True'.format(parameter)]
            )
            assert expected_message in result.output
