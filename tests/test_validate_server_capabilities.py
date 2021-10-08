# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2021 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""REANA client validate server capabilities tests."""

import pytest
from click.testing import CliRunner
from mock import Mock, patch
from pytest_reana.test_utils import make_mock_api_client

from reana_client.cli import cli
from reana_client.config import ERROR_MESSAGES


@pytest.mark.parametrize(
    "with_workspace, cli_args, expected_output, exit_code, available_workspaces",
    [
        (
            False,
            ["validate"],
            "appear valid",
            0,
            ["/var/reana", "/myexternaldisk/reana"],
        ),
        (
            False,
            ["validate", "--server-capabilities"],
            ERROR_MESSAGES["missing_access_token"],
            1,
            ["/var/reana", "/myexternaldisk/reana"],
        ),
        (
            False,
            ["validate", "-t", "00000", "--server-capabilities"],
            "WARNING: Workspace not found in REANA specification",
            0,
            ["/var/reana", "/myexternaldisk/reana"],
        ),
        (
            True,
            ["validate", "-t", "00000", "--server-capabilities"],
            "Workflow workspace appears valid.",
            0,
            ["/var/reana", "/myexternaldisk/reana"],
        ),
        (
            True,
            ["validate", "-t", "00000", "--server-capabilities"],
            'Desired workspace "/var/reana" not valid.',
            1,
            ["/foo/reana", "/bar/reana"],
        ),
    ],
)
def test_validate_workspaces(
    create_yaml_workflow_schema,
    create_yaml_workflow_schema_with_workspace,
    with_workspace,
    cli_args,
    expected_output,
    exit_code,
    available_workspaces,
):
    """Test multiple combinations of validating workflows workspaces."""
    env = {"REANA_SERVER_URL": "http://localhost"}
    runner = CliRunner(env=env)
    mock_http_response, mock_response = Mock(), Mock()
    mock_http_response.status_code = 200
    mock_response = {
        "default_workspace": {"value": available_workspaces[0]},
        "workspaces_available": {"value": available_workspaces},
    }
    with runner.isolation():
        with runner.isolated_filesystem():
            with open("reana.yaml", "w") as reana_schema:
                reana_schema.write(
                    create_yaml_workflow_schema_with_workspace
                    if with_workspace
                    else create_yaml_workflow_schema
                )
            with patch(
                "reana_client.api.client.current_rs_api_client",
                make_mock_api_client("reana-server")(mock_response, mock_http_response),
            ):
                result = runner.invoke(cli, cli_args)
                assert result.exit_code == exit_code
                assert expected_output in result.output
