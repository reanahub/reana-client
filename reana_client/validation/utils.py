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

from reana_commons.errors import REANAValidationError
from reana_commons.validation.operational_options import validate_operational_options
from reana_commons.validation.utils import validate_reana_yaml, validate_workflow_name


from reana_client.printer import display_message
from reana_client.validation.compute_backends import validate_compute_backends
from reana_client.validation.environments import validate_environment
from reana_client.validation.parameters import validate_parameters
from reana_client.validation.workspace import _validate_workspace


def validate_reana_spec(
    reana_yaml,
    filepath,
    access_token=None,
    skip_validation=False,
    skip_validate_environments=True,
    pull_environment_image=False,
    server_capabilities=False,
):
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
            f"Verifying REANA specification file... {filepath}", msg_type="info",
        )
        validate_reana_yaml(reana_yaml)
        display_message(
            "Valid REANA specification file.", msg_type="success", indented=True,
        )

        validate_parameters(reana_yaml)

        if server_capabilities:
            _validate_server_capabilities(reana_yaml, access_token)

    if not skip_validate_environments:
        display_message(
            "Verifying environments in REANA specification file...", msg_type="info",
        )
        validate_environment(reana_yaml, pull=pull_environment_image)


def _validate_server_capabilities(reana_yaml: Dict, access_token: str) -> None:
    """Validate server capabilities in REANA specification file.

    :param reana_yaml: dictionary which represents REANA specification file.
    :param access_token: access token of the current user.
    """
    from reana_client.api.client import info

    info_response = info(access_token)

    display_message(
        "Verifying compute backends in REANA specification file...", msg_type="info",
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
                "Given parameter - {0}, is not in reana.yaml".format(parameter),
                msg_type="error",
            )
            del live_parameters[parameter]
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
