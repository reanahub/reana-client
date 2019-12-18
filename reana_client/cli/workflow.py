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
import time
import traceback

import click
import tablib
from jsonschema.exceptions import ValidationError
from reana_client.api.client import (close_interactive_session,
                                     create_workflow, current_rs_api_client,
                                     delete_workflow, diff_workflows,
                                     get_workflow_disk_usage,
                                     get_workflow_logs,
                                     get_workflow_parameters,
                                     get_workflow_status, get_workflows,
                                     open_interactive_session, start_workflow,
                                     stop_workflow)
from reana_client.cli.files import get_files, upload_files
from reana_client.cli.utils import (add_access_token_options,
                                    add_workflow_option, check_connection,
                                    filter_data, format_session_uri,
                                    parse_parameters)
from reana_client.config import (ERROR_MESSAGES, TIMECHECK,
                                 reana_yaml_default_file_path)
from reana_client.utils import (get_workflow_name_and_run_number,
                                get_workflow_status_change_msg, is_uuid_v4,
                                load_reana_spec,
                                validate_cwl_operational_options,
                                validate_input_parameters,
                                validate_serial_operational_options,
                                workflow_uuid_or_name)
from reana_commons.config import INTERACTIVE_SESSION_TYPES
from reana_commons.utils import click_table_printer


@click.group(help='Workflow management commands')
@click.pass_context
def workflow_management_group(ctx):
    """Top level wrapper for workflow management."""
    logging.debug(ctx.info_name)


@click.group(help='Workflow execution commands')
@click.pass_context
def workflow_execution_group(ctx):
    """Top level wrapper for execution related interaction."""
    logging.debug(ctx.info_name)


@workflow_management_group.command('list')
@click.option(
    '-s',
    '--sessions',
    is_flag=True,
    help='List all open interactive sessions.')
@click.option(
    '--format',
    '_filter',
    multiple=True,
    help='Format output according to column titles or column values '
         '(case-sensitive). Use `<colum_name>=<columnn_value>` format. For '
         'E.g. dislpay workflow with failed status and named test_workflow '
         '`--format status=failed,name=test_workflow`.')
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
@check_connection
@click.pass_context
def workflow_workflows(ctx, sessions, _filter, output_format, access_token,
                       show_all, verbose):  # noqa: D301
    """List all workflows and sessions.

    The `list` command lists workflows and sessions. By default, the list of
    workflows is returned. If you would like to see the list of your open
    interactive sessions, you need to pass the `--sessions` command-line
    option.

    Example: \n
    \t $ reana-client list --all \n
    \t $ reana-client list --sessions
    """
    logging.debug('command: {}'.format(ctx.command_path.replace(" ", ".")))
    for p in ctx.params:
        logging.debug('{param}: {value}'.format(param=p, value=ctx.params[p]))
    type = 'interactive' if sessions else 'batch'
    if _filter:
        parsed_filters = parse_parameters(_filter)
    try:
        response = get_workflows(access_token, type, bool(verbose))
        verbose_headers = ['id', 'user', 'size']
        headers = {
            'batch': ['name', 'run_number', 'created', 'status'],
            'interactive': ['name', 'run_number', 'created', 'session_type',
                            'session_uri']
        }
        if verbose:
            headers[type] += verbose_headers
        data = []
        for workflow in response:
            if workflow['status'] == 'deleted' and not show_all:
                continue
            name, run_number = get_workflow_name_and_run_number(
                workflow['name'])
            workflow['name'] = name
            workflow['run_number'] = run_number
            if type == 'interactive':
                workflow['session_uri'] = format_session_uri(
                    reana_server_url=ctx.obj.reana_server_url,
                    path=workflow['session_uri'],
                    access_token=access_token)
            data.append([str(workflow[k]) for k in headers[type]])
        data = sorted(data, key=lambda x: int(x[1]))
        workflow_ids = ['{0}.{1}'.format(w[0], w[1]) for w in data]
        if os.getenv('REANA_WORKON', '') in workflow_ids:
            active_workflow_idx = \
                workflow_ids.index(os.getenv('REANA_WORKON', ''))
            for idx, row in enumerate(data):
                if idx == active_workflow_idx:
                    data[idx][headers[type].index('run_number')] += ' *'
        tablib_data = tablib.Dataset()
        tablib_data.headers = headers[type]
        for row in data:
            tablib_data.append(row=row, tags=row)

        if _filter:
            tablib_data, filtered_headers = \
                filter_data(parsed_filters, headers[type], tablib_data)
            if output_format:
                click.echo(json.dumps(tablib_data))
            else:
                tablib_data = [list(item.values()) for item in tablib_data]
                click_table_printer(filtered_headers, filtered_headers,
                                    tablib_data)
        else:
            if output_format:
                click.echo(tablib_data.export(output_format))
            else:
                click_table_printer(headers[type], _filter, data)

    except Exception as e:
        logging.debug(traceback.format_exc())
        logging.debug(str(e))
        click.echo(
            click.style('Workflow list could not be retrieved: \n{}'
                        .format(str(e)), fg='red'),
            err=True)


@workflow_management_group.command('create')
@click.option(
    '-f',
    '--file',
    type=click.Path(exists=True, resolve_path=True),
    default=reana_yaml_default_file_path,
    help='REANA specifications file describing the workflow and '
         'context which REANA should execute.')
@click.option(
    '-n', '--name',
    '-w', '--workflow',
    default='',
    help='Optional name of the workflow. [default is "workflow"]')
@click.option(
    '--skip-validation',
    is_flag=True,
    help="If set, specifications file is not validated before "
         "submitting it's contents to REANA server.")
@add_access_token_options
@check_connection
@click.pass_context
def workflow_create(ctx, file, name,
                    skip_validation, access_token):  # noqa: D301
    """Create a new workflow.

    The `create` command allows to create a new workflow from reana.yaml
    specifications file. The file is expected to be located in the current
    working directory, or supplied via command-line -f option, see examples
    below.

    Examples: \n
    \t $ reana-client create\n
    \t $ reana-client create -w myanalysis\n
    \t $ reana-client create -w myanalysis -f myreana.yaml\n
    """
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


@workflow_execution_group.command('start')
@add_workflow_option
@add_access_token_options
@check_connection
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
    help='Additional operational options for the workflow execution. '
         'E.g. CACHE=off. (workflow engine - serial) '
         'E.g. --debug (workflow engine - cwl)',
)
@click.option(
    '--follow', 'follow',
    is_flag=True,
    default=False,
    help='If set, follows the execution of the workflow until termination.',
)
@click.pass_context
def workflow_start(ctx, workflow, access_token,
                   parameters, options, follow):  # noqa: D301
    """Start previously created workflow.

    The `start` command allows to start previously created workflow. The
    workflow execution can be further influenced by passing input prameters
    using `-p` or `--parameters` flag and by setting additional operational
    options using `-o` or `--options`.  The input parameters and operational
    options can be repetitive. For example, to disable caching for the Serial
    workflow engine, you can set `-o CACHE=off`.

    Examples: \n
    \t $ reana-client start -w myanalysis.42 -p sleeptime=10 -p myparam=4 \n
    \t $ reana-client start -w myanalysis.42 -p myparam1=myvalue1 -o CACHE=off
    """
    logging.debug('command: {}'.format(ctx.command_path.replace(" ", ".")))
    for p in ctx.params:
        logging.debug('{param}: {value}'.format(param=p, value=ctx.params[p]))

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
            current_status = get_workflow_status(workflow,
                                                 access_token).get('status')
            click.secho(
                get_workflow_status_change_msg(workflow, current_status),
                fg='green')
            if follow:
                while 'running' in current_status:
                    time.sleep(TIMECHECK)
                    current_status = get_workflow_status(
                        workflow, access_token).get('status')
                    click.secho(
                        get_workflow_status_change_msg(
                            workflow, current_status), fg='green')
                    if 'finished' in current_status:
                        if follow:
                            click.secho(
                                        '[INFO] Listing workflow output '
                                        'files...', bold=True)
                            ctx.invoke(get_files,
                                       workflow=workflow,
                                       access_token=access_token,
                                       output_format='url')
                        sys.exit(0)
                    elif 'failed' in current_status or \
                            'stopped' in current_status:
                        sys.exit(1)
        except Exception as e:
            logging.debug(traceback.format_exc())
            logging.debug(str(e))
            click.echo(
                click.style('Workflow could not be started: \n{}'
                            .format(str(e)), fg='red'),
                err=True)
            if 'invoked_by_subcommand' in ctx.parent.__dict__:
                sys.exit(1)


@workflow_execution_group.command('status')
@add_workflow_option
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
@check_connection
@click.option(
    '-v',
    '--verbose',
    count=True,
    help='Set status information verbosity.')
@click.pass_context
def workflow_status(ctx, workflow, _filter, output_format,
                    access_token, verbose):  # noqa: D301
    """Get status of a workflow.

    The `status` command allow to retrieve status of a workflow. The status can
    be created, queued, running, failed, etc. You can increase verbosity or
    filter retrieved information by passing appropriate command-line options.

    Examples: \n
    \t $ reana-client status -w myanalysis.42 \n
    \t $ reana-client status -w myanalysis.42 -v --json
    """
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


@workflow_execution_group.command('logs')
@add_workflow_option
@click.option(
    '--json',
    'json_format',
    count=True,
    help='Get output in JSON format.')
@add_access_token_options
@check_connection
@click.pass_context
def workflow_logs(ctx, workflow, access_token, json_format):  # noqa: D301
    """Get  workflow logs.

    The `logs` command allows to retrieve logs of running workflow. Note that
    only finished steps of the workflow are returned, the logs of the currently
    processed step is not returned until it is finished.

    Examples: \n
    \t $ reana-client logs -w myanalysis.42
    """
    logging.debug('command: {}'.format(ctx.command_path.replace(" ", ".")))
    for p in ctx.params:
        logging.debug('{param}: {value}'.format(param=p, value=ctx.params[p]))

    if workflow:
        try:
            response = get_workflow_logs(workflow, access_token)
            workflow_logs = json.loads(response['logs'])
            if json_format:
                click.echo(json.dumps(workflow_logs, indent=2))
                sys.exit(0)

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


@workflow_execution_group.command('validate')
@click.option(
    '-f',
    '--file',
    type=click.Path(exists=True, resolve_path=True),
    default=reana_yaml_default_file_path,
    help='REANA specifications file describing the workflow and '
         'context which REANA should execute.')
@click.pass_context
def workflow_validate(ctx, file):  # noqa: D301
    """Validate workflow specification file.

    The `validate` command allows to check syntax and validate the reana.yaml
    workflow specification file.

    Examples: \n
    \t $ reana-client validate -f reana.yaml
    """
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


@workflow_execution_group.command('stop')
@click.option(
    '--force',
    'force_stop',
    is_flag=True,
    default=False,
    help='Stop a workflow without waiting for jobs to finish.')
@add_workflow_option
@add_access_token_options
@check_connection
@click.pass_context
def workflow_stop(ctx, workflow, force_stop, access_token):  # noqa: D301
    """Stop a running workflow.

    The `stop` command allows to hard-stop the running workflow process. Note
    that soft-stopping of the workflow is currently not supported. This command
    should be therefore used with care, only if you are absolutely sure that
    there is no point in continuing the running the workflow.

    Example: \n
    \t $ reana-client stop -w myanalysis.42 --force
    """
    if not force_stop:
        click.secho('Graceful stop not implement yet. If you really want to '
                    'stop your workflow without waiting for jobs to finish'
                    ' use: --force option', fg='red')
        raise click.Abort()

    if workflow:
        try:
            logging.info(
                'Sending a request to stop workflow {}'.format(workflow))
            response = stop_workflow(workflow, force_stop, access_token)
            click.secho(
                get_workflow_status_change_msg(workflow, 'stopped'),
                fg='green')
        except Exception as e:
            logging.debug(traceback.format_exc())
            logging.debug(str(e))
            click.secho('Workflow could not be stopped: \n{}'.format(str(e)),
                        fg='red', err=True)


@workflow_execution_group.command('run')
@click.option(
    '-f',
    '--file',
    type=click.Path(exists=True, resolve_path=True),
    default=reana_yaml_default_file_path,
    help='REANA specifications file describing the workflow and '
         'context which REANA should execute.')
@click.option(
    '-n', '--name',
    '-w', '--workflow',
    default='',
    help='Optional name of the workflow. [default is "workflow"]')
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
@click.option(
    '--follow', 'follow',
    is_flag=True,
    default=False,
    help='If set, follows the execution of the workflow until termination.',
)
@add_access_token_options
@check_connection
@click.pass_context
def workflow_run(ctx, file, name, skip_validation,
                 access_token, parameters, options, follow):  # noqa: D301
    """Shortcut to create, upload, start a new workflow.

    The `run` command allows to create a new workflow, upload its input files
    and start it in one command.

    Examples: \n
    \t $ reana-client run -w myanalysis-test-small -p myparam=mysmallvalue \n
    \t $ reana-client run -w myanalysis-test-big -p myparam=mybigvalue
    """
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
               filenames=None,
               access_token=access_token)
    click.secho('[INFO] Starting workflow...', bold=True)
    ctx.invoke(workflow_start,
               workflow=ctx.workflow_name,
               access_token=access_token,
               parameters=parameters,
               options=options,
               follow=follow)


@workflow_management_group.command('delete')
@click.option(
    '--include-all-runs',
    'all_runs',
    count=True,
    help='Delete all runs of a given workflow.')
@click.option(
    '--include-workspace',
    'workspace',
    count=True,
    help='Delete workspace from REANA.')
@click.option(
    '--include-records',
    'hard_delete',
    count=True,
    help='Delete all records of workflow, including database entries and'
         ' workspace.'
)
@add_workflow_option
@add_access_token_options
@check_connection
@click.pass_context
def workflow_delete(ctx, workflow, all_runs, workspace,
                    hard_delete, access_token):  # noqa: D301
    """Delete a workflow.

    The `delete` command allows to remove workflow runs from the database and
    the workspace. By default, the command removes the workflow and all its
    cached information and hides the workflow from the workflow list. Note that
    workflow workspace will still be accessible until you use
    `--include-workspace` flag. Note also that you can remove all past runs of
    a workflow by specifying `--include-all-runs` flag.

    Example: \n
    \t $ reana-client delete -w myanalysis.42 \n
    \t $ reana-client delete -w myanalysis.42 --include-records
    """
    logging.debug('command: {}'.format(ctx.command_path.replace(" ", ".")))
    for p in ctx.params:
        logging.debug('{param}: {value}'.format(param=p, value=ctx.params[p]))

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
                message = get_workflow_status_change_msg(workflow,
                                                         'deleted')
            click.secho(message, fg='green')

        except Exception as e:
            logging.debug(traceback.format_exc())
            logging.debug(str(e))
            click.echo(
                click.style('Workflow could not be deleted: \n{}'
                            .format(str(e)), fg='red'),
                err=True)


@workflow_management_group.command('diff')
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
@check_connection
@click.pass_context
def workflow_diff(ctx, workflow_a, workflow_b, brief,
                  access_token, context_lines):  # noqa: D301
    """Show diff between two workflows.

    The `diff` command allows to compare two workflows, the workflow_a and
    workflow_b, which must be provided as arguments. The output will show the
    difference in workflow run parameters, the generated files, the logs, etc.

    Examples: \n
    \t $ reana-client diff myanalysis.42 myotheranalysis.43 \n
    \t $ reana-client diff myanalysis.42 myotheranalysis.43 --brief
    """
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


@click.group(help='Workspace interactive commands')
def interactive_group():
    """Workspace interactive commands."""
    pass


@interactive_group.command('open')
@add_workflow_option
@click.argument(
    'interactive-session-type',
    metavar='interactive-session-type',
    type=click.Choice(INTERACTIVE_SESSION_TYPES))
@click.option(
    '-i',
    '--image',
    help='Docker image which will be used to spawn the interactive session. '
         'Overrides the default image for the selected type.')
@add_access_token_options
@check_connection
@click.pass_context
def workflow_open_interactive_session(ctx, workflow, interactive_session_type,
                                      image, access_token):  # noqa: D301
    """Open an interactive session inside the workspace.

    The `open` command allows to open interactive session processes on top of
    the workflow workspace, such as Jupyter notebooks. This is useful to
    quickly inspect and analyse the produced files while the workflow is stlil
    running.

    Examples:\n
    \t $ reana-client open -w myanalysis.42 jupyter
    """
    if workflow:
        try:
            logging.info(
                "Opening an interactive session on {}".format(workflow))
            interactive_session_configuration = {
                "image": image or None,
            }
            path = open_interactive_session(workflow, access_token,
                                            interactive_session_type,
                                            interactive_session_configuration)
            click.secho(format_session_uri(
                reana_server_url=ctx.obj.reana_server_url,
                path=path, access_token=access_token), fg="green")
            click.echo("It could take several minutes to start the "
                       "interactive session.")
        except Exception as e:
            logging.debug(traceback.format_exc())
            logging.debug(str(e))
            click.secho("Interactive session could not be opened: \n{}"
                        .format(str(e)), fg='red', err=True)
    else:
        click.secho("Workflow {} does not exist".format(workflow),
                    fg="red", err=True)


@interactive_group.command('close')
@add_workflow_option
@add_access_token_options
@check_connection
def workflow_close_interactive_session(workflow, access_token):  # noqa: D301
    """Close an interactive session.

    The `close` command allows to shut down any interactive sessions that you
    may have running. You would typically use this command after you finished
    exploring data in the Jupyter notebook and after you have transferred any
    code created in your interactive session.

    Examples:\n
    \t $ reana-client close -w myanalysis.42
    """
    if workflow:
        try:
            logging.info(
                "Closing an interactive session on {}".format(workflow))
            close_interactive_session(workflow, access_token)
            click.echo("Interactive session for workflow {}"
                       " was successfully closed".format(workflow))
        except Exception as e:
            logging.debug(traceback.format_exc())
            logging.debug(str(e))
            click.secho("Interactive session could not be closed: \n{}"
                        .format(str(e)), fg='red', err=True)
    else:
            click.secho("Workflow {} does not exist".format(workflow),
                        fg="red", err=True)
