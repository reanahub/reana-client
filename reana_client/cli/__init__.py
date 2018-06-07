# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2017, 2018 CERN.
#
# REANA is free software; you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software
# Foundation; either version 2 of the License, or (at your option) any later
# version.
#
# REANA is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
# A PARTICULAR PURPOSE. See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with
# REANA; if not, write to the Free Software Foundation, Inc., 59 Temple Place,
# Suite 330, Boston, MA 02111-1307, USA.
#
# In applying this license, CERN does not waive the privileges and immunities
# granted to it by virtue of its status as an Intergovernmental Organization or
# submit itself to any jurisdiction.
"""REANA command line interface client."""
import logging
import os
import sys

import click

from reana_client.api import Client
from reana_client.cli import analyses, workflow, inputs, outputs, \
    ping, code, status, users

DEBUG_LOG_FORMAT = '[%(asctime)s] p%(process)s ' \
                   '{%(pathname)s:%(lineno)d} ' \
                   '%(levelname)s - %(message)s'

LOG_FORMAT = '[%(levelname)s] %(message)s'


class Config(object):
    """Configuration object to share across commands."""

    def __init__(self):
        """Initialize config variables."""
        server_url = os.environ.get('REANA_SERVER_URL', None)

        if not server_url:
            logging.error(
                'REANA client is not connected to any REANA cluster.\n'
                'Please set REANA_SERVER_URL environment variable to '
                'the remote REANA cluster you would like to connect to.\n'
                'For example: export REANA_SERVER_URL=https://reana.cern.ch/')
            sys.exit(1)

        logging.info('REANA Server URL ($REANA_SERVER_URL) is: {}'
                     .format(server_url))

        self.client = Client(server_url)


@click.group()
@click.option(
    '--loglevel',
    '-l',
    help='Sets log level',
    type=click.Choice(['DEBUG', 'INFO', 'WARNING']),
    default='WARNING')
@click.pass_context
def cli(ctx, loglevel):
    """REANA Client for interacting with REANA Server."""
    logging.basicConfig(
        format=DEBUG_LOG_FORMAT if loglevel == 'DEBUG' else LOG_FORMAT,
        stream=sys.stderr,
        level=loglevel)
    ctx.obj = Config()


cli.add_command(ping.ping)
cli.add_command(analyses.analyses)
cli.add_command(workflow.workflow)
cli.add_command(inputs.inputs)
cli.add_command(outputs.outputs)
cli.add_command(code.code)
cli.add_command(status.status)
cli.add_command(users.users)
