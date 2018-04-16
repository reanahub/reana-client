# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2018 CERN.
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
"""REANA client code related commands."""

import logging
import os
import traceback

import click

import tablib

from ..config import default_organization, default_user
from ..errors import FileUploadError
from ..api.client import UploadType


@click.group(
    help='All interaction related to code files of workflows.')
@click.pass_context
def code(ctx):
    """Top level wrapper for code file and parameter related interaction."""
    logging.debug(ctx.info_name)


@click.command(
    'list',
    help='List code files of a workflow.')
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
    '-w',
    '--workflow',
    default=os.environ.get('REANA_WORKON', None),
    help='Name or UUID of the workflow whose code files should be listed.')
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
def code_list(ctx, user, organization, workflow, filter, output_format):
    """List code files of a workflow."""
    logging.debug('command: {}'.format(ctx.command_path.replace(" ", ".")))
    for p in ctx.params:
        logging.debug('{param}: {value}'.format(param=p, value=ctx.params[p]))

    try:
        response = ctx.obj.client.get_analysis_code(user, organization,
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
        logging.debug(traceback.format_exc())
        logging.debug(str(e))
        click.echo(
            click.style('Something went wrong while retrieving input file list'
                        ' for workflow {0}:\n{1}'.format(workflow, str(e)),
                        fg='red'),
            err=True)


@click.command(
    'upload',
    help='Upload one of more code files to the analysis workspace.')
@click.argument(
    'filenames',
    metavar='FILE',
    type=click.Path(exists=True, resolve_path=False),
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
    '-w',
    '--workflow',
    default=os.environ.get('REANA_WORKON', None),
    help='Name or UUID of the workflow where the files should be uploaded to. '
         'Overrides value of $REANA_WORKON.')
@click.pass_context
def code_upload(ctx, user, organization, workflow, filenames):
    """Upload code file(s) to analysis workspace. Associate with a workflow."""
    logging.debug('command: {}'.format(ctx.command_path.replace(" ", ".")))
    for p in ctx.params:
        logging.debug('{param}: {value}'.format(param=p, value=ctx.params[p]))

    if workflow:
        for filename in filenames:
            try:
                response = ctx.obj.client.\
                    upload_to_server(user,
                                     organization,
                                     workflow,
                                     filename,
                                     UploadType.code)
                if type(response) is list:
                    for _filename in response:
                        click.echo(
                            click.style('{} was uploaded successfully.'.
                                        format(_filename), fg='green'))
                elif response:
                    click.echo(
                        click.style('{} was uploaded successfully.'.
                                    format(filename), fg='green'))
            except FileUploadError as e:
                logging.debug(traceback.format_exc())
                logging.debug(str(e))
                click.echo(
                    click.style(
                        '{0}: {1}'.format(filename, str(e)),
                        fg='red'),
                    err=True)
            except Exception as e:
                logging.debug(traceback.format_exc())
                logging.debug(str(e))
                click.echo(
                    click.style(
                        '{0}'.format(str(e)),
                        fg='red'),
                    err=True)

    else:
        click.echo(
            click.style('Workflow name must be provided either with '
                        '`--workflow` option or with `$REANA_WORKON` '
                        'environment variable',
                        fg='red'),
            err=True)


code.add_command(code_list)
code.add_command(code_upload)
