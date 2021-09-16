# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2017, 2018 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""REANA client workflow tests."""

import json

import pytest
import yaml
from click.testing import CliRunner
from mock import Mock, patch
from pytest_reana.test_utils import make_mock_api_client
from reana_commons.config import INTERACTIVE_SESSION_TYPES

from reana_client.api.client import create_workflow_from_json
from reana_client.cli import cli
from reana_client.utils import get_workflow_status_change_msg


def test_workflows_server_not_connected():
    """Test workflows command when server is not connected."""
    runner = CliRunner()
    reana_token = "000000"
    result = runner.invoke(cli, ["list", "-t", reana_token])
    message = "REANA client is not connected to any REANA cluster."
    assert message in result.output
    assert result.exit_code == 1


def test_workflows_no_token():
    """Test workflows command when token is not set."""
    env = {"REANA_SERVER_URL": "localhost"}
    runner = CliRunner(env=env)
    result = runner.invoke(cli, ["list"])
    message = "Please provide your access token by using the -t"
    assert result.exit_code == 1
    assert message in result.output


def test_workflows_server_ok():
    """Test workflows command when server is reachable."""
    response = {
        "items": [
            {
                "status": "running",
                "created": "2018-06-13T09:47:35.66097",
                "user": "00000000-0000-0000-0000-000000000000",
                "name": "mytest.1",
                "id": "256b25f4-4cfb-4684-b7a8-73872ef455a1",
                "size": {"raw": 0, "human_readable": "0 Bytes"},
                "progress": {
                    "run_started_at": "2018-06-13T09:47:40.28223",
                    "run_finished_at": "2018-06-13T10:30:03.70303",
                },
            }
        ]
    }
    status_code = 200
    mock_http_response, mock_response = Mock(), Mock()
    mock_http_response.status_code = status_code
    mock_response = response
    env = {"REANA_SERVER_URL": "localhost", "REANA_WORKON": "mytest.1"}
    reana_token = "000000"
    runner = CliRunner(env=env)
    with runner.isolation():
        with patch(
            "reana_client.api.client.current_rs_api_client",
            make_mock_api_client("reana-server")(mock_response, mock_http_response),
        ):
            result = runner.invoke(
                cli, ["list", "-t", reana_token, "--include-progress"]
            )
            message = "RUN_NUMBER"
            assert result.exit_code == 0
            assert message in result.output


def test_workflows_sorting():
    """Test workflows sorting."""
    response = {
        "items": [
            {
                "status": "running",
                "created": "2018-06-13T09:47:35.66097",
                "user": "00000000-0000-0000-0000-000000000000",
                "name": "mytest.1",
                "id": "256b25f4-4cfb-4684-b7a8-73872ef455a1",
                "progress": {
                    "run_started_at": "2018-06-13T09:47:40.28223",
                    "run_finished_at": "2018-06-13T10:30:03.70303",
                },
                "size": {"raw": 0, "human_readable": "0 Bytes"},
            },
            {
                "status": "running",
                "created": "2018-06-13T09:55:35.66097",
                "user": "00000000-0000-0000-0000-000000000000",
                "name": "mytest.2",
                "id": "256b25f4-4cfb-4684-b7a8-73872ef455a2",
                "size": {"raw": 0, "human_readable": "0 Bytes"},
            },
        ]
    }
    status_code = 200
    mock_http_response, mock_response = Mock(), Mock()
    mock_http_response.status_code = status_code
    mock_response = response
    env = {"REANA_SERVER_URL": "localhost", "REANA_WORKON": "mytest.1"}
    reana_token = "000000"
    runner = CliRunner(env=env)
    with runner.isolation():
        with patch(
            "reana_client.api.client.current_rs_api_client",
            make_mock_api_client("reana-server")(mock_response, mock_http_response),
        ):
            result = runner.invoke(
                cli, ["list", "-t", reana_token, "--sort", "run_number"]
            )
            message = (
                "mytest   2            2018-06-13T09:55:35.66097   -"
                "                           -"
                "                           running\n"
                "mytest   1            2018-06-13T09:47:35.66097   "
                "2018-06-13T09:47:40.28223   2018-06-13T10:30:03.70303"
                "   running"
            )
            assert result.exit_code == 0
            assert message in result.output


def test_workflows_sessions():
    """Test list command for getting interactive sessions."""
    response = {
        "items": [
            {
                "created": "2019-03-19T14:37:58",
                "id": "29136cd0-b259-4d48-8c1e-afe3572df408",
                "name": "workflow.1",
                "session_type": "jupyter",
                "session_uri": "/29136cd0-b259-4d48-8c1e-afe3572df408",
                "size": {"raw": 0, "human_readable": "0 Bytes"},
                "status": "created",
                "user": "00000000-0000-0000-0000-000000000000",
            }
        ]
    }
    status_code = 200
    mock_http_response, mock_response = Mock(), Mock()
    mock_http_response.status_code = status_code
    mock_response = response
    env = {"REANA_SERVER_URL": "localhost", "REANA_WORKON": "mytest.1"}
    reana_token = "000000"
    runner = CliRunner(env=env)
    with runner.isolation():
        with patch(
            "reana_client.api.client.current_rs_api_client",
            make_mock_api_client("reana-server")(mock_response, mock_http_response),
        ):
            result = runner.invoke(cli, ["list", "-t", reana_token, "--sessions"])
            message = "RUN_NUMBER"
            assert result.exit_code == 0
            assert message in result.output


def test_workflows_valid_json():
    """Test workflows command with --json and -v flags."""
    response = {
        "items": [
            {
                "status": "running",
                "created": "2018-06-13T09:47:35.66097",
                "user": "00000000-0000-0000-0000-000000000000",
                "name": "mytest.1",
                "id": "256b25f4-4cfb-4684-b7a8-73872ef455a1",
                "size": {"raw": 0, "human_readable": "0 Bytes"},
            }
        ]
    }
    status_code = 200
    mock_http_response, mock_response = Mock(), Mock()
    mock_http_response.status_code = status_code
    mock_response = response
    env = {"REANA_SERVER_URL": "localhost"}
    reana_token = "000000"
    runner = CliRunner(env=env)
    with runner.isolation():
        with patch(
            "reana_client.api.client.current_rs_api_client",
            make_mock_api_client("reana-server")(mock_response, mock_http_response),
        ):
            result = runner.invoke(cli, ["list", "-v", "-t", reana_token, "--json"])
            assert result.exit_code == 0


def test_workflows_include_progress():
    """Test workflows command with --include-progress flag."""
    response = {
        "items": [
            {
                "status": "running",
                "created": "2018-06-13T09:47:35.66097",
                "user": "00000000-0000-0000-0000-000000000000",
                "name": "mytest.1",
                "id": "256b25f4-4cfb-4684-b7a8-73872ef455a1",
                "size": {"raw": 0, "human_readable": "0 Bytes"},
                "progress": {
                    "total": {"job_ids": [], "total": 5},
                    "running": {"job_ids": [], "total": 3},
                    "finished": {"job_ids": [], "total": 2},
                    "failed": {"job_ids": [], "total": 0},
                },
            }
        ]
    }
    status_code = 200
    mock_http_response, mock_response = Mock(), Mock()
    mock_http_response.status_code = status_code
    mock_response = response
    env = {"REANA_SERVER_URL": "localhost"}
    reana_token = "000000"
    runner = CliRunner(env=env)
    with runner.isolation():
        with patch(
            "reana_client.api.client.current_rs_api_client",
            make_mock_api_client("reana-server")(mock_response, mock_http_response),
        ):
            result = runner.invoke(
                cli, ["list", "--include-progress", "-t", reana_token]
            )
            assert result.exit_code == 0
            assert "PROGRESS" in result.output
            assert "2/5" in result.output


def test_workflows_without_include_progress():
    """Test workflows command without --include-progress flag."""
    response = {
        "items": [
            {
                "status": "running",
                "created": "2018-06-13T09:47:35.66097",
                "user": "00000000-0000-0000-0000-000000000000",
                "name": "mytest.1",
                "id": "256b25f4-4cfb-4684-b7a8-73872ef455a1",
                "size": {"raw": 0, "human_readable": "0 Bytes"},
                "progress": {
                    "run_started_at": "2021-05-10T12:55:04",
                    "run_finished_at": "2021-05-10T12:55:23",
                },
            }
        ]
    }
    status_code = 200
    mock_http_response, mock_response = Mock(), Mock()
    mock_http_response.status_code = status_code
    mock_response = response
    env = {"REANA_SERVER_URL": "localhost"}
    reana_token = "000000"
    runner = CliRunner(env=env)
    with runner.isolation():
        with patch(
            "reana_client.api.client.current_rs_api_client",
            make_mock_api_client("reana-server")(mock_response, mock_http_response),
        ):
            result = runner.invoke(cli, ["list", "-t", reana_token])
            assert result.exit_code == 0
            assert "PROGRESS" not in result.output
            assert "STARTED" in result.output
            assert "2021-05-10T12:55:04" in result.output


def test_workflows_include_workspace_size():
    """Test workflows command with --include-workspace-size flag."""
    response = {
        "items": [
            {
                "status": "running",
                "created": "2018-06-13T09:47:35.66097",
                "user": "00000000-0000-0000-0000-000000000000",
                "name": "mytest.1",
                "id": "256b25f4-4cfb-4684-b7a8-73872ef455a1",
                "size": {"human_readable": "15.97 MiB", "raw": 16741346},
            }
        ]
    }
    status_code = 200
    mock_http_response, mock_response = Mock(), Mock()
    mock_http_response.status_code = status_code
    mock_response = response
    env = {"REANA_SERVER_URL": "localhost"}
    reana_token = "000000"
    runner = CliRunner(env=env)
    with runner.isolation():
        with patch(
            "reana_client.api.client.current_rs_api_client",
            make_mock_api_client("reana-server")(mock_response, mock_http_response),
        ):
            result = runner.invoke(
                cli, ["list", "--include-workspace-size", "-t", reana_token]
            )
            assert result.exit_code == 0
            assert "SIZE" in result.output
            assert "16741346" in result.output


def test_workflows_without_include_workspace_size():
    """Test workflows command without --include-workspace-size flag."""
    response = {
        "items": [
            {
                "status": "running",
                "created": "2018-06-13T09:47:35.66097",
                "user": "00000000-0000-0000-0000-000000000000",
                "name": "mytest.1",
                "id": "256b25f4-4cfb-4684-b7a8-73872ef455a1",
                "size": {"human_readable": "", "raw": -1},
            }
        ]
    }
    status_code = 200
    mock_http_response, mock_response = Mock(), Mock()
    mock_http_response.status_code = status_code
    mock_response = response
    env = {"REANA_SERVER_URL": "localhost"}
    reana_token = "000000"
    runner = CliRunner(env=env)
    with runner.isolation():
        with patch(
            "reana_client.api.client.current_rs_api_client",
            make_mock_api_client("reana-server")(mock_response, mock_http_response),
        ):
            result = runner.invoke(cli, ["list", "-t", reana_token])
            assert result.exit_code == 0
            assert "SIZE" not in result.output


def test_workflows_format():
    """Test workflows command with --format."""
    response = {
        "items": [
            {
                "status": "running",
                "created": "2018-06-13T09:47:35.66097",
                "user": "00000000-0000-0000-0000-000000000000",
                "name": "mytest.1",
                "id": "256b25f4-4cfb-4684-b7a8-73872ef455a1",
                "size": {"raw": 0, "human_readable": "0 Bytes"},
            },
            {
                "status": "failed",
                "created": "2018-06-14T09:47:35.66097",
                "user": "00000000-0000-0000-0000-000000000000",
                "name": "mytest.2",
                "id": "256b25f4-4cfb-4684-b7a8-73872ef455a2",
                "size": {"raw": 0, "human_readable": "0 Bytes"},
            },
        ]
    }
    status_code = 200
    mock_http_response, mock_response = Mock(), Mock()
    mock_http_response.status_code = status_code
    mock_response = response
    env = {"REANA_SERVER_URL": "localhost"}
    reana_token = "000000"
    runner = CliRunner(env=env)
    _format = "status=failed"
    with runner.isolation():
        with patch(
            "reana_client.api.client.current_rs_api_client",
            make_mock_api_client("reana-server")(mock_response, mock_http_response),
        ):
            result = runner.invoke(
                cli,
                ["list", "-t", reana_token, "--json", '--format="{}"'.format(_format)],
            )
            json_response = json.loads(result.output)
            assert result.exit_code == 0
            assert isinstance(json_response, list)
            assert len(json_response) == 1
            assert "status" in json_response[0]
            assert json_response[0]["status"] == "failed"


def test_workflows_filter():
    """Test workflows command with --filter."""
    response = {
        "items": [
            {
                "status": "running",
                "created": "2018-06-13T09:47:35.66097",
                "user": "00000000-0000-0000-0000-000000000000",
                "name": "mytest.1",
                "id": "256b25f4-4cfb-4684-b7a8-73872ef455a1",
                "size": {"raw": 340, "human_readable": "340 Bytes"},
            }
        ]
    }
    status_code = 200
    mock_http_response, mock_response = Mock(), Mock()
    mock_http_response.status_code = status_code
    mock_response = response
    env = {"REANA_SERVER_URL": "localhost"}
    reana_token = "000000"
    runner = CliRunner(env=env)
    filter = "status=running"
    with runner.isolation():
        with patch(
            "reana_client.api.client.current_rs_api_client",
            make_mock_api_client("reana-server")(mock_response, mock_http_response),
        ):
            result = runner.invoke(
                cli, ["list", "-t", reana_token, "--json", "--filter", filter],
            )
            json_response = json.loads(result.output)
            assert result.exit_code == 0
            assert isinstance(json_response, list)
            assert len(json_response) == 1
            assert "status" in json_response[0]
            assert "running" in json_response[0]["status"]


def test_workflow_create_failed():
    """Test workflow create when creation fails."""
    env = {"REANA_SERVER_URL": "localhost"}
    runner = CliRunner(env=env)
    result = runner.invoke(cli, ["create"])
    message = "ERROR: No REANA specification file (reana.yaml) found"
    assert message in result.output
    assert result.exit_code == 1


def test_workflow_create_successful(create_yaml_workflow_schema):
    """Test workflow create when creation is successfull."""
    status_code = 201
    response = {
        "message": "The workflow has been successfully created.",
        "workflow_id": "cdcf48b1-c2f3-4693-8230-b066e088c6ac",
        "workflow_name": "mytest.1",
    }
    env = {"REANA_SERVER_URL": "localhost"}
    reana_token = "000000"
    mock_http_response, mock_response = Mock(), Mock()
    mock_http_response.status_code = status_code
    mock_response = response
    runner = CliRunner(env=env)
    with runner.isolation():
        with patch(
            "reana_client.api.client.current_rs_api_client",
            make_mock_api_client("reana-server")(mock_response, mock_http_response),
        ):
            with runner.isolated_filesystem():
                with open("reana.yaml", "w") as f:
                    f.write(create_yaml_workflow_schema)
                result = runner.invoke(
                    cli, ["create", "-t", reana_token, "--skip-validation"]
                )
                assert result.exit_code == 0
                assert response["workflow_name"] in result.output


def test_workflow_create_not_valid_name(create_yaml_workflow_schema):
    """Test workflow create when creation is successfull."""
    env = {"REANA_SERVER_URL": "localhost"}
    illegal_workflow_name = "workflow.name"
    runner = CliRunner(env=env)
    result = runner.invoke(cli, ["create", "-n", illegal_workflow_name])
    message = 'Workflow name {} contains illegal character "{}"'.format(
        illegal_workflow_name, "."
    )
    assert message in result.output
    assert result.exit_code == 1


def test_create_workflow_from_json(create_yaml_workflow_schema):
    """Test create workflow from json specification."""
    status_code = 201
    response = {
        "message": "The workflow has been successfully created.",
        "workflow_id": "cdcf48b1-c2f3-4693-8230-b066e088c6ac",
        "workflow_name": "mytest.1",
    }
    env = {"REANA_SERVER_URL": "localhost"}
    reana_token = "000000"
    mock_http_response, mock_response = Mock(), Mock()
    mock_http_response.status_code = status_code
    mock_response = response
    workflow_json = yaml.load(create_yaml_workflow_schema, Loader=yaml.FullLoader)
    with patch.dict("os.environ", env):
        with patch(
            "reana_client.api.client.current_rs_api_client",
            make_mock_api_client("reana-server")(mock_response, mock_http_response),
        ):
            result = create_workflow_from_json(
                workflow_json=workflow_json["workflow"],
                name=response["workflow_name"],
                access_token=reana_token,
                parameters=workflow_json["inputs"],
                workflow_engine="serial",
            )
            assert response["workflow_name"] == result["workflow_name"]
            assert response["message"] == result["message"]


@pytest.mark.parametrize(
    "status",
    ["created", "running", "finished", "failed", "deleted", "stopped", "queued"],
)
def test_workflow_start_successful(status):
    """Test workflow start when creation is successfull."""
    workflow_name = "mytest.1"
    response = {
        "status": status,
        "message": "Server message",
        "id": "256b25f4-4cfb-4684-b7a8-73872ef455a1",
        "workflow_name": workflow_name,
        "user": "00000000-0000-0000-0000-000000000000",
    }
    status_code = 200
    reana_token = "000000"
    expected_message = get_workflow_status_change_msg(workflow_name, status)
    mock_http_response = Mock()
    mock_http_response.status_code = status_code
    mock_response = response
    env = {"REANA_SERVER_URL": "localhost"}
    runner = CliRunner(env=env)
    with runner.isolation():
        with patch(
            "reana_client.api.client.current_rs_api_client",
            make_mock_api_client("reana-server")(mock_response, mock_http_response),
        ):
            result = runner.invoke(
                cli, ["start", "-t", reana_token, "-w", response["workflow_name"]]
            )
            assert result.exit_code == 0
            assert expected_message in result.output


@pytest.mark.parametrize(
    "initial_status, final_status, exit_code",
    [("running", "finished", 0), ("running", "failed", 1), ("running", "stopped", 1)],
)
def test_workflow_start_follow(initial_status, final_status, exit_code):
    """Test start workflow with follow flag."""
    workflow_name = "mytest.1"
    initial_reponse = {
        "status": initial_status,
        "message": "Server message",
        "id": "256b25f4-4cfb-4684-b7a8-73872ef455a1",
        "workflow_name": workflow_name,
        "user": "00000000-0000-0000-0000-000000000000",
        "size": {"raw": 0, "human_readable": "0 Bytes"},
    }
    final_reponse = {
        "status": final_status,
        "message": "Server message",
        "id": "256b25f4-4cfb-4684-b7a8-73872ef455a1",
        "workflow_name": workflow_name,
        "user": "00000000-0000-0000-0000-000000000000",
        "size": {"raw": 340, "human_readable": "340 Bytes"},
    }
    initial_expected_message = get_workflow_status_change_msg(
        workflow_name, initial_status
    )
    final_Expected_message = get_workflow_status_change_msg(workflow_name, final_status)
    status_code = 200
    mock_http_response = Mock()
    mock_http_response.status_code = status_code
    mock_api_client = Mock()
    mock_start_workflow_result = Mock(
        return_value=(mock_http_response, mock_http_response)
    )
    mock_api_client.api.start_workflow.return_value = Mock(
        result=mock_start_workflow_result
    )
    mock_get_workflow_status_result = Mock(
        side_effect=[
            (initial_reponse, mock_http_response),
            (final_reponse, mock_http_response),
        ]
    )
    mock_api_client.api.get_workflow_status.return_value = Mock(
        result=mock_get_workflow_status_result
    )
    reana_token = "000000"
    env = {"REANA_SERVER_URL": "localhost"}
    runner = CliRunner(env=env)
    with runner.isolation():
        with patch("reana_client.api.client.current_rs_api_client", mock_api_client):
            result = runner.invoke(
                cli, ["start", "-t", reana_token, "-w", workflow_name, "--follow"]
            )
            assert result.exit_code == exit_code
            assert initial_expected_message in result.output
            assert final_Expected_message in result.output


def test_workflows_validate(create_yaml_workflow_schema):
    """Test validation of REANA specifications file."""
    message = "Valid REANA specification file"
    env = {"REANA_SERVER_URL": "localhost"}
    reana_token = "000000"
    runner = CliRunner(env=env)
    with runner.isolated_filesystem():
        with open("reana.yaml", "w") as f:
            f.write(create_yaml_workflow_schema)
        result = runner.invoke(
            cli, ["validate", "-t", reana_token, "--file", "reana.yaml"],
        )
        assert result.exit_code == 0
        assert message in result.output


def test_get_workflow_status_ok():
    """Test workflow status."""
    status_code = 200
    response = {
        "created": "2018-10-29T12:50:12",
        "id": "4e576cf9-a946-4346-9cde-7712f8dcbb3f",
        "logs": "",
        "name": "workflow.5",
        "progress": {
            "current_command": None,
            "current_step_name": None,
            "failed": {"job_ids": [], "total": 0},
            "finished": {"job_ids": [], "total": 0},
            "run_started_at": "2018-10-29T12:51:04",
            "running": {"job_ids": [], "total": 0},
            "total": {"job_ids": [], "total": 1},
        },
        "status": "running",
        "user": "00000000-0000-0000-0000-000000000000",
    }
    env = {"REANA_SERVER_URL": "localhost"}
    mock_http_response, mock_response = Mock(), Mock()
    mock_http_response.status_code = status_code
    mock_response = response
    reana_token = "000000"
    runner = CliRunner(env=env)
    with runner.isolation():
        with patch(
            "reana_client.api.client.current_rs_api_client",
            make_mock_api_client("reana-server")(mock_response, mock_http_response),
        ):
            result = runner.invoke(
                cli,
                ["status", "-t", reana_token, "--json", "-v", "-w", response["name"]],
            )
            json_response = json.loads(result.output)
            assert result.exit_code == 0
            assert isinstance(json_response, list)
            assert len(json_response) == 1
            assert json_response[0]["name"] in response["name"]


@patch("reana_client.cli.workflow.workflow_create")
@patch("reana_client.cli.workflow.upload_files")
@patch("reana_client.cli.workflow.workflow_start")
def test_run(
    workflow_start_mock,
    upload_file_mock,
    workflow_create_mock,
    create_yaml_workflow_schema,
):
    """Test run command, if wrapped commands are called."""
    reana_workflow_schema = "reana.yaml"
    env = {"REANA_SERVER_URL": "localhost"}
    runner = CliRunner(env=env)
    reana_token = "000000"
    with runner.isolated_filesystem():
        with open(reana_workflow_schema, "w") as f:
            f.write(create_yaml_workflow_schema)
        runner.invoke(
            cli, ["run", "-t", reana_token, "-f", reana_workflow_schema],
        )
    assert workflow_create_mock.called is True
    assert upload_file_mock.called is True
    assert workflow_start_mock.called is True


def test_workflow_input_parameters():
    """Test if not existing input parameters from CLI are applied."""
    status_code = 200
    response = {
        "id": "d9304bdf-0d19-45d9-ae87-d5fd18059193",
        "name": "workflow.19",
        "type": "serial",
        "parameters": {
            "helloworld": "code/helloworld.py",
            "inputfile": "data/names.txt",
            "outputfile": "results/greetings.txt",
            "sleeptime": 2,
        },
    }
    env = {"REANA_SERVER_URL": "localhost"}
    mock_http_response, mock_response = Mock(), Mock()
    mock_http_response.status_code = status_code
    mock_response = response
    reana_token = "000000"
    runner = CliRunner(env=env)
    with runner.isolation():
        with patch(
            "reana_client.api.client.current_rs_api_client",
            make_mock_api_client("reana-server")(mock_response, mock_http_response),
        ):
            parameter = "Debug"
            expected_message = "{0}, is not in reana.yaml".format(parameter)
            result = runner.invoke(
                cli,
                [
                    "start",
                    "-t",
                    reana_token,
                    "-w workflow.19",
                    "-p {0}=True".format(parameter),
                ],
            )
            assert expected_message in result.output


@pytest.mark.parametrize(
    "interactive_session_type",
    INTERACTIVE_SESSION_TYPES
    + [pytest.param("wrong-interactive-type", marks=pytest.mark.xfail)],
)
def test_open_interactive_session(interactive_session_type):
    """Test opening an interactive session."""
    status_code = 200
    workflow_id = "d9304bdf-0d19-45d9-ae87-d5fd18059193"
    response = {"path": "/{}".format(workflow_id)}
    reana_server_url = "http://localhost"
    env = {"REANA_SERVER_URL": reana_server_url}
    mock_http_response, mock_response = Mock(), Mock()
    mock_http_response.status_code = status_code
    mock_response = response
    reana_token = "000000"
    runner = CliRunner(env=env)
    with runner.isolation():
        with patch(
            "reana_client.api.client.current_rs_api_client",
            make_mock_api_client("reana-server")(mock_response, mock_http_response),
        ):
            expected_message = "{reana_server_url}/{workflow_id}".format(
                reana_server_url=reana_server_url, workflow_id=workflow_id
            )
            result = runner.invoke(
                cli,
                [
                    "open",
                    "-t",
                    reana_token,
                    "-w",
                    workflow_id,
                    interactive_session_type,
                ],
            )
            assert expected_message in result.output


def test_close_interactive_session():
    """Test closing an interactive session."""
    status_code = 200
    workflow = "workflow.1"
    expected_message = (
        "Interactive session for workflow {} "
        "was successfully closed\n".format(workflow)
    )
    reana_server_url = "http://localhost"
    env = {"REANA_SERVER_URL": reana_server_url}
    mock_http_response, mock_response = Mock(), Mock()
    mock_http_response.status_code = status_code
    mock_response = expected_message
    reana_token = "000000"
    runner = CliRunner(env=env)
    with runner.isolation():
        with patch(
            "reana_client.api.client.current_rs_api_client",
            make_mock_api_client("reana-server")(mock_response, mock_http_response),
        ):
            result = runner.invoke(cli, ["close", "-t", reana_token, "-w", workflow])
            assert expected_message in result.output


def test_multiple_specifications(create_yaml_workflow_schema):
    env = {"REANA_SERVER_URL": "localhost"}
    runner = CliRunner(env=env)
    message = "ERROR: Found 2 REANA specification files " "(reana.yaml, reana.yml)."
    with runner.isolated_filesystem():
        with open("reana.yaml", "w") as reana_schema:
            reana_schema.write(create_yaml_workflow_schema)
        with open("reana.yml", "w") as reana_schema:
            reana_schema.write(create_yaml_workflow_schema)
        result = runner.invoke(cli, ["validate"])
        assert result.exit_code == 1
        assert message in result.output


def test_yml_ext_specification(create_yaml_workflow_schema):
    env = {"REANA_SERVER_URL": "localhost"}
    runner = CliRunner(env=env)
    message = "Valid REANA specification file"
    reana_token = "000000"
    with runner.isolated_filesystem():
        with open("reana.yml", "w") as reana_schema:
            reana_schema.write(create_yaml_workflow_schema)
        result = runner.invoke(cli, ["validate", "-t", reana_token])
        assert result.exit_code == 0
        assert message in result.output

    message = "ERROR: No REANA specification file (reana.yaml) found."
    with runner.isolated_filesystem():
        with open("reana.json", "w") as reana_schema:
            reana_schema.write(create_yaml_workflow_schema)
        result = runner.invoke(cli, ["validate", "-t", reana_token])
        assert result.exit_code != 0
        assert message in result.output
