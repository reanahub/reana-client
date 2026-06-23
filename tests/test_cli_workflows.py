# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""REANA client workflow tests."""

import copy
import json
import sys
from typing import List
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner
from mock import Mock, patch
from reana_commons.testing import make_mock_api_client
from reana_client.api.client import create_workflow_from_json
from reana_client.cli import cli
from reana_client.config import ERROR_MESSAGES, RUN_STATUSES
from reana_client.utils import get_workflow_status_change_msg
from reana_commons.api_client import BaseAPIClient
from reana_commons.config import INTERACTIVE_SESSION_TYPES
from reana_commons.specification import load_workflow_spec_from_reana_yaml
from reana_commons.validation.images import extract_images


def test_workflows_server_not_connected():
    """Test workflows command when server is not connected."""
    runner = CliRunner()
    result = runner.invoke(cli, ["list"])
    message = "REANA client is not connected to any REANA cluster."
    assert message in result.output
    assert result.exit_code == 1


def test_load_snakemake_workflow_extracts_container_image(tmp_path):
    """Test that client-side Snakemake expansion exposes container images."""
    snakefile = tmp_path / "Snakefile"
    snakefile.write_text("""
rule all:
    input: "output.txt"
    default_target: True

rule create_output:
    output: "output.txt"
    container: "docker://docker.io/library/ubuntu:24.04"
    shell: "touch {output}"
""")
    reana_yaml = {"workflow": {"type": "snakemake", "file": "Snakefile"}}

    reana_yaml["workflow"]["specification"] = load_workflow_spec_from_reana_yaml(
        reana_yaml, tmp_path
    )

    assert extract_images(reana_yaml) == ["docker.io/library/ubuntu:24.04"]


def test_workflows_no_token(monkeypatch):
    """Test workflows command when token is not set."""
    env = {"REANA_SERVER_URL": "localhost"}
    runner = CliRunner(env=env)
    monkeypatch.setattr(
        "reana_client.cli.utils.get_access_token",
        lambda: (_ for _ in ()).throw(Exception(ERROR_MESSAGES["missing_access_token"])),
    )
    result = runner.invoke(cli, ["list"])
    assert result.exit_code == 1
    assert ERROR_MESSAGES["missing_access_token"] in result.output


def test_workflows_server_ok():
    """Test workflows command when server is reachable."""
    response = {
        "items": [
            {
                "status": "running",
                "created": "2018-06-13T09:47:35",
                "user": "00000000-0000-0000-0000-000000000000",
                "name": "mytest.1",
                "id": "256b25f4-4cfb-4684-b7a8-73872ef455a1",
                "size": {"raw": 0, "human_readable": "0 Bytes"},
                "progress": {
                    "run_started_at": "2018-06-13T09:47:40",
                    "run_finished_at": "2018-06-13T10:30:03",
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
                cli, ["list", "--include-progress"]
            )
            message = "RUN_NUMBER"
            assert result.exit_code == 0
            assert message in result.output


@pytest.mark.parametrize(
    "cli_options,expected_status_filter",
    [
        ([], [status for status in RUN_STATUSES if status != "deleted"]),
        (["--show-deleted-runs"], RUN_STATUSES),
        (["--all"], RUN_STATUSES),
        (["--filter", "status=deleted"], ["deleted"]),
        (["--filter", "status=finished", "--show-deleted-runs"], ["finished"]),
        (["--filter", "status=finished", "--all"], ["finished"]),
        (
            ["--filter", "name=myworkflow"],
            [status for status in RUN_STATUSES if status != "deleted"],
        ),
        (["--filter", "name=myworkflow", "--show-deleted-runs"], RUN_STATUSES),
        (["--filter", "name=myworkflow", "--all"], RUN_STATUSES),
    ],
)
def test_deleted_workflows(cli_options: List[str], expected_status_filter: List[str]):
    """Test whatever deleted workflows are displayed correctly depending on options and filters."""
    # we do not care what response is in this case
    response = {"items": []}
    env = {"REANA_SERVER_URL": "localhost"}
    reana_token = "000000"
    runner = CliRunner(env=env)
    with runner.isolation():
        with patch("reana_client.api.client.get_workflows") as mock_get_workflows:
            mock_get_workflows.return_value = response
            runner.invoke(cli, ["list"] + cli_options)
            kwargs = mock_get_workflows.call_args.kwargs
            assert kwargs["status"] == expected_status_filter


@pytest.mark.parametrize(
    "cli_options, expected_output",
    [
        (
            ["list", "--sort", "Run_NUMber"],
            (
                "mytest   15           2018-06-13T10:55:37   -                     -                     running\n"
                "mytest   2            2018-06-13T09:55:35   -                     -                     running\n"
                "mytest   1 *          2018-06-13T09:47:35   2018-06-13T09:47:40   2018-06-13T10:30:03   running"
            ),
        ),
        (
            [
                "list",
                "--include-workspace-size",
                "-h",
                "--sort",
                "size",
            ],
            (
                "mytest   1 *          2018-06-13T09:47:35   2018-06-13T09:47:40   2018-06-13T10:30:03   running   1.55 MiB\n"
                "mytest   2            2018-06-13T09:55:35   -                     -                     running   540 KiB \n"
                "mytest   15           2018-06-13T10:55:37   -                     -                     running   192 KiB "
            ),
        ),
    ],
)
def test_workflows_sorting(cli_options: List[str], expected_output: str):
    """Test workflows sorting."""
    response = {
        "items": [
            {
                "status": "running",
                "created": "2018-06-13T09:47:35",
                "user": "00000000-0000-0000-0000-000000000000",
                "name": "mytest.1",
                "id": "256b25f4-4cfb-4684-b7a8-73872ef455a1",
                "progress": {
                    "run_started_at": "2018-06-13T09:47:40",
                    "run_finished_at": "2018-06-13T10:30:03",
                },
                "size": {"raw": 1622016, "human_readable": "1.55 MiB"},
            },
            {
                "status": "running",
                "created": "2018-06-13T09:55:35",
                "user": "00000000-0000-0000-0000-000000000000",
                "name": "mytest.2",
                "id": "256b25f4-4cfb-4684-b7a8-73872ef455a2",
                "size": {"raw": 552960, "human_readable": "540 KiB"},
            },
            {
                "status": "running",
                "created": "2018-06-13T10:55:37",
                "user": "00000000-0000-0000-0000-000000000000",
                "name": "mytest.15",
                "id": "256b25f4-4cfb-4684-b7a8-73872ef455a3",
                "size": {"raw": 196608, "human_readable": "192 KiB"},
            },
        ]
    }
    status_code = 200
    mock_http_response, mock_response = Mock(), Mock()
    mock_http_response.status_code = status_code
    mock_response = response
    env = {"REANA_SERVER_URL": "localhost", "REANA_WORKON": "mytest.1"}
    runner = CliRunner(env=env)
    with runner.isolation():
        with patch(
            "reana_client.api.client.current_rs_api_client",
            make_mock_api_client("reana-server")(mock_response, mock_http_response),
        ):
            result = runner.invoke(cli, cli_options)
            assert result.exit_code == 0
            assert expected_output in result.output


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
                "session_status": "created",
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
            result = runner.invoke(cli, ["list", "--sessions"])
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
                "progress": {},
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
            result = runner.invoke(cli, ["list", "-v", "--json"])
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
                cli, ["list", "--include-progress"]
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
            result = runner.invoke(cli, ["list"])
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
                cli, ["list", "--include-workspace-size"]
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
            result = runner.invoke(cli, ["list"])
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
                ["list", "--json", '--format="{}"'.format(_format)],
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
                cli,
                ["list", "--json", "--filter", filter],
            )
            json_response = json.loads(result.output)
            assert result.exit_code == 0
            assert isinstance(json_response, list)
            assert len(json_response) == 1
            assert "status" in json_response[0]
            assert "running" in json_response[0]["status"]


def test_workflows_shared():
    """Test workflow list command with --shared flag."""
    response = {
        "items": [
            {
                "status": "running",
                "created": "2018-06-13T09:47:35.66097",
                "user": "00000000-0000-0000-0000-000000000000",
                "name": "mytest.1",
                "id": "256b25f4-4cfb-4684-b7a8-73872ef455a1",
                "size": {"raw": 0, "human_readable": "0 Bytes"},
                "progress": {},
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
            result = runner.invoke(cli, ["list", "--shared"])
            assert result.exit_code == 0
            assert "SHARED_WITH" in result.output
            assert "SHARED_BY" in result.output


def test_workflows_shared_with():
    """Test workflow list command with --shared-with flag."""
    response = {
        "items": [
            {
                "status": "running",
                "created": "2018-06-13T09:47:35.66097",
                "user": "00000000-0000-0000-0000-000000000000",
                "name": "mytest.1",
                "id": "256b25f4-4cfb-4684-b7a8-73872ef455a1",
                "size": {"raw": 0, "human_readable": "0 Bytes"},
                "progress": {},
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
                cli, ["list", "--shared-with", "anybody"]
            )
            assert result.exit_code == 0
            assert "SHARED_WITH" in result.output
            assert "SHARED_BY" not in result.output


def test_workflows_shared_by():
    """Test workflow list command with --shared-by flag."""
    response = {
        "items": [
            {
                "status": "running",
                "created": "2018-06-13T09:47:35.66097",
                "user": "00000000-0000-0000-0000-000000000000",
                "name": "mytest.1",
                "id": "256b25f4-4cfb-4684-b7a8-73872ef455a1",
                "size": {"raw": 0, "human_readable": "0 Bytes"},
                "progress": {},
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
                cli, ["list", "--shared-by", "anybody"]
            )
            assert result.exit_code == 0
            assert "SHARED_WITH" not in result.output
            assert "SHARED_BY" in result.output


def test_workflows_shared_with_and_shared_by():
    """Test workflow list command with --shared-with and --shared-by flags."""
    response = {
        "items": [
            {
                "status": "running",
                "created": "2018-06-13T09:47:35.66097",
                "user": "00000000-0000-0000-0000-000000000000",
                "name": "mytest.1",
                "id": "256b25f4-4cfb-4684-b7a8-73872ef455a1",
                "size": {"raw": 0, "human_readable": "0 Bytes"},
                "progress": {},
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
                cli,
                [
                    "list",
                    "--shared-with",
                    "anybody",
                    "--shared-by",
                    "anybody",
                ],
            )
            assert result.exit_code == 1
            assert (
                "Please provide either --shared-by or --shared-with, not both"
                in result.output
            )


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
        ), patch("reana_client.api.client.requests.post") as upload_request:
            with runner.isolated_filesystem():
                with open("reana.yaml", "w") as f:
                    f.write(create_yaml_workflow_schema)
                result = runner.invoke(
                    cli, ["create", "--skip-validation"]
                )
                assert result.exit_code == 0
                assert response["workflow_name"] in result.output

                upload_request.assert_called_once()
                assert "File /reana.yaml was successfully uploaded." in result.output


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


def test_workflow_create_image_not_authorized(create_yaml_workflow_schema):
    """Test that create exits with code 1 when the workflow image is not in the allowlist."""
    env = {"REANA_SERVER_URL": "localhost"}
    reana_token = "000000"
    mock_cluster_info = {
        "compute_backends": {"value": ["kubernetes"]},
        "vetted_container_images_enabled": {"value": True},
        "vetted_container_images_allowlist": {"value": ["ubuntu:20.04"]},
    }
    runner = CliRunner(env=env)
    with runner.isolated_filesystem():
        with open("reana.yaml", "w") as f:
            f.write(create_yaml_workflow_schema)
        with patch("reana_client.api.client.info", return_value=mock_cluster_info):
            result = runner.invoke(
                cli, ["create", "-t", reana_token, "--file", "reana.yaml"]
            )
    assert result.exit_code == 1
    assert "Environment image is not allowed" in result.output


def test_create_workflow_from_json(create_yaml_workflow_schema):
    """Test create workflow from json specification."""
    status_code = 201
    response = {
        "message": "The workflow has been successfully created.",
        "workflow_id": "cdcf48b1-c2f3-4693-8230-b066e088c6ac",
        "workflow_name": "mytest",
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


def test_create_snakemake_workflow_from_json_parameters(
    create_snakemake_yaml_external_input_workflow_schema,
    tmp_path,
    snakemake_workflow_spec_step_param,
    external_parameter_yaml_file,
):
    """Test create workflow from json with external parameters."""
    status_code = 201
    response = {
        "message": "The workflow has been successfully created.",
        "workflow_id": "cdcf48b1-c2f3-4693-8230-b066e088c6ac",
        "workflow_name": "mytest",
    }
    env = {"REANA_SERVER_URL": "localhost"}
    reana_token = "000000"
    mock_http_response, mock_response = Mock(), Mock()
    mock_http_response.status_code = status_code
    mock_response = response
    workflow_json = yaml.load(
        create_snakemake_yaml_external_input_workflow_schema, Loader=yaml.FullLoader
    )
    with open(tmp_path / "Snakefile", "w") as f:
        f.write(snakemake_workflow_spec_step_param)
    with open(tmp_path / "config.yaml", "w") as f:
        f.write(external_parameter_yaml_file)
    with patch.dict("os.environ", env):
        with patch(
            "reana_client.api.client.current_rs_api_client",
            make_mock_api_client("reana-server")(mock_response, mock_http_response),
        ):
            result = create_workflow_from_json(
                workflow_file=str(tmp_path / "Snakefile"),
                name=response["workflow_name"],
                access_token=reana_token,
                parameters=workflow_json["inputs"],
                workflow_engine="snakemake",
                workspace_path=Path(tmp_path),
            )
            assert response["workflow_name"] == result["workflow_name"]
            assert response["message"] == result["message"]


@pytest.mark.parametrize(
    "status, exit_code",
    [
        ("created", 0),
        ("pending", 0),
        ("queued", 0),
        ("running", 0),
        ("finished", 0),
        ("failed", 1),
        ("deleted", 1),
        ("stopped", 1),
    ],
)
def test_workflow_start_successful(status, exit_code):
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
                cli, ["start", "-w", response["workflow_name"]]
            )
            assert result.exit_code == exit_code
            assert expected_message in result.output


@pytest.mark.parametrize(
    "initial_status, final_status, exit_code",
    [
        ("running", "finished", 0),
        ("running", "failed", 1),
        ("running", "stopped", 1),
        ("queued", "finished", 0),
        ("pending", "deleted", 1),
    ],
)
@patch("reana_client.cli.workflow.TIMECHECK", 0)
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

    # Also need to mock API calls made by get_files
    get_files_response = {"items": []}
    mock_get_files_result = Mock(return_value=(get_files_response, mock_http_response))
    mock_api_client.api.get_files.return_value = Mock(result=mock_get_files_result)
    mock_api_client.swagger_spec.spec_dict = {"paths": {}}

    reana_token = "000000"
    env = {"REANA_SERVER_URL": "localhost"}
    runner = CliRunner(env=env)
    with runner.isolation():
        with patch("reana_client.api.client.current_rs_api_client", mock_api_client):
            result = runner.invoke(
                cli, ["start", "-w", workflow_name, "--follow"]
            )
            assert result.exit_code == exit_code
            assert initial_expected_message in result.output
            assert final_Expected_message in result.output
            if final_status == "finished":
                assert "Listing workflow output files..." in result.output


def test_workflows_validate(create_yaml_workflow_schema):
    """Test validation of REANA specification file."""
    message = "Valid REANA specification file"
    env = {"REANA_SERVER_URL": "localhost"}
    reana_token = "000000"
    runner = CliRunner(env=env)
    with runner.isolated_filesystem():
        with open("reana.yaml", "w") as f:
            f.write(create_yaml_workflow_schema)
        result = runner.invoke(
            cli,
            ["validate", "--file", "reana.yaml"],
        )
        assert result.exit_code == 0
        assert message in result.output


def test_workflows_validate_image_not_authorized(create_yaml_workflow_schema):
    """Test that validate exits with code 1 when the workflow image is not in the allowlist."""
    from reana_client.validation.environments import EnvironmentValidatorSerial

    env = {"REANA_SERVER_URL": "localhost"}
    reana_token = "000000"
    mock_cluster_info = {
        "vetted_container_images_enabled": {"value": True},
        "vetted_container_images_allowlist": {"value": ["ubuntu:20.04"]},
    }
    runner = CliRunner(env=env)
    with runner.isolated_filesystem():
        with open("reana.yaml", "w") as f:
            f.write(create_yaml_workflow_schema)
        with patch(
            "reana_client.api.client.info", return_value=mock_cluster_info
        ), patch.object(
            EnvironmentValidatorSerial,
            "_image_exists",
            return_value=(False, True),
        ):
            result = runner.invoke(
                cli,
                [
                    "validate",
                    "--environments",
                    "-t",
                    reana_token,
                    "--file",
                    "reana.yaml",
                ],
            )
        assert result.exit_code == 1
        assert "Environment image is not allowed" in result.output


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
                ["status", "--json", "-v", "-w", response["name"]],
            )
            json_response = json.loads(result.output)
            assert result.exit_code == 0
            assert isinstance(json_response, list)
            assert len(json_response) == 1
            assert json_response[0]["name"] in response["name"]


def test_get_workflow_logs():
    """Test workflow logs."""
    status_code = 200
    response = {
        "logs": '{"workflow_logs": "workflow logs test"}',
        "user": "00000000-0000-0000-0000-000000000000",
        "workflow_id": "26a55924-83c9-493b-841b-8fd7629e25c9",
        "workflow_name": "helloworld-serial-kubernetes0.3",
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
                ["logs", "--json", "-w", response["workflow_name"]],
            )
            json_response = json.loads(result.output)
            assert result.exit_code == 0
            assert isinstance(json_response, dict)
            assert json_response["workflow_logs"] in "workflow logs test"


def test_follow_job_logs():
    """Test follow job logs."""
    logs = {
        "workflow_logs": "workflow logs test",
        "job_logs": {
            "job_id": {
                "workflow_uuid": "26a55924-83c9-493b-841b-8fd7629e25c9",
                "job_name": "hello1",
                "compute_backend": "Kubernetes",
                "backend_job_id": "reana-run-job-42532a36-4a41-4acf-a3b0-d61655030f43",
                "docker_img": "docker.io/library/python:3.8-slim",
                "cmd": "python",
                "status": "running",
                "logs": "job test logs\n",
                "started_at": "2024-09-26T09:02:36",
                "finished_at": None,
            }
        },
    }
    logs_next = copy.deepcopy(logs)
    logs_next["job_logs"]["job_id"]["status"] = "stopped"
    logs_next["job_logs"]["job_id"]["logs"] = "job test logs\nmore job logs\n"

    response = {
        "logs": json.dumps(logs),
        "user": "00000000-0000-0000-0000-000000000000",
        "workflow_id": "26a55924-83c9-493b-841b-8fd7629e25c9",
        "workflow_name": "helloworld-serial-kubernetes0.3",
        "live_logs_enabled": True,
    }
    response_next = copy.deepcopy(response)
    response_next["logs"] = json.dumps(logs_next)

    env = {"REANA_SERVER_URL": "localhost"}
    mock_http_response = Mock()
    mock_http_response.status_code = 200
    reana_token = "000000"
    runner = CliRunner(env=env)

    mock_http_client, mock_result = Mock(), Mock()
    mock_result.result.side_effect = [
        (response, mock_http_response),
        (response_next, mock_http_response),
    ]
    mock_http_client.request.return_value = mock_result

    with runner.isolation():
        with patch(
            "reana_client.api.client.current_rs_api_client",
            BaseAPIClient("reana-server", http_client=mock_http_client)._client,
        ):
            result = runner.invoke(
                cli,
                [
                    "logs",
                    "--follow",
                    "-i",
                    1,
                    "-w",
                    "helloworld-serial-kubernetes0.3",
                    "--filter",
                    "step=hello1",
                ],
            )
            assert result.exit_code == 0
            assert result.output == """job test logs
more job logs
==> Job has completed, you might want to rerun the command without the --follow flag.
"""


def test_follow_live_logs_disabled():
    """Test follow job logs when live logs are disabled."""
    logs = {
        "workflow_logs": "",
        "job_logs": {
            "job_id": {
                "workflow_uuid": "26a55924-83c9-493b-841b-8fd7629e25c9",
                "job_name": "hello1",
                "compute_backend": "Kubernetes",
                "backend_job_id": "reana-run-job-42532a36-4a41-4acf-a3b0-d61655030f43",
                "docker_img": "docker.io/library/python:3.8-slim",
                "cmd": "python",
                "status": "running",
                "logs": "",
                "started_at": "2024-09-26T09:02:36",
                "finished_at": None,
            }
        },
    }

    response = {
        "logs": json.dumps(logs),
        "user": "00000000-0000-0000-0000-000000000000",
        "workflow_id": "26a55924-83c9-493b-841b-8fd7629e25c9",
        "workflow_name": "helloworld-serial-kubernetes0.3",
    }

    env = {"REANA_SERVER_URL": "localhost"}
    mock_http_response = Mock()
    mock_http_response.status_code = 200
    reana_token = "000000"
    runner = CliRunner(env=env)

    mock_http_client, mock_result = Mock(), Mock()
    mock_result.result.side_effect = [
        (response, mock_http_response),
    ]
    mock_http_client.request.return_value = mock_result

    with runner.isolation():
        with patch(
            "reana_client.api.client.current_rs_api_client",
            BaseAPIClient("reana-server", http_client=mock_http_client)._client,
        ):
            result = runner.invoke(
                cli,
                [
                    "logs",
                    "--follow",
                    "-i",
                    1,
                    "-w",
                    "helloworld-serial-kubernetes0.3",
                    "--filter",
                    "step=hello1",
                ],
            )
            assert result.exit_code == 0
            assert (
                result.output
                == """==> ERROR: Live logs are not enabled, please rerun the command without the --follow flag.
"""
            )


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
            cli,
            ["run", "-f", reana_workflow_schema],
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
                    "-w workflow.19",
                    "-p {0}=True".format(parameter),
                ],
            )
            assert expected_message in result.output


@pytest.mark.parametrize(
    "interactive_session_type,reana_info,is_autoclosure_message_expected",
    [
        (
            session_type,
            {"maximum_interactive_session_inactivity_period": {"value": 30}},
            True,
        )
        for session_type in INTERACTIVE_SESSION_TYPES
    ]
    + [
        (
            INTERACTIVE_SESSION_TYPES[0],
            {"maximum_interactive_session_inactivity_period": None},
            False,
        ),
        (INTERACTIVE_SESSION_TYPES[0], dict(), False),
        pytest.param(
            "wrong-interactive-type",
            {"maximum_interactive_session_inactivity_period": {"value": 30}},
            True,
            marks=pytest.mark.xfail,
        ),
    ],
)
def test_open_interactive_session(
    interactive_session_type, reana_info, is_autoclosure_message_expected
):
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
        ), patch(
            "reana_client.api.client.info",
            return_value=reana_info,
        ):
            expected_url_session = "{reana_server_url}/{workflow_id}".format(
                reana_server_url=reana_server_url, workflow_id=workflow_id
            )
            expected_auto_closure_message = "will be automatically closed after 30 days"
            result = runner.invoke(
                cli,
                [
                    "open",
                    "-w",
                    workflow_id,
                    interactive_session_type,
                ],
            )
            assert expected_url_session in result.output
            if is_autoclosure_message_expected:
                assert expected_auto_closure_message in result.output
            else:
                assert expected_auto_closure_message not in result.output


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
            result = runner.invoke(cli, ["close", "-w", workflow])
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
        result = runner.invoke(cli, ["validate"])
        assert result.exit_code == 0
        assert message in result.output

    message = "ERROR: No REANA specification file (reana.yaml) found."
    with runner.isolated_filesystem():
        with open("reana.json", "w") as reana_schema:
            reana_schema.write(create_yaml_workflow_schema)
        result = runner.invoke(cli, ["validate"])
        assert result.exit_code != 0
        assert message in result.output


def test_run_with_no_inputs(spec_without_inputs):
    """Test running workflow when specification does not contain inputs."""
    env = {"REANA_SERVER_URL": "localhost"}
    reana_token = "000000"
    runner = CliRunner(env=env)
    with patch(
        "reana_client.cli.workflow.workflow_create"
    ) as cli_workflow_create, patch(
        "reana_client.cli.workflow.workflow_start"
    ) as cli_workflow_start, patch(
        "reana_client.api.client.get_workflow_specification",
        Mock(return_value={"specification": spec_without_inputs}),
    ) as get_workflow_specification, patch(
        "reana_client.api.client.upload_to_server"
    ) as upload_to_server, runner.isolated_filesystem():
        with open("reana.yaml", "w") as f:
            yaml.dump(spec_without_inputs, f)

        result = runner.invoke(cli, ["run"])

        assert result.exit_code == 0
        cli_workflow_create.assert_called()
        cli_workflow_start.assert_called()
        get_workflow_specification.assert_called()
        upload_to_server.assert_not_called()


def test_share_add_workflow():
    """Test share-add workflows."""
    status_code = 200
    response = {
        "message": "is now read-only shared with",
        "workflow_id": "string",
        "workflow_name": "string",
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
                [
                    "share-add",
                    "--workflow",
                    "test-workflow.1",
                    "--user",
                    "bob@.cern.ch",
                    "--message",
                    "Test message",
                    "--valid-until",
                    "2024-01-01",
                ],
            )
            assert result.exit_code == 0
            assert response["message"] in result.output


def test_share_remove_workflow():
    """Test share-remove workflows."""
    status_code = 200
    response = {
        "message": "is no longer shared with",
        "workflow_id": "string",
        "workflow_name": "string",
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
                [
                    "share-remove",
                    "--workflow",
                    "test-workflow.1",
                    "--user",
                    "bob@.cern.ch",
                ],
            )
            assert result.exit_code == 0
            assert response["message"] in result.output


def test_share_status_workflow():
    """Test share-status workflows."""
    status_code = 200
    response = {
        "message": "is not shared with anyone",
        "workflow_id": "string",
        "workflow_name": "string",
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
                [
                    "share-status",
                    "--workflow",
                    "test-workflow.1",
                ],
            )
            assert result.exit_code == 0
            assert response["message"] in result.output


# ---------------------------
# share-add JSON output tests
# ---------------------------


def test_share_add_workflow_json_success():
    """Test share-add --json outputs valid JSON on success."""
    status_code = 200
    response = {
        "message": "is now read-only shared with",
        "workflow_id": "string",
        "workflow_name": "string",
    }
    env = {"REANA_SERVER_URL": "localhost"}
    mock_http_response = Mock()
    mock_http_response.status_code = status_code
    reana_token = "000000"
    runner = CliRunner(env=env)
    with runner.isolation():
        with patch(
            "reana_client.api.client.current_rs_api_client",
            make_mock_api_client("reana-server")(response, mock_http_response),
        ):
            result = runner.invoke(
                cli,
                [
                    "share-add",
                    "--json",
                    "-t",
                    reana_token,
                    "--workflow",
                    "test-workflow.1",
                    "--user",
                    "bob@example.org",
                ],
            )
            assert result.exit_code == 0
            parsed = json.loads(result.output)
            assert parsed["workflow"] == "test-workflow.1"
            assert parsed["shared_with"] == ["bob@example.org"]
            assert parsed["errors"] == []


def test_share_add_workflow_json_all_fail():
    """Test share-add --json outputs errors and exits 1 when all shares fail."""
    env = {"REANA_SERVER_URL": "localhost"}
    reana_token = "000000"
    runner = CliRunner(env=env)
    with runner.isolation():
        with patch(
            "reana_client.api.client.share_workflow",
            side_effect=Exception("User not found"),
        ):
            result = runner.invoke(
                cli,
                [
                    "share-add",
                    "--json",
                    "-t",
                    reana_token,
                    "--workflow",
                    "test-workflow.1",
                    "--user",
                    "nobody@example.org",
                ],
            )
            assert result.exit_code == 1
            parsed = json.loads(result.output)
            assert parsed["workflow"] == "test-workflow.1"
            assert parsed["shared_with"] == []
            assert len(parsed["errors"]) == 1
            assert "nobody@example.org" in parsed["errors"][0]


def test_share_add_workflow_json_partial_failure():
    """Test share-add --json reports partial results and exits 1 on any error."""
    env = {"REANA_SERVER_URL": "localhost"}
    reana_token = "000000"
    runner = CliRunner(env=env)
    with runner.isolation():
        with patch(
            "reana_client.api.client.share_workflow",
            side_effect=[None, Exception("User not found")],
        ):
            result = runner.invoke(
                cli,
                [
                    "share-add",
                    "--json",
                    "-t",
                    reana_token,
                    "--workflow",
                    "test-workflow.1",
                    "--user",
                    "bob@example.org",
                    "--user",
                    "nobody@example.org",
                ],
            )
            assert result.exit_code == 1
            parsed = json.loads(result.output)
            assert parsed["shared_with"] == ["bob@example.org"]
            assert len(parsed["errors"]) == 1
            assert "nobody@example.org" in parsed["errors"][0]


# ------------------------------
# share-remove JSON output tests
# ------------------------------


def test_share_remove_workflow_json_success():
    """Test share-remove --json outputs valid JSON on success."""
    status_code = 200
    response = {
        "message": "is no longer shared with",
        "workflow_id": "string",
        "workflow_name": "string",
    }
    env = {"REANA_SERVER_URL": "localhost"}
    mock_http_response = Mock()
    mock_http_response.status_code = status_code
    reana_token = "000000"
    runner = CliRunner(env=env)
    with runner.isolation():
        with patch(
            "reana_client.api.client.current_rs_api_client",
            make_mock_api_client("reana-server")(response, mock_http_response),
        ):
            result = runner.invoke(
                cli,
                [
                    "share-remove",
                    "--json",
                    "-t",
                    reana_token,
                    "--workflow",
                    "test-workflow.1",
                    "--user",
                    "bob@example.org",
                ],
            )
            assert result.exit_code == 0
            parsed = json.loads(result.output)
            assert parsed["workflow"] == "test-workflow.1"
            assert parsed["unshared_with"] == ["bob@example.org"]
            assert parsed["errors"] == []


def test_share_remove_workflow_json_all_fail():
    """Test share-remove --json outputs errors and exits 1 when all unshares fail."""
    env = {"REANA_SERVER_URL": "localhost"}
    reana_token = "000000"
    runner = CliRunner(env=env)
    with runner.isolation():
        with patch(
            "reana_client.api.client.unshare_workflow",
            side_effect=Exception("Workflow not shared with user"),
        ):
            result = runner.invoke(
                cli,
                [
                    "share-remove",
                    "--json",
                    "-t",
                    reana_token,
                    "--workflow",
                    "test-workflow.1",
                    "--user",
                    "nobody@example.org",
                ],
            )
            assert result.exit_code == 1
            parsed = json.loads(result.output)
            assert parsed["workflow"] == "test-workflow.1"
            assert parsed["unshared_with"] == []
            assert len(parsed["errors"]) == 1
            assert "nobody@example.org" in parsed["errors"][0]


def test_share_remove_workflow_json_partial_failure():
    """Test share-remove --json reports partial results and exits 1 on any error."""
    env = {"REANA_SERVER_URL": "localhost"}
    reana_token = "000000"
    runner = CliRunner(env=env)
    with runner.isolation():
        with patch(
            "reana_client.api.client.unshare_workflow",
            side_effect=[None, Exception("Workflow not shared with user")],
        ):
            result = runner.invoke(
                cli,
                [
                    "share-remove",
                    "--json",
                    "-t",
                    reana_token,
                    "--workflow",
                    "test-workflow.1",
                    "--user",
                    "bob@example.org",
                    "--user",
                    "nobody@example.org",
                ],
            )
            assert result.exit_code == 1
            parsed = json.loads(result.output)
            assert parsed["unshared_with"] == ["bob@example.org"]
            assert len(parsed["errors"]) == 1
            assert "nobody@example.org" in parsed["errors"][0]


# ------------------------------
# share-status JSON output tests
# ------------------------------


def test_share_status_workflow_json_success():
    """Test share-status --json outputs a JSON array when workflow is shared."""
    status_code = 200
    response = {
        "shared_with": [
            {"user_email": "bob@example.org", "valid_until": "2025-12-31"},
            {"user_email": "alice@example.org", "valid_until": None},
        ]
    }
    env = {"REANA_SERVER_URL": "localhost"}
    mock_http_response = Mock()
    mock_http_response.status_code = status_code
    reana_token = "000000"
    runner = CliRunner(env=env)
    with runner.isolation():
        with patch(
            "reana_client.api.client.current_rs_api_client",
            make_mock_api_client("reana-server")(response, mock_http_response),
        ):
            result = runner.invoke(
                cli,
                [
                    "share-status",
                    "--json",
                    "-t",
                    reana_token,
                    "--workflow",
                    "test-workflow.1",
                ],
            )
            assert result.exit_code == 0
            parsed = json.loads(result.output)
            assert isinstance(parsed, list)
            assert len(parsed) == 2
            by_email = {row["user_email"]: row for row in parsed}
            assert by_email["bob@example.org"]["valid_until"] == "2025-12-31"
            assert by_email["alice@example.org"]["valid_until"] is None


def test_share_status_workflow_json_empty():
    """Test share-status --json outputs valid JSON when workflow is not shared."""
    status_code = 200
    response = {
        "message": "is not shared with anyone",
        "workflow_id": "string",
        "workflow_name": "string",
    }
    env = {"REANA_SERVER_URL": "localhost"}
    mock_http_response = Mock()
    mock_http_response.status_code = status_code
    reana_token = "000000"
    runner = CliRunner(env=env)
    with runner.isolation():
        with patch(
            "reana_client.api.client.current_rs_api_client",
            make_mock_api_client("reana-server")(response, mock_http_response),
        ):
            result = runner.invoke(
                cli,
                [
                    "share-status",
                    "--json",
                    "-t",
                    reana_token,
                    "--workflow",
                    "test-workflow.1",
                ],
            )
            assert result.exit_code == 0
            parsed = json.loads(result.output)
            assert parsed == []


def test_share_status_workflow_error_exits_nonzero():
    """Test share-status exits 1 when the API call fails."""
    env = {"REANA_SERVER_URL": "localhost"}
    reana_token = "000000"
    runner = CliRunner(env=env)
    with runner.isolation():
        with patch(
            "reana_client.api.client.get_workflow_sharing_status",
            side_effect=Exception("Workflow not found"),
        ):
            result = runner.invoke(
                cli,
                [
                    "share-status",
                    "-t",
                    reana_token,
                    "--workflow",
                    "nonexistent-workflow.1",
                ],
            )
            assert result.exit_code == 1


def test_share_add_workflow_text_error_exits_nonzero():
    """Test share-add exits 1 (text mode) when the API call fails."""
    env = {"REANA_SERVER_URL": "localhost"}
    reana_token = "000000"
    runner = CliRunner(env=env)
    with runner.isolation():
        with patch(
            "reana_client.api.client.share_workflow",
            side_effect=Exception("User not found"),
        ):
            result = runner.invoke(
                cli,
                [
                    "share-add",
                    "-t",
                    reana_token,
                    "--workflow",
                    "test-workflow.1",
                    "--user",
                    "nobody@example.org",
                ],
            )
            assert result.exit_code == 1
            assert "nobody@example.org" in result.output


def test_share_remove_workflow_text_error_exits_nonzero():
    """Test share-remove exits 1 (text mode) when the API call fails."""
    env = {"REANA_SERVER_URL": "localhost"}
    reana_token = "000000"
    runner = CliRunner(env=env)
    with runner.isolation():
        with patch(
            "reana_client.api.client.unshare_workflow",
            side_effect=Exception("Workflow not shared with user"),
        ):
            result = runner.invoke(
                cli,
                [
                    "share-remove",
                    "-t",
                    reana_token,
                    "--workflow",
                    "test-workflow.1",
                    "--user",
                    "nobody@example.org",
                ],
            )
            assert result.exit_code == 1
            assert "nobody@example.org" in result.output
