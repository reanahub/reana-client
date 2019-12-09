# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2019 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
"""REANA client workflow related commands."""
import logging
import sys
import traceback

import click
from reana_client.api.client import add_secrets, delete_secrets, \
    list_secrets, current_rs_api_client
from reana_client.cli.utils import (add_access_token_options, check_connection,
                                    NotRequiredIf)
from reana_client.config import ERROR_MESSAGES
from reana_commons.errors import (REANASecretAlreadyExists,
                                  REANASecretDoesNotExist)

from reana_commons.utils import click_table_printer

from reana_client.utils import parse_secret_from_path, \
    parse_secret_from_literal


@click.group(help='Secret management commands')
@click.pass_context
def secrets_group(ctx):
    """Top level wrapper for secrets management."""
    logging.debug(ctx.info_name)


@secrets_group.command()
@click.option(
    '--env',
    multiple=True,
    cls=NotRequiredIf,
    not_required_if='file',
    help='Secrets to be uploaded from literal string.'
         'e.g. PASSWORD=password123')
@click.option(
    '--file',
    multiple=True,
    cls=NotRequiredIf,
    type=click.Path(exists=True, file_okay=True, dir_okay=False,
                    readable=True),
    not_required_if='env',
    help='Secrets to be uploaded from file.')
@click.option(
    '--overwrite',
    is_flag=True,
    default=False,
    help='Overwrite the secret if already present')
@add_access_token_options
@check_connection
def secrets_add(env, file, overwrite, access_token):  # noqa: D301
    """Add secrets from literal string or from file.

    Examples: \n
    \t $ reana-client secrets-add --env PASSWORD=password \n
    \t $ reana-client secrets-add --file ~/.keytab \n
    \t $ reana-client secrets-add --env USER=reanauser \n
    \t                            --env PASSWORD=password \n
    \t                            --file ~/.keytab
    """
    secrets_ = {}
    for literal in env:
        secret = parse_secret_from_literal(literal)
        secrets_.update(secret)
    for path in file:
        secret = parse_secret_from_path(path)
        secrets_.update(secret)
    try:
        add_secrets(secrets_, overwrite, access_token)
    except REANASecretAlreadyExists as e:
        logging.debug(str(e), exc_info=True)
        click.echo(
            click.style(
                'One of the secrets already exists. No secrets were added. '
                'If you want to overwrite it use --overwrite option.',
                fg='red'),
            err=True)
        sys.exit(1)
    except Exception as e:
        logging.debug(str(e), exc_info=True)
        click.echo(
            click.style(
                'Something went wrong while uploading secrets',
                fg='red'),
            err=True)
    else:
        click.echo(
            click.style('Secrets {} were successfully uploaded.'.format(
                ', '.join(secrets_.keys())),
                fg='green')
        )


@secrets_group.command()
@add_access_token_options
@check_connection
@click.argument('secrets', type=str, nargs=-1)
def secrets_delete(secrets, access_token):  # noqa: D301
    """Delete user secrets by name.

     Examples: \n
    \t $ reana-client secrets-delete PASSWORD
    """
    try:
        deleted_secrets = delete_secrets(secrets, access_token)
    except REANASecretDoesNotExist as e:
        logging.debug(str(e), exc_info=True)
        click.echo(
            click.style(
                str('Secrets {} do not exist. Nothing was deleted'
                    .format(e.missing_secrets_list)
                    ),
                fg='red'),
            err=True)
    except Exception as e:
        logging.debug(str(e), exc_info=True)
        click.echo(
            click.style(
                'Something went wrong while deleting secrets',
                fg='red'),
            err=True)
    else:
        click.echo(
            click.style('Secrets {} were successfully deleted.'.format(
                ', '.join(deleted_secrets)),
                fg='green'))


@secrets_group.command()
@add_access_token_options
@check_connection
def secrets_list(access_token):  # noqa: D301
    """List user secrets.

    Examples: \n
    \t $ reana-client secrets-list
    """
    try:
        secrets = list_secrets(access_token)
        headers = ['name', 'type']
        data = []
        for secret_ in secrets:
            data.append(list(map(str, [secret_['name'],
                                       secret_['type']])))

        click_table_printer(headers, headers, data)
    except Exception as e:
        logging.debug(str(e), exc_info=True)
        click.echo(
            click.style(
                'Something went wrong while listing secrets',
                fg='red'),
            err=True)
