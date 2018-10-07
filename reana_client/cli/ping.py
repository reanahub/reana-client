# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2017, 2018 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
"""REANA client debugging commands."""

import logging
import traceback

import click

from reana_client.decorators import with_api_client


@click.command('ping', help='Health check REANA server.')
@click.pass_context
@with_api_client
def ping(ctx):
    """Health check REANA server."""
    try:
        logging.info('Connecting to {0}'.format(ctx.obj.client.server_url))
        response = ctx.obj.client.ping()
        click.echo(click.style('Connected to {0} - Server is running.'.format(
            ctx.obj.client.server_url), fg='green'))
        logging.debug('Server response:\n{}'.format(response))

    except Exception as e:
        logging.debug(traceback.format_exc())
        logging.debug(str(e))
        click.echo(click.style(
            'Could not connect to the selected '
            'REANA cluster server at {0}.'.format(ctx.obj.client.server_url),
            fg='red'), err=True)
