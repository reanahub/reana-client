# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2026 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""REANA client quota CLI tests."""

import json

from click.testing import CliRunner
from mock import patch

from reana_client.cli import cli


def _build_quota_response(quota_period_months=3, quota_period_start_at=None):
    """Return a dummy quota payload."""
    return {
        "cpu": {
            "usage": {"raw": 30, "human_readable": "30s"},
            "limit": {"raw": 1000, "human_readable": "16m 40s"},
            "health": "healthy",
            "quota_period_months": quota_period_months,
            "quota_period_start_at": quota_period_start_at,
        },
        "disk": {
            "usage": {"raw": 150, "human_readable": "150 Bytes"},
            "limit": {"raw": 0, "human_readable": "0 Bytes"},
            "health": None,
        },
    }


def test_info_displays_cpu_quota_period_details():
    """Test info surfaces the active CPU quota period."""
    env = {"REANA_SERVER_URL": "localhost"}
    runner = CliRunner(env=env)
    info_response = {
        "compute_backends": {
            "title": "List of supported compute backends",
            "value": ["kubernetes"],
        }
    }
    quota = _build_quota_response(
        quota_period_start_at="2026-06-04T00:00:00Z",
    )

    with patch("reana_client.api.client.info", return_value=info_response), patch(
        "reana_client.api.client.get_user_quota", return_value=quota
    ):
        result = runner.invoke(cli, ["info", "-t", "000000"])

    assert result.exit_code == 0
    assert "CPU quota period in months: 3" in result.output
    assert "Current CPU quota period start: 2026-06-04" in result.output
    assert "Current CPU quota period end: 2026-09-04" in result.output
def test_info_displays_disabled_cpu_quota_period_as_zero():
    """Test info shows disabled periodic CPU accounting as zero months."""
    env = {"REANA_SERVER_URL": "localhost"}
    runner = CliRunner(env=env)
    info_response = {
        "compute_backends": {
            "title": "List of supported compute backends",
            "value": ["kubernetes"],
        }
    }
    quota = _build_quota_response(
        quota_period_months=None,
        quota_period_start_at=None,
    )

    with patch("reana_client.api.client.info", return_value=info_response), patch(
        "reana_client.api.client.get_user_quota", return_value=quota
    ):
        result = runner.invoke(cli, ["info", "-t", "000000"])

    assert result.exit_code == 0
    assert "CPU quota period in months: 0" in result.output
    assert "Current CPU quota period start:" not in result.output
    assert "Current CPU quota period end:" not in result.output


def test_info_json_includes_cpu_quota_period_details():
    """Test info JSON output includes CPU quota period metadata."""
    env = {"REANA_SERVER_URL": "localhost"}
    runner = CliRunner(env=env)
    info_response = {
        "compute_backends": {
            "title": "List of supported compute backends",
            "value": ["kubernetes"],
        }
    }
    quota = _build_quota_response(
        quota_period_start_at="2026-06-04T00:00:00Z",
    )

    with patch("reana_client.api.client.info", return_value=info_response), patch(
        "reana_client.api.client.get_user_quota", return_value=quota
    ):
        result = runner.invoke(cli, ["info", "-t", "000000", "--json"])

    assert result.exit_code == 0
    response = json.loads(result.output)
    assert response["cpu_quota_period_months"]["value"] == 3
    assert response["current_cpu_quota_period_start"]["value"] == "2026-06-04"
    assert response["current_cpu_quota_period_end"]["value"] == "2026-09-04"
