# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2018 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
"""Common click options."""

import functools
import os

import click


def add_access_token_options(func):
    """Adds access token related options to click commands."""
    @click.option('-at', '--access-token',
                  default=os.environ.get('REANA_ACCESS_TOKEN', None),
                  help='Access token of the current user.')
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapper
