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
from unittest.mock import patch

from reana_commons.gherkin_parser.parser import AnalysisTestStatus, TestResult
from reana_commons.gherkin_parser.errors import FeatureFileError
from dataclasses import replace

passed_test = TestResult(
    scenario="scenario1",
    error_log=None,
    result=AnalysisTestStatus.passed,
    failed_testcase=None,
    feature="Run Duration",
    checked_at="2024-01-01T00:00:00.000000",
)

failed_test = TestResult(
    scenario="scenario2",
    error_log="Test designed to fail",
    result=AnalysisTestStatus.failed,
    failed_testcase="Scenario to fail",
    feature="Run Duration",
    checked_at="2024-01-01T00:00:00.000000",
)


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
    "reana_client.cli.test.get_workflow_status",
    return_value={"status": "running", "name": "myanalysis"},
)
def test_test_workflow_not_finished(mock_get_workflow_status):
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
    "reana_client.cli.test.get_workflow_status",
    return_value={"status": "deleted", "name": "myanalysis"},
)
def test_test_workflow_deleted(mock_get_workflow_status):
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
    "reana_client.cli.test.get_workflow_status",
    return_value={"status": "finished", "name": "myanalysis"},
)
@patch(
    "reana_client.cli.test.get_workflow_specification",
    return_value={"specification": {"inputs": {"directories": ["data"]}}},
)
def test_test_no_test_files(mock_get_workflow_status, mock_get_workflow_specification):
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
    "reana_client.cli.test.get_workflow_status",
    return_value={"status": "finished", "name": "myanalysis"},
)
@patch(
    "reana_client.cli.test.get_workflow_specification",
    return_value={"specification": {"inputs": {"directories": ["data"]}}},
)
def test_test_no_test_files_with_test_file_option(
    mock_get_workflow_status, mock_get_workflow_specification
):
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
        assert 'Testing file "test_analysis.feature"' in result.output


@patch(
    "reana_client.cli.test.get_workflow_status",
    return_value={"status": "finished", "name": "myanalysis"},
)
@patch(
    "reana_client.cli.test.get_workflow_specification",
    return_value={
        "specification": {
            "tests": {"files": ["test_analysis.feature", "test_analysis2.feature"]}
        }
    },
)
def test_test_multiple_test_files_with_test_file_option(
    mock_get_workflow_status, mock_get_workflow_specification
):
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
        assert 'Testing file "use_this.feature"' in result.output
        assert 'Testing file "test_analysis.feature"' not in result.output
        assert 'Testing file "test_analysis2.feature"' not in result.output


@patch(
    "reana_client.cli.test.get_workflow_status",
    return_value={"status": "finished", "name": "myanalysis"},
)
@patch(
    "reana_client.cli.test.get_workflow_specification",
    return_value={
        "specification": {"tests": {"files": ["use-me.feature", "me-too.feature"]}}
    },
)
@patch(
    "reana_client.cli.test.parse_and_run_tests",
    return_value=(
        "myanalysis",
        [passed_test],
    ),
)
def test_test_files_from_spec(
    mock_get_workflow_status, get_workflow_specification, mock_parse_and_run_tests
):
    """Test test command when test files are specified in reana.yml."""
    env = {"REANA_SERVER_URL": "localhost"}
    runner = CliRunner(env=env)
    with runner.isolation():
        result = runner.invoke(
            cli,
            ["test", "-w", "myanalysis", "-t", "000000"],
        )
        assert 'Testing file "use-me.feature"' in result.output
        assert 'Testing file "me-too.feature"' in result.output


@patch(
    "reana_client.cli.test.get_workflow_status",
    return_value={"status": "finished", "name": "myanalysis"},
)
@patch(
    "reana_client.cli.test.parse_and_run_tests",
    side_effect=FeatureFileError,
)
def test_test_parser_error(mock_get_workflow_status, mock_parse_and_run_tests):
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
    "reana_client.cli.test.get_workflow_status",
    return_value={"status": "finished", "name": "myanalysis"},
)
@patch(
    "reana_client.cli.test.parse_and_run_tests",
    side_effect=FileNotFoundError,
)
def test_test_feature_file_not_found(
    mock_get_workflow_status, mock_parse_and_run_tests
):
    """Test test command when a feature file is not found."""
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
    "reana_client.cli.test.get_workflow_status",
    return_value={"status": "finished", "name": "myanalysis"},
)
@patch(
    "reana_client.cli.test.parse_and_run_tests",
    return_value=(
        "myanalysis",
        [passed_test],
    ),
)
def test_test_multiple_test_files(mock_workflow_status, mock_parse_and_run_tests):
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
        assert 'Testing file "test_analysis.feature"' in result.output
        assert 'Testing file "test_analysis2.feature"' in result.output


@patch(
    "reana_client.cli.test.get_workflow_status",
    return_value={"status": "finished", "name": "myanalysis"},
)
@patch(
    "reana_client.cli.test.parse_and_run_tests",
    return_value=(
        "myanalysis",
        [passed_test, replace(passed_test, scenario="scenario2")],
    ),
)
def test_test_all_scenarios_pass(mock_workflow_status, mock_parse_and_run_tests):
    """Test test command when tests pass."""
    env = {"REANA_SERVER_URL": "localhost"}
    runner = CliRunner(env=env)
    with runner.isolated_filesystem():
        result = runner.invoke(
            cli,
            ["test", "-w", "myanalysis", "-n", "test_analysis.feature", "-t", "000000"],
        )
        assert "SUCCESS" in result.output and "ERROR" not in result.output
        assert result.exit_code == 0


@patch(
    "reana_client.cli.test.get_workflow_status",
    return_value={"status": "finished", "name": "myanalysis"},
)
@patch(
    "reana_client.cli.test.parse_and_run_tests",
    return_value=(
        "myanalysis",
        [replace(failed_test, scenario="scenario1"), failed_test],
    ),
)
def test_test_all_scenarios_fail(mock_workflow_status, mock_parse_and_run_tests):
    """Test test command when tests fail."""
    env = {"REANA_SERVER_URL": "localhost"}
    runner = CliRunner(env=env)
    with runner.isolation():
        result = runner.invoke(
            cli,
            ["test", "-w", "myanalysis", "-n", "test_analysis.feature", "-t", "000000"],
        )
        assert "ERROR" in result.output and "SUCCESS" not in result.output
        assert result.exit_code == 1


@patch(
    "reana_client.cli.test.get_workflow_status",
    return_value={"status": "finished", "name": "myanalysis"},
)
@patch(
    "reana_client.cli.test.parse_and_run_tests",
    return_value=(
        "myanalysis",
        [passed_test, failed_test],
    ),
)
def test_test_some_scenarios_pass(mock_workflow_status, mock_parse_and_run_tests):
    """Test test command when some tests pass and some fail."""
    env = {"REANA_SERVER_URL": "localhost"}
    runner = CliRunner(env=env)
    with runner.isolated_filesystem():
        result = runner.invoke(
            cli,
            ["test", "-w", "myanalysis", "-n", "test_analysis.feature", "-t", "000000"],
        )
        assert "SUCCESS" in result.output and "ERROR" in result.output
        assert result.exit_code == 1
