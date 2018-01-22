# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2017, 2018 CERN.
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
"""REANA REST API client."""

import json
import os

import pkg_resources
from bravado.client import SwaggerClient
from bravado.exception import HTTPError


class Client(object):
    """REANA API client code."""

    def __init__(self, server_url):
        """Create a OpenAPI client for REANA Server."""
        json_spec = self._get_spec('reana_server.json')
        self._client = SwaggerClient.from_spec(
            json_spec,
            config={'also_return_response': True})
        self._client.swagger_spec.api_url = server_url
        self.server_url = server_url

    def _get_spec(self, spec_file):
        """Get json specification from package data."""
        spec_file_path = os.path.join(
            pkg_resources.
            resource_filename(
                'reana_client',
                'openapi_connections'),
            spec_file)

        with open(spec_file_path) as f:
            json_spec = json.load(f)
        return json_spec

    def ping(self):
        """Health check REANA Server."""
        try:
            response, http_response = self._client.api.get_api_ping().result()
            if http_response.status_code == 200:
                return response['message']
            else:
                raise Exception(
                    "Expected status code 200 but replied with "
                    "{status_code}".format(
                        status_code=http_response.status_code))

        except Exception as e:
            raise e

    def get_all_analyses(self, user, organization):
        """List all existing analyses."""
        try:

            response, http_response = self._client.api.\
                                      get_analyses(user=user,
                                                   organization=organization)\
                                      .result()
            if http_response.status_code == 200:
                return response
            else:
                raise Exception(
                    "Expected status code 200 but replied with "
                    "{status_code}".format(
                        status_code=http_response.status_code))

        except Exception as e:
            raise e

    def get_analysis_status(self, user, organization, workflow):
        """Get status of previously created analysis."""
        try:

            response, http_response = self.\
                _client.api.get_analysis_status(user=user,
                                                organization=organization,
                                                analysis_id=workflow,
                                                ).result()
            if http_response.status_code == 200:
                return response
            else:
                raise Exception(
                    "Expected status code 200 but replied with "
                    "{status_code}".format(
                        status_code=http_response.status_code))

        except Exception as e:
            raise e

    def create_workflow(self, user, organization, reana_spec):
        """Create a workflow."""
        try:
            (response,
             http_response) = self._client.api.create_analysis(
                                  user=user,
                                  organization=organization,
                                  reana_spec=json.loads(json.dumps(
                                      reana_spec, sort_keys=True))).result()
            if http_response.status_code == 201:
                return response
            else:
                raise Exception(
                    "Expected status code 201 but replied with "
                    "{status_code}".format(
                        status_code=http_response.status_code))

        except Exception as e:
            raise e

    def start_analysis(self, user, organization, workflow):
        """Start a workflow."""
        try:
            (response,
             http_response) = self._client.api.set_analysis_status(
                                  user=user,
                                  organization=organization,
                                  analysis_id=workflow,
                                  status='start').result()
            if http_response.status_code == 200:
                return response
            else:
                raise Exception(
                    "Expected status code 200 but replied with "
                    "{status_code}".format(
                        status_code=http_response.status_code))

        except Exception as e:
            raise e

    def seed_analysis_inputs(self, user, organization, analysis_id, file_,
                             file_name):
        """Seed analysis with input files."""
        try:
            (response,
             http_response) = self._client.api.seed_analysis_inputs(
                 user=user,
                 organization=organization,
                 analysis_id=analysis_id,
                 file_content=file_,
                 file_name=file_name).result()

            if http_response.status_code == 200:
                return response
            else:
                raise Exception(
                    "Expected status code 200 but replied with "
                    "{status_code}".format(
                        status_code=http_response.status_code))

        except Exception as e:
            raise e

    def download_analysis_output_file(self, user, organization, analysis_id,
                                      file_name):
        """Downdloads the requested file if it exists.

        :param user: UUID of the analysis owner.
        :param organization: Organization which the user belongs to.
        :param analysis_id: UUID which identifies the analysis.
        :param file_name: File name or path to the file requested.
        :returns: .
        """
        try:
            (response,
             http_response) = self._client.api.get_analysis_outputs_file(
                 user=user,
                 organization=organization,
                 analysis_id=analysis_id,
                 file_name=file_name).result()

            if http_response.status_code == 200:
                return http_response.raw_bytes
            else:
                raise Exception(
                    "Expected status code 200 but replied with "
                    "{status_code}".format(
                        status_code=http_response.status_code))

        except HTTPError as e:
            raise Exception(e.response.json()['message'])
        except Exception as e:
            raise e

    def get_analysis_inputs(self, user, organization, analysis_id):
        """Return the list of inputs for a given analysis .

        :param user: UUID of the analysis owner.
        :param organization: Organization which the user belongs to.
        :param analysis_id: UUID which identifies the analysis.
        :returns: A list of dictionaries composed by the `name`, `size` and
                  `last-modified`.
        """
        try:
            (response,
             http_response) = self._client.api.get_analysis_inputs(
                 user=user,
                 organization=organization,
                 analysis_id=analysis_id).result()

            if http_response.status_code == 200:
                return response
            else:
                raise Exception(
                    "Expected status code 200 but replied with "
                    "{status_code}".format(
                        status_code=http_response.status_code))

        except HTTPError as e:
            raise Exception(e.response.json()['message'])
        except Exception as e:
            raise e

    def get_analysis_outputs(self, user, organization, analysis_id):
        """Return the list of outputs for a given analysis.

        :param user: UUID of the analysis owner.
        :param organization: Organization which the user belongs to.
        :param analysis_id: UUID which identifies the analysis.
        :returns: A list of dictionaries composed by the `name`, `size` and
                  `last-modified`.
        """
        try:
            (response,
             http_response) = self._client.api.get_analysis_outputs(
                 user=user,
                 organization=organization,
                 analysis_id=analysis_id).result()

            if http_response.status_code == 200:
                return response
            else:
                raise Exception(
                    "Expected status code 200 but replied with "
                    "{status_code}".format(
                        status_code=http_response.status_code))

        except HTTPError as e:
            raise Exception(e.response.json()['message'])
        except Exception as e:
            raise e
