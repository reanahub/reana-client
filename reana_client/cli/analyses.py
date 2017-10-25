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
"""REANA client analysis related commands."""

import logging

import click
import yaml

from ..config import (default_organisation, default_user,
                      reana_yaml_default_file_path)
from ..utils import load_reana_spec, load_workflow_spec


@click.command()
@click.option('-f',
              '--file',
              type=click.Path(exists=True, resolve_path=True),
              default=reana_yaml_default_file_path,
              help='REANA specifications file describing the workflow and '
                   'context which REANA should execute.')
@click.pass_context
def validate(ctx, file):
    """Validate given REANA specification file."""
    try:
        load_reana_spec(click.format_filename(file))

        click.echo('File {filename} is a valid REANA specification file.'
                   .format(filename=click.format_filename(file)))

    except Exception as e:
        logging.info('Something went wrong when trying to validate {0}'
                     .format(click.format_filename(file)))
        logging.debug(str(e))


@click.command('list')
@click.pass_context
def list_(ctx):
    """List all available analyses."""
    try:
        response = ctx.obj.client.get_all_analyses()
        for analysis in response:
            click.echo(analysis)

    except Exception as e:
        logging.info('Something went wrong when trying to connect to {0}'
                     .format(ctx.obj.client.server_url))
        logging.debug(str(e))


@click.command()
@click.option('-f',
              '--file',
              type=click.Path(exists=True, resolve_path=True),
              default=reana_yaml_default_file_path,
              help='REANA specifications file describing the workflow and '
                   'context which REANA should execute.')
@click.option('-u', '--user', default=default_user,
              help='User who submits the analysis.')
@click.option('-o', '--organization', default=default_organisation,
              help='Organization whose resources will be used.')
@click.option('--skip-validation', is_flag=True,
              help='If set, specifications file is not validated before '
                   'submitting it\'s contents to REANA Server.')
@click.pass_context
def run(ctx, file, user, organization, skip_validation):
    """Run a REANA compatible analysis using REANA spec file as input."""
    try:
        reana_spec = load_reana_spec(click.format_filename(file),
                                     skip_validation)

        reana_spec['workflow']['spec'] = load_workflow_spec(
            reana_spec['workflow']['type'],
            reana_spec['workflow']['file'],
        )
        if reana_spec['workflow']['type'] == 'cwl':
            with open(reana_spec['parameters']['input']) as f:
                reana_spec['parameters']['input'] = yaml.load(f)
        logging.info('Connecting to {0}'.format(ctx.obj.client.server_url))
        response = ctx.obj.client.run_analysis(user, organization,
                                               reana_spec)
        click.echo(response)

    except Exception as e:
        logging.debug(str(e))


@click.command()
@click.option('-u', '--user', default='00000000-0000-0000-0000-000000000000',
              help='User who submits the analysis.')
@click.option('-o', '--organization', default='default',
              help='Organization which resources will be used.')
@click.option('-a', '--analysis',
              help='UUID which identifies the analysis to be seeded.')
@click.argument('file_', type=click.File('rb'))
@click.pass_context
def seed(ctx, user, organization, analysis, file_):
    """Seed files to analysis workspace."""
    try:
        response = ctx.obj.client.seed_analysis(
            user,
            organization,
            analysis,
            file_,
            file_.name)
        click.echo(response)

    except Exception as e:
        logging.debug(str(e))
