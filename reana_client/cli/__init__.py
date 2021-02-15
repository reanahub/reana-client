# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2017, 2018 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
"""REANA command line interface client."""
import logging
import os
import sys

import click
from urllib3 import disable_warnings

from reana_client.cli import workflow, files, ping, secrets, quotas
from reana_client.utils import get_api_url

DEBUG_LOG_FORMAT = (
    "[%(asctime)s] p%(process)s "
    "{%(pathname)s:%(lineno)d} "
    "%(levelname)s - %(message)s"
)

LOG_FORMAT = "[%(levelname)s] %(message)s"


class Config(object):
    """Configuration object to share across commands."""

    def __init__(self):
        """Initialize config variables."""
        self.reana_server_url = get_api_url()


class ReanaCLI(click.Group):
    """REANA command line interface."""

    cmd_groups = [
        quotas.quota_group,
        ping.configuration_group,
        workflow.workflow_management_group,
        workflow.workflow_execution_group,
        workflow.interactive_group,
        files.files_group,
        secrets.secrets_group,
    ]

    def __init__(self, name=None, commands=None, **attrs):
        """Initialize REANA client commands."""
        disable_warnings()
        click.Group.__init__(self, name, **attrs)
        for group in ReanaCLI.cmd_groups:
            for cmd in group.commands.items():
                self.add_command(cmd=cmd[1], name=cmd[0])

    def format_commands(self, ctx, formatter):
        """Overides default click cmd display."""
        if ReanaCLI.cmd_groups:
            max_cmd_length = len(max([max(name) for name in self.list_commands(ctx)]))
            limit = formatter.width - 6 - max_cmd_length
            rows = []
            for group in ReanaCLI.cmd_groups:
                item = {"rows": []}
                item["group_help"] = group.get_short_help_str(limit)
                for command in sorted(group.commands.items()):
                    if command[1] is None:
                        continue
                    if command[1].hidden:
                        continue
                    command_help = command[1].get_short_help_str(limit)
                    item["rows"].append((command[0], command_help))
                rows.append(item)
            for item in rows:
                with formatter.section(item["group_help"]):
                    formatter.write_dl(item["rows"])


@click.command(cls=ReanaCLI)
@click.option(
    "--loglevel",
    "-l",
    help="Sets log level",
    type=click.Choice(["DEBUG", "INFO", "WARNING"]),
    default="WARNING",
)
@click.pass_context
@click.pass_obj
def cli(obj, ctx, loglevel):
    """REANA client for interacting with REANA server."""
    logging.basicConfig(
        format=DEBUG_LOG_FORMAT if loglevel == "DEBUG" else LOG_FORMAT,
        stream=sys.stderr,
        level=loglevel,
    )
    ctx.obj = obj or Config()
