# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2017, 2018 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""Pytest configuration for REANA client."""

from __future__ import absolute_import, print_function

import pytest
from mock import Mock
from pytest_reana.test_utils import make_mock_api_client

from reana_client.api.client import Client


@pytest.fixture()
def mock_base_api_client():
    """Create mocked api client."""
    def _make_mock_api_client(status_code=200,
                              response=None,
                              component='reana-server'):
        mock_http_response, mock_response = Mock(), Mock()
        mock_http_response.status_code = status_code
        mock_http_response.raw_bytes = str(response).encode()
        mock_response = response
        reana_server_client = make_mock_api_client(
            component)(mock_response, mock_http_response)
        reana_client_server_api = Client(component)
        reana_client_server_api._client = reana_server_client
        return reana_client_server_api
    return _make_mock_api_client


@pytest.fixture()
def create_yaml_workflow_schema():
    """Return dummy yaml workflow schema."""
    reana_yaml_schema = \
        '''
        version: 0.4.0
        inputs:
          files:
            - code/helloworld.py
            - inputs/names.txt
          parameters:
            sleeptime: 2
            inputfile: inputs/names.txt
            helloworld: code/helloworld.py
            outputfile: outputs/greetings.txt
        outputs:
          files:
           - outputs/greetings.txt
        workflow:
          type: serial
          specification:
            steps:
              - environment: 'python:2.7'
                commands:
                  - python "${helloworld}" --sleeptime ${sleeptime} \
                  --inputfile "${inputfile}" --outputfile "${outputfile}"
        '''
    return reana_yaml_schema
