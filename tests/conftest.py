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

import httpretty
import pytest


@pytest.yield_fixture()
def reana_server():
    """File pointer to YAML configuration file."""
    httpretty.enable()
    os.environ['REANA_SERVER_URL'] = 'http://reana.cern.ch'
    httpretty.register_uri(httpretty.GET, "http://reana.cern.ch/api/ping",
                           body='{"status": "200", "message": "OK"}',
                           content_type="application/json",
                           status=200)
    yield
    del os.environ['REANA_SERVER_URL']
    httpretty.disable()
    httpretty.reset()
