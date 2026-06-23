# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2017, 2018, 2019, 2020, 2021, 2022, 2026 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
"""REANA client configuration commands."""

import json
import logging
import sys
import traceback

import click
from reana_client.auth.oidc import (
    AuthenticationError,
    login_with_device_flow,
    login_with_loopback,
    logout as oidc_logout,
)
from reana_client.auth.storage import get_active_server, normalize_server_url
from reana_client.cli.utils import add_access_token_options, check_connection
from reana_client.config import JSON
from reana_client.printer import display_message
from reana_client.utils import build_cpu_quota_period_info
from reana_client.version import __version__


@click.group(help="Configuration commands")
def configuration_group():
    """Configuration commands."""
    pass


@configuration_group.command("login")
@click.option(
    "--server-url",
    envvar="REANA_SERVER_URL",
    help="REANA server URL to authenticate against.",
)
@click.option(
    "--headless",
    is_flag=True,
    default=False,
    help="Use device login instead of opening a local browser. "
    "Use this on machines without a browser (e.g. over SSH).",
)
@click.pass_context
def login(ctx, server_url, headless):  # noqa: D301
    """Authenticate against REANA server using OIDC.

    By default the browser-based loopback flow (authorization code with PKCE)
    is used. On headless machines pass ``--headless`` to use the device flow.
    """
    try:
        server_url = normalize_server_url(server_url or get_active_server())
        if headless:
            _device_login(server_url)
        else:
            _browser_login(server_url)
        display_message(f"Logged in to {server_url}")
    except (AuthenticationError, ValueError) as e:
        display_message(str(e), msg_type="error")
        ctx.exit(1)


def _browser_login(server_url):
    """Run the loopback authorization-code + PKCE login flow."""

    def display_url(authorization_url):
        display_message(
            "Opening your browser to authenticate. If it does not open "
            f"automatically, visit:\n{authorization_url}"
        )

    login_with_loopback(server_url, display_url)


def _device_login(server_url):
    """Run the OIDC device login flow."""

    def display_device_prompt(device_response):
        verification_uri_complete = device_response.get("verification_uri_complete")
        if verification_uri_complete:
            display_message(
                "Open the following URL to authenticate:\n"
                f"{verification_uri_complete}"
            )
        else:
            display_message(
                "Open the following URL to authenticate:\n"
                f"{device_response.get('verification_uri')}\n"
                f"Code: {device_response.get('user_code')}"
            )

    login_with_device_flow(server_url, display_device_prompt)


@configuration_group.command("logout")
@click.pass_context
def logout(ctx):  # noqa: D301
    """Logout from the active REANA server."""
    try:
        server_url = get_active_server()
        warning = oidc_logout(server_url)
        if warning:
            display_message(warning, msg_type="warning")
        display_message(f"Logged out from {server_url}")
    except (AuthenticationError, ValueError) as e:
        display_message(str(e), msg_type="error")
        ctx.exit(1)


@configuration_group.command("ping")
@click.pass_context
@add_access_token_options
@check_connection
def ping(ctx, access_token):  # noqa: D301
    """Check connection to REANA server.

    The ``ping`` command allows to test connection to REANA server.

    Examples:\n
    \t $ reana-client ping
    """
    try:
        from reana_client.api.client import ping as rs_ping
        from reana_client.utils import get_api_url

        logging.info("Connecting to {0}".format(get_api_url()))
        response = rs_ping(access_token)
        error = response.get("error")
        msg_color = "red" if error else "green"
        click.secho(
            "REANA server: {0}\n"
            "REANA server version: {1}\n"
            "REANA client version: {2}\n"
            "Authenticated as: {3} <{4}>\n"
            "Status: {5}".format(
                get_api_url(),
                response.get("reana_server_version", ""),
                __version__,
                response.get("full_name", ""),
                response.get("email"),
                response.get("status"),
            ),
            fg=msg_color,
        )
        logging.debug("Server response:\n{}".format(response))
        if error:
            sys.exit(1)
    except Exception as e:
        logging.debug(traceback.format_exc())
        logging.debug(str(e))
        display_message(
            "Could not connect to the selected REANA cluster "
            "server at {0}:\n{1}".format(get_api_url(), e),
            msg_type="error",
        )
        ctx.exit(1)


@configuration_group.command("version")
@click.pass_context
def version(ctx):  # noqa: D301
    """Show version.

    The ``version`` command shows REANA client version.

    Examples:\n
    \t $ reana-client version
    """
    display_message(__version__)


@configuration_group.command("info")
@click.option(
    "--json",
    "output_format",
    flag_value="json",
    default=None,
    help="Get output in JSON format.",
)
@click.pass_context
@add_access_token_options
@check_connection
def info(ctx, access_token: str, output_format: str):  # noqa: D301
    """List cluster general information.

    The ``info`` command lists general information about the cluster.

    Lists all the available workspaces. It also returns the default workspace
    defined by the admin.

    Examples:\n
    \t $ reana-client info
    """
    try:
        from reana_client.api.client import get_user_quota, info

        response = info(access_token)
        try:
            response.update(build_cpu_quota_period_info(get_user_quota(access_token)))
        except (KeyError, ValueError) as e:
            logging.debug(
                "Could not enrich cluster info with quota period details: %s", str(e)
            )
        if output_format == JSON:
            display_message(json.dumps(response))
        else:
            for item in response.values():
                if not item:
                    continue
                value = item.get("value")
                value = ", ".join(value) if isinstance(value, list) else value
                display_message(f"{item.get('title')}: {value}")

    except Exception as e:
        logging.debug(traceback.format_exc())
        logging.debug(str(e))
        display_message("Could not list cluster info:\n{0}".format(e), msg_type="error")
        ctx.exit(1)
