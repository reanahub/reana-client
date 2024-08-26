# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
"""REANA client utils."""

import base64
from datetime import datetime
import logging
import os
import pathlib
import sys
import traceback
from typing import Dict, Optional
from uuid import UUID

from reana_commons.utils import get_workflow_status_change_verb
from reana_commons.specification import load_reana_spec

from reana_client.config import reana_yaml_valid_file_names
from reana_client.printer import display_message
from reana_client.validation.utils import validate_reana_spec


def workflow_uuid_or_name(ctx, param, value):
    """Get UUID of workflow from configuration / cache file based on name."""
    if not value:
        display_message(
            "Workflow name must be provided either with "
            "`--workflow` option or with REANA_WORKON "
            "environment variable",
            msg_type="error",
        )
        sys.exit(1)
    else:
        return value


def load_validate_reana_spec(
    filepath,
    access_token=None,
    skip_validation=False,
    skip_validate_environments=True,
    pull_environment_image=False,
    server_capabilities=False,
    parameters=False,
):
    """Load and validate reana specification file.

    :raises IOError: Error while reading REANA spec file from given `filepath`.
    :raises ValidationError: Given REANA spec file does not validate against
        REANA specification.
    """

    try:
        reana_yaml = load_reana_spec(filepath)
        validate_reana_spec(
            reana_yaml,
            filepath,
            access_token=access_token,
            skip_validation=skip_validation,
            skip_validate_environments=skip_validate_environments,
            pull_environment_image=pull_environment_image,
            server_capabilities=server_capabilities,
            parameters=parameters,
        )

        if reana_yaml["workflow"]["type"] == "yadage":
            # We don't send the loaded Yadage workflow spec to the cluster as
            # it may result in inconsistencies between what's displayed in the
            # UI and the actual spec loaded at the workflow engine level.
            # More info: https://github.com/reanahub/reana-client/pull/462#discussion_r585794297
            reana_yaml["workflow"]["specification"] = None

        return reana_yaml
    except Exception as e:
        raise e


def is_uuid_v4(uuid_or_name):
    """Check if given string is a valid UUIDv4."""
    # Based on https://gist.github.com/ShawnMilo/7777304
    try:
        uuid = UUID(uuid_or_name, version=4)
    except Exception:
        return False

    return uuid.hex == uuid_or_name.replace("-", "")


def is_regular_path(path: str) -> bool:
    """Check if path does not refer to a symbolic link."""
    full_path = pathlib.Path(os.path.abspath(path))
    for parent in full_path.parents:
        if not parent.is_dir() or parent.is_symlink():
            return False
    return not full_path.is_symlink()


def get_workflow_name_and_run_number(workflow_name):
    """Return name and run_number of a workflow.

    :param workflow_name: String representing Workflow name.

        Name might be in format 'reana.workflow.123' with arbitrary
        number of dot-delimited substrings, where last substring specifies
        the run number of the workflow this workflow name refers to.

        If name does not contain a valid run number, name without run number
        is returned.
    """
    # Try to split a dot-separated string.
    try:
        name, run_number = workflow_name.split(".", 1)

        try:
            float(run_number)
        except ValueError:
            # `workflow_name` was split, so it is a dot-separated string
            # but it didn't contain a valid `run_number`.
            # Assume that this dot-separated string is the name of
            # the workflow and return just this without a `run_number`.
            return workflow_name, ""

        return name, run_number

    except ValueError:
        # Couldn't split. Probably not a dot-separated string.
        # Return the name given as parameter without a `run_number`.
        return workflow_name, ""


def get_workflow_duration(workflow: Dict) -> Optional[int]:
    """Calculate the duration of the workflow.

    :param workflow: Workflow details returned by the server.
    :return: The duration of the workflow in seconds or ``None`` if the starting
        time is not present.
    """

    # FIXME: Use datetime.fromisoformat when moving to Python 3.7 or higher
    def fromisoformat(date_string):
        return datetime.strptime(date_string, "%Y-%m-%dT%H:%M:%S")

    progress = workflow.get("progress", {})
    run_started_at = progress.get("run_started_at")
    run_finished_at = progress.get("run_finished_at")
    run_stopped_at = progress.get("run_stopped_at")

    duration = None
    if run_started_at:
        start_time = fromisoformat(run_started_at)
        if run_finished_at:
            end_time = fromisoformat(run_finished_at)
        elif run_stopped_at:
            end_time = fromisoformat(run_stopped_at)
        else:
            end_time = datetime.utcnow()
        duration = round((end_time - start_time).total_seconds())
    return duration


def get_workflow_root():
    """Return the current workflow root directory."""
    reana_yaml = get_reana_yaml_file_path()
    workflow_root = os.getcwd()
    while True:
        file_list = os.listdir(workflow_root)
        parent_dir = os.path.dirname(workflow_root)
        if reana_yaml in file_list:
            break
        else:
            if workflow_root == parent_dir:
                display_message(
                    "Not a workflow directory (or any of the parent directories).\n"
                    "Please upload from inside the directory containing "
                    "the reana.yaml file of your workflow.",
                    msg_type="error",
                )
                sys.exit(1)
            else:
                workflow_root = parent_dir
    workflow_root += "/"
    return workflow_root


def get_workflow_status_change_msg(workflow, status):
    """Choose verb conjugation depending on status.

    :param workflow: Workflow name whose status changed.
    :param status: String which represents the status the workflow changed to.
    """
    return "{workflow} {verb} {status}".format(
        workflow=workflow, verb=get_workflow_status_change_verb(status), status=status
    )


def parse_secret_from_literal(literal):
    """Parse a literal string, into a secret dict.

    :param literal: String containg a key and a value. (e.g. 'KEY=VALUE')
    :returns secret: Dictionary in the format suitable for sending
    via http request.
    """
    try:
        key, value = literal.split("=", 1)
        secret = {
            key: {
                "value": base64.b64encode(value.encode("utf-8")).decode("utf-8"),
                "type": "env",
            }
        }
        return secret

    except ValueError as e:
        logging.debug(traceback.format_exc())
        logging.debug(str(e))
        display_message(
            'Option "{0}" is invalid: \n'
            'For literal strings use "SECRET_NAME=VALUE" format'.format(literal),
            msg_type="error",
        )
        sys.exit(1)


def parse_secret_from_path(path):
    """Parse a file path into a secret dict.

    :param path: Path of the file containing secret
    :returns secret: Dictionary in the format suitable for sending
     via http request.
    """
    try:
        with open(os.path.expanduser(path), "rb") as file:
            file_name = os.path.basename(path)
            secret = {
                file_name: {
                    "value": base64.b64encode(file.read()).decode("utf-8"),
                    "type": "file",
                }
            }
        return secret
    except FileNotFoundError as e:
        logging.debug(traceback.format_exc())
        logging.debug(str(e))
        display_message(
            "File {0} could not be uploaded: {0} does not exist.".format(path),
            msg_type="error",
        )
        sys.exit(1)


def get_api_url():
    """Obtain REANA server API URL."""
    server_url = os.getenv("REANA_SERVER_URL")
    return server_url.strip(" \t\n\r/") if server_url else None


def get_reana_yaml_file_path():
    """REANA specification file location."""
    matches = [path for path in reana_yaml_valid_file_names if os.path.exists(path)]
    if len(matches) == 0:
        display_message(
            "No REANA specification file (reana.yaml) found. Exiting.",
            msg_type="error",
        )
        sys.exit(1)
    if len(matches) > 1:
        display_message(
            "Found {0} REANA specification files ({1}). "
            "Please use only one. Exiting.".format(len(matches), ", ".join(matches)),
            msg_type="error",
        )
        sys.exit(1)
    for path in reana_yaml_valid_file_names:
        if os.path.exists(path):
            return path
    # If none of the valid paths exists, fall back to reana.yaml.
    return "reana.yaml"
