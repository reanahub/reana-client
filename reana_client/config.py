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
from urllib.parse import urlparse

import urllib3

reana_yaml_valid_file_names = ["reana.yaml", "reana.yml"]
"""REANA specification valid file names."""

CA_CERTS_ENV = "REANA_SERVER_CA_CERTS"
"""Environment variable pointing to a CA bundle (PEM) to trust."""

TLS_VERIFY_ENV = "REANA_SERVER_TLS_VERIFY"
"""Environment variable controlling REANA server certificate verification."""

_TLS_VERIFY_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_TLS_VERIFY_FALSE_VALUES = frozenset({"0", "false", "no", "off"})
_LOGGER = logging.getLogger(__name__)
_tls_warning_emitted = False


def tls_verify() -> Union[bool, str]:
    """Return the ``verify`` value used for REANA server HTTP requests.

    TLS verification is enabled by default. For local deployments that use
    self-signed certificates it can be adjusted through environment variables:

    * ``REANA_SERVER_CA_CERTS``: path to a CA bundle (PEM) to trust, e.g. the
      certificate of a local REANA deployment. Verification stays enabled.
    * ``REANA_SERVER_TLS_VERIFY``: ``1``/``true``/``yes``/``on`` enable
      verification; ``0``/``false``/``no``/``off`` disable it for REANA server
      requests, including identity-provider endpoints on the same HTTPS
      hostname and port (local testing). Values are case-insensitive and ignore
      surrounding whitespace. Unset or empty values enable verification;
      other values raise ``ValueError``.

    ``REANA_SERVER_CA_CERTS`` takes precedence over ``REANA_SERVER_TLS_VERIFY``.
    When neither is set the standard ``REQUESTS_CA_BUNDLE`` environment
    variable is still honoured by ``requests``.
    """
    ca_certs = os.getenv(CA_CERTS_ENV)
    if ca_certs:
        return ca_certs
    raw = os.getenv(TLS_VERIFY_ENV, "").strip()
    value = raw.lower()
    if not value or value in _TLS_VERIFY_TRUE_VALUES:
        return True
    if value not in _TLS_VERIFY_FALSE_VALUES:
        raise ValueError(f"Invalid {TLS_VERIFY_ENV} value {raw!r}.")
    global _tls_warning_emitted
    if not _tls_warning_emitted:
        _LOGGER.warning(
            "REANA server TLS certificate verification is disabled by %s.",
            TLS_VERIFY_ENV,
        )
        _tls_warning_emitted = True
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    return False


def tls_verify_strict() -> Union[bool, str]:
    """Return the ``verify`` value used for requests to other HTTPS origins.

    Unlike :func:`tls_verify`, ``REANA_SERVER_TLS_VERIFY`` is not honoured
    here: it only controls verification of the REANA server's HTTPS origin.
    ``REANA_SERVER_CA_CERTS`` still applies, since a custom CA bundle is an
    explicit trust anchor, not a bypass, and a self-hosted deployment may
    reasonably use the same internal CA for both the REANA server and its
    issuer.
    """
    ca_certs = os.getenv(CA_CERTS_ENV)
    if ca_certs:
        return ca_certs
    return True


def tls_verify_for_url(server_url: str, endpoint: str) -> Union[bool, str]:
    """Apply server TLS settings only to endpoints on its HTTPS origin.

    Bundled Keycloak shares the REANA ingress certificate and origin, even
    though its endpoints have a different path. Other identity providers
    keep certificate verification enabled. Compare the actual endpoint, not
    its advertised issuer, and never infer trust from DNS or IP aliases.
    """
    try:
        server = urlparse(server_url)
        target = urlparse(endpoint)
        server_port = server.port if server.port is not None else 443
        target_port = target.port if target.port is not None else 443
        same_origin = (
            server.scheme == target.scheme == "https"
            and bool(server.hostname)
            and server.hostname == target.hostname
            and server.username is None
            and target.username is None
            and server_port == target_port
            and server_port > 0
        )
    except ValueError:
        same_origin = False
    return tls_verify() if same_origin else tls_verify_strict()


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
