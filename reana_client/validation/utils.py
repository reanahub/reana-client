# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2021, 2022 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""REANA client validation utilities."""

import sys
from typing import Dict, NoReturn, Union

import click
import json

from reana_commons.errors import REANAValidationError
from reana_commons.validation.operational_options import validate_operational_options
from reana_commons.validation.utils import validate_reana_yaml, validate_workflow_name


from reana_client.printer import display_message
from reana_client.validation.compute_backends import validate_compute_backends
from reana_client.validation.environments import validate_environment
from reana_client.validation.parameters import validate_parameters
from reana_client.validation.workspace import _validate_workspace

def display_reana_params_warnings(validator) -> None:
    """Display REANA specification parameter validation warnings."""
    _display_messages_type(
        info_msg="Verifying REANA specification parameters... ",
        success_msg="REANA specification parameters appear valid.",
        messages=validator["reana_params_warnings"],
    )


def display_workflow_params_warnings(validator) -> None:
    """Display REANA workflow parameter and command validation warnings."""
    _display_messages_type(
        info_msg="Verifying workflow parameters and commands... ",
        success_msg="Workflow parameters and commands appear valid.",
        messages=validator["workflow_params_warnings"],
    )


def display_operations_warnings(validator) -> None:
    """Display dangerous workflow operation warnings."""
    _display_messages_type(
        info_msg="Verifying dangerous workflow operations... ",
        success_msg="Workflow operations appear valid.",
        messages=validator["operations_warnings"],
    )


def _display_messages_type(info_msg, success_msg, messages) -> None:
    display_message(info_msg, msg_type="info")
    for msg in messages:
        display_message(msg["message"], msg_type=msg["type"], indented=True)
    if not messages:
        display_message(success_msg, msg_type="success", indented=True)

def validate_reana_spec(
    reana_yaml,
    filepath,
    access_token=None,
    skip_validation=False,
    skip_validate_environments=True,
    pull_environment_image=False,
    server_capabilities=False,
    parameters=False,
):
 
    local_validation(
        reana_yaml,
        filepath,
        access_token=access_token,
        skip_validation=skip_validation,
        skip_validate_environments=skip_validate_environments,
        pull_environment_image=pull_environment_image,
        server_capabilities=server_capabilities,
        parameters=parameters
    )

    server_validation(
        reana_yaml,
        filepath,
        access_token=access_token,
        skip_validation=skip_validation,
        skip_validate_environments=skip_validate_environments,
        pull_environment_image=pull_environment_image,
        server_capabilities=server_capabilities,
        parameters=parameters
    )

def local_validation(
    reana_yaml,
    filepath,
    access_token=None,
    skip_validation=False,
    skip_validate_environments=True,
    pull_environment_image=False,
    server_capabilities=False,
    parameters=False,
):
    
    print("")
    display_message(
        f"Results from local validation",
        msg_type="info",
    )

    """Validate REANA specification file."""
    if "options" in reana_yaml.get("inputs", {}):
        workflow_type = reana_yaml["workflow"]["type"]
        workflow_options = reana_yaml["inputs"]["options"]
        try:
            reana_yaml["inputs"]["options"] = validate_operational_options(
                workflow_type, workflow_options
            )
        except REANAValidationError as e:
            display_message(e.message, msg_type="error")
            sys.exit(1)

    if not skip_validation:
        display_message(
            f"Verifying REANA specification file... {filepath}",
            msg_type="info",
        )
        validation_warnings = validate_reana_yaml(reana_yaml)
        if validation_warnings:
            display_message(
                "The REANA specification appears valid, but some warnings were found.",
                msg_type="warning",
                indented=True,
            )
        for warning_key, warning_values in validation_warnings.items():
            if warning_key == "additional_properties":
                # warning_values is a list of unexpected properties
                messages = [
                    f"'{value['property']}'"
                    + (f" (at {value['path']})" if value["path"] else "")
                    for value in warning_values
                ]
                message = (
                    f"Unexpected properties found in REANA specification file: "
                    f"{', '.join(messages)}."
                )
            else:
                # warning_values is a list of dictionaries with 'message' and 'path'
                messages = [
                    f"{value['message']}"
                    + (f" (at {value['path']})" if value["path"] else "")
                    for value in warning_values
                ]
                message = f"{'; '.join(messages)}."
            display_message(
                message,
                msg_type="warning",
                indented=True,
            )
        if validation_warnings:
            display_message(
                "Please make sure that the REANA specification file is correct.",
                msg_type="warning",
                indented=True,
            )
        else:
            display_message(
                "Valid REANA specification file.",
                msg_type="success",
                indented=True,
            )

        validate_parameters(reana_yaml)

        if server_capabilities:
            _validate_server_capabilities(reana_yaml, access_token)

    if not skip_validate_environments:
        display_message(
            "Verifying environments in REANA specification file...",
            msg_type="info",
        )
        validate_environment(reana_yaml, pull=pull_environment_image)

def server_validation(
    reana_yaml,
    filepath,
    access_token=None,
    skip_validation=False,
    skip_validate_environments=True,
    pull_environment_image=False,
    server_capabilities=False,
    parameters=False,
):
   
    print("")
    display_message(
        f"Results from server side validation",
        msg_type="info",
    )

    reana_yaml = json.loads(json.dumps(reana_yaml))

    # Instruct server to also check server capanilities if needed
    reana_yaml['server_capabilities'] = server_capabilities

    # Add runtime_parameters if they exist
    reana_yaml['runtime_parameters'] = parameters

    # Also check environments if needed
    reana_yaml['skip_validate_environments'] = skip_validate_environments

    # Send to server's api for validation
    from reana_client.api.client import validate_workflow
    response, http_response = validate_workflow(reana_yaml)
    #TODO: remove
    #print("\nResponse from server:")
    #print(response, http_response)
    #print("")

    display_message(
        f"Verifying REANA specification file... {filepath}",
        msg_type="info",
    )

    validation_warnings = response["message"]["reana_spec_file_warnings"]
    if validation_warnings:
        display_message(
            "The REANA specification appears valid, but some warnings were found.",
            msg_type="warning",
            indented=True,
        )
    for warning_key, warning_values in validation_warnings.items():
        if warning_key == "additional_properties":
            # warning_values is a list of unexpected properties
            messages = [
                f"'{value['property']}'"
                + (f" (at {value['path']})" if value["path"] else "")
                for value in warning_values
            ]
            message = (
                f"Unexpected properties found in REANA specification file: "
                f"{', '.join(messages)}."
            )
        else:
            # warning_values is a list of dictionaries with 'message' and 'path'
            messages = [
                f"{value['message']}"
                + (f" (at {value['path']})" if value["path"] else "")
                for value in warning_values
            ]
            message = f"{'; '.join(messages)}."
        display_message(
            message,
            msg_type="warning",
            indented=True,
        )
    if validation_warnings:
        display_message(
            "Please make sure that the REANA specification file is correct.",
            msg_type="warning",
            indented=True,
        )
    else:
        display_message(
            "Valid REANA specification file.",
            msg_type="success",
            indented=True,
        )

    validation_parameter_warnings = json.loads(response["message"]["reana_spec_params_warnings"])
    display_reana_params_warnings(validation_parameter_warnings)
    display_workflow_params_warnings(validation_parameter_warnings)
    display_operations_warnings(validation_parameter_warnings)

    if parameters:
        display_message(
            f"Validating runtime parameters...",
            msg_type="info",
        )
        runtime_params_warnings = response["message"]["runtime_params_warnings"]
        if runtime_params_warnings:
            for warning_message in runtime_params_warnings:
                display_message(
                    warning_message,
                    msg_type="warning",
                    indented=True,
                )

        runtime_params_errors = response["message"]["runtime_params_errors"]
        if runtime_params_errors:
            for error_message in runtime_params_errors:
                display_message(
                    error_message,
                    msg_type="error",
                    indented=True,
                )
                sys.exit(1)

        if not runtime_params_warnings:
            display_message(
                "Runtime paramters appear valid.",
                msg_type="success",
                indented=True,
            )

    server_capabilities = response["message"]["server_capabilities"]
    if server_capabilities:
        display_message(
            f"Verifying compute backends in REANA specification file...",
            msg_type="info",
        )
        for message in server_capabilities:
            if message:
                display_message(
                    message["message"],
                    msg_type=message["msg_type"],
                    indented=True,
                )

    if not skip_validate_environments:
        display_message(
            "Verifying environments in REANA specification file...",
            msg_type="info",
        )
        environments_warnings = response["message"]["environments_warnings"]
        for message in environments_warnings:
            if message:
                display_message(
                    message["message"],
                    msg_type=message["type"],
                    indented=True,
                )        

    print("")

def _validate_server_capabilities(reana_yaml: Dict, access_token: str) -> None:
    """Validate server capabilities in REANA specification file.

    :param reana_yaml: dictionary which represents REANA specification file.
    :param access_token: access token of the current user.
    """
    from reana_client.api.client import info

    info_response = info(access_token)

    display_message(
        "Verifying compute backends in REANA specification file...",
        msg_type="info",
    )
    supported_backends = info_response.get("compute_backends", {}).get("value")
    validate_compute_backends(reana_yaml, supported_backends)

    root_path = reana_yaml.get("workspace", {}).get("root_path")
    available_workspaces = info_response.get("workspaces_available", {}).get("value")
    _validate_workspace(root_path, available_workspaces)


def validate_input_parameters(live_parameters, original_parameters):
    """Return validated input parameters."""
    parsed_input_parameters = dict(live_parameters)
    for parameter in parsed_input_parameters.keys():
        if parameter not in original_parameters:
            display_message(
                'Command-line parameter "{0}" is not defined in reana.yaml'.format(parameter),
                msg_type='error',
            )
            sys.exit(1)
    return live_parameters


def validate_workflow_name_parameter(
    ctx: click.core.Context, _: click.core.Option, workflow_name: str
) -> Union[str, NoReturn]:
    """Validate workflow name parameter."""
    try:
        return validate_workflow_name(workflow_name)
    except ValueError as e:
        display_message(str(e), msg_type="error")
        sys.exit(1)
