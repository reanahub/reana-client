# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2018 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
"""REANA command line decorators."""

import logging
import os
import sys

import click
from click.core import Context

from reana_client.api import Client


def with_api_client(f):
    """Decorator to inject the REANA server API client to a Click command."""
    def wrapper(*args, **kwargs):
        """Initialize config for API client.

        This decorator should be used right after @click.pass_context since it
        is injecting the API client inside the ``ctx`` object.
        """
        # Since we require the @click.pass_context decorator to be passed
        # before, we know ``ctx`` is the first argument.
        ctx = args[0]
        if isinstance(ctx, Context):
            server_url = os.environ.get('REANA_SERVER_URL', None)

            if not server_url:
                click.secho(
                    'REANA client is not connected to any REANA cluster.\n'
                    'Please set REANA_SERVER_URL environment variable to '
                    'the remote REANA cluster you would like to connect to.\n'
                    'For example: export '
                    'REANA_SERVER_URL=https://reana.cern.ch/',
                    fg='red',
                    err=True)
                sys.exit(1)

            logging.info('REANA server URL ($REANA_SERVER_URL) is: {}'
                         .format(server_url))
            if not ctx.obj.client:
                ctx.obj.client = Client('reana-server')
        else:
            raise Exception(
                'This decorator should be used after click.pass_context.')
        f(*args, **kwargs)
    return wrapper
