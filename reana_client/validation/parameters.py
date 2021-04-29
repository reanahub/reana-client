# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2021 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""REANA client parameters validation."""


import re
import sys
from collections import defaultdict
import os


from reana_client.config import COMMAND_DANGEROUS_OPERATIONS
from reana_client.validation.utils import run_command
from reana_client.printer import display_message


def validate_parameters(workflow_type, reana_yaml):
    """Validate the presence of input parameters in workflow step commands and viceversa.

    :param workflow_type: A supported workflow specification type.
    :param reana_yaml: REANA YAML specification.
    :returns: A bool indicating if parameters and commands are fully valid.
    """
    validate = {
        "yadage": _validate_yadage_parameters,
        "cwl": _validate_cwl_parameters,
        "serial": _validate_serial_parameters,
    }
    """Dictionary to extend with new workflow specification loaders."""
    if "inputs" not in reana_yaml:
        display_message(
            'Workflow "inputs" are missing in the REANA specification.',
            msg_type="warning",
            indented=True,
        )

    valid = validate[workflow_type](reana_yaml)
    if valid:
        display_message(
            "Workflow parameters and commands appear valid.",
            msg_type="success",
            indented=True,
        )
    return valid


def _warn_not_used_parameters(workflow_parameters, command_parameters, type_="REANA"):
    """Warn user about defined workflow parameter not being used.

    :param workflow_parameters: Set of parameters in workflow definition.
    :param command_parameters: Set of parameters used inside workflow.
    :param type: Type of workflow parameters, e.g. REANA for input parameters, Yadage
                 for parameters defined in Yadage spec.
    :returns: A dictionary containing the set of command parameters not referenced by
              workflow parameters and whether warnings were displayed.
    """

    unused_parameters = workflow_parameters.difference(command_parameters)
    for parameter in unused_parameters:
        display_message(
            '{} input parameter "{}" does not seem to be used.'.format(
                type_, parameter
            ),
            msg_type="warning",
            indented=True,
        )
    return {
        "rest_workflow_params": command_parameters.difference(workflow_parameters),
        "has_warnings": bool(unused_parameters),
    }


def _warn_not_defined_parameters(
    cmd_param_steps_mapping, workflow_parameters, workflow_type
):
    """Warn user about command parameters missing in workflow definition.

    :param cmd_param_steps_mapping: Mapping between command parameters and its step.
    :param workflow_parameters: Set of parameters in workflow definition.
    :param workflow_type: Workflow type being checked.
    :returns: A dictionary containing whether warnings were displayed.
    """
    command_parameters = set(cmd_param_steps_mapping.keys())
    command_parameters_not_defined = command_parameters.difference(workflow_parameters)
    for parameter in command_parameters_not_defined:
        steps_used = cmd_param_steps_mapping[parameter]

        display_message(
            '{type} parameter "{parameter}" found on step{s} "{steps}" is not defined in input parameters.'.format(
                type=workflow_type.capitalize(),
                parameter=parameter,
                steps=", ".join(steps_used),
                s="s" if len(steps_used) > 1 else "",
            ),
            msg_type="warning",
            indented=True,
        )
    return {"has_warnings": bool(command_parameters_not_defined)}


def _warn_misused_parameters_in_steps(
    param_steps_mapping, cmd_param_steps_mapping, workflow_type
):
    """Warn user about not used command parameters and not defined input parameters after checking each step of workflow definition.

    :param param_steps_mapping: Mapping between parameters in workflow definition and its step.
    :param cmd_param_steps_mapping: Mapping between command parameters and its step.
    :param workflow_type: Workflow type being checked.
    :returns: A dictionary containing whether warnings were displayed.
    """
    command_parameters = set(cmd_param_steps_mapping.keys())
    workflow_params = set(param_steps_mapping.keys())
    has_warnings = False
    for parameter in command_parameters:
        cmd_param_steps = cmd_param_steps_mapping[parameter]
        param_steps = param_steps_mapping[parameter]
        steps_diff = cmd_param_steps.difference(param_steps)
        if steps_diff:
            has_warnings = True
            display_message(
                '{type} parameter "{parameter}" found on step{s} "{steps}" is not defined in input parameters.'.format(
                    type=workflow_type.capitalize(),
                    parameter=parameter,
                    steps=", ".join(steps_diff),
                    s="s" if len(steps_diff) > 1 else "",
                ),
                msg_type="warning",
                indented=True,
            )
    for parameter in workflow_params:
        param_steps = param_steps_mapping[parameter]
        cmd_param_steps = cmd_param_steps_mapping[parameter]
        steps_diff = param_steps.difference(cmd_param_steps)
        if steps_diff:
            has_warnings = True
            display_message(
                '{type} input parameter "{parameter}" found on step{s} "{steps}" does not seem to be used.'.format(
                    type=workflow_type.capitalize(),
                    parameter=parameter,
                    steps=", ".join(steps_diff),
                    s="s" if len(steps_diff) > 1 else "",
                ),
                msg_type="warning",
                indented=True,
            )
    return {"has_warnings": has_warnings}


def _validate_cwl_parameters(reana_yaml):
    """Validate input parameters for CWL workflows.

    :param reana_yaml: REANA YAML specification.
    :returns: A bool indicating if no warnings were displayed, i.e. it's fully valid.
    """

    def _check_dangerous_operations(workflow):
        """Check for "baseCommand" and "arguments" in workflow.

        If these keys are found, validate if they have dangerous operations.
        """
        cmd_keys = ["baseCommand", "arguments"]
        for cmd_key in cmd_keys:
            if cmd_key in workflow:
                cmd_values = (
                    workflow[cmd_key]
                    if isinstance(workflow[cmd_key], list)
                    else [workflow[cmd_key]]
                )
                for cmd_value in cmd_values:
                    _validate_dangerous_operations(
                        str(cmd_value), step=workflow.get("id")
                    )

    cwl_main_spec_path = reana_yaml["workflow"].get("file")
    if os.path.exists(cwl_main_spec_path):
        run_command(
            "cwltool --validate --strict {}".format(cwl_main_spec_path),
            display=False,
            return_output=True,
            stderr_output=True,
        )
    else:
        display_message(
            "Workflow path {} is not valid.".format(cwl_main_spec_path),
            msg_type="error",
            indented=True,
        )
        sys.exit(1)

    workflow = reana_yaml["workflow"]["specification"].get(
        "$graph", reana_yaml["workflow"]["specification"]
    )
    if isinstance(workflow, dict):
        _check_dangerous_operations(workflow)
    elif isinstance(workflow, list):
        for wf in workflow:
            _check_dangerous_operations(wf)

    return True


def _validate_serial_parameters(reana_yaml):
    """Validate input parameters for Serial workflows.

    :param reana_yaml: REANA YAML specification.
    :returns: A bool indicating if no warnings were displayed, i.e. it's fully valid.
    """

    def parse_command(command):
        return re.findall(r".*?\${(.*?)}.*?", command)

    # REANA input parameters
    input_parameters = set(reana_yaml.get("inputs", {}).get("parameters", {}).keys())

    cmd_param_steps_mapping = defaultdict(set)
    for idx, step in enumerate(
        reana_yaml["workflow"]["specification"].get("steps", [])
    ):
        step_name = step.get("name", str(idx))
        for command in step["commands"]:
            _validate_dangerous_operations(command, step=step_name)
            cmd_params = parse_command(command)
            for cmd_param in cmd_params:
                cmd_param_steps_mapping[cmd_param].add(step_name)

    command_parameters = set(cmd_param_steps_mapping.keys())

    params_warning = _warn_not_used_parameters(input_parameters, command_parameters)
    command_warning = _warn_not_defined_parameters(
        cmd_param_steps_mapping, input_parameters, "serial"
    )

    return not (params_warning["has_warnings"] or command_warning["has_warnings"])


def _validate_yadage_parameters(reana_yaml):  # noqa: C901
    """Validate parameters for Yadage workflows.

    :param reana_yaml: REANA YAML specification.
    :returns: A bool indicating if no warnings were displayed, i.e. it's fully valid.
    """

    def parse_command(command):
        return re.findall(r".*?\{+(.*?)\}+.*?", command)

    def parse_command_params(step_value):
        if isinstance(step_value, dict):
            step_value = list(step_value.values())

        if isinstance(step_value, list):
            step_value = [
                value.values() if isinstance(value, dict) else value
                for value in step_value
            ]
        return parse_command(str(step_value))

    def get_publisher_definitions(
        step, step_name, step_key, step_val,
    ):
        """Save publisher definitions as command params."""
        publisher_cmd_param_steps_mapping = defaultdict(set)
        if step == "publisher":
            command_params = {
                "publish": lambda: step_val.keys(),
                "outputkey": lambda: [step_val],
            }.get(step_key, lambda: [])()
            for command_param in command_params:
                publisher_cmd_param_steps_mapping[command_param].add(step_name)
        return publisher_cmd_param_steps_mapping

    def parse_params(stages):
        param_steps_mapping = defaultdict(set)
        cmd_param_steps_mapping = defaultdict(set)
        for stage in stages:
            step_name = stage["name"]

            # Handle nested stages
            if "workflow" in stage["scheduler"]:
                nested_stages = stage["scheduler"]["workflow"].get("stages", {})
                nested_params_mapping, nested_cmd_param_mapping = parse_params(
                    nested_stages
                )

                for param, steps in nested_params_mapping.items():
                    param_steps_mapping[param].update(steps)

                for param, steps in nested_cmd_param_mapping.items():
                    cmd_param_steps_mapping[param].update(steps)

            # Extract defined stage params
            if "step" in stage["scheduler"].keys():
                for param in stage["scheduler"]["parameters"]:
                    param_steps_mapping[param["key"]].add(step_name)

            # Extract command params used in stage steps
            for step in stage["scheduler"].get("step", {}).keys():
                for step_key, step_val in stage["scheduler"]["step"][step].items():

                    # Parse publisher definitions
                    publisher_cmd_param_steps_mapping = get_publisher_definitions(
                        step, step_name, step_key, step_val
                    )
                    cmd_param_steps_mapping.update(publisher_cmd_param_steps_mapping)

                    # Validate operations
                    if step_key in ["script", "cmd"]:
                        command = step_val
                        _validate_dangerous_operations(command, step=step_name)

                    # Parse command params
                    step_commands_params = parse_command_params(step_val)
                    for command_param in step_commands_params:
                        cmd_param_steps_mapping[command_param].add(step_name)

        return param_steps_mapping, cmd_param_steps_mapping

    # REANA input parameters
    input_params = set(reana_yaml["inputs"].get("parameters", {}).keys())

    # Yadage parameters
    workflow_spec = reana_yaml["workflow"]["specification"]
    param_steps_mapping, cmd_param_steps_mapping = parse_params(workflow_spec["stages"])
    workflow_params = set(param_steps_mapping.keys())

    # REANA input parameters validation
    reana_params_warning = _warn_not_used_parameters(input_params, workflow_params)

    # Yadage command and input parameter validation
    yadage_params_warning = _warn_misused_parameters_in_steps(
        param_steps_mapping, cmd_param_steps_mapping, "Yadage"
    )

    return not (
        reana_params_warning["has_warnings"] or yadage_params_warning["has_warnings"]
    )


def _validate_dangerous_operations(command, step=None):
    """Warn the user if a command has dangerous operations.

    :param command: A workflow step command to validate.
    :param step: The workflow step that contains the given command.
    """
    for operation in COMMAND_DANGEROUS_OPERATIONS:
        if operation in command:
            msg = 'Operation "{}" found in step "{}" might be dangerous.'
            if not step:
                msg = 'Operation "{}" might be dangerous.'
            display_message(
                msg.format(operation.strip(), step if step else None),
                msg_type="warning",
                indented=True,
            )
