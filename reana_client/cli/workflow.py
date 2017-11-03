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
"""REANA client workflow related commands."""

import logging
import os
import random
import traceback
import uuid
from enum import Enum

import click
import tablib

from ..config import (default_organization, default_user,
                      reana_yaml_default_file_path)
from ..utils import load_reana_spec, load_workflow_spec
from .namesgenerator import get_random_name


class _WorkflowStatus(Enum):
    created = 0
    running = 1
    finished = 2
    failed = 3


@click.group(
    help='All interaction related to workflows on REANA cloud.')
@click.pass_context
def workflow(ctx):
    """Top level wrapper for workflow related interaction."""
    logging.debug('workflow')


@click.command(
    'list',
    help='List all available workflows.')
@click.option(
    '-u',
    '--user',
    default=default_user,
    help='User who created the analysis.')
@click.option(
    '-o',
    '--organization',
    default=default_organization,
    help='Organization whose resources will be used.')
@click.option(
    '--filter',
    multiple=True,
    help='Filter output according to column titles (case-sensitive).')
@click.option(
    '-of',
    '--output-format',
    type=click.Choice(['json', 'yaml']),
    help='Set output format.')
@click.pass_context
def workflow_list(ctx, user, organization, filter, output_format):
    """List all workflows user has."""
    logging.debug('workflow.list')
    logging.debug('user: {}'.format(user))
    logging.debug('organization: {}'.format(organization))
    logging.debug('filter: {}'.format(filter))
    logging.debug('output_format: {}'.format(output_format))

    data = tablib.Dataset()
    data.headers = ['Name', 'UUID', 'User', 'Organization', 'Status']

    try:
        response = ctx.obj.client.get_all_analyses(user, organization)
        for analysis in response:
            data.append([get_random_name(),
                        analysis['id'],
                        analysis['user'],
                        analysis['organization'],
                        analysis['status']])

        if filter:
            data = data.subset(rows=None, cols=list(filter))

        if output_format:
            click.echo(data.export(output_format))
        else:
            click.echo(data)

    except Exception as e:
        logging.error(traceback.format_exc())


@click.command(
    'create',
    help='Create a REANA compatible analysis workflow from REANA '
         'specifications file.')
@click.option(
    '-f',
    '--file',
    type=click.Path(exists=True, resolve_path=True),
    default=reana_yaml_default_file_path,
    help='REANA specifications file describing the workflow and '
         'context which REANA should execute.')
@click.option(
    '-u',
    '--user',
    default=default_user,
    help='User who creates the analysis.')
@click.option(
    '-o',
    '--organization',
    default=default_organization,
    help='Organization whose resources will be used.')
@click.option(
    '--skip-validation',
    is_flag=True,
    help="If set, specifications file is not validated before "
         "submitting it's contents to REANA Server.")
@click.pass_context
def workflow_create(ctx, file, user, organization, skip_validation):
    """Create a REANA compatible analysis workflow from REANA spec file."""
    logging.debug('workflow.create')
    logging.debug('file: {}'.format(file))
    logging.debug('user: {}'.format(user))
    logging.debug('organization: {}'.format(organization))
    logging.debug('skip_validation: {}'.format(skip_validation))

    try:
        reana_spec = load_reana_spec(click.format_filename(file),
                                     skip_validation)

        reana_spec['workflow']['spec'] = load_workflow_spec(
            reana_spec['workflow']['type'],
            reana_spec['workflow']['file'],
        )

        logging.info('Connecting to {0}'.format(ctx.obj.client.server_url))
        response = ctx.obj.client.create_workflow(user,
                                                  organization,
                                                  reana_spec)
        click.echo(response)

    except Exception as e:
        logging.error(traceback.format_exc())


@click.command(
    'start',
    help='Start previously created analysis workflow.')
@click.option(
    '-u',
    '--user',
    default=default_user,
    help='User who has created the workflow.')
@click.option(
    '-o',
    '--organization',
    default=default_organization,
    help='Organization whose resources will be used.')
@click.option(
    '--workflow',
    default=os.environ.get('REANA_WORKON', None),
    help='Name of the workflow to be started. '
         'Overrides value of $REANA_WORKON.')
@click.pass_context
def workflow_start(ctx, user, organization, workflow):
    """Start previously created analysis workflow."""
    logging.debug('workflow.start')
    logging.debug('user: {}'.format(user))
    logging.debug('organization: {}'.format(organization))
    logging.debug('workflow: {}'.format(workflow))

    if workflow:
        logging.info('Workflow `{}` selected'.format(workflow))
        click.echo('Workflow `{}` has been started.'.format(workflow))
    else:
        click.echo(
            click.style('Workflow name must be provided either with '
                        '`--workflow` option or with `$REANA_WORKON` '
                        'environment variable',
                        fg='red'),
            err=True)

    try:
        logging.info('Connecting to {0}'.format(ctx.obj.client.server_url))
        response = ctx.obj.client.start_analysis(user,
                                                 organization,
                                                 workflow)
        click.echo(response)
        click.echo('Workflow `{}` has been started.'.format(workflow))

    except Exception as e:
        logging.error(str(e))


@click.command(
    'status',
    help='Get status of a previously created analysis workflow.')
@click.option(
    '-u',
    '--user',
    default=default_user,
    help='User who has created the workflow.')
@click.option(
    '-o',
    '--organization',
    default=default_organization,
    help='Organization whose resources will be used.')
@click.option(
    '--workflow',
    default=os.environ.get('REANA_WORKON', None),
    help='Name of the workflow whose status should be resolved. '
         'Overrides value of $REANA_WORKON.')
@click.option(
    '--filter',
    multiple=True,
    help='Filter output according to column titles (case-sensitive).')
@click.option(
    '-of',
    '--output-format',
    type=click.Choice(['json', 'yaml']),
    help='Set output format.')
@click.pass_context
def workflow_status(ctx, user, organization, workflow, filter, output_format):
    """Get status of previously created analysis workflow."""
    logging.debug('workflow.start')
    logging.debug('user: {}'.format(user))
    logging.debug('organization: {}'.format(organization))
    logging.debug('workflow: {}'.format(workflow))

    data = tablib.Dataset()
    data.headers = ['Name', 'UUID', 'User', 'Organization', 'Status']

    if workflow:
        logging.info('Workflow "{}" selected'.format(workflow))

        try:
            response = ctx.obj.client.get_analysis_status(user,
                                                          organization,
                                                          workflow)
            if isinstance(response, list):
                for analysis in response:
                    data.append([get_random_name(),
                                analysis['id'],
                                analysis['user'],
                                analysis['organization'],
                                analysis['status']])
            else:
                data.append([get_random_name(),
                             response['id'],
                             response['user'],
                             response['organization'],
                             response['status']])

            if filter:
                data = data.subset(rows=None, cols=list(filter))

            if output_format:
                click.echo(data.export(output_format))
            else:
                click.echo(data)

        except Exception as e:
            logging.debug(str(e))

    else:
        click.echo(
            click.style('Workflow name must be provided either with '
                        '`--workflow` option or with `$REANA_WORKON` '
                        'environment variable',
                        fg='red'),
            err=True)


workflow.add_command(workflow_list)
workflow.add_command(workflow_create)
workflow.add_command(workflow_start)
workflow.add_command(workflow_status)
