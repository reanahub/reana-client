# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2022 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
"""REANA client retention rules tests."""

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from reana_client.cli import cli


@patch("reana_client.cli.retention_rules.get_workflow_retention_rules")
def test_retention_rules_list(mock_get_workflow_retention_rules: MagicMock):
    """Test retention-rules-list command."""
    workflow_id = "123456"
    workflow_name = "workflow"
    access_token = "secret"
    pattern = "*.tmp"
    mock_get_workflow_retention_rules.return_value = {
        "workflow_id": workflow_id,
        "workflow_name": workflow_name,
        "retention_rules": [
            {
                "workspace_files": pattern,
                "status": "created",
                "apply_on": None,
                "retention_days": 42,
            },
        ],
    }

    runner = CliRunner(env={"REANA_SERVER_URL": "localhost"})
    result = runner.invoke(
        cli, ["retention-rules-list", "-w", workflow_name, "-t", access_token]
    )

    assert result.exit_code == 0
    assert pattern in result.output
    mock_get_workflow_retention_rules.assert_called_once_with(
        workflow_name, access_token
    )
