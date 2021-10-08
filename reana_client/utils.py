# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2017, 2018 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
"""REANA client utils."""

import base64
import datetime
import json
import logging
import os
import subprocess
import sys
import traceback
from typing import NoReturn
from uuid import UUID

import click
import yaml
from jsonschema import ValidationError, validate
from reana_commons.errors import REANAValidationError
from reana_commons.operational_options import validate_operational_options
from reana_commons.serial import serial_load
from reana_commons.snakemake import snakemake_load
from reana_commons.yadage import yadage_load
from reana_commons.utils import get_workflow_status_change_verb
from reana_commons.workspaces import validate_workspace

from reana_client.config import (
    reana_yaml_schema_file_path,
    reana_yaml_valid_file_names,
)
from reana_client.printer import display_message
from reana_client.validation.environments import validate_environment
from reana_client.validation.parameters import validate_parameters


def workflow_uuid_or_name(ctx, param, value):
    """Get UUID of workflow from configuration / cache file based on name."""
    if not value:
        display_message(
            "Workflow name must be provided either with "
            "`--workflow` option or with REANA_WORKON "
            "environment variable",
            msg_type="error",
        )
    else:
        return value


def cwl_load(workflow_file, **kwargs):
    """Validate and return cwl workflow specification.

    :param workflow_file: A specification file compliant with
        `cwl` workflow specification.
    :returns: A dictionary which represents the valid `cwl` workflow.
    """
    result = subprocess.check_output(["cwltool", "--pack", "--quiet", workflow_file])
    value = result.decode("utf-8")
    return json.loads(value)


def load_workflow_spec(workflow_type, workflow_file, **kwargs):
    """Validate and return machine readable workflow specifications.

    :param workflow_type: A supported workflow specification type.
    :param workflow_file: A workflow file compliant with `workflow_type`
        specification.
    :returns: A dictionary which represents the valid workflow specification.
    """
    workflow_load = {
        "yadage": yadage_load,
        "cwl": cwl_load,
        "serial": serial_load,
        "snakemake": snakemake_load,
    }

    """Dictionary to extend with new workflow specification loaders."""
    load_function = workflow_load.get(workflow_type)
    if load_function:
        return load_function(workflow_file, **kwargs)
    return {}


def load_reana_spec(
    filepath,
    access_token=None,
    skip_validation=False,
    skip_validate_environments=True,
    pull_environment_image=False,
    server_capabilities=False,
):
    """Load and validate reana specification file.

    :raises IOError: Error while reading REANA spec file from given `filepath`.
    :raises ValidationError: Given REANA spec file does not validate against
        REANA specification.
    """

    def _prepare_kwargs(reana_yaml):
        kwargs = {}
        workflow_type = reana_yaml["workflow"]["type"]
        if workflow_type == "serial":
            kwargs["specification"] = reana_yaml["workflow"].get("specification")
            kwargs["parameters"] = reana_yaml.get("inputs", {}).get("parameters", {})
            kwargs["original"] = True
        if "options" in reana_yaml.get("inputs", {}):
            try:
                reana_yaml["inputs"]["options"] = validate_operational_options(
                    workflow_type, reana_yaml["inputs"]["options"]
                )
            except REANAValidationError as e:
                display_message(e.message, msg_type="error")
                sys.exit(1)
            kwargs.update(reana_yaml["inputs"]["options"])
        if workflow_type == "snakemake":
            kwargs["input"] = (
                reana_yaml.get("inputs", {}).get("parameters", {}).get("input")
            )
        return kwargs

    try:
        with open(filepath) as f:
            reana_yaml = yaml.load(f.read(), Loader=yaml.FullLoader)
        if not skip_validation:
            display_message(
                "Verifying REANA specification file... {filepath}".format(
                    filepath=filepath
                ),
                msg_type="info",
            )
            _validate_reana_yaml(reana_yaml)
        workflow_type = reana_yaml["workflow"]["type"]
        reana_yaml["workflow"]["specification"] = load_workflow_spec(
            workflow_type,
            reana_yaml["workflow"].get("file"),
            **_prepare_kwargs(reana_yaml)
        )

        if (
            workflow_type == "cwl" or workflow_type == "snakemake"
        ) and "inputs" in reana_yaml:
            with open(reana_yaml["inputs"]["parameters"]["input"]) as f:
                reana_yaml["inputs"]["parameters"] = yaml.load(
                    f, Loader=yaml.FullLoader
                )

        if not skip_validation:
            validate_parameters(workflow_type, reana_yaml)

        if not skip_validate_environments:
            display_message(
                "Verifying environments in REANA specification file...",
                msg_type="info",
            )
            validate_environment(reana_yaml, pull=pull_environment_image)

        if server_capabilities:
            root_path = reana_yaml.get("workspace", {}).get("root_path")
            display_message(
                "Verifying workspace in REANA specification file...", msg_type="info",
            )
            _validate_workspace(root_path, access_token)

        if workflow_type == "yadage":
            # We don't send the loaded Yadage workflow spec to the cluster as
            # it may result in inconsistencies between what's displayed in the
            # UI and the actual spec loaded at the workflow engine level.
            # More info: https://github.com/reanahub/reana-client/pull/462#discussion_r585794297
            reana_yaml["workflow"]["specification"] = None

        return reana_yaml
    except IOError as e:
        logging.info(
            "Something went wrong when reading specifications file from "
            "{filepath} : \n"
            "{error}".format(filepath=filepath, error=e.strerror)
        )
        raise e
    except Exception as e:
        raise e


def _validate_reana_yaml(reana_yaml):
    """Validate REANA specification file according to jsonschema.

    :param reana_yaml: Dictionary which represents REANA specifications file.
    :raises ValidationError: Given REANA spec file does not validate against
        REANA specification schema.
    """
    try:
        with open(reana_yaml_schema_file_path, "r") as f:
            reana_yaml_schema = json.loads(f.read())
            validate(reana_yaml, reana_yaml_schema)
        display_message(
            "Valid REANA specification file.", msg_type="success", indented=True,
        )
    except IOError as e:
        logging.info(
            "Something went wrong when reading REANA validation schema from "
            "{filepath} : \n"
            "{error}".format(filepath=reana_yaml_schema_file_path, error=e.strerror)
        )
        raise e
    except ValidationError as e:
        logging.info("Invalid REANA specification: {error}".format(error=e.message))
        raise e


def is_uuid_v4(uuid_or_name):
    """Check if given string is a valid UUIDv4."""
    # Based on https://gist.github.com/ShawnMilo/7777304
    try:
        uuid = UUID(uuid_or_name, version=4)
    except Exception:
        return False

    return uuid.hex == uuid_or_name.replace("-", "")


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


def validate_input_parameters(live_parameters, original_parameters):
    """Return validated input parameters."""
    parsed_input_parameters = dict(live_parameters)
    for parameter in parsed_input_parameters.keys():
        if parameter not in original_parameters:
            display_message(
                "Given parameter - {0}, is not in reana.yaml".format(parameter),
                msg_type="error",
            )
            del live_parameters[parameter]
    return live_parameters


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


def run_command(cmd, display=True, return_output=False, stderr_output=False):
    """Run given command on shell in the current directory.

    Exit in case of troubles.

    :param cmd: shell command to run
    :param display: should we display command to run?
    :param return_output: shall the output of the command be returned?
    :type cmd: str
    :type display: bool
    :type return_output: bool
    """
    now = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    if display:
        click.secho("[{0}] ".format(now), bold=True, nl=False, fg="green")
        click.secho("{0}".format(cmd), bold=True)
    try:
        if return_output:
            stderr_flag_val = subprocess.STDOUT if stderr_output else None
            result = subprocess.check_output(cmd, stderr=stderr_flag_val, shell=True)
            return result.decode().rstrip("\r\n")
        else:
            subprocess.check_call(cmd, shell=True)
    except subprocess.CalledProcessError as err:
        if display:
            click.secho("[{0}] ".format(now), bold=True, nl=False, fg="green")
            click.secho("{0}".format(err), bold=True, fg="red")
        if stderr_output:
            sys.exit(err.output.decode())
        sys.exit(err.returncode)


def _validate_workspace(root_path: str, access_token: str) -> NoReturn:
    """Validate workspace in REANA specification file.

    :param root_path: workspace root path to be validated.
    :param access_token: access token of the current user.

    :raises ValidationError: Given workspace in REANA spec file does not validate against
        allowed workspaces.
    """
    from reana_client.api.client import info

    if not root_path:
        display_message(
            "Workspace not found in REANA specification file. Validation skipped.",
            msg_type="warning",
            indented=True,
        )
    else:
        available_workspaces = (
            info(access_token).get("workspaces_available", {}).get("value")
        )
        try:
            validate_workspace(root_path, available_workspaces)
            display_message(
                "Workflow workspace appears valid.", msg_type="success", indented=True,
            )
        except REANAValidationError as e:
            display_message(e.message, msg_type="error")
            sys.exit(1)
