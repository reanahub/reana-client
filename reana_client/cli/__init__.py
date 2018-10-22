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

from reana_client.api import Client
from reana_client.cli import workflow, files, ping

DEBUG_LOG_FORMAT = '[%(asctime)s] p%(process)s ' \
                   '{%(pathname)s:%(lineno)d} ' \
                   '%(levelname)s - %(message)s'

LOG_FORMAT = '[%(levelname)s] %(message)s'


class Config(object):
    """Configuration object to share across commands."""

    def __init__(self, api_client=None):
        """Initialize config variables.

        :param api_client: An instance of
            :class:`bravado.client.SwaggerClient`.
        """
        self.client = api_client


@click.group()
@click.option(
    '--loglevel',
    '-l',
    help='Sets log level',
    type=click.Choice(['DEBUG', 'INFO', 'WARNING']),
    default='WARNING')
@click.pass_context
@click.pass_obj
def cli(obj, ctx, loglevel):
    """REANA client for interacting with REANA server."""
    logging.basicConfig(
        format=DEBUG_LOG_FORMAT if loglevel == 'DEBUG' else LOG_FORMAT,
        stream=sys.stderr,
        level=loglevel)
    ctx.obj = obj if obj else Config()

commands = []
commands.extend(workflow.workflow.commands.values())
commands.extend(files.files.commands.values())
for cmd in commands:
    cli.add_command(cmd)
cli.add_command(ping.ping)
