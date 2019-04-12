# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2018 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
"""Common click options."""

import functools
import json
import os
import shlex

import click

from reana_client.utils import workflow_uuid_or_name


def add_access_token_options(func):
    """Add access token related options to click commands."""
    @click.option('-t', '--access-token',
                  default=os.getenv('REANA_ACCESS_TOKEN', None),
                  help='Access token of the current user.')
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapper


def add_workflow_option(func):
    """Add workflow related option to click commands."""
    @click.option('-w', '--workflow',
                  default=os.environ.get('REANA_WORKON', None),
                  callback=workflow_uuid_or_name,
                  help='Name or UUID of the workflow. Overrides value of '
                       'REANA_WORKON environment variable.')
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapper


def parse_parameters(_filter):
    """Return parsed filter parameters."""
    try:
        parsed_filters = []
        filters = ' '.join(_filter).replace(',', ' ')
        for item in shlex.split(filters):
            if '=' in item:
                filter_item = {
                    'column_name': item.split('=')[0],
                    'column_value': item.split('=')[1]}
            else:
                filter_item = {
                    'column_name': item,
                    'column_value': None}
            parsed_filters.append(filter_item)
        return parsed_filters
    except ValueError as e:
        click.echo(click.style('Wrong filter format \n{0}'
                               .format(e.message),
                               fg='red'), err=True)


def filter_data(parsed_filters, headers, tablib_data):
    """Return filtered data."""
    parsed_filters = \
        [i for i in parsed_filters if i['column_name'] in headers]
    column_headers = [i['column_name'] for i in parsed_filters] or None
    tablib_data = tablib_data.subset(rows=None,
                                     cols=column_headers)
    tablib_data = json.loads(tablib_data.export('json'))
    filtered_data = list(tablib_data)
    for item in filtered_data:
        for filter_ in parsed_filters:
            if (filter_['column_value'] is not None and
                    filter_['column_value'] != item[filter_['column_name']]):
                tablib_data.remove(item)
    return tablib_data, column_headers or []


def format_session_uri(reana_server_url, path, access_token):
    """Format interactive session URI."""
    return "{reana_server_url}{path}?token={access_token}".format(
        reana_server_url=reana_server_url,
        path=path, access_token=access_token)
