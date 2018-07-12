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
import traceback

import click

from ..config import default_user


@click.command()
@click.pass_context
@click.option(
    '-u',
    '--user',
    default=default_user,
    help='User who has created the workflow.')
def status(ctx, user):
    """Show current status of the client session."""
    try:
        click.echo(click.style('User: {}'.format(user), fg='green'))
        click.echo(click.style('REANA cluster selected: {}'.
                   format(ctx.obj.client.server_url), fg='green'))
        _ = ctx.obj.client.ping()
        click.echo(click.style('REANA cluster status: ready', fg='green'))
        workflow = os.environ.get('REANA_WORKON', None)
        click.echo(click.style('Workflow selected: {}'.
                   format(workflow), fg='green'))
        workflow_status_response = ctx.obj.client.get_workflow_status(
            user, workflow)
        click.echo(click.style('Workflow status: {}'.
                               format(workflow_status_response['status']),
                               fg='green'))

    except Exception as e:
        logging.debug(traceback.format_exc())
        logging.debug(str(e))
        click.echo(
            click.style('Could not retrieve current status. Error: {}'.
                        format(str(e)), fg='red'), err=True)
