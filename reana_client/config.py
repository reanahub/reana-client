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
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Union
from urllib.parse import urlparse

import urllib3

reana_yaml_valid_file_names = ["reana.yaml", "reana.yml"]
"""REANA specification valid file names."""

CA_CERTS_ENV = "REANA_SERVER_CA_CERTS"
"""Environment variable pointing to a CA bundle (PEM) to trust."""

TLS_VERIFY_ENV = "REANA_SERVER_TLS_VERIFY"
"""Retired verification variable, retained only for migration diagnostics."""

_LOGGER = logging.getLogger(__name__)
_tls_warning_emitted = False


_connection = ContextVar("reana_connection", default=None)

NO_SERVER = (
    "No REANA server is configured. Run `reana-client login --server "
    "https://your-reana-server` using the URL from your REANA administrator."
)


def check_retired_environment():
    """Reject stale connection exports rather than silently changing destination."""
    names = [name for name in ("REANA_SERVER_URL", TLS_VERIFY_ENV) if os.getenv(name)]
    if names:
        raise ValueError(
            " and ".join(names) + " are no longer client inputs. "
            "Unset them, then run `reana-client login --server https://your-reana-server`. "
            "For self-signed development HTTPS, add --no-tls-verify."
        )


@contextmanager
def connection_scope(server_url=None, verify=None, source=None):
    """Bind destination and TLS policy for one invocation, including notebook links."""
    token = _connection.set(
        {
            "server": server_url,
            "verify": verify,
            "source": source,
            "policies": {},
            "warned": set(),
        }
    )
    try:
        yield
    finally:
        _connection.reset(token)


def selected_server():
    """Return the destination already bound to this invocation, if any."""
    state = _connection.get()
    return state.get("server") if state else None


def bind_server(server_url, source):
    """Remember the selected destination without changing the saved selection."""
    state = _connection.get()
    if state is not None and not state["server"]:
        state.update(server=server_url, source=source)
    return server_url


def server_description(server_url):
    """Describe the destination and where it was selected."""
    state = _connection.get()
    source = state.get("source") if state and state["server"] == server_url else None
    source = source or "saved login"
    return f"{server_url} (from {source})"


def requested_tls_verify(server_url):
    """Return an explicit login choice, which may be saved only after success."""
    state = _connection.get()
    return state["verify"] if state and state["server"] == server_url else None


def tls_verify(server_url=None, warn=True) -> Union[bool, str]:
    """Resolve the effective per-server policy, with CA trust taking precedence."""
    from reana_client.auth.storage import get_active_server, get_server_entry

    check_retired_environment()
    server_url = server_url or get_active_server()
    state = _connection.get()
    policies = state["policies"] if state else {}
    if server_url not in policies:
        explicit = requested_tls_verify(server_url)
        ca_certs = os.getenv(CA_CERTS_ENV)
        if explicit is False and ca_certs:
            raise ValueError(
                "--no-tls-verify conflicts with REANA_SERVER_CA_CERTS. "
                "Unset the CA bundle override first."
            )
        if ca_certs:
            verify = True
        elif explicit is not None:
            verify = explicit
        else:
            entry = get_server_entry(server_url) if server_url else {}
            settings = entry.get("tls", {})
            if not isinstance(settings, dict) or not isinstance(
                settings.get("verify", True), bool
            ):
                raise ValueError(
                    f"Invalid saved TLS verification setting for {server_url}."
                )
            verify = settings.get("verify", True)
        policies[server_url] = ca_certs or verify
    policy = policies[server_url]
    if warn and policy is False:
        global _tls_warning_emitted
        warned = state["warned"] if state else set()
        if server_url not in warned and (state is not None or not _tls_warning_emitted):
            _LOGGER.warning(
                "TLS certificate verification is disabled for %s.", server_url
            )
            warned.add(server_url)
            _tls_warning_emitted = True
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    return policy


def tls_status(server_url=None):
    """Describe effective verification, including any CA bundle override."""
    policy = tls_verify(server_url, warn=False)
    return "disabled" if policy is False else "enabled"


def tls_verify_strict() -> Union[bool, str]:
    """Verify other HTTPS origins, retaining an explicit CA trust bundle."""
    check_retired_environment()
    ca_certs = os.getenv(CA_CERTS_ENV)
    if ca_certs:
        return ca_certs
    return True


def same_https_origin(server_url: str, endpoint: str) -> bool:
    """Compare HTTPS hosts and effective ports without trusting DNS aliases."""
    try:
        server = urlparse(server_url)
        target = urlparse(endpoint)
        server_port = server.port if server.port is not None else 443
        target_port = target.port if target.port is not None else 443
        return (
            server.scheme == target.scheme == "https"
            and bool(server.hostname)
            and server.hostname == target.hostname
            and server.username is None
            and target.username is None
            and server_port == target_port
            and server_port > 0
        )
    except ValueError:
        return False


def tls_verify_for_url(server_url: str, endpoint: str) -> Union[bool, str]:
    """Apply server TLS settings only to endpoints on its HTTPS origin.

    Bundled Keycloak shares the REANA ingress certificate and origin, even
    though its endpoints have a different path. Other identity providers
    keep certificate verification enabled. Compare the actual endpoint, not
    its advertised issuer, and never infer trust from DNS or IP aliases.
    """
    return (
        tls_verify(server_url)
        if same_https_origin(server_url, endpoint)
        else tls_verify_strict()
    )


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
