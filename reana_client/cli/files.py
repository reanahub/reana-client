# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2017, 2018 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
"""REANA client output related commands."""

import json
import logging
import os
import sys
import traceback

import click
import tablib
from reana_commons.errors import MissingAPIClientConfiguration
from reana_commons.utils import click_table_printer

from reana_client.api.client import (current_rs_api_client, delete_file,
                                     download_file, get_workflow_status,
                                     list_files, mv_files, upload_to_server)
from reana_client.cli.utils import (add_access_token_options, filter_data,
                                    parse_parameters)
from reana_client.config import ERROR_MESSAGES
from reana_client.errors import FileDeletionError, FileUploadError
from reana_client.utils import get_workflow_root, load_reana_spec


@click.group(
    help='All interaction related to files.')
@click.pass_context
def files(ctx):
    """Top level wrapper for files related interactions."""
    logging.debug(ctx.info_name)


@click.command(
    'ls',
    help='List workflow workspace files.')
@click.option(
    '-w',
    '--workflow',
    default=os.environ.get('REANA_WORKON', None),
    help='Name or UUID of the workflow whose files should be listed. '
         'Overrides value of REANA_WORKON environment variable.')
@click.option(
    '--format',
    '_filter',
    multiple=True,
    help='Format output according to column titles or column values '
         '(case-sensitive). Use `<colum_name>=<columnn_value>` format. For '
         'E.g. dislpay FILES named data.txt '
         '`--format name=data.txt`.')
@click.option(
    '--json',
    'output_format',
    flag_value='json',
    default=None,
    help='Get output in JSON format.')
@add_access_token_options
@click.pass_context
def get_files(ctx, workflow, _filter,
              output_format, access_token):
    """List workflow workspace files."""
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
    if _filter:
        parsed_filters = parse_parameters(_filter)
    if workflow:
        logging.info('Workflow "{}" selected'.format(workflow))
        try:
            response = list_files(workflow, access_token)
            headers = ['name', 'size', 'last-modified']
            data = []
            for file_ in response:
                data.append(list(map(str, [file_['name'],
                                           file_['size'],
                                           file_['last-modified']])))
            tablib_data = tablib.Dataset()
            tablib_data.headers = headers
            for row in data:
                    tablib_data.append(row)
            if _filter:
                tablib_data, filtered_headers = \
                    filter_data(parsed_filters, headers, tablib_data)
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
                    click_table_printer(headers, _filter, data)

        except Exception as e:
            logging.debug(traceback.format_exc())
            logging.debug(str(e))

            click.echo(
                click.style('Something went wrong while retrieving file list'
                            ' for workflow {0}:\n{1}'.format(workflow,
                                                             str(e)),
                            fg='red'),
                err=True)
    else:
        click.echo(
            click.style('Workflow name must be provided either with '
                        '`--workflow` option or with REANA_WORKON '
                        'environment variable',
                        fg='red'),
            err=True)


@click.command(
    'download',
    help='Download all output files declared in the reana.yaml'
         'specification or download files listed as '
         'FILE command-line arguments. Note that downloading directories'
         ' is not yet supported.')
@click.argument(
    'filenames',
    metavar='FILES',
    nargs=-1)
@click.option(
    '-w',
    '--workflow',
    default=os.environ.get('REANA_WORKON', None),
    help='Name or UUID of that workflow where files should downloaded from. '
         'Overrides value of REANA_WORKON environment variable.')
@click.option(
    '-o',
    '--output-directory',
    default=os.getcwd(),
    help='Path to the directory where files will be downloaded.')
@add_access_token_options
@click.pass_context
def download_files(ctx, workflow, filenames, output_directory, access_token):
    """Download workflow workspace file(s)."""
    logging.debug('command: {}'.format(ctx.command_path.replace(" ", ".")))
    for p in ctx.params:
        logging.debug('{param}: {value}'.format(param=p, value=ctx.params[p]))

    if not access_token:
        click.echo(
            click.style(ERROR_MESSAGES['missing_access_token'],
                        fg='red'), err=True)
        sys.exit(1)

    if not filenames:
        reana_spec = load_reana_spec(os.path.join(get_workflow_root(),
                                     'reana.yaml'),
                                     False)
        if 'outputs' in reana_spec:
            filenames = reana_spec['outputs'].get('files') or []

    if workflow:
        for file_name in filenames:
            try:
                binary_file = download_file(workflow,
                                            file_name,
                                            access_token)

                logging.info('{0} binary file downloaded ... writing to {1}'.
                             format(file_name, output_directory))

                outputs_file_path = os.path.join(output_directory, file_name)
                if not os.path.exists(os.path.dirname(outputs_file_path)):
                    os.makedirs(os.path.dirname(outputs_file_path))

                with open(outputs_file_path, 'wb') as f:
                    f.write(binary_file)
                click.secho(
                    'File {0} downloaded to {1}.'.format(
                        file_name, output_directory),
                    fg='green')
            except OSError as e:
                logging.debug(traceback.format_exc())
                logging.debug(str(e))
                click.echo(
                    click.style('File {0} could not be written.'.
                                format(file_name),
                                fg='red'), err=True)
            except Exception as e:
                logging.debug(traceback.format_exc())
                logging.debug(str(e))
                click.echo(click.style('File {0} could not be downloaded: {1}'.
                                       format(file_name, e), fg='red'),
                           err=True)
    else:
        click.echo(
            click.style('Workflow name must be provided either with '
                        '`--workflow` option or with REANA_WORKON '
                        'environment variable',
                        fg='red'),
            err=True)


@click.command(
    'upload',
    help='Upload all input sources declared in the reana.yaml'
         'specification or upload files and directories listed as '
         'SOURCE command-line arguments. If a symbolic link is provided,'
         ' it is resolved and a hard copy is uploaded.')
@click.argument(
    'filenames',
    metavar='SOURCES',
    type=click.Path(exists=True, resolve_path=True),
    nargs=-1)
@click.option(
    '-w',
    '--workflow',
    default=os.environ.get('REANA_WORKON', None),
    help='Name or UUID of the workflow you are uploading files for. '
         'Overrides value of REANA_WORKON environment variable.')
@add_access_token_options
@click.pass_context
def upload_files(ctx, workflow, filenames, access_token):
    """Upload files and directories to workflow workspace."""
    logging.debug('command: {}'.format(ctx.command_path.replace(" ", ".")))
    for p in ctx.params:
        logging.debug('{param}: {value}'.format(param=p, value=ctx.params[p]))

    if not access_token:
        click.echo(
            click.style(ERROR_MESSAGES['missing_access_token'], fg='red'),
            err=True)
        sys.exit(1)

    if not filenames:
        reana_spec = load_reana_spec(os.path.join(get_workflow_root(),
                                     'reana.yaml'),
                                     False)
        if 'inputs' in reana_spec:
            filenames = []
            filenames += [os.path.join(get_workflow_root(), f)
                          for f in reana_spec['inputs'].get('files') or []]
            filenames += [os.path.join(get_workflow_root(), d)
                          for d in reana_spec['inputs'].
                          get('directories') or []]

    if workflow:
        for filename in filenames:
            try:
                response = upload_to_server(workflow,
                                            filename,
                                            access_token)
                for file_ in response:
                    if file_.startswith('symlink:'):
                        click.echo(
                            click.style('Symlink resolved to {}. Uploaded'
                                        ' hard copy.'.
                                        format(file_[len('symlink:'):]),
                                        fg='green'))
                    else:
                        click.echo(
                            click.style('File {} was successfully uploaded.'.
                                        format(file_), fg='green'))
            except FileNotFoundError as e:
                logging.debug(traceback.format_exc())
                logging.debug(str(e))
                click.echo(
                    click.style(
                        'File {0} could not be uploaded: {0} does not exist.'.
                        format(filename),
                        fg='red'),
                    err=True)
                if 'invoked_by_subcommand' in ctx.parent.__dict__:
                    sys.exit(1)
            except FileUploadError as e:
                logging.debug(traceback.format_exc())
                logging.debug(str(e))
                click.echo(
                    click.style(
                        'Something went wrong while uploading {0}.\n{1}'.
                        format(filename, str(e)),
                        fg='red'),
                    err=True)
                if 'invoked_by_subcommand' in ctx.parent.__dict__:
                    sys.exit(1)
            except Exception as e:
                logging.debug(traceback.format_exc())
                logging.debug(str(e))
                click.echo(
                    click.style(
                        'Something went wrong while uploading {}'.
                        format(filename),
                        fg='red'),
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
    'rm',
    help='Delete the specified file or pattern.')
@click.argument(
    'filenames',
    metavar='SOURCES',
    nargs=-1)
@click.option(
    '-w',
    '--workflow',
    default=os.environ.get('REANA_WORKON', None),
    help='Name or UUID of the workflow you are deleting files for. '
         'Overrides value of REANA_WORKON environment variable.')
@add_access_token_options
@click.pass_context
def delete_files(ctx, workflow, filenames, access_token):
    """Delete files contained in the workflow workspace."""
    logging.debug('command: {}'.format(ctx.command_path.replace(" ", ".")))
    for p in ctx.params:
        logging.debug('{param}: {value}'.format(param=p, value=ctx.params[p]))

    if not access_token:
        click.echo(
            click.style(ERROR_MESSAGES['missing_access_token'], fg='red'),
            err=True)
        sys.exit(1)

    if workflow:
        for filename in filenames:
            try:
                response = delete_file(workflow, filename, access_token)
                freed_space = 0
                for file_ in response['deleted']:
                    freed_space += response['deleted'][file_]['size']
                    click.echo(click.style(
                        'File {} was successfully deleted.'.
                        format(file_), fg='green'))
                for file_ in response['failed']:
                    click.echo(
                        click.style(
                            'Something went wrong while deleting {}.\n{}'.
                            format(file_, response['failed'][file_]['error']),
                            fg='red'), err=True)
                if freed_space:
                    click.echo(click.style('{} bytes freed up.'.format(
                        freed_space), fg='green'))
            except FileDeletionError as e:
                click.echo(click.style(str(e), fg='red'), err=True)
                if 'invoked_by_subcommand' in ctx.parent.__dict__:
                    sys.exit(1)
            except Exception as e:
                logging.debug(traceback.format_exc())
                logging.debug(str(e))
                click.echo(
                    click.style(
                        'Something went wrong while deleting {}'.
                        format(filename),
                        fg='red'),
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


@click.command('mv')
@click.argument('source')
@click.argument('target')
@click.option(
    '-w',
    '--workflow',
    default=os.environ.get('REANA_WORKON', None),
    help='Name or UUID of the workflow you are moving files for. '
         'Overrides value of REANA_WORKON environment variable.')
@add_access_token_options
@click.pass_context
def move_files(ctx, source, target, workflow, access_token):  # noqa: D301
    r"""Move files within workspace.

    Examples:\n
    \t $ reana-client mv data/input.txt input/input.txt

    """
    logging.debug('command: {}'.format(ctx.command_path.replace(" ", ".")))
    for p in ctx.params:
        logging.debug('{param}: {value}'.format(param=p, value=ctx.params[p]))

    if not access_token:
        click.echo(
            click.style(ERROR_MESSAGES['missing_access_token'], fg='red'),
            err=True)
        sys.exit(1)
    if workflow:
        try:
            current_status = get_workflow_status(workflow,
                                                 access_token).get('status')
            if current_status == 'running':
                click.echo(
                    click.style('File(s) could not be moved for running '
                                'workflow', fg='red'),
                    err=True)
                sys.exit(1)
            files = list_files(workflow, access_token)
            current_files = [file['name'] for file in files]
            if not any(source in item for item in current_files):
                click.echo(
                    click.style('Source file(s) {} does not exist in '
                                'workspace {}'.format(source,
                                                      current_files),
                                fg='red'),
                    err=True)
                sys.exit(1)
            response = mv_files(source, target, workflow, access_token)
            click.echo(click.style(
                '{} was successfully moved to {}.'.
                format(source, target), fg='green'))
        except Exception as e:
            logging.debug(traceback.format_exc())
            logging.debug(str(e))
            click.echo(
                click.style('Something went wrong. {}'.format(e), fg='red'),
                err=True)


files.add_command(get_files)
files.add_command(download_files)
files.add_command(upload_files)
files.add_command(delete_files)
files.add_command(move_files)
