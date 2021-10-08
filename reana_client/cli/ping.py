# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2017, 2018, 2021 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
"""REANA client configuration commands."""

import json
import logging
import traceback

import click
from reana_client.cli.utils import add_access_token_options, check_connection
from reana_client.config import JSON
from reana_client.printer import display_message
from reana_client.version import __version__


@click.group(help="Configuration commands")
def configuration_group():
    """Configuration commands."""
    pass


@configuration_group.command("ping")
@click.pass_context
@add_access_token_options
@check_connection
def ping(ctx, access_token):  # noqa: D301
    """Check connection to REANA server.

    The `ping` command allows to test connection to REANA server.

    Examples: \n
    \t $ reana-client ping
    """
    try:
        from reana_client.api.client import ping as rs_ping
        from reana_client.utils import get_api_url

        logging.info("Connecting to {0}".format(get_api_url()))
        response = rs_ping(access_token)
        msg_color = "red" if response.get("error") else "green"
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

    The `version` command shows REANA client version.

    Examples: \n
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
    - Lists all the available workspaces. It also returns the default workspace
    defined by the admin.

    Examples: \n
    \t $ reana-client info
    """
    try:
        from reana_client.api.client import info

        response = info(access_token)
        if output_format == JSON:
            display_message(json.dumps(response))
        else:
            for item in response.values():
                value = item.get("value")
                value = ", ".join(value) if isinstance(value, list) else value
                display_message(f"{item.get('title')}: {value}")

    except Exception as e:
        logging.debug(traceback.format_exc())
        logging.debug(str(e))
        display_message("Could not list cluster info:\n{0}".format(e), msg_type="error")
        ctx.exit(1)
