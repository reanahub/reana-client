# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2022 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
"""REANA client retention-rules related commands."""

import logging
import sys
from typing import Optional, Tuple

import click

from reana_client.api.client import get_workflow_retention_rules
from reana_client.cli.utils import (
    add_access_token_options,
    add_workflow_option,
    check_connection,
    display_formatted_output,
)
from reana_client.printer import display_message


@click.group(help="Workspace file retention commands")
def retention_rules_group():
    """Workspace file retention commands."""
    pass


@retention_rules_group.command()
@add_workflow_option
@add_access_token_options
@check_connection
@click.option(
    "--format",
    "_format",
    multiple=True,
    help="Format output according to column titles or column values. "
    "Use `<columm_name>=<column_value>` format. "
    "E.g. display pattern and status of active retention rules "
    "`--format workspace_files,status=active`.",
)
@click.option(
    "--json",
    "output_format",
    flag_value="json",
    default=None,
    help="Get output in JSON format.",
)
def retention_rules_list(
    access_token: str, workflow: str, _format: Tuple[str], output_format: Optional[str]
) -> None:  # noqa: D301
    """List the retention rules for a workflow.

    Example:\n
    \t $ reana-client retention-rules-list -w myanalysis.42
    """
    try:
        rules = get_workflow_retention_rules(workflow, access_token).get(
            "retention_rules", []
        )
    except Exception as e:
        logging.debug(e, exc_info=True)
        display_message(str(e), msg_type="error")
        sys.exit(1)

    sorted_rules = sorted(rules, key=lambda rule: rule["retention_days"])

    headers = ["workspace_files", "retention_days", "apply_on", "status"]
    rows = [[rule[h] or "-" for h in headers] for rule in sorted_rules]
    display_formatted_output(rows, headers, _format, output_format)
