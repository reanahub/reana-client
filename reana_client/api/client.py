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

import traceback
import enum
import json
import logging
import os

import pkg_resources
from bravado.client import SwaggerClient
from bravado.exception import HTTPError
from reana_client.errors import FileUploadError
from reana_client.utils import get_analysis_root


class UploadType(enum.Enum):
    """Possible workflow status list enum."""

    inputs = 0
    code = 1


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

        except HTTPError as e:
            logging.debug(
                'REANA Server health check failed: '
                '\nStatus: {}\nReason: {}\n'
                'Message: {}'.format(e.response.status_code,
                                     e.response.reason,
                                     e.response.json()['message']))
            raise Exception(e.response.json()['message'])
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

        except HTTPError as e:
            logging.debug(
                'The list of analyses could not be retrieved: '
                '\nStatus: {}\nReason: {}\n'
                'Message: {}'.format(e.response.status_code,
                                     e.response.reason,
                                     e.response.json()['message']))
            raise Exception(e.response.json()['message'])
        except Exception as e:
            raise e

    def get_analysis_status(self, user, organization, workflow):
        """Get status of previously created analysis."""
        try:
            response, http_response = self.\
                _client.api.get_analysis_status(user=user,
                                                organization=organization,
                                                analysis_id_or_name=workflow,
                                                ).result()
            if http_response.status_code == 200:
                return response
            else:
                raise Exception(
                    "Expected status code 200 but replied with "
                    "{status_code}".format(
                        status_code=http_response.status_code))

        except HTTPError as e:
            logging.debug(
                'Analysis status could not be retrieved: '
                '\nStatus: {}\nReason: {}\n'
                'Message: {}'.format(e.response.status_code,
                                     e.response.reason,
                                     e.response.json()['message']))
            raise Exception(e.response.json()['message'])
        except Exception as e:
            raise e

    def create_workflow(self, user, organization, reana_spec, name):
        """Create a workflow."""
        try:
            (response,
             http_response) = self._client.api.create_analysis(
                                  user=user,
                                  organization=organization,
                                  reana_spec=json.loads(json.dumps(
                                      reana_spec, sort_keys=True)),
                                  workflow_name=name).result()
            if http_response.status_code == 201:
                return response
            else:
                raise Exception(
                    "Expected status code 201 but replied with "
                    "{status_code}".format(
                        status_code=http_response.status_code))

        except HTTPError as e:
            logging.debug(
                'Workflow creation failed: '
                '\nStatus: {}\nReason: {}\n'
                'Message: {}'.format(e.response.status_code,
                                     e.response.reason,
                                     e.response.json()['message']))
            raise Exception(e.response.json()['message'])
        except Exception as e:
            raise e

    def start_analysis(self, user, organization, workflow):
        """Start a workflow."""
        try:
            (response,
             http_response) = self._client.api.set_analysis_status(
                                  user=user,
                                  organization=organization,
                                  analysis_id_or_name=workflow,
                                  status='start').result()
            if http_response.status_code == 200:
                return response
            else:
                raise Exception(
                    "Expected status code 200 but replied with "
                    "{status_code}".format(
                        status_code=http_response.status_code))

        except HTTPError as e:
            logging.debug(
                'Workflow could not be started: '
                '\nStatus: {}\nReason: {}\n'
                'Message: {}'.format(e.response.status_code,
                                     e.response.reason,
                                     e.response.json()['message']))
            raise Exception(e.response.json()['message'])
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
                 analysis_id_or_name=analysis_id,
                 file_content=file_,
                 file_name=file_name).result()

            if http_response.status_code == 200:
                return response
            else:
                raise Exception(
                    "Expected status code 200 but replied with "
                    "{status_code}".format(
                        status_code=http_response.status_code))

        except HTTPError as e:
            logging.debug(
                'Input files could not be uploaded: '
                '\nStatus: {}\nReason: {}\n'
                'Message: {}'.format(e.response.status_code,
                                     e.response.reason,
                                     e.response.json()['message']))
            raise Exception(e.response.json()['message'])
        except Exception as e:
            raise e

    def seed_analysis_code(self, user, organization, analysis_id, file_,
                           file_name):
        """Seed analysis with code."""
        try:
            (response,
             http_response) = self._client.api.seed_analysis_code(
                 user=user,
                 organization=organization,
                 analysis_id_or_name=analysis_id,
                 file_content=file_,
                 file_name=file_name).result()

            if http_response.status_code == 200:
                return response
            else:
                raise Exception(
                    "Expected status code 200 but replied with "
                    "{status_code}".format(
                        status_code=http_response.status_code))

        except HTTPError as e:
            logging.debug(
                'Code file could not be uploaded: '
                '\nStatus: {}\nReason: {}\n'
                'Message: {}'.format(e.response.status_code,
                                     e.response.reason,
                                     e.response.json()['message']))
            raise Exception(e.response.json()['message'])
        except Exception:
            raise

    def get_workflow_logs(self, user, organization, analysis_id):
        """Get logs from a workflow engine."""
        try:
            (response,
             http_response) = self._client.api.get_analysis_logs(
                 user=user,
                 organization=organization,
                 analysis_id_or_name=analysis_id).result()

            if http_response.status_code == 200:
                return response
            else:
                raise Exception(
                    "Expected status code 200 but replied with "
                    "{status_code}".format(
                        status_code=http_response.status_code))

        except HTTPError as e:
            logging.debug(
                'Workflow logs could not be retrieved: '
                '\nStatus: {}\nReason: {}\n'
                'Message: {}'.format(e.response.status_code,
                                     e.response.reason,
                                     e.response.json()['message']))
            raise Exception(e.response.json()['message'])
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
                 analysis_id_or_name=analysis_id,
                 file_name=file_name).result()

            if http_response.status_code == 200:
                return http_response.raw_bytes
            else:
                raise Exception(
                    "Expected status code 200 but replied with "
                    "{status_code}".format(
                        status_code=http_response.status_code))

        except HTTPError as e:
            logging.debug(
                'Output file could not be downloaded: '
                '\nStatus: {}\nReason: {}\n'
                'Message: {}'.format(e.response.status_code,
                                     e.response.reason,
                                     e.response.json()['message']))
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
                 analysis_id_or_name=analysis_id).result()

            if http_response.status_code == 200:
                return response
            else:
                raise Exception(
                    "Expected status code 200 but replied with "
                    "{status_code}".format(
                        status_code=http_response.status_code))

        except HTTPError as e:
            logging.debug(
                'Analysis input file list could not be retrieved: '
                '\nStatus: {}\nReason: {}\n'
                'Message: {}'.format(e.response.status_code,
                                     e.response.reason,
                                     e.response.json()['message']))
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
                 analysis_id_or_name=analysis_id).result()

            if http_response.status_code == 200:
                return response
            else:
                raise Exception(
                    "Expected status code 200 but replied with "
                    "{status_code}".format(
                        status_code=http_response.status_code))

        except HTTPError as e:
            logging.debug(
                'Analysis output file list could not be retrieved: '
                '\nStatus: {}\nReason: {}\n'
                'Message: {}'.format(e.response.status_code,
                                     e.response.reason,
                                     e.response.json()['message']))
            raise Exception(e.response.json()['message'])
        except Exception as e:
            raise e

    def get_analysis_code(self, user, organization, analysis_id):
        """Return the list of code files for a given analysis.

        :param user: UUID of the analysis owner.
        :param organization: Organization which the user belongs to.
        :param analysis_id: UUID which identifies the analysis.
        :returns: A list of dictionaries composed by the `name`, `size` and
                  `last-modified`.
        """
        try:
            (response,
             http_response) = self._client.api.get_analysis_code(
                 user=user,
                 organization=organization,
                 analysis_id_or_name=analysis_id).result()

            if http_response.status_code == 200:
                return response
            else:
                raise Exception(
                    "Expected status code 200 but replied with "
                    "{status_code}".format(
                        status_code=http_response.status_code))

        except HTTPError as e:
            logging.debug(
                'Analysis code files list could not be retrieved: '
                '\nStatus: {}\nReason: {}\n'
                'Message: {}'.format(e.response.status_code,
                                     e.response.reason,
                                     e.response.json()['message']))
            raise Exception(e.response.json()['message'])
        except Exception as e:
            raise e

    def upload_to_server(self, user, organization, workflow,
                         paths, upload_type):
        """Upload file or directory to REANA-Server.

        Shared e.g. by `code upload` and `inputs upload`.

        :param user: User ID
        :param organization: Organization ID
        :param workflow: ID of that Workflow whose workspace should be
            used to store the files.
        :param paths: Absolute filepath(s) of files to be uploaded.
        :param upload_type: Which type of upload is this.
        :type upload_type: reana-client.utils.UploadType
        """
        if not workflow:
            raise ValueError(
                'Workflow name or id must be provided')
        if not paths:
            raise ValueError(
                'Please provide path(s) to file(s) that '
                'should be uploaded to workspace.')
        if not upload_type:
            raise ValueError(
                "Please provide an upload type one of '{}' or '{}'.".
                format(str(UploadType.inputs), str(UploadType.code)))

        logging.info('Workflow "{}" selected'.format(workflow))

        # Check if multiple paths were given and iterate over them
        if type(paths) is list or type(paths) is tuple:
            for path in paths:
                self.upload_to_server(user, organization, workflow,
                                      path, upload_type)
        # `paths` points to a single file or directory
        else:
            path = paths
            if '..' in paths.split('/'):
                raise FileUploadError('Path cannot contain ".."')

            # Check if input is a directory and upload everything
            # including subdirectories.

            if os.path.isdir(path):
                logging.debug("'{}' is a directory.".format(path))
                logging.info("Uploading contents of folder '{}' ..."
                             .format(path))
                for root, dirs, files in os.walk(path, topdown=False):
                    responses = []
                    for next_path in files + dirs:
                        response = self.upload_to_server(
                            user, organization, workflow,
                            os.path.join(root, next_path),
                            upload_type)
                        responses.append(os.path.join(root, next_path))
                return responses

            # Check if input is an absolute path and upload file.
            else:
                with open(path) as f:
                    fname = os.path.basename(f.name)
                    analysis_root = get_analysis_root()
                    if not path.startswith(analysis_root):
                        raise FileUploadError(
                            'Files and directories to be uploaded'
                            'must be under the analysis root directory.')
                    # Calculate the path that will store the file
                    # in the workflow controller, by subtracting
                    # the analysis root path from the file path
                    save_path = path.replace(analysis_root, '')
                    # Remove prepending dirs named "." or as the upload type
                    while len(save_path.split('/')) > 1 and \
                            save_path.split('/')[0] in \
                            [UploadType(upload_type).name, '.']:
                        save_path = "/".join(
                            save_path.strip("/").split('/')[1:])
                    logging.debug("'{}' is an absolute filepath."
                                  .format(os.path.basename(fname)))
                    logging.info("Uploading '{}' ...".format(fname))
                    try:
                        if upload_type is UploadType.code:
                            response = self.seed_analysis_code(
                                user, organization, workflow, f, save_path)
                        elif upload_type is UploadType.inputs:
                            response = self.seed_analysis_inputs(
                                user, organization, workflow, f, save_path)
                        else:
                            logging.warning("Unknown upload type of '{}'."
                                            "File '{}' was not uploaded."
                                            .format(upload_type, path))
                        if response:
                            logging.info("File '{}' was successfully "
                                         "uploaded.".format(fname))
                    except Exception as e:
                        logging.debug(traceback.format_exc())
                        logging.debug(str(e))
                        logging.info("Something went wrong while uploading {}".
                                     format(fname))
                    return response
