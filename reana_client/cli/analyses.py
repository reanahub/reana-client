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
import traceback

import click

from ..config import (default_organization, default_user,
                      reana_yaml_default_file_path)
from ..utils import load_reana_spec, load_workflow_spec


@click.group(
    help='All analysis related interaction on REANA cloud.')
@click.pass_context
def analyses(ctx):
    """Top level wrapper for analysis related interaction."""
    logging.debug('analysis')


@click.command(
    'validate',
    help='Validate REANA specification file.')
@click.option(
    '-f',
    '--file',
    type=click.Path(exists=True, resolve_path=True),
    default=reana_yaml_default_file_path,
    help='REANA specifications file describing the workflow and '
         'context which REANA should execute.')
@click.pass_context
def validate(ctx, file):
    """Validate given REANA specification file."""
    logging.debug('analyses.validate')
    logging.debug('file: {}'.format(file))

    try:
        load_reana_spec(click.format_filename(file))

        click.echo('File {filename} is a valid REANA specification file.'
                   .format(filename=click.format_filename(file)))

    except Exception as e:
        logging.info('Something went wrong when trying to validate {0}'
                     .format(click.format_filename(file)))
        logging.error(traceback.format_exc())


analyses.add_command(validate)
