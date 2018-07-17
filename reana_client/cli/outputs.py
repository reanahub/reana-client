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

from ..config import default_download_path, default_organization, default_user
from reana_commons.utils import click_table_printer


@click.group(
    help='All interaction related to output files of workflows.')
@click.pass_context
def outputs(ctx):
    """Top level wrapper for output files related interaction.."""
    logging.debug(ctx.info_name)


@click.command(
    'list',
    help='List files workflow has outputted.')
@click.option(
    '-o',
    '--organization',
    default=default_organization,
    help='Organization whose resources will be used.')
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
@click.option(
    '-t',
    '--token',
    default=os.environ.get('REANA_ACCESS_TOKEN', None),
    help='API token of the current user.')
@click.pass_context
def outputs_list(ctx, organization, workflow, _filter,
                 output_format, token):
    """List files a workflow has outputted."""
    logging.debug('command: {}'.format(ctx.command_path.replace(" ", ".")))
    for p in ctx.params:
        logging.debug('{param}: {value}'.format(param=p, value=ctx.params[p]))

    if not token:
        click.echo(
            click.style('Please provide your API token, either by setting the'
                        ' REANA_ACCESS_TOKEN environment variable, or by using'
                        ' the -t/--token flag.', fg='red'), err=True)
        sys.exit(1)
    if workflow:
        logging.info('Workflow "{}" selected'.format(workflow))
        try:
            response = ctx.obj.client.get_workflow_outputs(organization,
                                                           workflow, token)
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
                click.style('Something went wrong while retrieving output file'
                            ' list for workflow {0}:\n{1}'.format(workflow,
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
    help='Download one or more FILE that the workflow has outputted.')
@click.argument(
    'file_',
    metavar='FILE',
    nargs=-1)
@click.option(
    '-o',
    '--organization',
    default=default_organization,
    help='Organization whose resources will be used.')
@click.option(
    '-w',
    '--workflow',
    default=os.environ.get('REANA_WORKON', None),
    help='Name or UUID of that workflow where files should downloaded from. '
         'Overrides value of REANA_WORKON.')
@click.option(
    '--output-directory',
    default=default_download_path,
    help='Path to the directory where files outputted '
         'by a workflow will be downloaded')
@click.option(
    '-t',
    '--token',
    default=os.environ.get('REANA_ACCESS_TOKEN', None),
    help='API token of the current user.')
@click.pass_context
def outputs_download(ctx, organization, workflow, file_,
                     output_directory, token):
    """Download file(s) workflow has outputted."""
    logging.debug('command: {}'.format(ctx.command_path.replace(" ", ".")))
    for p in ctx.params:
        logging.debug('{param}: {value}'.format(param=p, value=ctx.params[p]))

    if not token:
        click.echo(
            click.style('Please provide your API token, either by setting the'
                        ' REANA_ACCESS_TOKEN environment variable, or by using'
                        ' the -t/--token flag.', fg='red'), err=True)
        sys.exit(1)

    if workflow:
        for file_name in file_:
            try:
                binary_file = \
                    ctx.obj.client.download_workflow_output_file(organization,
                                                                 workflow,
                                                                 file_name,
                                                                 token)
                logging.info('{0} binary file downloaded ... writing to {1}'.
                             format(file_name, output_directory))

                outputs_file_path = os.path.join(output_directory, file_name)
                if not os.path.exists(os.path.dirname(outputs_file_path)):
                    os.makedirs(os.path.dirname(outputs_file_path))

                with open(outputs_file_path, 'wb') as f:
                    f.write(binary_file)
                click.echo(
                    click.style(
                        'File {0} downloaded to {1}'.format(file_name,
                                                            output_directory),
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


outputs.add_command(outputs_list)
outputs.add_command(outputs_download)
