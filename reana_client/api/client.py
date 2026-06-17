# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
"""REANA REST API client."""

import json
import logging
import os
import shutil
import tempfile
import traceback
import warnings
import zipfile
from urllib.parse import urljoin

import requests
import yaml
from bravado.exception import BravadoConnectionError, BravadoTimeoutError, HTTPError
from reana_client.api.utils import get_content_disposition_filename
from reana_client.config import ERROR_MESSAGES, tls_verify
from reana_client.errors import FileDeletionError, FileUploadError
from reana_client.utils import is_regular_path, is_uuid_v4
from reana_commons.api_client import get_current_api_client
from reana_commons.config import (
    REANA_WORKFLOW_ENGINES,
    WORKFLOW_SPECIFICATION_BUNDLES_CAPABILITY,
)
from reana_commons.validation.utils import validate_workflow_name
from reana_commons.errors import (
    REANASecretAlreadyExists,
    REANASpecificationScopeError,
    REANASecretDoesNotExist,
)
from reana_commons.specification_paths import (
    SPECIFICATION_BUNDLE_MAX_BYTES,
    SPECIFICATION_BUNDLE_MAX_FILES,
    gather_validation_members,
    open_regular_file_beneath,
)
from werkzeug.local import LocalProxy

FILE_TRANSFER_TIMEOUT = (30, 300)
"""Connect/read timeout used for potentially large workspace transfers."""


def _get_current_reana_server_api_client():
    """Return a generated API client using the shared TLS policy.

    The active server is resolved once, here, and handed to the generated
    client explicitly, so that authentication, raw file transfers and generated
    API calls all address the same normalised origin.
    """
    from reana_client.auth.storage import get_active_server

    return get_current_api_client(
        component="reana-server",
        ssl_verify=tls_verify(),
        server_url=get_active_server(),
    )


current_rs_api_client = LocalProxy(_get_current_reana_server_api_client)

_TRANSFER_REQUEST_OPTIONS = {"connect_timeout": 10, "timeout": 300}
_CONTROL_REQUEST_OPTIONS = {"connect_timeout": 10, "timeout": 300}

_MIGRATION_HINT = (
    "Write a raw reana.yaml specification, declare any loader dependencies "
    "through workflow.files/workflow.directories, and call "
    "create_workflow_from_bundle()."
)


def _untranslatable_json_creation(workflow_engine, workflow_file):
    """Explain why a historical creation call cannot be translated safely."""
    return (
        "create_workflow_from_json() can only translate an inline serial "
        "workflow (workflow_engine='serial' with workflow_json and no "
        "workflow_file); got workflow_engine='{}'{}. The workflow is loaded "
        "server-side from its specification files, which this call does not "
        "identify unambiguously. {}".format(
            workflow_engine,
            (
                " and workflow_file='{}'".format(workflow_file)
                if workflow_file is not None
                else ""
            ),
            _MIGRATION_HINT,
        )
    )


class _BoundedSpecificationReader:
    """Stream one specification without exposing bytes beyond its size limit."""

    def __init__(self, specification, limit):
        self.specification = specification
        self.limit = limit
        self.remaining = limit
        self.too_large = False

    def read(self, size=-1):
        """Read bounded bytes and fail if the open file has grown too large."""
        if self.too_large:
            raise FileUploadError(
                "Restart specification is too large (maximum is {} bytes).".format(
                    self.limit
                )
            )
        requested = self.remaining + 1
        if size is not None and size >= 0:
            requested = min(size, requested)
        contents = self.specification.read(requested)
        if len(contents) > self.remaining:
            self.too_large = True
            raise FileUploadError(
                "Restart specification is too large (maximum is {} bytes).".format(
                    self.limit
                )
            )
        self.remaining -= len(contents)
        return contents

    def __getattr__(self, name):
        """Delegate file metadata used by multipart transports."""
        return getattr(self.specification, name)


class _SnapshotUploadReader:
    """Expose exactly the bytes present when a workspace upload starts."""

    def __init__(self, source, length):
        self.source = source
        self.length = length
        self.remaining = length

    def __len__(self):
        """Return the request body's exact declared length."""
        return self.length

    def read(self, size=-1):
        """Read at most the snapshotted number of bytes."""
        if self.remaining == 0:
            return b""
        if size == 0:
            return b""
        if size is None or size < 0:
            size = self.remaining
        contents = self.source.read(min(size, self.remaining))
        if not contents:
            raise FileUploadError("The upload file changed while it was being read.")
        self.remaining -= len(contents)
        return contents


def _remaining_file_length(source):
    """Return remaining bytes without consuming a seekable upload source."""
    try:
        position = source.tell()
        source.seek(0, os.SEEK_END)
        length = source.tell() - position
        source.seek(position)
    except (AttributeError, OSError) as error:
        raise FileUploadError(
            "Workspace uploads require a seekable file source."
        ) from error
    if length < 0:
        raise FileUploadError("Could not determine the upload size.")
    return length


def _auth_request_options(access_token):
    """Return bravado request options carrying bearer authentication."""
    return {"headers": {"Authorization": "Bearer {}".format(access_token)}}


def _auth_headers(access_token, extra_headers=None):
    """Return requests headers carrying bearer authentication."""
    headers = {"Authorization": "Bearer {}".format(access_token)}
    if extra_headers:
        headers.update(extra_headers)
    return headers


def ping(access_token):
    """Check if the REANA server is reachable and the user is correctly authenticated.

    :param access_token: access token of the current user.

    :return: a dictionary with the ``status`` key (``"Connected"`` if the server is reachable, the error message if
             there is a problem), the ``error`` key (``True`` if there is an error, ``False`` otherwise),
             and info about the current user in ``full_name`` and ``email``.
    """
    try:
        response, http_response = current_rs_api_client.api.get_you(
            _request_options=_auth_request_options(access_token),
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
            _request_options=_auth_request_options(access_token),
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
    include_session_secrets=None,
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
    :param include_session_secrets: include owned interactive-session launch secrets.
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
            _request_options=_auth_request_options(access_token),
            verbose=verbose,
            type=type,
            page=page,
            size=size,
            status=status,
            search=search,
            include_progress=include_progress,
            include_workspace_size=include_workspace_size,
            include_session_secrets=include_session_secrets,
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
            _request_options=_auth_request_options(access_token),
            workflow_id_or_name=workflow,
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


def _gather_spec_members(reana_file):
    """Return the explicitly declared, containment-safe validation members."""
    try:
        members, _specification, _legacy_parameters = gather_validation_members(
            reana_file
        )
        return members
    except REANASpecificationScopeError:
        # Preserve the authoritative server-side error taxonomy. A malformed or
        # wrongly shaped specification has no trustworthy declared scope, so
        # only its canonical file may be forwarded. Containment, symlink and
        # missing-path errors deliberately do not use this fallback.
        return {"reana.yaml": os.path.abspath(reana_file)}


def _require_workflow_specification_bundles():
    """Refuse a server that cannot accept a workflow specification bundle.

    ``create``, ``validate`` and a replacement ``restart`` upload the raw
    specification bundle that the server loads and validates authoritatively.
    A released server only understands the retired client-serialized JSON
    protocol, so the pairing must be refused here -- before any bundle is built
    or uploaded -- rather than failing mid-transfer with a wire-level error.

    The capability is read from the unauthenticated ``ping`` operation so it
    works before authentication. Support is decided by the advertised
    capability, never by comparing version strings.

    :raises RuntimeError: if the connected server does not advertise
        ``workflow-specification-bundles-v1``.
    """
    response, _http_response = current_rs_api_client.api.ping(
        _request_options=_CONTROL_REQUEST_OPTIONS
    ).result()
    capabilities = (response or {}).get("api_capabilities") or []
    if WORKFLOW_SPECIFICATION_BUNDLES_CAPABILITY in capabilities:
        return

    server_version = (response or {}).get("reana_server_version")
    raise RuntimeError(
        "The connected REANA server{} does not support the server-side workflow "
        "specification validation protocol used by this client (missing '{}'). "
        "Please upgrade the REANA cluster, or use a REANA client release that "
        "matches it.".format(
            " (version {})".format(server_version) if server_version else "",
            WORKFLOW_SPECIFICATION_BUNDLES_CAPABILITY,
        )
    )


def _post_spec_members(operation_id, members, access_token, params):
    """Call a Bravado operation with one deterministic ZIP ``bundle`` field.

    :param operation_id: OpenAPI operation name.
    :param members: mapping of bundle-relative path to local file path.
    :param access_token: access token of the current user.
    :param params: query parameters (e.g. ``workflow_name``).
    :return: the Bravado result and response adapter.
    """
    _require_workflow_specification_bundles()
    if len(members) > SPECIFICATION_BUNDLE_MAX_FILES:
        raise FileUploadError(
            "Specification bundle has too many files (maximum is {}).".format(
                SPECIFICATION_BUNDLE_MAX_FILES
            )
        )
    specification_path = members.get("reana.yaml")
    if specification_path is None:
        raise FileUploadError("Specification bundle is missing canonical reana.yaml.")
    base_directory = os.path.dirname(os.path.abspath(specification_path))

    with tempfile.TemporaryFile() as archive:
        total_bytes = 0
        with zipfile.ZipFile(
            archive, mode="w", compression=zipfile.ZIP_STORED, allowZip64=False
        ) as bundle:
            for member in sorted(members):
                info = zipfile.ZipInfo(member, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_STORED
                info.create_system = 3
                info.external_attr = 0o100600 << 16
                source_relative_path = os.path.relpath(
                    os.path.abspath(members[member]), base_directory
                ).replace(os.sep, "/")
                descriptor = open_regular_file_beneath(
                    base_directory,
                    source_relative_path,
                    "specification bundle",
                )
                with os.fdopen(descriptor, "rb") as source, bundle.open(
                    info, "w"
                ) as target:
                    while True:
                        chunk = source.read(1024 * 1024)
                        if not chunk:
                            break
                        total_bytes += len(chunk)
                        if total_bytes > SPECIFICATION_BUNDLE_MAX_BYTES:
                            raise FileUploadError(
                                "Specification bundle is too large "
                                "(maximum is {} bytes).".format(
                                    SPECIFICATION_BUNDLE_MAX_BYTES
                                )
                            )
                        target.write(chunk)

        archive.seek(0)
        operation = getattr(current_rs_api_client.api, operation_id)
        return operation(
            bundle=("validation-bundle.zip", archive),
            _request_options={
                **_TRANSFER_REQUEST_OPTIONS,
                **_auth_request_options(access_token),
            },
            **params,
        ).result()


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
    response, _http_response = _post_spec_members(
        "create_workflow",
        _gather_spec_members(reana_file),
        access_token,
        {"workflow_name": name},
    )
    return response


def create_workflow_from_bundle_dir(bundle_dir, name, access_token):
    """Create a workflow from declarations in ``bundle_dir/reana.yaml``.

    Used when the caller has assembled a local source directory (e.g. the
    ``reana-cwl-runner`` entrypoint). Only files explicitly selected by the
    specification's validation-scope declarations are uploaded.

    :param bundle_dir: directory containing the canonical specification and its
        declared workflow-definition files.
    :param name: name of the workflow.
    :param access_token: access token of the current user.
    :return: server response dict.
    """
    response, _http_response = _post_spec_members(
        "create_workflow",
        _gather_spec_members(os.path.join(bundle_dir, "reana.yaml")),
        access_token,
        {"workflow_name": name},
    )
    return response


def create_workflow_from_json(
    name,
    access_token,
    workflow_json=None,
    workflow_file=None,
    parameters=None,
    workflow_engine="yadage",
    outputs=None,
    workspace_path=None,
):
    """Create a workflow from an inline JSON specification (deprecated).

    .. deprecated::
        Write a raw ``reana.yaml`` and call :func:`create_workflow_from_bundle`
        instead. The server now loads and validates the specification
        authoritatively, so a client-serialized specification is no longer
        accepted.

    Only the documented inline **serial** use case is translated: it is the one
    shape the server-side loader can reconstruct, because a serial workflow is
    the only engine whose loader accepts an inline ``workflow.specification``
    with no ``workflow.file``. Every other historical call shape referenced
    local loader dependencies that a single dictionary does not identify, so
    those fail with migration guidance rather than silently submitting a
    specification the server cannot re-derive.

    :param name: name or UUID of the workflow to be created.
    :param access_token: access token of the current user.
    :param workflow_json: workflow specification in JSON format.
    :param workflow_file: workflow specification file path. No longer
        translatable; kept so historical calls fail with guidance.
    :param parameters: workflow input parameters dictionary.
    :param workflow_engine: one of the workflow engines. Only ``serial`` is
        translatable.
    :param outputs: dictionary with expected workflow outputs.
    :param workspace_path: accepted for call compatibility; unused.

    :return: server response dict with ``workflow_id`` and ``workflow_name``.

    :raises ValueError: for call shapes that cannot be translated safely.

    :Example:

      .. code:: python

        create_workflow_from_json(
            workflow_json=workflow_json,
            name='workflow_name.1',
            access_token='access_token',
            parameters={'files': ['file.txt'],
                'parameters': {'key': 'value'}},
            workflow_engine='serial')
    """
    warnings.warn(
        "create_workflow_from_json() is deprecated. Write a raw reana.yaml "
        "specification and call create_workflow_from_bundle() instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    validate_workflow_name(name)
    if is_uuid_v4(name):
        raise ValueError("Workflow name cannot be a valid UUIDv4")
    if not access_token:
        raise Exception(ERROR_MESSAGES["missing_access_token"])
    from reana_client.utils import get_api_url

    if get_api_url() is None:
        raise Exception("REANA server URL is not set")
    workflow_engine = workflow_engine.lower()
    if workflow_engine not in REANA_WORKFLOW_ENGINES:
        raise Exception(
            "Workflow engine - {} not found. You must use one of "
            "these engines - {}".format(workflow_engine, REANA_WORKFLOW_ENGINES)
        )
    # Historically ``workflow_file`` took precedence over ``workflow_json``, so
    # report it first to keep the diagnosis stable for existing callers.
    if workflow_file is not None or workflow_engine != "serial":
        raise ValueError(_untranslatable_json_creation(workflow_engine, workflow_file))
    if not workflow_json:
        raise ValueError(
            "An inline serial workflow specification is required in "
            "'workflow_json'. " + _MIGRATION_HINT
        )

    reana_yaml = {"workflow": {"type": workflow_engine, "specification": workflow_json}}
    if parameters:
        reana_yaml["inputs"] = parameters
    if outputs:
        reana_yaml["outputs"] = outputs
    # Normalise to JSON-native types: ``workflow_json`` comes from arbitrary
    # caller code and yaml.safe_dump cannot represent tuples, sets or numpy
    # scalars. The removed implementation round-tripped the same way before
    # sending, so translated calls keep behaving identically.
    reana_yaml = json.loads(json.dumps(reana_yaml, sort_keys=True))

    # Legacy ``inputs.files`` stay data inputs here: with no ``workflow.file``
    # the specification does not use the legacy validation scope, so they are
    # not loader dependencies and must not be gathered into the bundle.
    bundle_dir = tempfile.mkdtemp(prefix="reana-workflow-json-")
    try:
        specification_path = os.path.join(bundle_dir, "reana.yaml")
        with open(specification_path, "w") as specification:
            yaml.safe_dump(reana_yaml, specification, default_flow_style=False)
        return create_workflow_from_bundle(specification_path, name, access_token)
    finally:
        shutil.rmtree(bundle_dir, ignore_errors=True)


def validate_workflow_spec_bundle(reana_file, access_token, environments=False):
    """Validate a raw specification bundle server-side.

    :param reana_file: path to the local ``reana.yaml`` specification file.
    :param access_token: access token of the current user.
    :param environments: if True, ask the server to check runtime environment
        image tags and return effective runtime identities.
    :return: validation report dict ``{valid, errors, warnings}``.
    """
    params = {}
    if environments:
        params["environments"] = True
    response, _http_response = _post_spec_members(
        "validate_workflow_specification",
        _gather_spec_members(reana_file),
        access_token,
        params,
    )
    return response


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
            _request_options={
                **_CONTROL_REQUEST_OPTIONS,
                **_auth_request_options(access_token),
            },
            workflow_id_or_name=workflow,
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


def restart_workflow(workflow, replacement, access_token, parameters):
    """Atomically restart a workflow with one replacement specification.

    The multipart request is described by the server's OpenAPI 2.0 contract and
    dispatched through Bravado like every other generated API operation.
    """
    _require_workflow_specification_bundles()
    replacement = os.path.abspath(replacement)
    base_directory = os.path.dirname(replacement)
    descriptor = open_regular_file_beneath(
        base_directory,
        os.path.basename(replacement),
        "restart specification",
    )
    try:
        if os.fstat(descriptor).st_size > SPECIFICATION_BUNDLE_MAX_BYTES:
            raise FileUploadError(
                "Restart specification is too large (maximum is {} bytes).".format(
                    SPECIFICATION_BUNDLE_MAX_BYTES
                )
            )
        with os.fdopen(descriptor, "rb") as specification:
            descriptor = None
            bounded_specification = _BoundedSpecificationReader(
                specification, SPECIFICATION_BUNDLE_MAX_BYTES
            )
            response, http_response = current_rs_api_client.api.restart_workflow(
                workflow_id_or_name=workflow,
                replacement=(os.path.basename(replacement), bounded_specification),
                parameters=json.dumps(parameters),
                _request_options={
                    **_TRANSFER_REQUEST_OPTIONS,
                    **_auth_request_options(access_token),
                },
            ).result()
    except HTTPError as error:
        raise Exception(error.response.json()["message"])
    finally:
        if descriptor is not None:
            os.close(descriptor)

    if http_response.status_code != 200:
        raise Exception(
            "Expected status code 200 but replied with {}".format(
                http_response.status_code
            )
        )
    return response


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
        length = _remaining_file_length(file_)
        endpoint = current_rs_api_client.api.upload_file.operation.path_name.format(
            workflow_id_or_name=workflow,
        )
        http_response = requests.post(
            urljoin(get_api_url(), endpoint),
            data=_SnapshotUploadReader(file_, length),
            params={"file_name": file_name},
            headers=_auth_headers(
                access_token,
                {
                    "Content-Type": "application/octet-stream",
                    "Content-Length": str(length),
                },
            ),
            verify=tls_verify(),
            timeout=FILE_TRANSFER_TIMEOUT,
        )
        response = http_response.json()
        if http_response.ok:
            return response
        raise Exception(response.get("message"))
    except requests.exceptions.ConnectionError:
        from reana_client.utils import get_api_url

        logging.debug("File could not be uploaded.", exc_info=True)
        raise Exception("Could not connect to the server {}".format(get_api_url()))
    except requests.exceptions.Timeout:
        logging.debug("Timeout while trying to establish connection.", exc_info=True)
        raise Exception("The request to the server has timed out.")
    except requests.exceptions.RequestException:
        logging.debug("The request to the server failed.", exc_info=True)
        raise Exception("The request to the server has failed.")
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
            _request_options=_auth_request_options(access_token),
            workflow_id_or_name=workflow,
            steps=steps,
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
        logging.getLogger("urllib3").setLevel(logging.CRITICAL)
        _response, http_response = current_rs_api_client.api.download_file(
            workflow_id_or_name=workflow,
            file_name=file_name,
            _request_options={
                **_TRANSFER_REQUEST_OPTIONS,
                **_auth_request_options(access_token),
            },
        ).result()
        if "Content-Disposition" in http_response.headers:
            file_name = get_content_disposition_filename(
                http_response.headers.get("Content-Disposition")
            )

        # A zip archive is downloaded if multiple files are requested
        multiple_files_zipped = (
            http_response.headers.get("Content-Type") == "application/zip"
        )

        if http_response.status_code == 200:
            return http_response.raw_bytes, file_name, multiple_files_zipped
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
            _request_options=_auth_request_options(access_token),
            workflow_id_or_name=workflow,
            file_name=file_name,
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
            _request_options=_auth_request_options(access_token),
            workflow_id_or_name=workflow,
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
            _request_options=_auth_request_options(access_token),
            workflow_id_or_name=workflow,
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
            _request_options=_auth_request_options(access_token),
            workflow_id_or_name=workflow,
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
            _request_options=_auth_request_options(access_token),
            workflow_id_or_name=workflow,
            status="deleted",
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
        response, http_response = current_rs_api_client.api.set_workflow_status(
            _request_options=_auth_request_options(access_token),
            workflow_id_or_name=workflow,
            status="stop",
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
            _request_options=_auth_request_options(access_token),
            workflow_id_or_name_a=workflow_id_a,
            workflow_id_or_name_b=workflow_id_b,
            brief=brief,
            context_lines=context_lines,
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
            _request_options=_auth_request_options(access_token),
            workflow_id_or_name=workflow,
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


def get_interactive_session_secret(workflow, access_token):
    """Return the per-session notebook access secret for a workflow owner."""
    try:
        response, http_response = (
            current_rs_api_client.api.get_interactive_session_secret(
                _request_options=_auth_request_options(access_token),
                workflow_id_or_name=workflow,
            ).result()
        )
        if http_response.status_code == 200:
            return response
        raise Exception(
            "Expected status code 200 but replied with {}".format(
                http_response.status_code
            )
        )
    except HTTPError as error:
        logging.debug(
            "Interactive session secret could not be retrieved.", exc_info=True
        )
        try:
            message = error.response.json().get("message")
        except (AttributeError, ValueError):
            message = None
        raise Exception(
            message
            or "Interactive session secret request failed with HTTP {}.".format(
                error.response.status_code
            )
        ) from error


def close_interactive_session(workflow, access_token):
    """Close an interactive workflow session.

    :param workflow: name or id of the workflow to close.
    :param access_token: workflow owner REANA access token.

    :return: the relative path to the interactive session.
    """
    try:
        response, http_response = current_rs_api_client.api.close_interactive_session(
            _request_options=_auth_request_options(access_token),
            workflow_id_or_name=workflow,
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
            _request_options=_auth_request_options(access_token),
            source=source,
            target=target,
            workflow_id_or_name=workflow,
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
            _request_options=_auth_request_options(access_token),
            workflow_id_or_name=workflow,
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
            _request_options=_auth_request_options(access_token),
            secrets=secrets,
            overwrite=overwrite,
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
            _request_options=_auth_request_options(access_token),
            secrets=secrets,
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
            _request_options=_auth_request_options(access_token),
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
            _request_options=_auth_request_options(access_token),
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
            _request_options=_auth_request_options(access_token),
            workflow_id_or_name=workflow,
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
            _request_options=_auth_request_options(access_token),
            workflow_id_or_name=workflow,
            include_inputs=include_inputs,
            include_outputs=include_outputs,
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
            _request_options=_auth_request_options(access_token),
            workflow_id_or_name=workflow,
            share_details=share_params,
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
        }

        response, http_response = current_rs_api_client.api.unshare_workflow(
            _request_options=_auth_request_options(access_token),
            **unshare_params,
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
            _request_options=_auth_request_options(access_token),
            workflow_id_or_name=workflow,
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
