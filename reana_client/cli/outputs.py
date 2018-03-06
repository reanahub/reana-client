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

import click
import tablib

from ..config import default_download_path, default_organization, default_user


@click.group(
    help='All interaction related to output files of workflows.')
@click.pass_context
def outputs(ctx):
    """Top level wrapper for output files related interaction.."""
    logging.debug('outputs')


@click.command(
    'list',
    help='List files workflow has outputted.')
@click.option(
    '-u',
    '--user',
    default=default_user,
    help='User who created the workflow.')
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
def outputs_list(ctx, user, organization, workflow, filter, output_format):
    """List files a workflow has outputted."""
    logging.debug('outputs.list')
    logging.debug('user: {}'.format(user))
    logging.debug('organization: {}'.format(organization))
    logging.debug('workflow: {}'.format(workflow))
    logging.debug('filter: {}'.format(filter))
    logging.debug('output_format: {}'.format(output_format))

    if workflow:
        logging.info('Workflow "{}" selected'.format(workflow))

        try:
            response = ctx.obj.client.get_analysis_outputs(user, organization,
                                                           workflow)

            data = tablib.Dataset()
            data.headers = ['name', 'size', 'last-modified']

            for file_ in response:
                data.append([file_['name'],
                             file_['size'],
                             file_['last-modified']])

            if filter:
                data = data.subset(rows=None, cols=list(filter))

            if output_format:
                click.echo(data.export(output_format))
            else:
                click.echo(data)
        except Exception as e:
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
                        '`--workflow` option or with `$REANA_WORKON` '
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
    '-u',
    '--user',
    default=default_user,
    help='User who created the workflow.')
@click.option(
    '-o',
    '--organization',
    default=default_organization,
    help='Organization whose resources will be used.')
@click.option(
    '--workflow',
    default=os.environ.get('REANA_WORKON', None),
    help='Name of the workflow you are uploading files for. '
         'Overrides value of $REANA_WORKON.')
@click.option(
    '--output-directory',
    default=default_download_path,
    help='Path to the directory where files outputted '
         'by a workflow will be downloaded')
@click.pass_context
def outputs_download(ctx, user, organization, workflow, file_,
                     output_directory):
    """Download file(s) workflow has outputted."""
    logging.debug('outputs.download')
    logging.debug('user: {}'.format(user))
    logging.debug('organization: {}'.format(organization))
    logging.debug('workflow: {}'.format(workflow))
    logging.debug('file_: {}'.format(file_))
    logging.debug('output_directory: {}'.format(output_directory))
    for file_name in file_:
        try:
            binary_file = \
                ctx.obj.client.download_analysis_output_file(user,
                                                             organization,
                                                             workflow,
                                                             file_name)
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
            click.echo(
                click.style('File {0} could not be written.'.format(file_name),
                            fg='red'))
            logging.debug(str(e))
        except Exception as e:
            click.echo(
                click.style(
                    'File {0} could not be downloaded.'.format(file_name),
                    fg='red'))
            logging.debug(str(e))


outputs.add_command(outputs_list)
outputs.add_command(outputs_download)
