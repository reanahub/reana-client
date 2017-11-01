# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2017 CERN.
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

from reana_client.cli.namesgenerator import get_random_name

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
    help='Name of the workflow to be started. '
         'Overrides value of $REANA_WORKON.')
@click.option(
    '--filter',
    multiple=True,
    help='Filter output according to column titles (case-sensitive).')
@click.option(
    '-of',
    '--output-format',
    type=click.Choice(['json', 'yaml']),
    help='Set output format.')
@click.pass_context
def outputs_list(ctx, user, organization, workflow, filter, output_format):
    """List files a workflow has outputted."""
    logging.debug('outputs.list')
    logging.debug('user: {}'.format(user))
    logging.debug('organization: {}'.format(organization))
    logging.debug('workflow: {}'.format(workflow))
    logging.debug('filter: {}'.format(filter))
    logging.debug('output_format: {}'.format(output_format))

    workflow_name = workflow or os.environ.get('$REANA_WORKON', None)

    if workflow_name:
        logging.info('Workflow "{}" selected'.format(workflow_name))

        data = tablib.Dataset()
        data.headers = ['Name', 'Size', 'Last-Modified', 'Path']

        for i in range(1, 10):
            data.append([get_random_name(),
                         '99kb',
                         '2017-10-05 14:27',
                         '/output'])

        if filter:
            data = data.subset(rows=None, cols=list(filter))

        if output_format:
            click.echo(data.export(output_format))
        else:
            click.echo(data)

    else:
        click.echo(
            click.style('Workflow name must be provided either with '
                        '`--workflow` option or with `$REANA_WORKON` '
                        'environment variable',
                        fg='red'),
            err=True)


@click.command(
    'download',
    help='Download file(s) a workflow has outputted.')
@click.argument(
    'file_',
    metavar='[FILE(S)]',
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
    help='Name of the workflow you are uploading files for. '
         'Overrides value of $REANA_WORKON.')
@click.option(
    '--output-folder',
    default=default_download_path,
    help='Path to the folder where files outputted '
         'by a workflow will be downloaded')
@click.pass_context
def outputs_download(ctx, user, organization, workflow, file_, output_folder):
    """Download file(s) workflow has outputted."""
    logging.debug('outputs.download')
    logging.debug('user: {}'.format(user))
    logging.debug('organization: {}'.format(organization))
    logging.debug('workflow: {}'.format(workflow))
    logging.debug('file_: {}'.format(file_))
    logging.debug('output_folder: {}'.format(output_folder))

    for f in file_:
        click.echo('File `{}` downloaded to `{}`'.format(f, output_folder))

outputs.add_command(outputs_list)
outputs.add_command(outputs_download)
