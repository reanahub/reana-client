# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2024 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""REANA client test tests."""

from click.testing import CliRunner
from reana_client.cli import cli
from unittest.mock import Mock, patch

from pytest_reana.test_utils import make_mock_api_client
from reana_commons.gherkin_parser.parser import AnalysisTestStatus
from reana_commons.gherkin_parser.errors import FeatureFileError


def test_test_workflow_not_found():
    """Test test command when workflow is not found."""
    env = {"REANA_SERVER_URL": "localhost"}
    runner = CliRunner(env=env)
    with runner.isolated_filesystem():
        result = runner.invoke(
            cli,
            [
                "test",
                "-w",
                "myanalysis",
                "-n",
                "test_analysis.feature",
                "-t",
                "000000",
            ],
        )
    assert "Could not find workflow ``myanalysis``." in result.output
    assert result.exit_code == 1


@patch(
    "reana_client.api.client.current_rs_api_client",
    new_callable=lambda: make_mock_api_client("reana-server")(
        {
            "status": "running",
            "id": "31415",
        },
        Mock(status_code=200),
    ),
)
def test_test_workflow_not_finished(mock_api_client):
    """Test test command when workflow is not finished."""

    env = {"REANA_SERVER_URL": "localhost"}
    runner = CliRunner(env=env)
    with runner.isolation():
        result = runner.invoke(
            cli,
            [
                "test",
                "-w",
                "myanalysis",
                "-n",
                "test_analysis.feature",
                "-t",
                "000000",
            ],
        )
        assert (
            "``myanalysis`` is running. It must be finished to run tests."
            in result.output
        )
        assert result.exit_code == 1


@patch(
    "reana_client.api.client.current_rs_api_client",
    new_callable=lambda: make_mock_api_client("reana-server")(
        {"status": "deleted", "id": "31415"}, Mock(status_code=200)
    ),
)
def test_test_workflow_deleted(mock_api_client):
    """Test test command when workflow is deleted."""
    env = {"REANA_SERVER_URL": "localhost"}
    runner = CliRunner(env=env)
    with runner.isolation():
        result = runner.invoke(
            cli,
            ["test", "-w", "myanalysis", "-n", "test_analysis.feature", "-t", "000000"],
        )
        assert (
            "``myanalysis`` is deleted. It must be finished to run tests."
            in result.output
        )
        assert result.exit_code == 1


@patch(
    "reana_client.api.client.current_rs_api_client",
    new_callable=lambda: make_mock_api_client("reana-server")(
        {"status": "finished", "id": "1111"}, Mock(status_code=200)
    ),
)
def test_test_no_test_files(mock_api_client):
    """Test test command when no test files are specified."""
    env = {"REANA_SERVER_URL": "localhost"}
    runner = CliRunner(env=env)
    with runner.isolation():
        result = runner.invoke(cli, ["test", "-w", "myanalysis", "-t", "000000"])
        assert (
            "No test files specified in reana.yaml and no -n option provided."
            in result.output
        )
        assert result.exit_code == 1


@patch(
    "reana_client.api.client.current_rs_api_client",
    new_callable=lambda: make_mock_api_client("reana-server")(
        {"status": "finished", "id": "496"}, Mock(status_code=200)
    ),
)
def test_test_no_test_files_with_test_file_option(mock_api_client):
    """Test test command when no test files are specified in reana.yml and when the test file option is provided."""
    env = {"REANA_SERVER_URL": "localhost"}
    runner = CliRunner(env=env)
    with runner.isolation():
        result = runner.invoke(
            cli,
            [
                "test",
                "-w",
                "myanalysis",
                "-t",
                "000000",
                "-n",
                "test_analysis.feature",
            ],
        )
        assert "Using test file test_analysis.feature" in result.output


@patch(
    "reana_client.api.client.current_rs_api_client",
    new_callable=lambda: make_mock_api_client("reana-server")(
        {
            "status": "finished",
            "id": "496",
            "specification": {"tests": {"files": ["test1.feature", "test2.feature"]}},
        },
        Mock(status_code=200),
    ),
)
def test_test_multiple_test_files_with_test_file_option(mock_api_client):
    """Test test command when multiple test files are specified in reana.yml and test file option is provided.
    In this case, the test-file option should be used instead of the test files specified in reana.yml.
    """
    env = {"REANA_SERVER_URL": "localhost"}
    runner = CliRunner(env=env)
    with runner.isolation():
        result = runner.invoke(
            cli,
            [
                "test",
                "-w",
                "myanalysis",
                "-t",
                "000000",
                "-n",
                "use_this.feature",
            ],
        )
        assert "Using test file use_this.feature" in result.output
        assert "Using test file test_analysis.feature" not in result.output
        assert "Using test file test_analysis2.feature" not in result.output


@patch(
    "reana_client.api.client.current_rs_api_client",
    new_callable=lambda: make_mock_api_client("reana-server")(
        {
            "status": "finished",
            "id": "496",
            "specification": {"tests": {"files": ["use-me.feature", "me-too.feature"]}},
        },
        Mock(status_code=200),
    ),
)
@patch(
    "reana_client.cli.test.parse_and_run_tests",
    return_value=(
        "myanalysis",
        [
            {"scenario": "scenario1", "result": AnalysisTestStatus.passed},
        ],
    ),
)
def test_test_files_from_spec(mock_api_client, mock_parse_and_run_tests):
    """Test test command when test files are specified in reana.yml."""
    env = {"REANA_SERVER_URL": "localhost"}
    runner = CliRunner(env=env)
    with runner.isolation():
        result = runner.invoke(
            cli,
            ["test", "-w", "myanalysis", "-t", "000000"],
        )
        assert "Using test file use-me.feature" in result.output
        assert "Using test file me-too.feature" in result.output


@patch(
    "reana_client.api.client.current_rs_api_client",
    new_callable=lambda: make_mock_api_client("reana-server")(
        {"status": "finished", "id": "28"}, Mock(status_code=200)
    ),
)
@patch(
    "reana_client.cli.test.parse_and_run_tests",
    side_effect=FeatureFileError,
)
def test_test_parser_error(mock_api_client, mock_parse_and_run_tests):
    """Test test command when parser error occurs."""
    env = {"REANA_SERVER_URL": "localhost"}
    runner = CliRunner(env=env)
    with runner.isolation():
        result = runner.invoke(
            cli,
            [
                "test",
                "-w",
                "myanalysis",
                "-t",
                "000000",
                "-n",
                "test_analysis.feature",
            ],
        )
        assert "Error parsing feature file test_analysis.feature" in result.output
        assert result.exit_code == 1


@patch(
    "reana_client.api.client.current_rs_api_client",
    new_callable=lambda: make_mock_api_client("reana-server")(
        {"status": "finished", "id": "28"}, Mock(status_code=200)
    ),
)
@patch(
    "reana_client.cli.test.parse_and_run_tests",
    side_effect=FileNotFoundError,
)
def test_test_test_file_not_found(mock_api_client, mock_parse_and_run_tests):
    """Test test command when parser error occurs."""
    env = {"REANA_SERVER_URL": "localhost"}
    runner = CliRunner(env=env)
    with runner.isolation():
        result = runner.invoke(
            cli,
            [
                "test",
                "-w",
                "myanalysis",
                "-t",
                "000000",
                "-n",
                "test_analysis.feature",
            ],
        )
        assert "Test file test_analysis.feature not found." in result.output
        assert result.exit_code == 1


@patch(
    "reana_client.api.client.current_rs_api_client",
    new_callable=lambda: make_mock_api_client("reana-server")(
        {"status": "finished", "id": "1618"}, Mock(status_code=200)
    ),
)
@patch(
    "reana_client.cli.test.parse_and_run_tests",
    return_value=(
        "myanalysis",
        [{"scenario": "scenario1", "result": AnalysisTestStatus.passed}],
    ),
)
def test_test_multiple_test_files(mock_api_client, mock_parse_and_run_tests):
    """Test test command when multiple test files are specified."""
    env = {"REANA_SERVER_URL": "localhost"}
    runner = CliRunner(env=env)
    with runner.isolation():
        result = runner.invoke(
            cli,
            [
                "test",
                "-w",
                "myanalysis",
                "-t",
                "000000",
                "-n",
                "test_analysis.feature",
                "-n",
                "test_analysis2.feature",
            ],
        )
        assert "Using test file test_analysis.feature" in result.output
        assert "Using test file test_analysis2.feature" in result.output


@patch(
    "reana_client.api.client.current_rs_api_client",
    new_callable=lambda: make_mock_api_client("reana-server")(
        {"status": "finished", "id": "1618"}, Mock(status_code=200)
    ),
)
@patch(
    "reana_client.cli.test.parse_and_run_tests",
    return_value=(
        "myanalysis",
        [
            {"scenario": "scenario1", "result": AnalysisTestStatus.passed},
            {"scenario": "scenario2", "result": AnalysisTestStatus.passed},
        ],
    ),
)
def test_test_all_scenarios_pass(mock_api_client, mock_parse_and_run_tests):
    """Test test command when tests pass."""
    env = {"REANA_SERVER_URL": "localhost"}
    runner = CliRunner(env=env)
    with runner.isolated_filesystem():
        result = runner.invoke(
            cli,
            ["test", "-w", "myanalysis", "-n", "test_analysis.feature", "-t", "000000"],
        )
        assert "passed" in result.output and "failed" not in result.output
        assert result.exit_code == 0


@patch(
    "reana_client.api.client.current_rs_api_client",
    new_callable=lambda: make_mock_api_client("reana-server")(
        {"status": "finished", "id": "2998"}, Mock(status_code=200)
    ),
)
@patch(
    "reana_client.cli.test.parse_and_run_tests",
    return_value=(
        "myanalysis",
        [
            {"scenario": "scenario1", "result": AnalysisTestStatus.failed},
            {"scenario": "scenario2", "result": AnalysisTestStatus.failed},
        ],
    ),
)
def test_test_all_scenarios_fail(mock_api_client, mock_parse_and_run_tests):
    """Test test command when tests fail."""
    env = {"REANA_SERVER_URL": "localhost"}
    runner = CliRunner(env=env)
    with runner.isolation():
        result = runner.invoke(
            cli,
            ["test", "-w", "myanalysis", "-n", "test_analysis.feature", "-t", "000000"],
        )
        assert "failed" in result.output and "passed" not in result.output
        assert result.exit_code == 0


@patch(
    "reana_client.api.client.current_rs_api_client",
    new_callable=lambda: make_mock_api_client("reana-server")(
        {"status": "finished", "id": "8128"}, Mock(status_code=200)
    ),
)
@patch(
    "reana_client.cli.test.parse_and_run_tests",
    return_value=(
        "myanalysis",
        [
            {"scenario": "scenario1", "result": AnalysisTestStatus.passed},
            {"scenario": "scenario2", "result": AnalysisTestStatus.failed},
        ],
    ),
)
def test_test_some_scenarios_pass(mock_api_client, mock_parse_and_run_tests):
    """Test test command when some tests pass and some fail."""
    env = {"REANA_SERVER_URL": "localhost"}
    runner = CliRunner(env=env)
    with runner.isolated_filesystem():
        result = runner.invoke(
            cli,
            ["test", "-w", "myanalysis", "-n", "test_analysis.feature", "-t", "000000"],
        )
        assert "passed" in result.output and "failed" in result.output
        assert result.exit_code == 0
