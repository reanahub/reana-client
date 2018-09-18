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
"""REANA client output related commands."""

import logging
import os
import sys
import traceback

import click

import tablib

from reana_client.config import ERROR_MESSAGES, default_user
from reana_client.errors import FileUploadError
from reana_client.utils import get_workflow_root, load_reana_spec
from reana_client.cli.utils import add_access_token_options
from reana_client.decorators import with_api_client
from reana_commons.utils import click_table_printer


@click.group(
    help='All interaction related to files.')
@click.pass_context
def files(ctx):
    """Top level wrapper for files related interactions."""
    logging.debug(ctx.info_name)


@click.command(
    'list',
    help='List workflow workspace files.')
@click.option(
    '-w',
    '--workflow',
    default=os.environ.get('REANA_WORKON', None),
    help='Name or UUID of the workflow whose files should be listed. '
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
@click.pass_context
@with_api_client
def get_files(ctx, workflow, _filter,
              output_format, access_token):
    """List workflow workspace files."""
    logging.debug('command: {}'.format(ctx.command_path.replace(" ", ".")))
    for p in ctx.params:
        logging.debug('{param}: {value}'.format(param=p, value=ctx.params[p]))

    if not access_token:
        click.echo(
            click.style(ERROR_MESSAGES['missing_access_token'],
                        fg='red'), err=True)
        sys.exit(1)
    if workflow:
        logging.info('Workflow "{}" selected'.format(workflow))
        try:
            response = ctx.obj.client.get_files(workflow, access_token)
            headers = ['name', 'size', 'last-modified']
            data = []
            for file_ in response:
                data.append(list(map(str, [file_['name'],
                                           file_['size'],
                                           file_['last-modified']])))
            if output_format:
                tablib_data = tablib.Dataset()
                tablib_data.headers = headers
                for row in data:
                        tablib_data.append(row)

                if _filter:
                    tablib_data = tablib_data.subset(
                        rows=None, cols=list(_filter))
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
         'Overrides value of REANA_WORKON.')
@click.option(
    '--output-directory',
    default=os.getcwd(),
    help='Path to the directory where files  will be downloaded.')
@add_access_token_options
@click.pass_context
@with_api_client
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
                binary_file = \
                    ctx.obj.client.download_file(workflow,
                                                 file_name,
                                                 access_token)
                logging.info('{0} binary file downloaded ... writing to {1}'.
                             format(file_name, output_directory))

                outputs_file_path = os.path.join(output_directory, file_name)
                if not os.path.exists(os.path.dirname(outputs_file_path)):
                    os.makedirs(os.path.dirname(outputs_file_path))

                with open(outputs_file_path, 'wb') as f:
                    f.write(binary_file)
                click.echo(
                    click.style(
                        'File {0} downloaded to {1}.'.format(
                            file_name, output_directory),
                        fg='green'))
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
         'Overrides value of $REANA_WORKON.')
@add_access_token_options
@click.pass_context
@with_api_client
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
                response = ctx.obj.client.\
                    upload_to_server(workflow,
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
            except FileUploadError as e:
                logging.debug(traceback.format_exc())
                logging.debug(str(e))
                click.echo(
                    click.style(
                        'Something went wrong while uploading {0}.\n{1}'.
                        format(filename, str(e)),
                        fg='red'),
                    err=True)
            except Exception as e:
                logging.debug(traceback.format_exc())
                logging.debug(str(e))
                click.echo(
                    click.style(
                        'Something went wrong while uploading {}'.
                        format(filename),
                        fg='red'),
                    err=True)

    else:
        click.echo(
            click.style('Workflow name must be provided either with '
                        '`--workflow` option or with REANA_WORKON '
                        'environment variable',
                        fg='red'),
            err=True)


files.add_command(get_files)
files.add_command(download_files)
files.add_command(upload_files)
