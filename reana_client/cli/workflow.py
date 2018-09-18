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
from jsonschema.exceptions import ValidationError
from reana_commons.utils import click_table_printer

from reana_client.decorators import with_api_client

from reana_client.config import ERROR_MESSAGES, reana_yaml_default_file_path
from reana_client.utils import (get_workflow_name_and_run_number, is_uuid_v4,
                                load_reana_spec, load_workflow_spec,
                                workflow_uuid_or_name)
from reana_client.cli.utils import add_access_token_options


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
    'workflows',
    help='List all available workflows.')
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
@add_access_token_options
@click.option(
    '-v',
    '--verbose',
    count=True,
    help='Set status information verbosity.')
@click.pass_context
@with_api_client
def workflow_workflows(ctx, _filter, output_format, access_token,
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
        response = ctx.obj.client.get_workflows(access_token)
        verbose_headers = ['id', 'user']
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
    '--skip-validation',
    is_flag=True,
    help="If set, specifications file is not validated before "
         "submitting it's contents to REANA server.")
@add_access_token_options
@click.pass_context
@with_api_client
def workflow_create(ctx, file, name, skip_validation, access_token):
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

        logging.info('Connecting to {0}'.format(ctx.obj.client.server_url))
        response = ctx.obj.client.create_workflow(reana_spec,
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
    help="""
    Start previously created workflow.

    The workflow execution can be further influenced by setting operational
    prameters using `-p` or `--parameter` option.  The option can be
    repetitive. For example, to disable caching for the Serial workflow
    engine, you can set ``-p CACHE=off``.
    """)
@click.option(
    '-w',
    '--workflow',
    default=os.environ.get('REANA_WORKON', None),
    callback=workflow_uuid_or_name,
    help='Name or UUID of the workflow to be started. '
         'Overrides value of REANA_WORKON.')
@add_access_token_options
@click.option(
    '-p', '--parameter',
    multiple=True,
    help='Optional operational parameters for the workflow execution. '
         'E.g. CACHE=off.',
)
@click.pass_context
@with_api_client
def workflow_start(ctx, workflow, access_token, parameter):  # noqa: D301
    """Start previously created workflow."""
    logging.debug('command: {}'.format(ctx.command_path.replace(" ", ".")))
    for p in ctx.params:
        logging.debug('{param}: {value}'.format(param=p, value=ctx.params[p]))

    if not access_token:
        click.echo(
            click.style(ERROR_MESSAGES['missing_access_token'],
                        fg='red'), err=True)
        sys.exit(1)

    parsed_parameters = {'parameters':
                         dict(p.split('=') for p in parameter)}

    if workflow:
        try:
            logging.info('Connecting to {0}'.format(ctx.obj.client.server_url))
            response = ctx.obj.client.start_workflow(workflow,
                                                     access_token,
                                                     parsed_parameters)
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
@add_access_token_options
@click.option(
    '-v',
    '--verbose',
    count=True,
    help='Set status information verbosity.')
@click.pass_context
@with_api_client
def workflow_status(ctx, workflow, _filter, output_format,
                    access_token, verbose):
    """Get status of previously created workflow."""
    def render_progress(finished_jobs, total_jobs):
        if total_jobs:
            return '{0}/{1}'.format(finished_jobs, total_jobs)
        else:
            return '-/-'

    def add_data_from_reponse(row, data, headers):
        name, run_number = get_workflow_name_and_run_number(
            row['name'])
        total_jobs = row['progress'].get('total')
        if total_jobs:
            total_jobs = total_jobs.get('total')
        else:
            total_jobs = 0
        finished_jobs = row['progress'].get('finished')
        if finished_jobs:
            finished_jobs = finished_jobs.get('total')
        else:
            finished_jobs = 0
        if row['progress']['total'].get('total') or 0 > 0:
            if 'progress' not in headers:
                headers += ['progress']

        data.append(list(map(
            str,
            [name,
             run_number,
             row['created'],
             row['status'],
             render_progress(finished_jobs, total_jobs)])))
        return data

    def add_verbose_data_from_response(response, verbose_headers,
                                       headers, data):
        for k in verbose_headers:
            if k == 'command':
                current_command = response['progress']['current_command']
                if current_command:
                    if current_command.startswith('bash -c "cd '):
                        current_command = current_command[
                            current_command.
                            index(';') + 2:-2]
                    data[-1] += [current_command]
                else:
                    if 'current_step_name' in response['progress'] and \
                            response['progress'].get('current_step_name'):
                        current_step_name = response['progress'].\
                            get('current_step_name')
                        data[-1] += [current_step_name]
                    else:
                        headers.remove('command')
            else:
                data[-1] += [response.get(k)]
        return data

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
            response = ctx.obj.client.get_workflow_status(workflow,
                                                          access_token)
            headers = ['name', 'run_number', 'created', 'status', 'progress']
            verbose_headers = ['id', 'user', 'command']
            data = []
            if not isinstance(response, list):
                response = [response]
            for workflow in response:
                add_data_from_reponse(workflow, data, headers)
                if verbose:
                    headers += verbose_headers
                    add_verbose_data_from_response(
                        workflow, verbose_headers,
                        headers, data)

            if output_format:
                tablib_data = tablib.Dataset()
                tablib_data.headers = headers
                for row in data:
                    tablib_data.append(row)

                if _filter:
                    tablib_data = tablib_data.subset(rows=None,
                                                     cols=list(_filter))

                click.echo(tablib_data.export(output_format))
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


@click.command(
    'logs',
    help='Get workflow logs.')
@click.option(
    '-w',
    '--workflow',
    default=os.environ.get('REANA_WORKON', None),
    callback=workflow_uuid_or_name,
    help='Name or UUID of the workflow whose logs should be fetched. '
         'Overrides value of REANA_WORKON.')
@add_access_token_options
@click.pass_context
@with_api_client
def workflow_logs(ctx, workflow, access_token):
    """Get workflow logs."""
    logging.debug('command: {}'.format(ctx.command_path.replace(" ", ".")))
    for p in ctx.params:
        logging.debug('{param}: {value}'.format(param=p, value=ctx.params[p]))

    if workflow:
        try:
            response = ctx.obj.client.get_workflow_logs(workflow, access_token)
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


@click.command(
    'validate',
    help='Validate the REANA specification.')
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


workflow.add_command(workflow_workflows)
workflow.add_command(workflow_create)
workflow.add_command(workflow_start)
workflow.add_command(workflow_validate)
workflow.add_command(workflow_status)
# workflow.add_command(workflow_logs)
