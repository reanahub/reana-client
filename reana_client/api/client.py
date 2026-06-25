# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
"""REANA REST API client."""

import logging
import os
import traceback
from functools import partial
from urllib.parse import urljoin

import requests
from bravado.exception import HTTPError
from reana_client.api.utils import get_content_disposition_filename
from reana_client.errors import FileDeletionError, FileUploadError
from reana_client.utils import is_regular_path
from reana_commons.api_client import get_current_api_client
from reana_commons.errors import REANASecretAlreadyExists, REANASecretDoesNotExist
from reana_commons.validation.sandbox import REANA_SPEC_FILENAMES
from werkzeug.local import LocalProxy

current_rs_api_client = LocalProxy(
    partial(get_current_api_client, component="reana-server")
)


def ping(access_token):
    """Check if the REANA server is reachable and the user is correctly authenticated.

    :param access_token: access token of the current user.

    :return: a dictionary with the ``status`` key (``"Connected"`` if the server is reachable, the error message if
             there is a problem), the ``error`` key (``True`` if there is an error, ``False`` otherwise),
             and info about the current user in ``full_name`` and ``email``.
    """
    try:
        response, http_response = current_rs_api_client.api.get_you(
            access_token=access_token
        ).result()
        if http_response.status_code == 200:
            response["status"] = "Connected"
            response["error"] = False
            return response
        else:
            raise Exception(
                "Expected status code 200 but replied with "
                "{status_code}".format(status_code=http_response.status_code)
            )

    except HTTPError as e:
        logging.debug(
            "REANA server health check failed: "
            "\nStatus: {}\nReason: {}".format(e.response.status_code, e.response.reason)
        )
        if e.response.status_code == 404:
            return {"status": "ERROR: INVALID SERVER", "error": True}
        if e.response.status_code == 403:
            return {"status": "ERROR: INVALID ACCESS TOKEN", "error": True}
        raise Exception(e.response)
    except Exception:
        return {"status": "ERROR: INVALID SERVER", "error": True}


def get_user_quota(access_token):
    """Retrieve user quota usage and limits.

    :param access_token: access token of the current user.

    :return: a dictionary with the information about the usage and limits of the user's quota.
             The keys are ``cpu`` and ``disk``, and refer to the respective usage and limits.
    """
    try:
        response, http_response = current_rs_api_client.api.get_you(
            access_token=access_token
        ).result()
        if http_response.status_code == 200:
            return response["quota"]
        raise Exception(
            "Expected status code 200 but replied with "
            "{status_code}".format(status_code=http_response.status_code)
        )

    except HTTPError as e:
        logging.debug(
            "User quotas could not be retrieved: "
            "\nStatus: {}\nReason: {}\n"
            "Message: {}".format(
                e.response.status_code, e.response.reason, e.response.json()["message"]
            )
        )
        raise Exception(e.response.json()["message"])
    except Exception as e:
        raise e


def get_workflows(
    access_token,
    type,
    verbose=False,
    page=None,
    size=None,
    status=None,
    search=None,
    include_progress=None,
    include_workspace_size=None,
    workflow=None,
    shared=None,
    shared_by=None,
    shared_with=None,
):
    """List all existing workflows.

    :param access_token: access token of the current user.
    :param type: type of workflow to be listed: ``"interactive"`` if you want to
                 list only the workflows that have an interactive session attached, with the
                 info about the session, or ``"batch"`` (default) otherwise.
    :param verbose: show detailed information about workflows.
    :param page: page number of the paginated list of workflows.
    :param size: number of workflows per page.
    :param status: filter workflows by status.
    :param search: search workflows by name.
    :param include_progress: include progress information in the response.
    :param include_workspace_size: include workspace size information in the response.
    :param workflow: name or id of the workflow.
    :param shared: list all shared (owned and unowned) workflows.
    :param shared_by: list workflows shared by the specified user(s).
    :param shared_with: list workflows shared with the specified user(s).

    :return: a list of dictionaries with the information about the workflows.
             The information includes the workflow ``name``, ``id``, ``status``, ``size``,
             ``user`` (given as the user's ID), and info about the interactive session if
             present.
    """
    try:
        response, http_response = current_rs_api_client.api.get_workflows(
            access_token=access_token,
            verbose=verbose,
            type=type,
            page=page,
            size=size,
            status=status,
            search=search,
            include_progress=include_progress,
            include_workspace_size=include_workspace_size,
            workflow_id_or_name=workflow,
            shared=shared,
            shared_by=shared_by,
            shared_with=shared_with,
        ).result()
        if http_response.status_code == 200:
            return response.get("items")
        raise Exception(
            "Expected status code 200 but replied with "
            "{status_code}".format(status_code=http_response.status_code)
        )

    except HTTPError as e:
        logging.debug(
            "The list of workflows could not be retrieved: "
            "\nStatus: {}\nReason: {}\n"
            "Message: {}".format(
                e.response.status_code, e.response.reason, e.response.json()["message"]
            )
        )
        raise Exception(e.response.json()["message"])
    except Exception as e:
        raise e


def get_workflow_status(workflow, access_token):
    """Get status of previously created workflow.

    :param workflow: name or id of the workflow.
    :param access_token: access token of the current user.

    :return: a dictionary with the information about the workflow status.
             The dictionary has the following keys: ``id``, ``logs``, ``name``,
             ``progress``, ``status``, ``user``.
    """
    try:
        response, http_response = current_rs_api_client.api.get_workflow_status(
            workflow_id_or_name=workflow, access_token=access_token
        ).result()
        if http_response.status_code == 200:
            return response
        else:
            raise Exception(
                "Expected status code 200 but replied with "
                "{status_code}".format(status_code=http_response.status_code)
            )

    except HTTPError as e:
        logging.debug(
            "Analysis status could not be retrieved: "
            "\nStatus: {}\nReason: {}\n"
            "Message: {}".format(
                e.response.status_code, e.response.reason, e.response.json()["message"]
            )
        )
        raise Exception(e.response.json()["message"])
    except Exception as e:
        raise e


_SPEC_BUNDLE_EXCLUDED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".snakemake",
    ".pytest_cache",
    "__pycache__",
}
_SPEC_BUNDLE_EXCLUDED_FILES = {
    ".coverage",
    "coverage.xml",
}


def _is_excluded_spec_bundle_path(parts, filename=None):
    """Return whether a path should be omitted from an uploaded spec bundle."""
    if any(part in _SPEC_BUNDLE_EXCLUDED_DIRS for part in parts):
        return True
    return filename in _SPEC_BUNDLE_EXCLUDED_FILES


def _load_spec_mapping(reana_file):
    """Best-effort parse of a REANA spec into a mapping.

    Used only to scope the upload bundle; if the file is malformed the server is
    the authority that produces the real validation error, so we return an empty
    mapping and let the (still uploaded) ``reana.yaml`` fail server-side.
    """
    import yaml

    try:
        with open(reana_file) as spec_file:
            loaded = yaml.safe_load(spec_file)
    except (OSError, yaml.YAMLError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _is_within_base(base_dir, abs_path):
    """Whether ``abs_path`` resolves to a location inside ``base_dir``.

    Uses ``realpath`` on both sides so a symlink or ``..`` segment that escapes
    the spec directory is detected and the file is never read or uploaded.
    """
    real_base = os.path.realpath(base_dir)
    real_path = os.path.realpath(abs_path)
    return real_path == real_base or real_path.startswith(real_base + os.sep)


def _add_file_member(members, base_dir, rel_path):
    """Add ``rel_path`` to ``members`` if it is a regular file inside ``base_dir``.

    Path containment is enforced client-side, before the file is opened: a
    member that is absolute, escapes ``base_dir`` (``../secret``, ``/etc/...``),
    or is a symlink (or sits under a symlinked parent) is skipped, so building
    the bundle never reads or transmits files from outside the spec directory.
    """
    abs_path = os.path.normpath(os.path.join(base_dir, rel_path))
    if not _is_within_base(base_dir, abs_path):
        return
    # ``is_regular_path`` rejects symlinks and symlinked parents.
    if not is_regular_path(abs_path) or not os.path.isfile(abs_path):
        return
    member = os.path.relpath(abs_path, base_dir)
    if member in REANA_SPEC_FILENAMES:
        # Keep the explicitly selected spec canonical; never clobber it.
        return
    members[member] = abs_path


def _add_workflow_file_members(members, base_dir, workflow_file):
    """Add ``workflow.file`` to the bundle, with its sub-tree if it lives in one.

    A workflow file in a sub-directory (e.g. ``workflow/snakemake/Snakefile``)
    typically imports co-located files (``include:``/``$import``/stage files), so
    its whole sub-tree is bundled. A top-level workflow file is bundled on its
    own — we do not fall back to gathering the entire spec directory.
    """
    abs_path = os.path.normpath(os.path.join(base_dir, workflow_file))
    workflow_dir = os.path.dirname(abs_path)

    # Never read or walk outside the spec directory: a workflow.file that escapes
    # the base dir (``../x``, an absolute path, a symlink) is not bundled. Per-file
    # containment is also enforced in ``_add_file_member`` below.
    if not _is_within_base(base_dir, workflow_dir):
        return

    same_dir = os.path.realpath(workflow_dir) == os.path.realpath(base_dir)
    if same_dir or not os.path.isdir(workflow_dir):
        _add_file_member(members, base_dir, workflow_file)
        return

    for root, dirs, files in os.walk(workflow_dir):
        root_parts = os.path.relpath(root, base_dir).split(os.sep)
        dirs[:] = [
            directory
            for directory in dirs
            if not _is_excluded_spec_bundle_path(root_parts + [directory])
        ]
        for filename in files:
            if _is_excluded_spec_bundle_path(root_parts, filename):
                continue
            _add_file_member(
                members,
                base_dir,
                os.path.relpath(os.path.join(root, filename), base_dir),
            )


def _gather_spec_members(reana_file):
    """Return ``{bundle_relative_path: local_path}`` for a scoped spec bundle.

    Bundles only what the server needs to load and validate the specification
    authoritatively:

    - the selected spec, always uploaded as the canonical ``reana.yaml``;
    - ``workflow.file`` (the engine workflow definition) and, when it lives in a
      sub-directory, that whole sub-tree, to capture co-located includes/imports
      (e.g. ``include: "rules/*.smk"`` in a Snakefile);
    - ``inputs.parameters.input`` when it points to an existing file (the
      Snakemake config / CWL job file read while loading the spec).

    Input *data* (``inputs.files``/``inputs.directories``) is intentionally NOT
    bundled here: it is uploaded separately into the workspace. Scoping the
    bundle keeps it small and avoids seeding unrelated/large files (``.venv``,
    sibling spec variants, datasets) into the workspace.

    :param reana_file: path to the local ``reana.yaml`` specification file.
    """
    base_dir = os.path.dirname(os.path.abspath(reana_file))
    reana_file = os.path.abspath(reana_file)

    # Preserve compatibility with callers passing ``-f myreana.yaml``: the
    # server still receives it under the canonical top-level name it searches.
    members = {"reana.yaml": reana_file}

    spec = _load_spec_mapping(reana_file)
    workflow = spec.get("workflow") or {}
    workflow_file = workflow.get("file")
    if isinstance(workflow_file, str) and workflow_file:
        _add_workflow_file_members(members, base_dir, workflow_file)

    parameters = (spec.get("inputs") or {}).get("parameters") or {}
    param_input = parameters.get("input")
    if isinstance(param_input, str) and param_input:
        _add_file_member(members, base_dir, param_input)

    return members


def _members_from_dir(bundle_dir):
    """Return ``{relative_path: local_path}`` for every file under a directory."""
    members = {}
    for root, dirs, files in os.walk(bundle_dir):
        rel_root = os.path.relpath(root, bundle_dir)
        root_parts = [] if rel_root == "." else rel_root.split(os.sep)
        dirs[:] = [
            directory
            for directory in dirs
            if not _is_excluded_spec_bundle_path(root_parts + [directory])
        ]
        for filename in files:
            abs_path = os.path.join(root, filename)
            if _is_excluded_spec_bundle_path(root_parts, filename):
                continue
            members[os.path.relpath(abs_path, bundle_dir)] = abs_path
    return members


def _post_spec_members(path, members, params):
    """POST a spec bundle (mapping of relative path -> local path) as multipart.

    Field names are the paths relative to the bundle root so the server's loader
    can resolve referenced files.

    :param path: API path to POST to (e.g. ``/api/workflows``).
    :param members: mapping of bundle-relative path to local file path.
    :param params: query parameters (e.g. ``access_token``, ``workflow_name``).
    :return: the ``requests`` response object.
    """
    from reana_client.utils import get_api_url

    open_files = {}
    try:
        for member, local_path in members.items():
            if not os.path.isfile(local_path):
                raise FileUploadError(
                    "Specification bundle file not found: {}".format(member)
                )
            open_files[member] = open(local_path, "rb")
        return requests.post(
            urljoin(get_api_url(), path),
            params=params,
            files=open_files,
            verify=False,
        )
    finally:
        for file_handle in open_files.values():
            file_handle.close()


def _raise_for_spec_response(http_response):
    """Raise an :class:`Exception` carrying the server's error message."""
    try:
        message = http_response.json().get("message", http_response.text)
    except ValueError:
        message = http_response.text
    raise Exception(message)


def _handle_create_response(http_response):
    """Return the create response JSON or raise with the server message."""
    if http_response.status_code == 201:
        return http_response.json()
    _raise_for_spec_response(http_response)


def create_workflow_from_bundle(reana_file, name, access_token):
    """Create a workflow by uploading the raw specification bundle.

    The server loads and validates the specification authoritatively (in a
    sandbox for Snakemake/CWL/Yadage), so the client does not run the workflow
    engines locally.

    :param reana_file: path to the local ``reana.yaml`` specification file.
    :param name: name of the workflow.
    :param access_token: access token of the current user.
    :return: server response dict with ``workflow_id``, ``workflow_name`` and
             (optionally) ``validation_warnings``.
    """
    http_response = _post_spec_members(
        "/api/workflows",
        _gather_spec_members(reana_file),
        {"workflow_name": name, "access_token": access_token},
    )
    return _handle_create_response(http_response)


def create_workflow_from_bundle_dir(bundle_dir, name, access_token):
    """Create a workflow by uploading every file under ``bundle_dir``.

    Used when the caller has already assembled a complete, self-contained bundle
    directory (e.g. the ``reana-cwl-runner`` entrypoint, which stages the CWL
    workflow and all its file dependencies).

    :param bundle_dir: directory whose entire contents form the bundle.
    :param name: name of the workflow.
    :param access_token: access token of the current user.
    :return: server response dict.
    """
    http_response = _post_spec_members(
        "/api/workflows",
        _members_from_dir(bundle_dir),
        {"workflow_name": name, "access_token": access_token},
    )
    return _handle_create_response(http_response)


def validate_workflow_spec_bundle(
    reana_file, access_token, environments=False, pull=False
):
    """Validate a raw specification bundle server-side.

    :param reana_file: path to the local ``reana.yaml`` specification file.
    :param access_token: access token of the current user.
    :param environments: if True, ask the server to also check the runtime
        environment images (existence and tag) against their registry.
    :param pull: if True (with ``environments``), also have the server inspect
        each image's default user and warn on a UID mismatch.
    :return: validation report dict ``{valid, reana_specification, errors,
             warnings}``.
    """
    params = {"access_token": access_token}
    if environments:
        params["environments"] = "true"
    if pull:
        params["pull"] = "true"
    http_response = _post_spec_members(
        "/api/workflows/validate",
        _gather_spec_members(reana_file),
        params,
    )
    if http_response.ok:
        return http_response.json()
    _raise_for_spec_response(http_response)


def start_workflow(workflow, access_token, parameters):
    """Start a workflow.

    :param workflow: name or id of previously created workflow.
    :param access_token: access token of the current user.
    :param parameters: dict of workflow parameters to override the original
        ones (after workflow creation).

    :return: if the workflow was started successfully, a dictionary with the information about
             the ``workflow_id``, ``workflow_name``, ``run_number``, ``status``, and ``user``,
             along with a ``message`` of success.
    """
    try:
        response, http_response = current_rs_api_client.api.start_workflow(
            workflow_id_or_name=workflow,
            access_token=access_token,
            parameters=parameters,
        ).result()
        if http_response.status_code == 200:
            return response
        else:
            raise Exception(
                "Expected status code 200 but replied with "
                "{status_code}".format(status_code=http_response.status_code)
            )

    except HTTPError as e:
        logging.debug(
            "Workflow run could not be started: "
            "\nStatus: {}\nReason: {}\n"
            "Message: {}".format(
                e.response.status_code, e.response.reason, e.response.json()["message"]
            )
        )
        raise Exception(e.response.json()["message"])
    except Exception as e:
        raise e


def upload_file(workflow, file_, file_name, access_token):
    """Upload file to workflow workspace.

    :param workflow: name or id of the workflow.
    :param file_: content of a file that will be uploaded.
    :param file_name: name of a file that will be uploaded.
    :param access_token: access token of the current user.

    :return: if the file was uploaded successfully, a dictionary
             with a ``message`` of success.
    """
    from reana_client.utils import get_api_url

    try:
        endpoint = current_rs_api_client.api.upload_file.operation.path_name.format(
            workflow_id_or_name=workflow
        )
        http_response = requests.post(
            urljoin(get_api_url(), endpoint),
            data=file_,
            params={"file_name": file_name, "access_token": access_token},
            headers={"Content-Type": "application/octet-stream"},
            verify=False,
        )
        if http_response.ok:
            return http_response.json()
        raise Exception(http_response.json().get("message"))
    except requests.exceptions.ConnectionError:
        logging.debug("File could not be uploaded.", exc_info=True)
        raise Exception("Could not connect to the server {}".format(get_api_url()))
    except requests.exceptions.HTTPError as e:
        logging.debug("The server responded with an HTTP error code.", exc_info=True)
        raise Exception("Unexpected response from the server: \n{}".format(e.response))
    except requests.exceptions.Timeout:
        logging.debug("Timeout while trying to establish connection.", exc_info=True)
        raise Exception("The request to the server has timed out.")
    except requests.exceptions.RequestException:
        logging.debug(
            "Something went wrong while connecting to the server.", exc_info=True
        )
        raise Exception("The request to the server has failed for an unknown reason.")
    except Exception as e:
        raise e


def get_workflow_logs(workflow, access_token, steps=None, page=None, size=None):
    """Get logs from a workflow engine.

    :param workflow: name or id of the workflow.
    :param access_token: access token of the current user.
    :param steps: list of step names to get logs for.
    :param page: page number of returned log list.
    :param size: page size of returned log list.

    :return: a dictionary with a ``logs`` key containing a JSON string that
             contains the requested logs.
    """
    try:
        response, http_response = current_rs_api_client.api.get_workflow_logs(
            workflow_id_or_name=workflow,
            steps=steps,
            access_token=access_token,
            page=page,
            size=size,
        ).result()

        if http_response.status_code == 200:
            return response
        else:
            raise Exception(
                "Expected status code 200 but replied with "
                "{status_code}".format(status_code=http_response.status_code)
            )

    except HTTPError as e:
        logging.debug(
            "Workflow logs could not be retrieved: "
            "\nStatus: {}\nReason: {}\n"
            "Message: {}".format(
                e.response.status_code, e.response.reason, e.response.json()["message"]
            )
        )
        raise Exception(e.response.json()["message"])
    except Exception as e:
        raise e


def download_file(workflow, file_name, access_token):
    """Download the requested file if it exists.

    :param workflow: name or id of the workflow.
    :param file_name: file name or path to the file requested.
    :param access_token: access token of the current user.

    :return: a tuple containing file binary content, filename and whether
        the returned file is a zip archive containing multiple files.
    """
    try:
        from reana_client.utils import get_api_url

        logging.getLogger("urllib3").setLevel(logging.CRITICAL)
        endpoint = current_rs_api_client.api.download_file.operation.path_name.format(
            workflow_id_or_name=workflow, file_name=file_name
        )
        http_response = requests.get(
            urljoin(get_api_url(), endpoint),
            params={"file_name": file_name, "access_token": access_token},
            verify=False,
        )
        if "Content-Disposition" in http_response.headers:
            file_name = get_content_disposition_filename(
                http_response.headers.get("Content-Disposition")
            )

        # A zip archive is downloaded if multiple files are requested
        multiple_files_zipped = (
            http_response.headers.get("Content-Type") == "application/zip"
        )

        if http_response.status_code == 200:
            return http_response.content, file_name, multiple_files_zipped
        else:
            raise Exception(
                "Error {status_code} {reason} {message}".format(
                    status_code=http_response.status_code,
                    reason=http_response.reason,
                    message=http_response.json().get("message"),
                )
            )

    except HTTPError as e:
        logging.debug(
            "Output file could not be downloaded: "
            "\nStatus: {}\nReason: {}\n"
            "Message: {}".format(
                e.response.status_code, e.response.reason, e.response.json()["message"]
            )
        )
        raise Exception(e.response.json()["message"])
    except Exception as e:
        raise e


def delete_file(workflow, file_name, access_token):
    """Delete the requested file if it exists.

    :param workflow: name or id of the workflow.
    :param file_name: file name or path to the file requested.
    :param access_token: access token of the current user.

    :return: a dictionary with two keys: ``deleted`` and ``failed``.
             Each of this keys contains another dictionary with the
             name of the file as key and info about the size as value.
    """
    try:
        response, http_response = current_rs_api_client.api.delete_file(
            workflow_id_or_name=workflow,
            file_name=file_name,
            access_token=access_token,
        ).result()
        if http_response.status_code == 200 and (
            response["deleted"] or response["failed"]
        ):
            return response
        elif not (response["deleted"] or response["failed"]):
            raise FileDeletionError(
                "{} did not match any existing " "file.".format(file_name)
            )
        else:
            raise Exception(
                "Expected status code 200 but replied with "
                "{status_code}".format(status_code=http_response.status_code)
            )

    except HTTPError as e:
        logging.debug(
            "File could not be downloaded: "
            "\nStatus: {}\nReason: {}\n"
            "Message: {}".format(
                e.response.status_code, e.response.reason, e.response.json()["message"]
            )
        )
        raise Exception(e.response.json()["message"])
    except Exception as e:
        raise e


def list_files(
    workflow, access_token, file_name=None, page=None, size=None, search=None
):
    """Return the list of files for a given workflow workspace.

    :param workflow: name or id of the workflow.
    :param access_token: access token of the current user.
    :param file_name: file name(s) (glob) to list.
    :param page: page number of returned file list.
    :param size: page size of returned file list.
    :param search: filter search results by parameters.
    :returns: a list of dictionaries that have the ``name``, ``size`` and
                ``last-modified`` keys.
    """
    try:
        response, http_response = current_rs_api_client.api.get_files(
            workflow_id_or_name=workflow,
            access_token=access_token,
            file_name=file_name,
            page=page,
            size=size,
            search=search,
        ).result()

        if http_response.status_code == 200:
            return response.get("items")
        raise Exception(
            "Expected status code 200 but replied with "
            "{status_code}".format(status_code=http_response.status_code)
        )

    except HTTPError as e:
        logging.debug(
            "File list could not be retrieved: "
            "\nStatus: {}\nReason: {}\n"
            "Message: {}".format(
                e.response.status_code, e.response.reason, e.response.json()["message"]
            )
        )
        raise Exception(e.response.json()["message"])
    except Exception as e:
        raise e


def upload_to_server(workflow, paths, access_token):
    """Upload file or directory to REANA server.

    Shared e.g. by `code upload` and `inputs upload`.

    :param workflow: name or id of workflow whose workspace should be
        used to store the files.
    :param paths: absolute filepath(s) of files to be uploaded.
    :param access_token: access token of the current user.

    :return: the list of path of files that were uploaded.
    """
    if not workflow:
        raise ValueError("Workflow name or id must be provided")
    if not paths:
        logging.info(
            "No path(s) to file(s) that should be uploaded to workspace was provided."
        )
        return []

    logging.info('Workflow "{}" selected'.format(workflow))

    # Check if multiple paths were given and iterate over them
    if type(paths) is list or type(paths) is tuple:
        for path in paths:
            upload_to_server(workflow, path, access_token)
    # `paths` points to a single file or directory
    else:
        path = paths
        if ".." in paths.split("/"):
            raise FileUploadError('Path cannot contain ".."')

        if not is_regular_path(path):
            logging.info(f"Ignoring symlink {path}")
            return []

        # Check if input is a directory and upload everything
        # including subdirectories.
        if os.path.isdir(path):
            logging.debug("'{}' is a directory.".format(path))
            logging.info("Uploading contents of folder '{}' ...".format(path))
            for root, dirs, files in os.walk(path, topdown=False):
                uploaded_files = []
                for next_path in files + dirs:
                    next_uploaded_files = upload_to_server(
                        workflow, os.path.join(root, next_path), access_token
                    )
                    if next_uploaded_files:
                        uploaded_files.extend(next_uploaded_files)
            return uploaded_files

        # Check if input is an absolute path and upload file.
        else:
            with open(path, "rb") as f:
                fname = os.path.basename(f.name)
                # Calculate the path that will store the file
                # in the workflow controller, by subtracting
                # the workflow root path from the file path
                save_path = path.replace(os.getcwd(), "")
                # Remove prepending dirs named "." or as the upload type
                while len(save_path.split("/")) > 1 and save_path.split("/")[0] == ".":
                    save_path = "/".join(save_path.strip("/").split("/")[1:])
                logging.debug(
                    "'{}' is an absolute filepath.".format(os.path.basename(fname))
                )
                logging.info("Uploading '{}' ...".format(fname))
                try:
                    upload_file(workflow, f, save_path, access_token)
                    logging.info("File '{}' was successfully uploaded.".format(fname))
                    return [save_path]
                except Exception as e:
                    logging.debug(traceback.format_exc())
                    logging.debug(str(e))
                    logging.info(
                        "Something went wrong while uploading {}".format(fname)
                    )
                    raise e


def get_workflow_parameters(workflow, access_token):
    """Get parameters of previously created workflow.

    :param workflow: name or id of the workflow.
    :param access_token: access token of the current user.

    :returns: a dictionary that cointains info about the workflow (``name``, ``type``), and
              a dictionary of workflow parameters under the ``parameters`` key.
    """
    try:
        response, http_response = current_rs_api_client.api.get_workflow_parameters(
            workflow_id_or_name=workflow, access_token=access_token
        ).result()
        if http_response.status_code == 200:
            return response
        else:
            raise Exception(
                "Expected status code 200 but replied with "
                "{status_code}".format(status_code=http_response.status_code)
            )

    except HTTPError as e:
        logging.debug(
            "Workflow parameters could not be retrieved: "
            "\nStatus: {}\nReason: {}\n"
            "Message: {}".format(
                e.response.status_code, e.response.reason, e.response.json()["message"]
            )
        )
        raise Exception(e.response.json()["message"])
    except Exception as e:
        raise e


def get_workflow_specification(workflow, access_token):
    """Get specification of previously created workflow.

    :param workflow: name or id of the workflow.
    :param access_token: access token of the current user.

    :returns: a dictionary that cointains two top-level keys: ``parameters``, and
              ``specification`` (which contains a dictionary created from the workflow specification).
    """
    try:
        response, http_response = current_rs_api_client.api.get_workflow_specification(
            workflow_id_or_name=workflow, access_token=access_token
        ).result()
        if http_response.status_code == 200:
            return response
        else:
            raise Exception(
                "Expected status code 200 but replied with "
                "{status_code}".format(status_code=http_response.status_code)
            )

    except HTTPError as e:
        logging.debug(
            "Workflow specification could not be retrieved: "
            "\nStatus: {}\nReason: {}\n"
            "Message: {}".format(
                e.response.status_code, e.response.reason, e.response.json()["message"]
            )
        )
        raise Exception(e.response.json()["message"])
    except Exception as e:
        raise e


def delete_workflow(workflow, all_runs: bool, workspace: bool, access_token: str):
    """Delete a workflow.

    Please note that the workspace will always be deleted, even if ``workspace`` is set to ``False``.

    :param workflow: name or id of the workflow.
    :param all_runs: whether to delete all the runs of the workflow.
    :param workspace: whether to delete the workspace of the workflow.
    :param access_token: access token of the current user.

    :return: a dictionary that cointains info about the deleted workflow (``workflow_id``, ``workflow_name``,
             ``status``, ``user``), and a ``message`` key.
    """
    if not workspace:
        logging.warning(
            "Parameter workspace=False was specified in delete_workflow() but workspace will still be deleted."
        )
    workspace = True

    try:
        parameters = {
            "all_runs": all_runs,
            "workspace": workspace,
        }
        response, http_response = current_rs_api_client.api.set_workflow_status(
            workflow_id_or_name=workflow,
            status="deleted",
            access_token=access_token,
            parameters=parameters,
        ).result()
        if http_response.status_code == 200:
            return response
        else:
            raise Exception(
                "Expected status code 200 but replied with "
                "{status_code}".format(status_code=http_response.status_code)
            )

    except HTTPError as e:
        logging.debug(
            "Workflow run could not be deleted: "
            "\nStatus: {}\nReason: {}\n"
            "Message: {}".format(
                e.response.status_code, e.response.reason, e.response.json()["message"]
            )
        )
        raise Exception(e.response.json()["message"])
    except Exception as e:
        raise e


def stop_workflow(workflow, force_stop, access_token):
    """Stop a workflow.

    :param workflow: name or id of the workflow.
    :param force_stop: whether to stop the workflow immediately, without
        waiting for the jobs to finish.
    :param access_token: access token of the current user.

    :return: a dictionary that cointains info about the stopped workflow (``workflow_id``, ``workflow_name``,
             ``status``, ``user``), and a ``message`` key.
    """
    try:
        parameters = {"force_stop": force_stop}
        response, http_response = current_rs_api_client.api.set_workflow_status(
            workflow_id_or_name=workflow,
            status="stop",
            access_token=access_token,
            parameters=parameters,
        ).result()
        if http_response.status_code == 200:
            return response
        else:
            raise Exception(
                "Expected status code 200 but replied with "
                "{status_code}".format(status_code=http_response.status_code)
            )
    except HTTPError as e:
        logging.debug(
            "Workflow run could not be stopped: "
            "\nStatus: {}\nReason: {}\n"
            "Message: {}".format(
                e.response.status_code, e.response.reason, e.response.json()["message"]
            )
        )
        raise Exception(e.response.json()["message"])
    except Exception as e:
        raise e


def diff_workflows(workflow_id_a, workflow_id_b, brief, access_token, context_lines):
    """Return the list of differences between two workflows.

    :param workflow_id_a: UUID which identifies the first workflow.
    :param workflow_id_b: UUID which identifies the second workflow.
    :param brief: Flag specifying desired detail in diff.
    :param context_lines: Optional parameter to set the number of
                          context lines shown in the diff output.
    :param access_token: API token of user requesting diff.

    :return: a list of dictionaries composed by ``asset``, ``type``, ``lines``,
        ``a`` and ``b``. Asset refers to the workflow asset where a
        difference was found, type refers to the asset type, lines refer
        to the lines of the file where the differences are and a, b fields
        are the actual lines that differ.
    """
    try:
        response, http_response = current_rs_api_client.api.get_workflow_diff(
            workflow_id_or_name_a=workflow_id_a,
            workflow_id_or_name_b=workflow_id_b,
            brief=brief,
            context_lines=context_lines,
            access_token=access_token,
        ).result()

        if http_response.status_code == 200:
            return response
        else:
            raise Exception(
                "Expected status code 200 but replied with "
                "{status_code}".format(status_code=http_response.status_code)
            )

    except HTTPError as e:
        logging.debug(
            "File list could not be retrieved: "
            "\nStatus: {}\nReason: {}\n"
            "Message: {}".format(
                e.response.status_code, e.response.reason, e.response.json()["message"]
            )
        )
        raise Exception(e.response.json()["message"])
    except Exception as e:
        raise e


def open_interactive_session(
    workflow, access_token, interactive_session_type, interactive_session_configuration
):
    """Open an interactive session inside the workflow workspace.

    :param workflow: name or id of the workflow whose workspace will be available inside the
        interactive session.
    :param access_token: Workflow owner REANA access token.
    :param interactive_session_type: Type of interactive session to spawn.
    :param interactive_session_configuration: Specific configuration for
        the interactive session.

    :return: the relative path to the interactive session.
    """
    try:
        response, http_response = current_rs_api_client.api.open_interactive_session(
            workflow_id_or_name=workflow,
            access_token=access_token,
            interactive_session_type=interactive_session_type,
            interactive_session_configuration=interactive_session_configuration,
        ).result()
        if http_response.status_code == 200:
            return response["path"]
        else:
            raise Exception(
                "Expected status code 200 but replied with "
                "{status_code}".format(status_code=http_response.status_code)
            )
    except HTTPError as e:
        logging.debug(
            "Interactive session could not be opened: "
            "\nStatus: {}\nReason: {}\n"
            "Message: {}".format(
                e.response.status_code, e.response.reason, e.response.json()["message"]
            )
        )
        raise Exception(e.response.json()["message"])
    except Exception as e:
        raise e


def close_interactive_session(workflow, access_token):
    """Close an interactive workflow session.

    :param workflow: name or id of the workflow to close.
    :param access_token: workflow owner REANA access token.

    :return: the relative path to the interactive session.
    """
    try:
        response, http_response = current_rs_api_client.api.close_interactive_session(
            workflow_id_or_name=workflow,
            access_token=access_token,
        ).result()
        if http_response.status_code == 200:
            return response
        else:
            raise Exception(
                "Expected status code 200 but replied with "
                "{status_code}".format(status_code=http_response.status_code)
            )
    except HTTPError as e:
        logging.debug(
            "Interactive session could not be closed: "
            "\nStatus: {}\nReason: {}\n"
            "Message: {}".format(
                e.response.status_code, e.response.reason, e.response.json()["message"]
            )
        )
        raise Exception(e.response.json()["message"])
    except Exception as e:
        raise e


def mv_files(source, target, workflow, access_token):
    """Move target file(s) within workspace.

    :param source: source filename or path.
    :param target: target filename or path.
    :param workflow: name or id of the workflow.
    :param access_token: token of user.

    :return: a dictionary containing the ``workflow_id``, ``workflow_name``,
             and a ``message`` about the success of the operation.
    """
    try:
        response, http_response = current_rs_api_client.api.move_files(
            source=source,
            target=target,
            workflow_id_or_name=workflow,
            access_token=access_token,
        ).result()

        if http_response.status_code == 200:
            return response
        else:
            raise Exception(
                "Expected status code 200 but replied with "
                "{status_code}".format(status_code=http_response.status_code)
            )

    except HTTPError as e:
        logging.debug(
            "Files move command failed: "
            "\nStatus: {}\nReason: {}\n"
            "Message: {}".format(
                e.response.status_code, e.response.reason, e.response.json()["message"]
            )
        )
        raise Exception(e.response.json()["message"])
    except Exception as e:
        raise e


def get_workflow_disk_usage(workflow, parameters, access_token):
    """Display disk usage workflow.

    :param workflow: name or id of the workflow.
    :param parameters: a dictionary to customize the response. It has the following
        (optional) keys:

        - ``summarize``: a boolean value to indicate whether to summarize the response
          to include only the total workspace disk usage
        - ``search``: a string to filter the response by file name

    :param access_token: access token of the current user.

    :return: a dictionary containing the ``workflow_id``, ``workflow_name``, and the ``user`` ID, with
             a ``disk_usage_info`` keys that contains a list of dictionaries, each of one corresponding
             to a file, with the ``name`` and ``size`` keys.
    """
    try:
        response, http_response = current_rs_api_client.api.get_workflow_disk_usage(
            workflow_id_or_name=workflow,
            parameters=parameters,
            access_token=access_token,
        ).result()
        if http_response.status_code == 200:
            return response
        else:
            raise Exception(
                "Expected status code 200 but replied with "
                "{status_code}".format(status_code=http_response.status_code)
            )

    except HTTPError as e:
        logging.debug(
            "Workflow disk usage could not be retrieved: "
            "\nStatus: {}\nReason: {}\n"
            "Message: {}".format(
                e.response.status_code, e.response.reason, e.response.json()["message"]
            )
        )
        raise Exception(e.response.json()["message"])
    except Exception as e:
        raise e


def add_secrets(secrets, overwrite, access_token):
    """Add new secrets.

    :param secrets: dictionary containing all the secrets to be sent.
        The dictionary has the secret names for keys and for each key there is
        a dictionary with two fields:

        - ``value``:  a base64 encoded file or literal string
        - ``type``: ``"file"`` or ``"env"``

    :param overwrite: whether secrets should be overwritten when they
     already exist.
    :param access_token: access token of the current user.

    :return: a dictionary containing the ``message`` key with a success message.
    """
    try:
        response, http_response = current_rs_api_client.api.add_secrets(
            secrets=secrets, access_token=access_token, overwrite=overwrite
        ).result()
        if http_response.status_code == 201:
            return response
        else:
            raise Exception(
                "Expected status code 201 but replied with "
                "{status_code}".format(status_code=http_response.status_code)
            )

    except HTTPError as e:
        logging.debug(
            "Secrets could not be added: "
            "\nStatus: {}\nReason: {}\n"
            "Message: {}".format(
                e.response.status_code, e.response.reason, e.response.json()["message"]
            )
        )
        if e.status_code == 409:
            raise REANASecretAlreadyExists()
        else:
            raise Exception(e.response.json()["message"])
    except Exception as e:
        raise e


def delete_secrets(secrets, access_token):
    """Delete a list of secrets.

    :param secrets: list of secret names to be deleted.
    :param access_token: access token of the current user.

    :return: a list with the names of the deleted secrets.
    """
    try:
        response, http_response = current_rs_api_client.api.delete_secrets(
            secrets=secrets, access_token=access_token
        ).result()
        if http_response.status_code == 200:
            return response
        else:
            raise Exception(
                "Expected status code 200 but replied with "
                "{status_code}".format(status_code=http_response.status_code)
            )

    except HTTPError as e:
        if e.response.status_code == 404:
            raise REANASecretDoesNotExist(e.response.json())
        else:
            logging.debug(
                "Secrets could not be deleted: "
                "\nStatus: {}\nReason: {}\n"
                "Message: {}".format(
                    e.response.status_code,
                    e.response.reason,
                    e.response.json()["message"],
                )
            )
        raise Exception(e.response.json()["message"])
    except Exception as e:
        raise e


def list_secrets(access_token):
    """List user secrets.

    :param access_token: access token of the current user.

    :return: a list of dictionaries, each of one corresponding to a secret, with the
             ``name`` and ``type`` keys.
    """
    try:
        response, http_response = current_rs_api_client.api.get_secrets(
            access_token=access_token
        ).result()
        if http_response.status_code == 200:
            return response
        else:
            raise Exception(
                "Expected status code 200 but replied with "
                "{status_code}".format(status_code=http_response.status_code)
            )

    except HTTPError as e:
        logging.debug(
            "Secrets could not be listed: "
            "\nStatus: {}\nReason: {}\n"
            "Message: {}".format(
                e.response.status_code, e.response.reason, e.response.json()["message"]
            )
        )
        raise Exception(e.response.json()["message"])
    except Exception as e:
        raise e


def info(access_token):
    """List general information about the cluster.

    :param access_token: access token of the current user.

    :return: a dictionary containing relevant values and configuration options about the cluster.
             Each key contains a dictionary with the ``title`` key, explaining the meaning of the
             value, and the ``value`` key, containing the value itself.
             Example of the returned keys include ``compute_backends``, ``default_kubernetes_memory_limit``,
             and ``maximum_interactive_session_inactivity_period``.
    """
    try:
        response, http_response = current_rs_api_client.api.info(
            access_token=access_token
        ).result()
        if http_response.status_code == 200:
            return response
        else:
            raise Exception(
                "Expected status code 200 but replied with "
                "{status_code}".format(status_code=http_response.status_code)
            )

    except HTTPError as e:
        logging.debug(
            "Workspaces could not be listed: "
            "\nStatus: {}\nReason: {}\n"
            "Message: {}".format(
                e.response.status_code, e.response.reason, e.response.json()["message"]
            )
        )
        raise Exception(e.response.json()["message"])
    except Exception as e:
        raise e


def get_workflow_retention_rules(workflow, access_token):
    """Get the retention rules of a workflow.

    :param workflow: name or id of the workflow.
    :param access_token: access token of the current user.

    :return: a dictionary containing the ``workflow_id``, ``workflow_name``, and
             the ``retention_rules`` key with a list of dictionaries representing
             the retention rules of the workflow. Each dictionary contains info
             about the affected workspace files, and the schedule of the retention
             rule.
    """
    try:
        (
            response,
            http_response,
        ) = current_rs_api_client.api.get_workflow_retention_rules(
            workflow_id_or_name=workflow,
            access_token=access_token,
        ).result()
        if http_response.status_code == 200:
            return response
        else:
            raise Exception(
                "Expected status code 200 but replied with "
                "{status_code}".format(status_code=http_response.status_code)
            )

    except HTTPError as e:
        logging.debug(
            "Workflow retention rules could not be retrieved: "
            "\nStatus: {}\nReason: {}\n"
            "Message: {}".format(
                e.response.status_code, e.response.reason, e.response.json()["message"]
            )
        )
        raise Exception(e.response.json()["message"])


def prune_workspace(workflow, include_inputs, include_outputs, access_token):
    """Prune workspace files.

    :param workflow: name or id of the workflow.
    :param include_inputs: whether to also delete inputs.
    :param include_outputs: whether to also delete outputs.
    :param access_token: access token of the current user.

    :return: a dictionary containing the ``workflow_id``, ``workflow_name``, and
             a ``message`` key with the result of the operation.
    """
    try:
        response, http_response = current_rs_api_client.api.prune_workspace(
            workflow_id_or_name=workflow,
            include_inputs=include_inputs,
            include_outputs=include_outputs,
            access_token=access_token,
        ).result()

        if http_response.status_code == 200:
            return response
        else:
            raise Exception(
                "Expected status code 200 but replied with "
                "{status_code}".format(status_code=http_response.status_code)
            )

    except HTTPError as e:
        logging.debug(
            "Workspace could not be pruned: "
            "\nStatus: {}\nReason: {}\n"
            "Message: {}".format(
                e.response.status_code, e.response.reason, e.response.json()["message"]
            )
        )
        raise Exception(e.response.json()["message"])


def share_workflow(
    workflow, user_email_to_share_with, access_token, message=None, valid_until=None
):
    """Share a workflow with a user.

    :param workflow: name or id of the workflow.
    :param user_email_to_share_with: user to share the workflow with.
    :param access_token: access token of the current user.
    :param message: Optional message to include when sharing the workflow.
    :param valid_until: Specify the date when access to the workflow will expire (format: YYYY-MM-DD).

    :return: a dictionary containing the ``workflow_id``, ``workflow_name``, and
             a ``message`` key with the result of the operation.
    """
    try:
        share_params = {
            "user_email_to_share_with": user_email_to_share_with,
        }

        if message:
            share_params["message"] = message

        if valid_until:
            share_params["valid_until"] = valid_until

        response, http_response = current_rs_api_client.api.share_workflow(
            workflow_id_or_name=workflow,
            share_details=share_params,
            access_token=access_token,
        ).result()

        if http_response.status_code == 200:
            return response
        else:
            raise Exception(
                "Expected status code 200 but replied with "
                f"{http_response.status_code}"
            )

    except HTTPError as e:
        logging.debug(
            "Workflow could not be shared: "
            f"\nStatus: {e.response.status_code}\nReason: {e.response.reason}\n"
            f"Message: {e.response.json()['message']}"
        )
        raise Exception(e.response.json()["message"])


def unshare_workflow(workflow, user_email_to_unshare_with, access_token):
    """Unshare a workflow with a user.

    :param workflow: name or id of the workflow.
    :param user_email_to_unshare_with: user to unshare the workflow with.
    :param access_token: access token of the current user.

    :return: a dictionary containing the ``workflow_id``, ``workflow_name``, and
             a ``message`` key with the result of the operation.
    """
    try:
        unshare_params = {
            "workflow_id_or_name": workflow,
            "user_email_to_unshare_with": user_email_to_unshare_with,
            "access_token": access_token,
        }

        response, http_response = current_rs_api_client.api.unshare_workflow(
            **unshare_params
        ).result()

        if http_response.status_code == 200:
            return response
        else:
            raise Exception(
                "Expected status code 200 but replied with "
                f"{http_response.status_code}"
            )

    except HTTPError as e:
        logging.debug(
            "Workflow could not be unshared: "
            f"\nStatus: {e.response.status_code}\nReason: {e.response.reason}\n"
            f"Message: {e.response.json()['message']}"
        )
        raise Exception(e.response.json()["message"])


def get_workflow_sharing_status(workflow, access_token):
    """Get the share status of a workflow.

    :param workflow: name or id of the workflow.
    :param access_token: access token of the current user.

    :return: a dictionary containing the ``workflow_id``, ``workflow_name``, and
             a ``sharing_status`` key with the result of the operation.
    """
    try:
        (
            response,
            http_response,
        ) = current_rs_api_client.api.get_workflow_share_status(
            workflow_id_or_name=workflow,
            access_token=access_token,
        ).result()

        if http_response.status_code == 200:
            return response
        else:
            raise Exception(
                "Expected status code 200 but replied with "
                f"{http_response.status_code}"
            )

    except HTTPError as e:
        logging.debug(
            "Workflow sharing status could not be retrieved: "
            f"\nStatus: {e.response.status_code}\nReason: {e.response.reason}\n"
            f"Message: {e.response.json()['message']}"
        )
        raise Exception(e.response.json()["message"])
