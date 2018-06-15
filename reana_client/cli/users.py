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
"""REANA client user related commands."""

import logging
import traceback

import click
import tablib

from reana_commons.utils import click_table_printer


@click.group(
    help='All interaction related to user management on REANA cloud.')
@click.pass_context
def users(ctx):
    """Top level wrapper for user related interaction."""
    logging.debug(ctx.info_name)


@click.command(
    'get',
    help='Get information about a user.')
@click.option(
    '--id',
    help='The id of the user.')
@click.option(
    '-e',
    '--email',
    help='The email of the user.')
@click.option(
    '-t',
    '--token',
    help='The api key of an administrator.')
@click.option(
    '--json',
    'output_format',
    flag_value='json',
    default=None,
    help='Get output in JSON format.')
@click.pass_context
def get_user(ctx, id, email, token, output_format):
    """Return information about a specific user."""
    try:
        response = ctx.obj.client.get_user(id, email, token)
        headers = ['id', 'email', 'token']
        data = [(response['id_'], response['email'], response['token'])]
        if output_format:
            tablib_data = tablib.Dataset()
            tablib_data.headers = headers
            for row in data:
                tablib_data.append(row)

            click.echo(tablib_data.export(output_format))
        else:
            click_table_printer(headers, [], data)

    except Exception as e:
        logging.debug(traceback.format_exc())
        logging.debug(str(e))
        click.echo(
            click.style('User could not be retrieved: \n{}'
                        .format(str(e)), fg='red'),
            err=True)


@click.command(
    'create',
    help='Create a new user.')
@click.option(
    '-e',
    '--email',
    help='The email of the user.')
@click.option(
    '-t',
    '--token',
    help='The api key of an administrator.')
@click.pass_context
def create_user(ctx, email, token):
    """Create a new user."""
    try:
        response = ctx.obj.client.create_user(email, token)
        headers = ['id', 'email', 'token']
        data = [(response['id_'], response['email'], response['token'])]
        click.echo(
            click.style('User was successfully created.', fg='green'))
        click_table_printer(headers, [], data)

    except Exception as e:
        logging.debug(traceback.format_exc())
        logging.debug(str(e))
        click.echo(
            click.style('User could not be created: \n{}'
                        .format(str(e)), fg='red'),
            err=True)


@click.command(
    'register',
    help='Register a new user.')
@click.option(
    '-e',
    '--email',
    help='The email of the user.')
@click.pass_context
def register_user(ctx, email):
    """Register a new user."""
    try:
        response = ctx.obj.client.register_user(email)
        headers = ['id', 'email', 'token']
        data = [(response['id_'], response['email'], response['token'])]
        click.echo(
            click.style('User was successfully registered.', fg='green'))
        click_table_printer(headers, [], data)

    except Exception as e:
        logging.debug(traceback.format_exc())
        logging.debug(str(e))
        click.echo(
            click.style('User could not be registered: \n{}'
                        .format(str(e)), fg='red'),
            err=True)



users.add_command(get_user)
users.add_command(create_user)
