# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2026 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
"""REANA client configuration."""

import os
import logging
from typing import Union

import urllib3

reana_yaml_valid_file_names = ["reana.yaml", "reana.yml"]
"""REANA specification valid file names."""

CA_CERTS_ENV = "REANA_SERVER_CA_CERTS"
"""Environment variable pointing to a CA bundle (PEM) to trust."""

INSECURE_ENV = "REANA_INSECURE"
"""Environment variable to disable TLS verification (local testing only)."""

_INSECURE_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_LOGGER = logging.getLogger(__name__)
_insecure_warning_emitted = False


def tls_verify() -> Union[bool, str]:
    """Return the ``verify`` value used for REANA server HTTP requests.

    TLS verification is enabled by default. For local deployments that use
    self-signed certificates it can be adjusted through environment variables:

    * ``REANA_SERVER_CA_CERTS``: path to a CA bundle (PEM) to trust, e.g. the
      certificate of a local REANA deployment. Verification stays enabled.
    * ``REANA_INSECURE`` (``true``/``1``/``yes``/``on``): disable verification
      altogether. Intended for local testing only, never for production.

    ``REANA_SERVER_CA_CERTS`` takes precedence over ``REANA_INSECURE``. When
    neither is set the standard ``REQUESTS_CA_BUNDLE`` environment variable is
    still honoured by ``requests``.
    """
    ca_certs = os.getenv(CA_CERTS_ENV)
    if ca_certs:
        return ca_certs
    if os.getenv(INSECURE_ENV, "").strip().lower() in _INSECURE_TRUE_VALUES:
        global _insecure_warning_emitted
        if not _insecure_warning_emitted:
            _LOGGER.warning(
                "TLS certificate verification is disabled by %s.", INSECURE_ENV
            )
            _insecure_warning_emitted = True
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        return False
    return True


ERROR_MESSAGES = {
    "missing_access_token": (
        "Please run `reana-client login` to authenticate, or provide an access "
        "token using -t/--access-token or the REANA_ACCESS_TOKEN environment "
        "variable."
    )
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
