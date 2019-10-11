# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2017, 2018 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
"""REANA REST API client."""

import json
import logging
import os
import traceback
from functools import partial

import requests
from bravado.exception import HTTPError
from reana_client.config import ERROR_MESSAGES, WORKFLOW_ENGINES
from reana_client.errors import FileDeletionError, FileUploadError
from reana_client.utils import (_validate_reana_yaml, get_workflow_root,
                                is_uuid_v4)
from reana_commons.api_client import get_current_api_client
from reana_commons.errors import (REANASecretAlreadyExists,
                                  REANASecretDoesNotExist)
from werkzeug.local import LocalProxy

try:
    from urllib.parse import urljoin
except ImportError:
    from urlparse import urljoin

current_rs_api_client = LocalProxy(
    partial(get_current_api_client, component='reana-server'))


def ping():
    """Health check REANA server."""
    try:
        response, http_response = current_rs_api_client.api.ping().result()
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


def get_workflows(access_token, type, verbose=False):
    """List all existing workflows."""
    try:
        response, http_response = current_rs_api_client.api.\
            get_workflows(access_token=access_token, verbose=verbose,
                          type=type).result()
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


def get_workflow_status(workflow, access_token):
    """Get status of previously created workflow."""
    try:
        response, http_response = current_rs_api_client.api\
            .get_workflow_status(
                workflow_id_or_name=workflow,
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
            'Analysis status could not be retrieved: '
            '\nStatus: {}\nReason: {}\n'
            'Message: {}'.format(e.response.status_code,
                                 e.response.reason,
                                 e.response.json()['message']))
        raise Exception(e.response.json()['message'])
    except Exception as e:
        raise e


def create_workflow(reana_specification, name, access_token):
    """Create a workflow."""
    try:
        (response,
            http_response) = current_rs_api_client.api.create_workflow(
                reana_specification=json.loads(json.dumps(
                    reana_specification, sort_keys=True)),
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


def create_workflow_from_json(workflow_json, name, access_token,
                              parameters=None, workflow_engine='yadage',
                              outputs=None):
    """Create a workflow from json specification.

    :param workflow_json: workflow specification in json format.
    :param name: name or UUID of the workflow to be started.
    :param access_token: Access token of the current user.
    :param parameters: workflow input parameters dictionary.
    :param workflow_engine: one of the workflow engines (yadage, serial, cwl)
    :param outputs: dictionary with expected workflow outputs.

    :Example:

      .. code:: python

        create_workflow_from_json(
            workflow_json=workflow_json,
            name='workflow_name.1',
            access_token='access_token',
            parameters={'files': ['file.txt'], 'parameters': {'key': 'value'}},
            workflow_engine='serial')
    """
    if is_uuid_v4(name):
        raise ValueError('Workflow name cannot be a valid UUIDv4')
    if not access_token:
        raise Exception(ERROR_MESSAGES['missing_access_token'])
    if os.environ.get('REANA_SERVER_URL') is None:
        raise Exception('Environment variable REANA_SERVER_URL is not set')
    workflow_engine = workflow_engine.lower()
    if workflow_engine not in WORKFLOW_ENGINES:
        raise Exception('Workflow engine - {} not found. You must use one of '
                        'these engines - {}'.format(workflow_engine,
                                                    WORKFLOW_ENGINES))
    try:
        reana_yaml = {}
        reana_yaml['workflow'] = {'specification': workflow_json}
        reana_yaml['workflow']['type'] = workflow_engine
        if parameters:
            reana_yaml['inputs'] = parameters
        if outputs:
            reana_yaml['outputs'] = outputs
        _validate_reana_yaml(reana_yaml)
        reana_specification = reana_yaml
        (response,
            http_response) = current_rs_api_client.api.create_workflow(
                reana_specification=json.loads(json.dumps(
                    reana_specification, sort_keys=True)),
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


def start_workflow(workflow, access_token, parameters):
    """Start a workflow.

    :param workflow: name or id of previously created workflow.
    :param access_token: access token of the current user.
    :param parameters: dict of workflow parameters to override the original
        ones (after workflow creation).
    """
    try:
        (response,
         http_response) = current_rs_api_client.api.start_workflow(
            workflow_id_or_name=workflow,
            access_token=access_token,
            parameters=parameters).result()
        if http_response.status_code == 200:
            return response
        else:
            raise Exception(
                "Expected status code 200 but replied with "
                "{status_code}".format(status_code=http_response.status_code))

    except HTTPError as e:
        logging.debug(
            'Workflow run could not be started: '
            '\nStatus: {}\nReason: {}\n'
            'Message: {}'.format(e.response.status_code,
                                 e.response.reason,
                                 e.response.json()['message']))
        raise Exception(e.response.json()['message'])
    except Exception as e:
        raise e


def upload_file(workflow_id, file_, file_name, access_token):
    """Upload file to workflow workspace.

    :param workflow_id: UID which identifies the workflow.
    :param file_: content of a file that will be uploaded.
    :param file_name: name of a file that will be uploaded.
    :param access_token: access token of the current user.
    """
    try:
        api_url = current_rs_api_client.swagger_spec.__dict__.get('api_url')
        endpoint = \
            current_rs_api_client.api.upload_file.operation.path_name.format(
                workflow_id_or_name=workflow_id)
        http_response = requests.post(urljoin(api_url, endpoint),
                                      data=file_,
                                      params={'file_name': file_name,
                                              'access_token': access_token},
                                      headers={'Content-Type':
                                               'application/octet-stream'},
                                      verify=False)
        return http_response.json()
    except requests.exceptions.ConnectionError:
        logging.debug(
            'File could not be uploaded.', exc_info=True)
        raise Exception(
            'Could not connect to the server {}'.format(api_url))
    except requests.exceptions.HTTPError as e:
        logging.debug(
            'The server responded with an HTTP error code.', exc_info=True)
        raise Exception(
            'Unexpected response from the server: \n{}'.format(e.response))
    except requests.exceptions.Timeout:
        logging.debug(
            'Timeout while trying to establish connection.', exc_info=True)
        raise Exception('The request to the server has timed out.')
    except requests.exceptions.RequestException:
        logging.debug(
            'Something went wrong while connecting to the server.',
            exc_info=True)
        raise Exception('The request to the server has failed for an '
                        'unknown reason.')
    except Exception as e:
        raise e


def get_workflow_logs(workflow_id, access_token):
    """Get logs from a workflow engine."""
    try:
        (response,
            http_response) = current_rs_api_client.api.get_workflow_logs(
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


def download_file(workflow_id, file_name, access_token):
    """Downdload the requested file if it exists.

    :param workflow_id: UUID which identifies the workflow.
    :param file_name: File name or path to the file requested.
    :returns: .
    """
    try:
        logging.getLogger("urllib3").setLevel(logging.CRITICAL)
        (response,
            http_response) = current_rs_api_client.api.download_file(
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


def delete_file(workflow_id, file_name, access_token):
    """Delete the requested file if it exists.

    :param workflow_id: UUID which identifies the workflow.
    :param file_name: File name or path to the file requested.
    """
    try:
        (response,
            http_response) = current_rs_api_client.api.delete_file(
                workflow_id_or_name=workflow_id,
                file_name=file_name,
                access_token=access_token).result()
        if http_response.status_code == 200 and (response['deleted'] or
                                                 response['failed']):
            return response
        elif not (response['deleted'] or response['failed']):
            raise FileDeletionError('{} did not match any existing '
                                    'file.'.format(file_name))
        else:
            raise Exception(
                "Expected status code 200 but replied with "
                "{status_code}".format(
                    status_code=http_response.status_code))

    except HTTPError as e:
        logging.debug(
            'File could not be downloaded: '
            '\nStatus: {}\nReason: {}\n'
            'Message: {}'.format(e.response.status_code,
                                 e.response.reason,
                                 e.response.json()['message']))
        raise Exception(e.response.json()['message'])
    except Exception as e:
        raise e


def list_files(workflow_id, access_token):
    """Return the list of file for a given workflow workspace.

    :param workflow_id: UUID which identifies the workflow.
    :returns: A list of dictionaries composed by the `name`, `size` and
                `last-modified`.
    """
    try:
        (response,
            http_response) = current_rs_api_client.api.get_files(
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


def upload_to_server(workflow, paths, access_token):
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
            upload_to_server(workflow, path, access_token)
    # `paths` points to a single file or directory
    else:
        path = paths
        if '..' in paths.split('/'):
            raise FileUploadError('Path cannot contain ".."')

        # Check if input is a directory and upload everything
        # including subdirectories.

        if os.path.isdir(path):
            logging.debug("'{}' is a directory.".format(path))
            logging.info("Uploading contents of folder '{}' ...".format(path))
            for root, dirs, files in os.walk(path, topdown=False):
                uploaded_files = []
                for next_path in files + dirs:
                    next_uploaded_files = upload_to_server(
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
                    response = upload_file(workflow, f, save_path,
                                           access_token)
                    logging.info("File '{}' was successfully "
                                 "uploaded.".format(fname))
                    if symlink:
                        save_path = 'symlink:{}'.format(save_path)
                    return [save_path]
                except Exception as e:
                    logging.debug(traceback.format_exc())
                    logging.debug(str(e))
                    logging.info("Something went wrong while uploading {}"
                                 .format(fname))


def get_workflow_parameters(workflow, access_token):
    """Get parameters of previously created workflow."""
    try:
        response, http_response = current_rs_api_client.api\
            .get_workflow_parameters(
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
            'Workflow parameters could not be retrieved: '
            '\nStatus: {}\nReason: {}\n'
            'Message: {}'.format(e.response.status_code,
                                 e.response.reason,
                                 e.response.json()['message']))
        raise Exception(e.response.json()['message'])
    except Exception as e:
        raise e


def delete_workflow(workflow, all_runs, hard_delete,
                    workspace, access_token):
    """Delete a workflow."""
    try:
        parameters = {
            'all_runs': True if all_runs == 1 else False,
            'hard_delete': True if hard_delete == 1 else False,
            'workspace': True if hard_delete == 1 or workspace == 1 else False
        }
        (response,
            http_response) = current_rs_api_client.api.set_workflow_status(
            workflow_id_or_name=workflow,
            status='deleted',
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
            'Workflow run could not be deleted: '
            '\nStatus: {}\nReason: {}\n'
            'Message: {}'.format(e.response.status_code,
                                 e.response.reason,
                                 e.response.json()['message']))
        raise Exception(e.response.json()['message'])
    except Exception as e:
        raise e


def stop_workflow(workflow, force_stop, access_token):
    """Stop a workflow."""
    try:
        parameters = {'force_stop': force_stop}
        (response, http_response) = current_rs_api_client.api\
            .set_workflow_status(
            workflow_id_or_name=workflow,
            status='stop',
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
            'Workflow run could not be stopped: '
            '\nStatus: {}\nReason: {}\n'
            'Message: {}'.format(e.response.status_code,
                                 e.response.reason,
                                 e.response.json()['message']))
        raise Exception(e.response.json()['message'])
    except Exception as e:
        raise e


def diff_workflows(workflow_id_a, workflow_id_b,
                   brief, access_token, context_lines):
    """Return the list of differences between two workflows.

    :param workflow_id_a: UUID which identifies the first workflow.
    :param workflow_id_b: UUID which identifies the second workflow.
    :param brief: Flag specifying desired detail in diff.
    :param context_lines: Optional parameter to set the number of
                          context lines shown in the diff output.
    :param access_token: API token of user requesting diff.
    :returns: A list of dictionaries composed by `asset`, `type`, `lines`,
        `a` and `b`. Asset refers to the workflow asset where a
        difference was found, type refers to the asset type, lines refer
        to the lines of the file where the differences are and a, b fields
        are the actual lines that differ.
    """
    try:
        (response,
         http_response) = current_rs_api_client.api.get_workflow_diff(
             workflow_id_or_name_a=workflow_id_a,
             workflow_id_or_name_b=workflow_id_b,
             brief=brief,
             context_lines=context_lines,
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


def open_interactive_session(workflow, access_token,
                             interactive_session_type,
                             interactive_session_configuration):
    """Open an interactive session inside the workflow workspace.

    :param workflow: Workflow which workspace will be available inside the
        interactive session.
    :param access_token: Workflow owner REANA access token.
    :param interactive_session_type: Type of interactive session to spawn.
    :param interactive_session_configuration: Specific configuration for
        the interactive session.

    :return: Gives the relative path to the interactive service.
    """
    try:
        (response, http_response) = current_rs_api_client.api\
            .open_interactive_session(
            workflow_id_or_name=workflow,
            access_token=access_token,
            interactive_session_type=interactive_session_type,
            interactive_session_configuration=interactive_session_configuration
        ).result()
        if http_response.status_code == 200:
            return response['path']
        else:
            raise Exception(
                "Expected status code 200 but replied with "
                "{status_code}".format(
                    status_code=http_response.status_code))
    except HTTPError as e:
        logging.debug(
            'Interactive session could not be opened: '
            '\nStatus: {}\nReason: {}\n'
            'Message: {}'.format(e.response.status_code,
                                 e.response.reason,
                                 e.response.json()['message']))
        raise Exception(e.response.json()['message'])
    except Exception as e:
        raise e


def close_interactive_session(workflow, access_token):
    """Close an interactive workflow session.

    :param workflow: Workflow name to close.
    :param access_token: Workflow owner REANA access token.

    :return: Gives the relative path to the interactive service.
    """
    try:
        (response, http_response) = current_rs_api_client.api\
            .close_interactive_session(
            workflow_id_or_name=workflow,
            access_token=access_token,
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
            'Interactive session could not be closed: '
            '\nStatus: {}\nReason: {}\n'
            'Message: {}'.format(e.response.status_code,
                                 e.response.reason,
                                 e.response.json()['message']))
        raise Exception(e.response.json()['message'])
    except Exception as e:
        raise e


def mv_files(source, target, workflow, access_token):
    """Move target file(s) within workspace.

    :param source: source filename or path.
    :param target: target filename or path.
    :param workflow_id: UUID which identifies the workflowself.
    :param access_token: token of user.
    """
    try:
        (response, http_response) = current_rs_api_client.api.move_files(
            source=source,
            target=target,
            workflow_id_or_name=workflow,
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
            'Files move command failed: '
            '\nStatus: {}\nReason: {}\n'
            'Message: {}'.format(e.response.status_code,
                                 e.response.reason,
                                 e.response.json()['message']))
        raise Exception(e.response.json()['message'])
    except Exception as e:
        raise e


def get_workflow_disk_usage(workflow, parameters, access_token):
    """Display disk usage workflow."""
    try:
        (response, http_response) = current_rs_api_client.api\
            .get_workflow_disk_usage(
            workflow_id_or_name=workflow,
            parameters=parameters,
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
            'Workflow disk usage could not be retrieved: '
            '\nStatus: {}\nReason: {}\n'
            'Message: {}'.format(e.response.status_code,
                                 e.response.reason,
                                 e.response.json()['message']))
        raise Exception(e.response.json()['message'])
    except Exception as e:
        raise e


def add_secrets(secrets, overwrite, access_token):
    """Add new secrets.

    :param secrets: dictionary containing all the secrets to be sent.
      The dictionary with secret names for keys and for each key there is
       a dictionary with two fields:
      - 'value':  a base64 encoded file or literal string
      - 'type': 'file' or 'env'
    :param overwrite: whether secrets should be overwritten when they
     already exist.
    :param access_token: access token of the current user.

    """
    try:
        (response,
            http_response) = current_rs_api_client.api.add_secrets(
            secrets=secrets,
            access_token=access_token,
            overwrite=overwrite).result()
        if http_response.status_code == 201:
            return response
        else:
            raise Exception(
                "Expected status code 201 but replied with "
                "{status_code}".format(
                    status_code=http_response.status_code))

    except HTTPError as e:
        logging.debug(
            'Secrets could not be added: '
            '\nStatus: {}\nReason: {}\n'
            'Message: {}'.format(e.response.status_code,
                                 e.response.reason,
                                 e.response.json()['message']))
        if e.status_code == 409:
            raise REANASecretAlreadyExists()
        else:
            raise Exception(e.response.json()['message'])
    except Exception as e:
        raise e


def delete_secrets(secrets, access_token):
    """Delete a list of secrets.

    :param secrets: List of secret names to be deleted.
    :param access_token: access token of the current user.

    """
    try:
        (response,
            http_response) = current_rs_api_client.api.delete_secrets(
            secrets=secrets,
            access_token=access_token).result()
        if http_response.status_code == 200:
            return response
        else:
            raise Exception(
                "Expected status code 200 but replied with "
                "{status_code}".format(
                    status_code=http_response.status_code))

    except HTTPError as e:
        if e.response.status_code == 404:
            raise REANASecretDoesNotExist(e.response.json())
        else:
            logging.debug(
                'Secrets could not be deleted: '
                '\nStatus: {}\nReason: {}\n'
                'Message: {}'.format(e.response.status_code,
                                     e.response.reason,
                                     e.response.json()['message']))
        raise Exception(e.response.json()['message'])
    except Exception as e:
        raise e


def list_secrets(access_token):
    """List user secrets.

    :param access_token: access token of the current user.

    """
    try:
        (response,
            http_response) = current_rs_api_client.api.get_secrets(
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
            'Secrets could not be listed: '
            '\nStatus: {}\nReason: {}\n'
            'Message: {}'.format(e.response.status_code,
                                 e.response.reason,
                                 e.response.json()['message']))
        raise Exception(e.response.json()['message'])
    except Exception as e:
        raise e
