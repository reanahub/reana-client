# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2018 CERN.
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
"""REANA client status command."""

import logging
import os
import sys
import traceback

import click
from requests.exceptions import ConnectionError

from ..config import default_user


@click.command()
@click.pass_context
@click.option(
    '-at',
    '--access-token',
    default=os.environ.get('REANA_ACCESS_TOKEN', None),
    help='Access token of the current user.')
def status(ctx, access_token):
    """Show current status of the client session."""
    try:
        _ = ctx.obj.client.ping()
        click.echo(click.style('Connected to: {}'.
                   format(ctx.obj.client.server_url), fg='green'))
        workflow = os.environ.get('REANA_WORKON', None)
        if workflow:
            try:
                workflow_status_response = ctx.obj.client.get_workflow_status(
                    workflow, access_token)
                click.echo(click.style('Working on: {}'.
                           format(workflow), fg='green'))
                click.echo(click.style(
                    'Workflow status: {}'.
                    format(workflow_status_response['status']),
                    fg='green'))
            except Exception as e:
                click.echo(
                    click.style('Could not retrieve workflow status.\n'
                                'Error: {}'.format(str(e)), fg='red'),
                    err=True)
                sys.exit(1)
        else:
            click.echo(click.style('No workflow is selected currently.',
                                   fg='green'))
    except ConnectionError as e:
        click.echo(
            click.style(
                'Could not connect to the selected '
                'REANA cluster server at {0}.\n'
                'Please make sure you have set your REANA_SERVER_URL'
                ' environment variable correctly.'.
                format(ctx.obj.client.server_url),
                fg='red'),
            err=True)
    except Exception as e:
        logging.debug(traceback.format_exc())
        logging.debug(str(e))
        click.echo(
            click.style('Could not retrieve current status.', fg='red'),
            err=True)
        if str(e):
            click.echo(
                click.style('Error: {}'.format(str(e)), fg='red'),
                err=True)
        sys.exit(1)
