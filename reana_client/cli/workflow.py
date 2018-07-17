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
from jsonschema.exceptions import ValidationError
import tablib
import yaml

from ..config import ERROR_MESSAGES, default_organization, \
    reana_yaml_default_file_path
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
    '-at',
    '--access-token',
    default=os.environ.get('REANA_ACCESS_TOKEN', None),
    help='Access token of the current user.')
@click.option(
    '-v',
    '--verbose',
    count=True,
    help='Set status information verbosity.')
@click.pass_context
def workflow_list(ctx, organization, _filter, output_format, access_token,
                  verbose):
    """List all workflows user has."""
    logging.debug('command: {}'.format(ctx.command_path.replace(" ", ".")))
    for p in ctx.params:
        logging.debug('{param}: {value}'.format(param=p, value=ctx.params[p]))

    if not access_token:
        click.echo(
            click.style(ERROR_MESSAGES['missing_access_token'],
                        fg='red'), err=True)
        sys.exit(1)

    try:
        response = ctx.obj.client.get_all_workflows(organization, access_token)
        verbose_headers = ['id', 'user', 'organization']
        headers = ['name', 'run_number', 'created', 'status']
        if verbose:
            headers += verbose_headers
        data = []
        for workflow in response:
            name, run_number = get_workflow_name_and_run_number(
                workflow['name'])
            data.append(list(map(str, [name,
                                       run_number,
                                       workflow['created'],
                                       workflow['status']])))
            if verbose:
                data[-1] += [workflow[k] for k in verbose_headers]
        data = sorted(data, key=lambda x: int(x[1]))
        workflow_ids = ['{0}.{1}'.format(w[0], w[1]) for w in data]

        if os.getenv('REANA_WORKON', '') in workflow_ids:
            active_workflow_idx = \
                workflow_ids.index(os.getenv('REANA_WORKON', ''))
            for idx, row in enumerate(data):
                if idx == active_workflow_idx:
                    data[idx][headers.index('run_number')] += ' *'
                else:
                    data[idx].append(' ')

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
            click.style('Workflow list could not be retrieved: \n{}'
                        .format(str(e)), fg='red'),
            err=True)


@click.command(
    'create',
    help='Create a REANA compatible workflow from REANA '
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
    '-at',
    '--access-token',
    default=os.environ.get('REANA_ACCESS_TOKEN', None),
    help='Access token of the current user.')
@click.pass_context
def workflow_create(ctx, file, name, organization,
                    skip_validation, access_token):
    """Create a REANA compatible workflow from REANA spec file."""
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
    if not access_token:
        click.echo(
            click.style(ERROR_MESSAGES['missing_access_token'],
                        fg='red'), err=True)
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
                                                  access_token)
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
    help='Start previously created workflow.')
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
    '-at',
    '--access-token',
    default=os.environ.get('REANA_ACCESS_TOKEN', None),
    help='Access token of the current user.')
@click.pass_context
def workflow_start(ctx, organization, workflow, access_token):
    """Start previously created workflow."""
    logging.debug('command: {}'.format(ctx.command_path.replace(" ", ".")))
    for p in ctx.params:
        logging.debug('{param}: {value}'.format(param=p, value=ctx.params[p]))

    if not access_token:
        click.echo(
            click.style(ERROR_MESSAGES['missing_access_token'],
                        fg='red'), err=True)
        sys.exit(1)

    if workflow:
        try:
            logging.info('Connecting to {0}'.format(ctx.obj.client.server_url))
            response = ctx.obj.client.start_workflow(organization,
                                                     workflow,
                                                     access_token)
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
    help='Get status of a previously created workflow.')
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
    '-at',
    '--access-token',
    default=os.environ.get('REANA_ACCESS_TOKEN', None),
    help='Access token of the current user.')
@click.option(
    '-v',
    '--verbose',
    count=True,
    help='Set status information verbosity.')
@click.pass_context
def workflow_status(ctx, organization, workflow, _filter, output_format,
                    access_token, verbose):
    """Get status of previously created workflow."""
    logging.debug('command: {}'.format(ctx.command_path.replace(" ", ".")))
    for p in ctx.params:
        logging.debug('{param}: {value}'.format(param=p, value=ctx.params[p]))

    if not access_token:
        click.echo(
            click.style(ERROR_MESSAGES['missing_access_token'],
                        fg='red'), err=True)
        sys.exit(1)

    if workflow:
        try:
            response = ctx.obj.client.get_workflow_status(organization,
                                                          workflow,
                                                          access_token)
            verbose_headers = ['id', 'user', 'organization']
            headers = ['name', 'run_number', 'created',
                       'status', 'progress', 'command']
            if verbose:
                headers += verbose_headers
            data = []
            if isinstance(response, list):
                for workflow in response:
                    name, run_number = get_workflow_name_and_run_number(
                        workflow['name'])
                    current_command = workflow['progress']['current_command']
                    if current_command:
                        if current_command.startswith('bash -c "cd '):
                            current_command = current_command[
                                current_command.
                                index(';') + 2:-2]
                    else:
                        if 'command' in headers:
                            headers.remove('command')
                    data.append(list(map(
                        str,
                        [name,
                         run_number,
                         workflow['created'],
                         workflow['status'],
                         '{0}/{1}'.
                         format(
                             workflow['progress']['succeeded'],
                             workflow['progress']['total_jobs']),
                         current_command])))

                    if verbose:
                        data[-1] += [workflow.get(k) for k in verbose_headers]
            else:
                name, run_number = get_workflow_name_and_run_number(
                    response['name'])
                current_command = response['progress'].get('current_command')
                if current_command:
                    if current_command.startswith('bash -c "cd '):
                        current_command = current_command[
                            current_command.
                            index(';') + 2:-2]
                else:
                    if 'command' in headers:
                        headers.remove('command')
                data.append(list(
                    map(str,
                        [name,
                         run_number,
                         response['created'],
                         response['status'],
                         '{0}/{1}'.
                         format(
                             response['progress'].get('succeeded', '-'),
                             response['progress'].get('total_jobs', '-')),
                         current_command])))
                if verbose:
                    data[-1] += [response.get(k) for k in verbose_headers]

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
    '-at',
    '--access-token',
    default=os.environ.get('REANA_ACCESS_TOKEN', None),
    help='Access token of the current user.')
@click.pass_context
def workflow_logs(ctx, organization, workflow, access_token):
    """Get status of previously created workflow."""
    logging.debug('command: {}'.format(ctx.command_path.replace(" ", ".")))
    for p in ctx.params:
        logging.debug('{param}: {value}'.format(param=p, value=ctx.params[p]))

    if workflow:
        try:
            response = ctx.obj.client.get_workflow_logs(organization,
                                                        workflow, access_token)
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


@click.command('validate')
@click.option(
    '-f',
    '--file',
    type=click.Path(exists=True, resolve_path=True),
    default=reana_yaml_default_file_path,
    help='REANA specifications file describing the workflow and '
         'context which REANA should execute.')
@click.pass_context
def workflow_validate(ctx, file):
    """Validate given REANA specification file."""
    logging.debug('command: {}'.format(ctx.command_path.replace(" ", ".")))
    for p in ctx.params:
        logging.debug('{param}: {value}'.format(param=p, value=ctx.params[p]))
    try:
        load_reana_spec(click.format_filename(file))
        click.echo(
            click.style('File {filename} is a valid REANA specification file.'
                        .format(filename=click.format_filename(file)),
                        fg='green'))

    except ValidationError as e:
        logging.debug(traceback.format_exc())
        logging.debug(str(e))
        click.echo(click.style('{0} is not a valid REANA specification:\n{1}'
                               .format(click.format_filename(file),
                                       e.message),
                               fg='red'), err=True)
    except Exception as e:
        logging.debug(traceback.format_exc())
        logging.debug(str(e))
        click.echo(
            click.style('Something went wrong when trying to validate {}'
                        .format(file), fg='red'),
            err=True)


workflow.add_command(workflow_list)
workflow.add_command(workflow_create)
workflow.add_command(workflow_start)
workflow.add_command(workflow_status)
workflow.add_command(workflow_validate)
# workflow.add_command(workflow_logs)
