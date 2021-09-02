# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2017, 2018 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
"""REANA client debugging commands."""

import logging
import traceback

import click
from reana_client.cli.utils import add_access_token_options, check_connection
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
        display_message(
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


@configuration_group.command("workspaces")
@click.pass_context
@add_access_token_options
@check_connection
def workspaces(ctx, access_token):  # noqa: D301
    """List available workspaces.

    The `workspaces` command lists all the available workspaces.
    It also returns the default workspace defined by the admin.

    Examples: \n
    \t $ reana-client workspaces
    """
    try:
        from reana_client.api.client import workspaces

        response = workspaces(access_token)
        display_message(
            "List of available workspaces: {0}\n"
            "Default workspace: {1}".format(
                ", ".join(response.get("workspaces_available")),
                response.get("default"),
            )
        )

    except Exception as e:
        logging.debug(traceback.format_exc())
        logging.debug(str(e))
        display_message(
            "Could not list available workspaces:\n{0}".format(e), msg_type="error"
        )
        ctx.exit(1)
