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
import traceback
from enum import Enum

import click
import tablib
import yaml

from ..config import (default_organization, default_user,
                      reana_yaml_default_file_path)
from ..utils import get_workflow_name_and_run_number, load_reana_spec, \
    load_workflow_spec, is_uuid_v4, workflow_uuid_or_name


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
    '--json',
    'output_format',
    flag_value='json',
    default=None,
    help='Get output in JSON format.')
@click.pass_context
def workflow_list(ctx, user, organization, filter, output_format):
    """List all workflows user has."""
    logging.debug('workflow.list')
    logging.debug('user: {}'.format(user))
    logging.debug('organization: {}'.format(organization))
    logging.debug('filter: {}'.format(filter))
    logging.debug('output_format: {}'.format(output_format))

    data = tablib.Dataset()
    data.headers = ['name', 'run_number', 'id', 'user', 'organization',
                    'status']

    try:
        response = ctx.obj.client.get_all_analyses(user, organization)
        for analysis in response:
            name, run_number = get_workflow_name_and_run_number(
                analysis['name'])
            data.append([name,
                         run_number,
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
        logging.debug(traceback.format_exc())
        logging.debug(str(e))
        click.echo(
            click.style('Workflow list culd not be retrieved: \n{}'
                        .format(str(e)), fg='red'),
            err=True)


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
    '-n',
    '--name',
    default='',
    help='Name of the workflow.')
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
def workflow_create(ctx, file, user, name, organization, skip_validation):
    """Create a REANA compatible analysis workflow from REANA spec file."""
    logging.debug('workflow.create')
    logging.debug('file: {}'.format(file))
    logging.debug('user: {}'.format(user))
    logging.debug('organization: {}'.format(organization))
    logging.debug('skip_validation: {}'.format(skip_validation))

    # Check that name is not an UUIDv4.
    # Otherwise it would mess up `--workflow` flag usage because no distinction
    # could be made between the name and actual UUID of workflow.
    if is_uuid_v4(name):
        click.echo(
            click.style('Workflow name cannot be a valid UUIDv4', fg='red'),
            err=True)

    try:
        reana_spec = load_reana_spec(click.format_filename(file),
                                     skip_validation)

        reana_spec['workflow']['spec'] = load_workflow_spec(
            reana_spec['workflow']['type'],
            reana_spec['workflow']['file'],
        )
        if reana_spec['workflow']['type'] == 'cwl':
            with open(reana_spec['inputs']['parameters']['input']) as f:
                reana_spec['inputs']['parameters']['input'] = yaml.load(f)

        logging.info('Connecting to {0}'.format(ctx.obj.client.server_url))
        response = ctx.obj.client.create_workflow(user,
                                                  organization,
                                                  reana_spec,
                                                  name)
        click.echo(click.style(response['workflow_name'], fg='green'))

    except Exception as e:
        logging.debug(traceback.format_exc())
        logging.debug(str(e))
        click.echo(
            click.style('Workflow could not be created: \n{}'
                        .format(str(e)), fg='red'),
            err=True)


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
    callback=workflow_uuid_or_name,
    help='Name or UUID of the workflow to be started. '
         'Overrides value of $REANA_WORKON.')
@click.pass_context
def workflow_start(ctx, user, organization, workflow):
    """Start previously created analysis workflow."""
    logging.debug('workflow.start')
    logging.debug('user: {}'.format(user))
    logging.debug('organization: {}'.format(organization))
    logging.debug('workflow: {}'.format(workflow))

    logging.info('Workflow `{}` selected'.format(workflow))
    click.echo('Workflow `{}` selected.'.format(workflow))

    try:

        logging.info('Connecting to {0}'.format(ctx.obj.client.server_url))
        response = ctx.obj.client.start_analysis(user,
                                                 organization,
                                                 workflow)
        click.echo(
            click.style('Workflow `{}` has been started.'
                        .format(response['workflow_id']),
                        fg='green'))

    except Exception as e:
        logging.debug(traceback.format_exc())
        logging.debug(str(e))
        click.echo(
            click.style('Workflow could not be started: \n{}'
                        .format(str(e)), fg='red'),
            err=True)


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
    callback=workflow_uuid_or_name,
    help='Name or UUID of the workflow whose status should be resolved. '
         'Overrides value of $REANA_WORKON.')
@click.option(
    '--filter',
    multiple=True,
    help='Filter output according to column titles (case-sensitive).')
@click.option(
    '--json',
    'output_format',
    flag_value='json',
    default=None,
    help='Get output in JSON format.')
@click.pass_context
def workflow_status(ctx, user, organization, workflow, filter, output_format):
    """Get status of previously created analysis workflow."""
    logging.debug('workflow.start')
    logging.debug('user: {}'.format(user))
    logging.debug('organization: {}'.format(organization))
    logging.debug('workflow: {}'.format(workflow))
    logging.debug('output_format: {}'.format(output_format))
    logging.info('Workflow "{}" selected'.format(workflow))

    data = tablib.Dataset()
    data.headers = ['name', 'run_number', 'id', 'user', 'organization',
                    'status']

    try:
        response = ctx.obj.client.get_analysis_status(user,
                                                      organization,
                                                      workflow)
        if isinstance(response, list):
            for analysis in response:
                name, run_number = get_workflow_name_and_run_number(
                    analysis['name'])
                data.append([name,
                             run_number,
                             analysis['id'],
                             analysis['user'],
                             analysis['organization'],
                             analysis['status']])
        else:
            name, run_number = get_workflow_name_and_run_number(
                response['name'])
            data.append([name,
                         run_number,
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
        logging.debug(traceback.format_exc())
        logging.debug(str(e))
        click.echo(
            click.style('Workflow status could not be retrieved: \n{}'
                        .format(str(e)), fg='red'),
            err=True)


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
    callback=workflow_uuid_or_name,
    help='Name or UUID of the workflow whose logs should be fetched. '
         'Overrides value of $REANA_WORKON.')
@click.pass_context
def workflow_logs(ctx, user, organization, workflow):
    """Get status of previously created analysis workflow."""
    logging.debug('workflow.start')
    logging.debug('user: {}'.format(user))
    logging.debug('organization: {}'.format(organization))
    logging.debug('workflow: {}'.format(workflow))

    workflow_name = workflow or os.environ.get('$REANA_WORKON', None)

    try:
        response = ctx.obj.client.get_workflow_logs(user,
                                                    organization,
                                                    workflow)
        click.echo(response)
    except Exception as e:
        logging.debug(traceback.format_exc())
        logging.debug(str(e))
        click.echo(
            click.style('Workflow logs could not be retrieved: \n{}'
                        .format(str(e)), fg='red'),
            err=True)


workflow.add_command(workflow_list)
workflow.add_command(workflow_create)
workflow.add_command(workflow_start)
workflow.add_command(workflow_status)
# workflow.add_command(workflow_logs)
