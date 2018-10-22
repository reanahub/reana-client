# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2017, 2018 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""Pytest configuration for REANA client."""

from __future__ import absolute_import, print_function

import os

import pytest
from pytest_reana.test_utils import make_mock_api_client

from reana_client.cli import Config, cli


@pytest.fixture(scope='module')
def click_config_obj():
    """."""
    api_client = make_mock_api_client('reana-server')
    return Config(api_client)
