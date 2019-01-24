# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2017, 2018 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
"""REANA client workflow related commands."""

import json
import logging
import os
import sys
import traceback
from enum import Enum

import click
import tablib
from jsonschema.exceptions import ValidationError

from reana_client.api.client import (create_workflow, current_rs_api_client,
                                     delete_workflow, diff_workflows,
                                     get_workflow_logs,
                                     get_workflow_parameters,
                                     get_workflow_status, get_workflows,
                                     start_workflow, stop_workflow)
from reana_client.cli.files import upload_files
from reana_client.cli.utils import add_access_token_options
from reana_client.config import ERROR_MESSAGES, reana_yaml_default_file_path
from reana_client.utils import (get_workflow_name_and_run_number, is_uuid_v4,
                                load_reana_spec,
                                validate_cwl_operational_options,
                                validate_input_parameters,
                                validate_serial_operational_options,
                                workflow_uuid_or_name)
from reana_commons.errors import MissingAPIClientConfiguration
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
@click.option(
    '--all',
    'show_all',
    count=True,
    help='Show all workflows including deleted ones.'
)
@click.option(
    '-v',
    '--verbose',
    count=True,
    help='Set status information verbosity.')
@add_access_token_options
@click.pass_context
def workflow_workflows(ctx, _filter, output_format, access_token,
                       show_all, verbose):
    """List all workflows user has."""
    logging.debug('command: {}'.format(ctx.command_path.replace(" ", ".")))
    for p in ctx.params:
        logging.debug('{param}: {value}'.format(param=p, value=ctx.params[p]))

    try:
        _url = current_rs_api_client.swagger_spec.api_url
    except MissingAPIClientConfiguration as e:
        click.secho(
            'REANA client is not connected to any REANA cluster.',
            fg='red', err=True
        )
        sys.exit(1)
    if not access_token:
        click.echo(
            click.style(ERROR_MESSAGES['missing_access_token'],
                        fg='red'), err=True)
        sys.exit(1)

    try:
        response = get_workflows(access_token)
        verbose_headers = ['id', 'user']
        headers = ['name', 'run_number', 'created', 'status']
        if verbose:
            headers += verbose_headers
        data = []
        for workflow in response:
            if workflow['status'] == 'deleted' and not show_all:
                continue
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
        reana_specification = load_reana_spec(click.format_filename(file),
                                              skip_validation)
        logging.info('Connecting to {0}'.format(
            current_rs_api_client.swagger_spec.api_url))
        response = create_workflow(reana_specification,
                                   name,
                                   access_token)
        click.echo(click.style(response['workflow_name'], fg='green'))
        # check if command is called from wrapper command
        if 'invoked_by_subcommand' in ctx.parent.__dict__:
            ctx.parent.workflow_name = response['workflow_name']
    except Exception as e:
        logging.debug(traceback.format_exc())
        logging.debug(str(e))
        click.echo(
            click.style('Workflow could not be created: \n{}'
                        .format(str(e)), fg='red'),
            err=True)
        if 'invoked_by_subcommand' in ctx.parent.__dict__:
            sys.exit(1)


@click.command(
    'start',
    help="""
    Start previously created workflow.

    The workflow execution can be further influenced by setting input prameters
    using `-p` or `--parameters` flag or by setting operational options using
    `-o` or `--options`.  The input parameters and operational options can be
    repetitive. For example, to disable caching for the Serial workflow engine,
    you can set ``-o CACHE=off``.
    """)
@click.option(
    '-w',
    '--workflow',
    default=os.environ.get('REANA_WORKON', None),
    callback=workflow_uuid_or_name,
    help='Name or UUID of the workflow to be started. '
         'Overrides value of REANA_WORKON environment variable.')
@add_access_token_options
@click.option(
    '-p', '--parameter', 'parameters',
    multiple=True,
    help='Additional input parameters to override '
         'original ones from reana.yaml. '
         'E.g. -p myparam1=myval1 -p myparam2=myval2.',
)
@click.option(
    '-o', '--option', 'options',
    multiple=True,
    help='Additional operatioal options for the workflow execution. '
         'E.g. CACHE=off. (workflow engine - serial) '
         'E.g. --debug (workflow engine - cwl)',
)
@click.pass_context
def workflow_start(ctx, workflow, access_token,
                   parameters, options):  # noqa: D301
    """Start previously created workflow."""
    logging.debug('command: {}'.format(ctx.command_path.replace(" ", ".")))
    for p in ctx.params:
        logging.debug('{param}: {value}'.format(param=p, value=ctx.params[p]))

    if not access_token:
        click.echo(
            click.style(ERROR_MESSAGES['missing_access_token'],
                        fg='red'), err=True)
        sys.exit(1)
    parsed_parameters = {'input_parameters':
                         dict(p.split('=') for p in parameters)}
    parsed_parameters['operational_options'] = ' '.join(options).split()
    if workflow:
        if parameters or options:
            try:
                response = get_workflow_parameters(workflow, access_token)
                if response['type'] == 'cwl':
                    validate_cwl_operational_options(
                        parsed_parameters['operational_options'])
                if response['type'] == 'serial':
                    parsed_parameters['operational_options'] = \
                        validate_serial_operational_options(
                            parsed_parameters['operational_options'])
                parsed_parameters['input_parameters'] = \
                    validate_input_parameters(
                        parsed_parameters['input_parameters'],
                        response['parameters'])
            except Exception as e:
                click.echo(
                    click.style('Could not apply given input parameters: '
                                '{0} \n{1}'.format(parameters, str(e))),
                    err=True)

        try:
            logging.info('Connecting to {0}'.format(
                current_rs_api_client.swagger_spec.api_url))
            response = start_workflow(workflow,
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
            if 'invoked_by_subcommand' in ctx.parent.__dict__:
                sys.exit(1)
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
         'Overrides value of REANA_WORKON environment variable.')
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
            response = get_workflow_status(workflow, access_token)
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


@click.command(
    'logs',
    help='Get workflow logs.')
@click.option(
    '-w',
    '--workflow',
    default=os.environ.get('REANA_WORKON', None),
    callback=workflow_uuid_or_name,
    help='Name or UUID of the workflow whose logs should be fetched. '
         'Overrides value of REANA_WORKON environment variable.')
@add_access_token_options
@click.pass_context
def workflow_logs(ctx, workflow, access_token):
    """Get workflow logs."""
    logging.debug('command: {}'.format(ctx.command_path.replace(" ", ".")))
    for p in ctx.params:
        logging.debug('{param}: {value}'.format(param=p, value=ctx.params[p]))

    if workflow:
        try:
            response = get_workflow_logs(workflow, access_token)
            workflow_logs = json.loads(response['logs'])
            if workflow_logs.get('workflow_logs', None):
                click.secho('workflow engine logs'.upper(), fg='green')
                click.echo(workflow_logs['workflow_logs'])

            first = True
            for job_id, job_logs in workflow_logs['job_logs'].items():
                if job_logs:
                    if first:
                        click.echo('\n')
                        click.secho('job logs'.upper(), fg='green')
                        first = False
                    click.secho('job id: {}'.format(job_id), fg='green')
                    click.echo(job_logs)
            if workflow_logs.get('engine_specific', None):
                click.echo('\n')
                click.secho('engine internal logs'.upper(), fg='green')
                click.secho(workflow_logs['engine_specific'])

        except Exception as e:
            logging.debug(traceback.format_exc())
            logging.debug(str(e))
            click.echo(
                click.style('Workflow status could not be retrieved: \n{}'
                            .format(str(e)), fg='red'),
                err=True)
            click.echo(response)
        except Exception as e:
            logging.debug(traceback.format_exc())
            logging.debug(str(e))
            click.echo(
                click.style('Workflow logs could not be retrieved: \n{}'
                            .format(str(e)), fg='red'),
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


@click.command(
    'stop',
    help='Stop a running workflow')
@click.option(
    '--force',
    'force_stop',
    is_flag=True,
    default=False,
    help='Stop a workflow without waiting for jobs to finish.')
@click.option(
    '-w',
    '--workflow',
    default=os.environ.get('REANA_WORKON', None),
    callback=workflow_uuid_or_name,
    help='Name and run number to be stopped. '
         'Overrides value of REANA_WORKON environment variable.')
@add_access_token_options
@click.pass_context
def workflow_stop(ctx, workflow, force_stop, access_token):
    """Stop given workflow."""
    if not force_stop:
        click.secho('Graceful stop not implement yet. If you really want to '
                    'stop your workflow without waiting for jobs to finish'
                    ' use: --force option', fg='red')
        raise click.Abort()

    if not access_token:
        click.secho(
            ERROR_MESSAGES['missing_access_token'], fg='red', err=True)
        sys.exit(1)

    if workflow:
        try:
            logging.info(
                'Sending a request to stop workflow {}'.format(workflow))
            response = stop_workflow(workflow, force_stop, access_token)
            click.secho('{} has been stopped.'.format(workflow), fg='green')
        except Exception as e:
            logging.debug(traceback.format_exc())
            logging.debug(str(e))
            click.secho('Workflow could not be stopped: \n{}'.format(str(e)),
                        fg='red', err=True)


@click.command(
    'run',
    help='Create, upload and start the REANA workflow.')
@click.option(
    '-f',
    '--file',
    type=click.Path(exists=True, resolve_path=True),
    default=reana_yaml_default_file_path,
    help='REANA specifications file describing the workflow and '
         'context which REANA should execute.')
@click.argument(
    'filenames',
    metavar='SOURCES',
    type=click.Path(exists=True, resolve_path=True),
    nargs=-1)
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
@click.option(
    '-p', '--parameter', 'parameters',
    multiple=True,
    help='Additional input parameters to override '
         'original ones from reana.yaml. '
         'E.g. -p myparam1=myval1 -p myparam2=myval2.',
)
@click.option(
    '-o', '--option', 'options',
    multiple=True,
    help='Additional operatioal options for the workflow execution. '
         'E.g. CACHE=off.',
)
@add_access_token_options
@click.pass_context
def workflow_run(ctx, file, filenames, name, skip_validation,
                 access_token, parameters, options):
    """Create, upload and start wrapper command."""
    # set context parameters for subcommand
    ctx.invoked_by_subcommand = True
    ctx.workflow_name = ""
    click.secho('[INFO] Creating a workflow...', bold=True)
    ctx.invoke(workflow_create,
               file=file,
               name=name,
               skip_validation=skip_validation,
               access_token=access_token)
    click.secho('[INFO] Uploading files...', bold=True)
    ctx.invoke(upload_files,
               workflow=ctx.workflow_name,
               filenames=filenames,
               access_token=access_token)
    click.secho('[INFO] Starting workflow...', bold=True)
    ctx.invoke(workflow_start,
               workflow=ctx.workflow_name,
               access_token=access_token,
               parameters=parameters,
               options=options)


@click.command(
    'delete',
    help='Delete a workflow run. By default removes all cached'
         ' information of the given workflow and hides it from'
         ' the workflow list.\n'
         'Workspaces of deleted workflows'
         ' are accessible to retrieve files, to remove the workspace'
         ' too pass --include-workspace flag.\n'
         'By passing --include-all-runs all workflows with the same'
         ' will be deleted.\n'
         'The --include-records flag will delete'
         ' all workflow data from the database and remove its workspace.')
@click.option(
    '--include-all-runs',
    'all_runs',
    count=True,
    help='Delete all runs of a given workflow.')
@click.option(
    '--include-workspace',
    'workspace',
    count=True,
    help='Delete workflow workspace from REANA.')
@click.option(
    '--include-records',
    'hard_delete',
    count=True,
    help='Delete all records of workflow, including database entries and'
         ' workspace.'
)
@click.option(
    '-w',
    '--workflow',
    default=os.environ.get('REANA_WORKON', None),
    callback=workflow_uuid_or_name,
    help='Name and run number to be deleted. '
         'Overrides value of REANA_WORKON environment variable.')
@add_access_token_options
@click.pass_context
def workflow_delete(ctx, workflow, all_runs, workspace,
                    hard_delete, access_token):
    """Delete a workflow run given the workflow name and run number."""
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
            logging.info('Connecting to {0}'.format(
                current_rs_api_client.swagger_spec.api_url))
            response = delete_workflow(workflow,
                                       all_runs,
                                       hard_delete,
                                       workspace,
                                       access_token)
            if all_runs:
                message = 'All workflows named \'{}\' have been deleted.'.\
                    format(workflow.split('.')[0])
            else:
                message = '{} has been deleted.'.format(workflow)
            click.secho(message,
                        fg='green')

        except Exception as e:
            logging.debug(traceback.format_exc())
            logging.debug(str(e))
            click.echo(
                click.style('Workflow could not be deleted: \n{}'
                            .format(str(e)), fg='red'),
                err=True)


@click.command(
    'diff',
    help='Show differences between two workflows.')
@click.argument(
    'workflow_a',
    default=os.environ.get('REANA_WORKON', None),
    callback=workflow_uuid_or_name)
@click.argument(
    'workflow_b',
    callback=workflow_uuid_or_name)
@click.option(
    '-q',
    '--brief',
    is_flag=True,
    help="If not set, differences in the contents of the files in the two"
         "workspaces are shown.")
@click.option(
    '-u',
    '-U',
    '--unified',
    'context_lines',
    type=int,
    default=5,
    help="Sets number of context lines for workspace diff output.")
@add_access_token_options
@click.pass_context
def workflow_diff(ctx, workflow_a, workflow_b, brief,
                  access_token, context_lines):
    """Show diff between two worklows."""
    logging.debug('command: {}'.format(ctx.command_path.replace(" ", ".")))
    for p in ctx.params:
        logging.debug('{param}: {value}'.format(param=p, value=ctx.params[p]))

    def print_color_diff(lines):
        for line in lines:
            line_color = None
            if line[0] == '@':
                line_color = 'cyan'
            elif line[0] == '-':
                line_color = 'red'
            elif line[0] == '+':
                line_color = 'green'
            click.secho(line, fg=line_color)
    try:
        response = diff_workflows(workflow_a, workflow_b, brief, access_token,
                                  str(context_lines))
        if response.get('reana_specification'):
            specification_diff = json.loads(response['reana_specification'])
            nonempty_sections = {k: v for k, v in specification_diff.items()
                                 if v}
            if nonempty_sections:
                click.echo('differences in reana specification:'.upper())
            else:
                click.echo('No differences in reana specifications.')
            for section, content in nonempty_sections.items():
                click.echo('In {}:'.format(section))
                print_color_diff(content)
        click.echo('')  # Leave 1 line for separation
        if response.get('workspace_listing'):
            workspace_diff = json.loads(response.get('workspace_listing')).\
                splitlines()
            click.echo('differences in workspace listings:'.upper())
            print_color_diff(workspace_diff)

    except Exception as e:
        logging.debug(traceback.format_exc())
        logging.debug(str(e))
        click.echo(
            click.style('Something went wrong when trying to get diff:\n{}'.
                        format(str(e)), fg='red'),
            err=True)


workflow.add_command(workflow_workflows)
workflow.add_command(workflow_create)
workflow.add_command(workflow_start)
workflow.add_command(workflow_validate)
workflow.add_command(workflow_status)
workflow.add_command(workflow_stop)
workflow.add_command(workflow_run)
workflow.add_command(workflow_delete)
workflow.add_command(workflow_diff)
workflow.add_command(workflow_logs)
