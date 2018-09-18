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
"""REANA command line decorators."""

import logging
import os
import sys

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
                logging.error(
                    'REANA client is not connected to any REANA cluster.\n'
                    'Please set REANA_SERVER_URL environment variable to '
                    'the remote REANA cluster you would like to connect to.\n'
                    'For example: export '
                    'REANA_SERVER_URL=https://reana.cern.ch/')
                sys.exit(1)

            logging.info('REANA server URL ($REANA_SERVER_URL) is: {}'
                         .format(server_url))
            if ctx.obj is None:
                from reana_client.cli import Config
                ctx.obj = Config()
            ctx.obj.client = Client(server_url)
        else:
            raise Exception(
                'This decorator should be used after click.pass_context.')
        f(*args, **kwargs)
    return wrapper
