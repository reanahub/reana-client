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
from reana_client.utils import get_workflow_root


class Client(object):
    """REANA API client code."""

    def __init__(self, server_url):
        """Create a OpenAPI client for REANA server."""
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
        """Health check REANA server."""
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
                'REANA server health check failed: '
                '\nStatus: {}\nReason: {}\n'
                'Message: {}'.format(e.response.status_code,
                                     e.response.reason,
                                     e.response.json()['message']))
            raise Exception(e.response.json()['message'])
        except Exception as e:
            raise e

    def get_workflows(self, access_token):
        """List all existing workflows."""
        try:

            response, http_response = self._client.api.\
                get_workflows(access_token=access_token).result()
            if http_response.status_code == 200:
                return response
            else:
                raise Exception(
                    "Expected status code 200 but replied with "
                    "{status_code}".format(
                        status_code=http_response.status_code))

        except HTTPError as e:
            logging.debug(
                'The list of workflows could not be retrieved: '
                '\nStatus: {}\nReason: {}\n'
                'Message: {}'.format(e.response.status_code,
                                     e.response.reason,
                                     e.response.json()['message']))
            raise Exception(e.response.json()['message'])
        except Exception as e:
            raise e

    def get_workflow_status(self, workflow, access_token):
        """Get status of previously created workflow."""
        try:
            response, http_response = self.\
                _client.api.get_workflow_status(
                    workflow_id_or_name=workflow,
                    access_token=access_token)\
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
                'Analysis status could not be retrieved: '
                '\nStatus: {}\nReason: {}\n'
                'Message: {}'.format(e.response.status_code,
                                     e.response.reason,
                                     e.response.json()['message']))
            raise Exception(e.response.json()['message'])
        except Exception as e:
            raise e

    def create_workflow(self, reana_spec, name, access_token):
        """Create a workflow."""
        try:
            (response,
             http_response) = self._client.api.create_workflow(
                 reana_spec=json.loads(json.dumps(
                     reana_spec, sort_keys=True)),
                 workflow_name=name,
                 access_token=access_token).result()
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

    def start_workflow(self, workflow, access_token, parameters):
        """Start a workflow."""
        try:
            (response,
             http_response) = self._client.api.set_workflow_status(
                 workflow_id_or_name=workflow,
                 status='start',
                 access_token=access_token,
                 parameters=parameters).result()
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

    def upload_file(self, workflow_id, file_, file_name, access_token):
        """Upload file to workflow workspace."""
        try:
            (response,
             http_response) = self._client.api.upload_file(
                 workflow_id_or_name=workflow_id,
                 file_content=file_,
                 file_name=file_name,
                 access_token=access_token).result()

            if http_response.status_code == 200:
                return response
            else:
                raise Exception(
                    "Expected status code 200 but replied with "
                    "{status_code}".format(
                        status_code=http_response.status_code))

        except HTTPError as e:
            logging.debug(
                'File could not be uploaded: '
                '\nStatus: {}\nReason: {}\n'
                'Message: {}'.format(e.response.status_code,
                                     e.response.reason,
                                     e.response.json()['message']))
            raise Exception(e.response.json()['message'])
        except Exception as e:
            raise e

    def get_workflow_logs(self, workflow_id, access_token):
        """Get logs from a workflow engine."""
        try:
            (response,
             http_response) = self._client.api.get_workflow_logs(
                 workflow_id_or_name=workflow_id,
                 access_token=access_token).result()

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

    def download_file(self, workflow_id, file_name, access_token):
        """Downdload the requested file if it exists.

        :param workflow_id: UUID which identifies the workflow.
        :param file_name: File name or path to the file requested.
        :returns: .
        """
        try:
            logging.getLogger("urllib3").setLevel(logging.CRITICAL)
            (response,
             http_response) = self._client.api.download_file(
                 workflow_id_or_name=workflow_id,
                 file_name=file_name,
                 access_token=access_token).result()

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

    def get_files(self, workflow_id, access_token):
        """Return the list of file for a given workflow workspace.

        :param workflow_id: UUID which identifies the workflow.
        :returns: A list of dictionaries composed by the `name`, `size` and
                  `last-modified`.
        """
        try:
            (response,
             http_response) = self._client.api.get_files(
                 workflow_id_or_name=workflow_id,
                 access_token=access_token).result()

            if http_response.status_code == 200:
                return response
            else:
                raise Exception(
                    "Expected status code 200 but replied with "
                    "{status_code}".format(
                        status_code=http_response.status_code))

        except HTTPError as e:
            logging.debug(
                'File list could not be retrieved: '
                '\nStatus: {}\nReason: {}\n'
                'Message: {}'.format(e.response.status_code,
                                     e.response.reason,
                                     e.response.json()['message']))
            raise Exception(e.response.json()['message'])
        except Exception as e:
            raise e

    def upload_to_server(self, workflow, paths, access_token):
        """Upload file or directory to REANA server.

        Shared e.g. by `code upload` and `inputs upload`.

        :param workflow: ID of that Workflow whose workspace should be
            used to store the files.
        :param paths: Absolute filepath(s) of files to be uploaded.
        """
        if not workflow:
            raise ValueError(
                'Workflow name or id must be provided')
        if not paths:
            raise ValueError(
                'Please provide path(s) to file(s) that '
                'should be uploaded to workspace.')

        logging.info('Workflow "{}" selected'.format(workflow))

        # Check if multiple paths were given and iterate over them
        if type(paths) is list or type(paths) is tuple:
            for path in paths:
                self.upload_to_server(workflow, path, access_token)
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
                    uploaded_files = []
                    for next_path in files + dirs:
                        next_uploaded_files = self.upload_to_server(
                            workflow, os.path.join(root, next_path),
                            access_token)
                        if next_uploaded_files:
                            uploaded_files.extend(next_uploaded_files)
                return uploaded_files

            # Check if input is an absolute path and upload file.
            else:
                symlink = False
                if os.path.islink(path):
                    path = os.path.realpath(path)
                    logging.info(
                        'Symlink {} found, uploading'
                        ' hard copy.'.
                        format(path))
                    symlink = True
                with open(path, 'rb') as f:
                    fname = os.path.basename(f.name)
                    workflow_root = get_workflow_root()
                    if not path.startswith(workflow_root):
                        raise FileUploadError(
                            'Files and directories to be uploaded'
                            'must be under the workflow root directory.')
                    # Calculate the path that will store the file
                    # in the workflow controller, by subtracting
                    # the workflow root path from the file path
                    save_path = path.replace(workflow_root, '')
                    # Remove prepending dirs named "." or as the upload type
                    while len(save_path.split('/')) > 1 and \
                            save_path.split('/')[0] == '.':
                        save_path = "/".join(
                            save_path.strip("/").split('/')[1:])
                    logging.debug("'{}' is an absolute filepath."
                                  .format(os.path.basename(fname)))
                    logging.info("Uploading '{}' ...".format(fname))
                    try:
                        response = self.upload_file(workflow, f,
                                                    save_path, access_token)
                        logging.info("File '{}' was successfully "
                                     "uploaded.".format(fname))
                        if symlink:
                            save_path = 'symlink:{}'.format(save_path)
                        return [save_path]
                    except Exception as e:
                        logging.debug(traceback.format_exc())
                        logging.debug(str(e))
                        logging.info("Something went wrong while uploading {}".
                                     format(fname))
