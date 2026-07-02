# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2026 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
"""REANA client configuration."""

reana_yaml_valid_file_names = ["reana.yaml", "reana.yml"]
"""REANA specification valid file names."""

ERROR_MESSAGES = {
    "missing_access_token": "Please provide your access token by using"
    " the -t/--access-token flag, or by setting the"
    " REANA_ACCESS_TOKEN environment variable."
}

JSON = "json"
"""Json output format."""

TIMECHECK = 5
"""Time between workflow status check."""

URL = "url"
"""Url output format."""

RUN_STATUSES = [
    "created",
    "running",
    "finished",
    "failed",
    "deleted",
    "stopped",
    "queued",
    "pending",
]
"""Available run statuses."""

PRINTER_COLOUR_SUCCESS = "green"
"""Default colour for success messages on terminal."""

PRINTER_COLOUR_WARNING = "yellow"
"""Default colour for warning messages on terminal."""

PRINTER_COLOUR_ERROR = "red"
"""Default colour for error messages on terminal."""

PRINTER_COLOUR_INFO = "cyan"
"""Default colour for info messages on terminal."""

JOB_STATUS_TO_MSG_COLOR = {
    "failed": "red",
    "finished": "green",
    "running": "bright_blue",
}

STD_OUTPUT_CHAR = "-"
"""Character used to refer to the standard output."""

CLI_LOGS_FOLLOW_MIN_INTERVAL = 1
"""Minimum interval between log requests in seconds."""

CLI_LOGS_FOLLOW_DEFAULT_INTERVAL = 10
"""Default interval between log requests in seconds."""

MAX_RUN_LABELS_SHOWN = 10
"""Maximum number of run labels to print in CLI output, extra labels are collapsed as '+N more'."""

CLI_WORKFLOWS_LIST_MAX_RESULTS = 1000
"""Max number of workflow runs to fetch in a single API call (used when resolving restarts)."""
