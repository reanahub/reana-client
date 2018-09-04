# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2017 CERN.
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
"""REANA client debugging commands."""

import logging
import traceback

import click

from reana_client.decorators import with_api_client


@click.command('ping', help='Health check REANA server.')
@click.pass_context
@with_api_client
def ping(ctx):
    """Health check REANA server."""
    try:
        logging.info('Connecting to {0}'.format(ctx.obj.client.server_url))
        response = ctx.obj.client.ping()
        click.echo(click.style('Connected to {0} - Server is running.'.format(
            ctx.obj.client.server_url), fg='green'))
        logging.debug('Server response:\n{}'.format(response))

    except Exception as e:
        logging.debug(traceback.format_exc())
        logging.debug(str(e))
        click.echo(click.style(
            'Could not connect to the selected '
            'REANA cluster server at {0}.'.format(ctx.obj.client.server_url),
            fg='red'), err=True)
