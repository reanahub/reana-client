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
import sys
import traceback
from enum import Enum

import click
import tablib
import yaml

from ..config import (default_organization, default_user,
                      reana_yaml_default_file_path)
from ..utils import get_workflow_name_and_run_number, load_reana_spec, \
    load_workflow_spec, is_uuid_v4, workflow_uuid_or_name
from reana_commons.utils import click_table_printer


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
    logging.debug(ctx.info_name)


@click.command(
    'list',
    help='List all available workflows.')
@click.option(
    '-o',
    '--organization',
    default=default_organization,
    help='Organization whose resources will be used.')
@click.option(
    '--filter',
    '_filter',
    multiple=True,
    help='Filter output according to column titles (case-sensitive).')
@click.option(
    '--json',
    'output_format',
    flag_value='json',
    default=None,
    help='Get output in JSON format.')
@click.option(
    '-t',
    '--token',
    default=os.environ.get('REANA_TOKEN', None),
    help='API token of the current user.')
@click.pass_context
def workflow_list(ctx, organization, _filter, output_format, token):
    """List all workflows user has."""
    logging.debug('command: {}'.format(ctx.command_path.replace(" ", ".")))
    for p in ctx.params:
        logging.debug('{param}: {value}'.format(param=p, value=ctx.params[p]))

    if not token:
        click.echo(
            click.style('Please provide your API token, either by setting the'
                        ' REANA_TOKEN environment variable, or by using'
                        ' the -t/--token flag.', fg='red'), err=True)
        sys.exit(1)

    try:
        response = ctx.obj.client.get_all_analyses(organization, token)
        headers = ['name', 'run_number', 'id', 'user', 'organization',
                   'status']
        data = []
        for analysis in response:
            name, run_number = get_workflow_name_and_run_number(
                analysis['name'])
            data.append(list(map(str, [name,
                                       run_number,
                                       analysis['id'],
                                       analysis['user'],
                                       analysis['organization'],
                                       analysis['status']])))
        if output_format:
            tablib_data = tablib.Dataset()
            tablib_data.headers = headers
            for row in data:
                tablib_data.append(row)

            if _filter:
                tablib_data = tablib_data.subset(rows=None, cols=list(_filter))

            click.echo(tablib_data.export(output_format))
        else:
            click_table_printer(headers, _filter, data)

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
@click.option(
    '-t',
    '--token',
    default=os.environ.get('REANA_TOKEN', None),
    help='API token of the current user.')
@click.pass_context
def workflow_create(ctx, file, name, organization,
                    skip_validation, token):
    """Create a REANA compatible analysis workflow from REANA spec file."""
    logging.debug('command: {}'.format(ctx.command_path.replace(" ", ".")))
    for p in ctx.params:
        logging.debug('{param}: {value}'.format(param=p, value=ctx.params[p]))

    # Check that name is not an UUIDv4.
    # Otherwise it would mess up `--workflow` flag usage because no distinction
    # could be made between the name and actual UUID of workflow.
    if is_uuid_v4(name):
        click.echo(
            click.style('Workflow name cannot be a valid UUIDv4', fg='red'),
            err=True)
    if not token:
        click.echo(
            click.style('Please provide your API token, either by setting the'
                        ' REANA_TOKEN environment variable, or by using'
                        ' the -t/--token flag.', fg='red'), err=True)
        sys.exit(1)
    try:
        reana_spec = load_reana_spec(click.format_filename(file),
                                     skip_validation)

        kwargs = {}
        if reana_spec['workflow']['type'] == 'serial':
            kwargs['specification'] = reana_spec['workflow'].\
                get('specification')
        reana_spec['workflow']['spec'] = load_workflow_spec(
            reana_spec['workflow']['type'],
            reana_spec['workflow'].get('file'),
            **kwargs
        )

        if reana_spec['workflow']['type'] == 'cwl':
            with open(reana_spec['inputs']['parameters']['input']) as f:
                reana_spec['inputs']['parameters']['input'] = yaml.load(f)

        logging.info('Connecting to {0}'.format(ctx.obj.client.server_url))
        response = ctx.obj.client.create_workflow(organization,
                                                  reana_spec,
                                                  name,
                                                  token)
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
    '-o',
    '--organization',
    default=default_organization,
    help='Organization whose resources will be used.')
@click.option(
    '-w',
    '--workflow',
    default=os.environ.get('REANA_WORKON', None),
    callback=workflow_uuid_or_name,
    help='Name or UUID of the workflow to be started. '
         'Overrides value of REANA_WORKON.')
@click.option(
    '-t',
    '--token',
    default=os.environ.get('REANA_TOKEN', None),
    help='API token of the current user.')
@click.pass_context
def workflow_start(ctx, organization, workflow, token):
    """Start previously created analysis workflow."""
    logging.debug('command: {}'.format(ctx.command_path.replace(" ", ".")))
    for p in ctx.params:
        logging.debug('{param}: {value}'.format(param=p, value=ctx.params[p]))

    if not token:
        click.echo(
            click.style('Please provide your API token, either by setting the'
                        ' REANA_TOKEN environment variable, or by using'
                        ' the -t/--token flag.', fg='red'), err=True)
        sys.exit(1)

    if workflow:
        try:
            logging.info('Connecting to {0}'.format(ctx.obj.client.server_url))
            response = ctx.obj.client.start_analysis(organization,
                                                     workflow,
                                                     token)
            click.echo(
                click.style('{} has been started.'.format(workflow),
                            fg='green'))

        except Exception as e:
            logging.debug(traceback.format_exc())
            logging.debug(str(e))
            click.echo(
                click.style('Workflow could not be started: \n{}'
                            .format(str(e)), fg='red'),
                err=True)
    else:
        click.echo(
            click.style('Workflow name must be provided either with '
                        '`--workflow` option or with REANA_WORKON '
                        'environment variable',
                        fg='red'),
            err=True)


@click.command(
    'status',
    help='Get status of a previously created analysis workflow.')
@click.option(
    '-o',
    '--organization',
    default=default_organization,
    help='Organization whose resources will be used.')
@click.option(
    '-w',
    '--workflow',
    default=os.environ.get('REANA_WORKON', None),
    callback=workflow_uuid_or_name,
    help='Name or UUID of the workflow whose status should be resolved. '
         'Overrides value of REANA_WORKON.')
@click.option(
    '--filter',
    '_filter',
    multiple=True,
    help='Filter output according to column titles (case-sensitive).')
@click.option(
    '--json',
    'output_format',
    flag_value='json',
    default=None,
    help='Get output in JSON format.')
@click.option(
    '-t',
    '--token',
    default=os.environ.get('REANA_TOKEN', None),
    help='API token of the current user.')
@click.option(
    '-v',
    '--verbose',
    count=True,
    help='Set status information verbosity.')
@click.pass_context
def workflow_status(ctx, organization, workflow, _filter, output_format,
                    token, verbose):
    """Get status of previously created analysis workflow."""
    logging.debug('command: {}'.format(ctx.command_path.replace(" ", ".")))
    for p in ctx.params:
        logging.debug('{param}: {value}'.format(param=p, value=ctx.params[p]))

    if not token:
        click.echo(
            click.style('Please provide your API token, either by setting the'
                        ' REANA_TOKEN environment variable, or by using'
                        ' the -t/--token flag.', fg='red'), err=True)
        sys.exit(1)

    if workflow:
        try:
            response = ctx.obj.client.get_analysis_status(organization,
                                                          workflow,
                                                          token)
            verbose_headers = ['id', 'user', 'organization']
            headers = ['name', 'run_number',
                       'status', 'command', 'progress']
            if verbose:
                headers += verbose_headers
            data = []
            if isinstance(response, list):
                for analysis in response:
                    name, run_number = get_workflow_name_and_run_number(
                        analysis['name'])
                    data.append(list(map(
                        str,
                        [name,
                         run_number,
                         analysis['status'],
                         analysis['current_command'],
                         '{0}/{1}'.format(
                             analysis['current_command_idx'],
                             analysis['total_commands'])])))
                    if verbose:
                        data[-1] += [analysis[k] for k in verbose_headers]
            else:
                name, run_number = get_workflow_name_and_run_number(
                    response['name'])
                data.append(list(
                    map(str,
                        [name,
                         run_number,
                         response['status'],
                         response['progress'].get('current_command'),
                         '{0}/{1}'.format(
                             response['progress'].get('current_command_idx'),
                             response['progress'].get('total_commands'))])))
                if verbose:
                    data[-1] += [response[k] for k in verbose_headers]

            if output_format:
                tablib_data = tablib.Dataset()
                tablib_data.headers = headers
                for row in data:
                    tablib_data.append(row)

                if _filter:
                    data = data.subset(rows=None, cols=list(_filter))

                click.echo(data.export(output_format))
            else:
                click_table_printer(headers, _filter, data)

        except Exception as e:
            logging.debug(traceback.format_exc())
            logging.debug(str(e))
            click.echo(
                click.style('Workflow status could not be retrieved: \n{}'
                            .format(str(e)), fg='red'),
                err=True)
    else:
        click.echo(
            click.style('Workflow name must be provided either with '
                        '`--workflow` option or with REANA_WORKON '
                        'environment variable',
                        fg='red'),
            err=True)


@click.option(
    '-o',
    '--organization',
    default=default_organization,
    help='Organization whose resources will be used.')
@click.option(
    '-w',
    '--workflow',
    default=os.environ.get('REANA_WORKON', None),
    callback=workflow_uuid_or_name,
    help='Name or UUID of the workflow whose logs should be fetched. '
         'Overrides value of REANA_WORKON.')
@click.option(
    '-t',
    '--token',
    default=os.environ.get('REANA_TOKEN', None),
    help='API token of the current user.')
@click.pass_context
def workflow_logs(ctx, organization, workflow, token):
    """Get status of previously created analysis workflow."""
    logging.debug('command: {}'.format(ctx.command_path.replace(" ", ".")))
    for p in ctx.params:
        logging.debug('{param}: {value}'.format(param=p, value=ctx.params[p]))

    if workflow:
        try:
            response = ctx.obj.client.get_workflow_logs(organization,
                                                        workflow, token)
            click.echo(response)
        except Exception as e:
            logging.debug(traceback.format_exc())
            logging.debug(str(e))
            click.echo(
                click.style('Workflow logs could not be retrieved: \n{}'
                            .format(str(e)), fg='red'),
                err=True)
    else:
        click.echo(
            click.style('Workflow name must be provided either with '
                        '`--workflow` option or with REANA_WORKON '
                        'environment variable',
                        fg='red'),
            err=True)


workflow.add_command(workflow_list)
workflow.add_command(workflow_create)
workflow.add_command(workflow_start)
workflow.add_command(workflow_status)
# workflow.add_command(workflow_logs)
