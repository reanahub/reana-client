# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2017, 2018 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
"""REANA client configuration."""

import os

import pkg_resources

reana_yaml_default_file_path = './reana.yaml'  # e.g. `./.reana.yaml`
"""REANA specification file default location."""

reana_yaml_schema_file_path = pkg_resources.resource_filename(
        __name__,
        'schemas/reana_analysis_schema.json')
"""REANA specification schema location."""

default_user = '00000000-0000-0000-0000-000000000000'
"""Default user to use when submitting workflows to REANA Server."""

ERROR_MESSAGES = {
        'missing_access_token':
        'Please provide your access token by using'
        ' the -t/--access-token flag, or by setting the'
        ' REANA_ACCESS_TOKEN environment variable.'
}

JSON = 'json'
"""Json output format."""

TIMECHECK = 5
"""Time between workflow status check."""

URL = 'url'
"""Url output format."""

WORKFLOW_ENGINES = ['serial', 'cwl', 'yadage']
"""Supported workflow engines."""
