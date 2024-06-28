# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2024 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
"""REANA client test commands."""

import sys
import click
import logging
import traceback
import time
from reana_client.cli.utils import add_access_token_options, check_connection
from reana_commons.gherkin_parser.parser import (
    parse_and_run_tests,
    AnalysisTestStatus,
)
from reana_commons.gherkin_parser.data_fetcher import DataFetcherBase
from reana_commons.gherkin_parser.errors import FeatureFileError
from reana_client.printer import display_message
from reana_client.api.client import (
    list_files,
    get_workflow_disk_usage,
    get_workflow_logs,
    get_workflow_status,
    get_workflow_specification,
    download_file,
)
from reana_client.cli.utils import add_workflow_option


class DataFetcherClient(DataFetcherBase):
    """Implementation of the DataFetcherBase using reana_client.api.client methods."""

    def __init__(self, access_token):
        """Initialize DataFetcherClient with access token."""
        self.access_token = access_token

    def list_files(self, workflow, file_name=None, page=None, size=None, search=None):
        """Return the list of files for a given workflow workspace."""
        return list_files(workflow, self.access_token, file_name, page, size, search)

    def get_workflow_disk_usage(self, workflow, parameters):
        """Display disk usage workflow."""
        return get_workflow_disk_usage(workflow, parameters, self.access_token)

    def get_workflow_logs(self, workflow, steps=None, page=None, size=None):
        """Get logs from a workflow engine, use existing API function."""
        return get_workflow_logs(workflow, self.access_token, steps, page, size)

    def get_workflow_status(self, workflow):
        """Get of a previously created workflow."""
        return get_workflow_status(workflow, self.access_token)

    def get_workflow_specification(self, workflow):
        """Get specification of previously created workflow."""
        return get_workflow_specification(workflow, self.access_token)

    def download_file(self, workflow, file_path):
        """Download the requested file if it exists."""
        return download_file(workflow, file_path, self.access_token)


@click.group(help="Workflow run test commands")
def test_group():
    """Workflow run test commands."""


@test_group.command("test")
@click.option(
    "-n",
    "--test-files",
    multiple=True,
    default=None,
    help="Gherkin file for testing properties of a workflow execution. Overrides files in reana.yaml if provided.",
)
@click.pass_context
@add_access_token_options
@check_connection
@add_workflow_option
def test(ctx, workflow, test_files, access_token):
    r"""
    Test workflow execution, based on a given Gherkin file.

    Gherkin files can be specified in the reana specification file (reana.yaml),
    or by using the ``-n`` option.

    The ``test`` command allows for testing of a workflow execution,
    by assessing whether it meets certain properties specified in a
    chosen gherkin file.

    Example:
        $ reana-client test -w myanalysis -n test_analysis.feature
        $ reana-client test -w myanalysis
        $ reana-client test -w myanalysis -n test1.feature -n test2.feature
    """
    start_time = time.time()
    try:
        workflow_status = get_workflow_status(
            workflow=workflow, access_token=access_token
        )
        status = workflow_status["status"]
        workflow_name = workflow_status["name"]
    except Exception as e:
        logging.debug(traceback.format_exc())
        logging.debug(str(e))
        display_message(f"Could not find workflow ``{workflow}``.", msg_type="error")
        sys.exit(1)

    if status != "finished":
        display_message(
            f"``{workflow}`` is {status}. It must be finished to run tests.",
            msg_type="error",
        )
        sys.exit(1)

    if not test_files:
        reana_specification = get_workflow_specification(workflow, access_token)
        try:
            test_files = reana_specification["specification"]["tests"]["files"]
        except KeyError as e:
            logging.debug(traceback.format_exc())
            logging.debug(str(e))
            display_message(
                "No test files specified in reana.yaml and no -n option provided.",
                msg_type="error",
            )
            sys.exit(1)

    passed = 0
    failed = 0
    data_fetcher = DataFetcherClient(access_token)
    for test_file in test_files:
        click.echo("\n", nl=False)
        display_message(f'Testing file "{test_file}"...', msg_type="info")
        try:
            results = parse_and_run_tests(test_file, workflow_name, data_fetcher)
        except FileNotFoundError as e:
            logging.debug(traceback.format_exc())
            logging.debug(str(e))
            display_message(f"Test file {test_file} not found.", msg_type="error")
            sys.exit(1)
        except FeatureFileError as e:
            logging.debug(traceback.format_exc())
            logging.debug(str(e))
            display_message(
                f"Error parsing feature file {test_file}: {e}", msg_type="error"
            )
            sys.exit(1)

        for scenario in results[1]:
            if scenario.result == AnalysisTestStatus.failed:
                display_message(
                    f'Scenario "{scenario.scenario}"', msg_type="error", indented=True
                )
                failed += 1
            else:
                display_message(
                    f'Scenario "{scenario.scenario}"', msg_type="success", indented=True
                )
                passed += 1

    end_time = time.time()
    duration = round(end_time - start_time)
    click.echo(f"\n{passed} passed, {failed} failed in {duration}s")
    if failed > 0:
        sys.exit(1)
