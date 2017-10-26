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
"""REANA client inputs related commands."""

import logging
import os

import click
import tablib

from ..config import default_organisation, default_user
from .namesgenerator import get_random_name


@click.group(
    help='All interaction related to input files and parameters of workflows.')
@click.pass_context
def inputs(ctx):
    """Top level wrapper for input file and parameter related interaction."""
    logging.debug('inputs')


@click.command(
    'list',
    help='List input files of a workflow.')
@click.option(
    '-u',
    '--user',
    default=default_user,
    help='User who created the workflow.')
@click.option(
    '-o',
    '--organization',
    default=default_organisation,
    help='Organization whose resources will be used.')
@click.option(
    '--workflow',
    help='Name of the workflow whose input files you want to list.')
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
def inputs_list(ctx, user, organization, workflow, filter, output_format):
    """List input files of a workflow."""
    logging.debug('inputs.list')
    logging.debug('user: {}'.format(user))
    logging.debug('organization: {}'.format(organization))
    logging.debug('workflow: {}'.format(workflow))
    logging.debug('filter: {}'.format(filter))
    logging.debug('output_format: {}'.format(output_format))

    data = tablib.Dataset()
    data.headers = ['Name', 'Size', 'Last-Modified', 'Path']
    for i in range(1, 10):
        data.append([get_random_name(),
                     '1kb',
                     '2017-10-05 14:27',
                     '/input'])

    if filter:
        data = data.subset(rows=None, cols=list(filter))

    if output_format:
        click.echo(data.export(output_format))
    else:
        click.echo(data)


@click.command(
    'upload',
    help='Upload file(s) to analysis workspace. Associate with a workflow.')
@click.argument(
    'file_',
    metavar='[FILE(S)]',
    type=click.File('rb'),
    nargs=-1)
@click.option(
    '-u',
    '--user',
    default=default_user,
    help='User who created the workflow.')
@click.option(
    '-o',
    '--organization',
    default=default_organisation,
    help='Organization whose resources will be used.')
@click.option(
    '--workflow',
    help='Name of the workflow you are uploading files for. '
         'Overrides value of $REANA_WORKON.')
@click.pass_context
def inputs_upload(ctx, user, organization, workflow, file_):
    """Upload file(s) to analysis workspace. Associate with a workflow."""
    logging.debug('inputs.upload')
    logging.debug('file_: {}'.format(file_))
    logging.debug('user: {}'.format(user))
    logging.debug('organization: {}'.format(organization))
    logging.debug('workflow: {}'.format(workflow))

    workflow_name = workflow or os.environ.get('$REANA_WORKON', None)

    if workflow_name:
        logging.info('Workflow "{}" selected'.format(workflow_name))
        for f in file_:
            click.echo('Uploading {} ...'.format(f))

            response = True

            if response:
                click.echo('File {} was successfully uploaded.'.format(f))
    else:
        click.echo(
            click.style('Workflow name must be provided either with '
                        '`--workflow` option or with `$REANA_WORKON` '
                        'environment variable',
                        fg='red'),
            err=True)

    # try:
    #     response = ctx.obj.client.seed_analysis(
    #         user,
    #         organization,
    #         workflow,
    #         file_,
    #         file_.name)
    #     click.echo(response)

    # except Exception as e:
    #     logging.debug(str(e))

inputs.add_command(inputs_list)
inputs.add_command(inputs_upload)
