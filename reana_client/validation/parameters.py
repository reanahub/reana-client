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
from reana_client.printer import display_message
from reana_client.errors import ParameterValidationError


def validate_parameters(workflow_type, reana_yaml):
    """Validate the presence of input parameters in workflow step commands and viceversa.

    :param workflow_type: A supported workflow specification type.
    :param reana_yaml: REANA YAML specification.
    """

    def build_validator(workflow_type, reana_yaml):
        if workflow_type == "serial":
            return SerialParameterValidator(reana_yaml)
        if workflow_type == "yadage":
            return YadageParameterValidator(reana_yaml)
        if workflow_type == "cwl":
            return CWLParameterValidator(reana_yaml)
        if workflow_type == "snakemake":
            return SnakemakeParameterValidator(reana_yaml)

    validator = build_validator(workflow_type, reana_yaml)
    validator.validate()
    validator.display_messages()


class ParameterValidatorBase:
    """REANA workflow parameter validation base class."""

    def __init__(self, reana_yaml):
        """Validate parameters in REANA workflow.

        :param reana_yaml: REANA YAML specification.
        """
        self.reana_yaml = reana_yaml
        self.specification = reana_yaml.get("workflow", {}).get("specification", {})
        self.input_parameters = set(
            reana_yaml.get("inputs", {}).get("parameters", {}).keys()
        )
        self.operations_warnings = []
        self.reana_params_warnings = []
        self.workflow_params_warnings = []

        self.steps = self.parse_specification()
        self._initial_parameter_validation()

    def parse_specification(self):
        """Parse REANA workflow specification tree."""
        raise NotImplementedError

    def validate_parameters(self):
        """Validate parameters in REANA workflow."""
        raise NotImplementedError

    def validate(self):
        """Validate REANA workflow parameters."""
        try:
            self.validate_parameters()
        except ParameterValidationError as e:
            self.display_messages()
            display_message(
                str(e), msg_type="error", indented=True,
            )
            sys.exit(1)

    def display_messages(self):
        """Display messages in console."""
        self._display_reana_params_warnings()
        self._display_workflow_params_warnings()
        self._display_operations_warnings()

    def _display_reana_params_warnings(self):
        """Display REANA specification parameter validation warnings."""
        self._display_messages_type(
            info_msg="Verifying REANA specification parameters... ",
            success_msg="REANA specification parameters appear valid.",
            messages=self.reana_params_warnings,
        )

    def _display_workflow_params_warnings(self):
        """Display REANA workflow parameter and command validation warnings."""
        self._display_messages_type(
            info_msg="Verifying workflow parameters and commands... ",
            success_msg="Workflow parameters and commands appear valid.",
            messages=self.workflow_params_warnings,
        )

    def _display_operations_warnings(self):
        """Display dangerous workflow operation warnings."""
        self._display_messages_type(
            info_msg="Verifying dangerous workflow operations... ",
            success_msg="Workflow operations appear valid.",
            messages=self.operations_warnings,
        )

    def _display_messages_type(self, info_msg, success_msg, messages):
        display_message(info_msg, msg_type="info")
        for msg in messages:
            display_message(msg["message"], msg_type=msg["type"], indented=True)
        if not messages:
            display_message(success_msg, msg_type="success", indented=True)

    def _initial_parameter_validation(self):
        if "inputs" not in self.reana_yaml:
            self.reana_params_warnings.append(
                {
                    "type": "warning",
                    "message": 'Workflow "inputs" are missing in the REANA specification.',
                }
            )

    def _validate_dangerous_operations(self, commands, step=None):
        """Validate if commands have dangerous operations.

        :param commands: A workflow step command list to validate.
        :param step: The workflow step that contains the given command.
        """
        for command in commands:
            for operation in COMMAND_DANGEROUS_OPERATIONS:
                if operation in str(command):
                    msg = 'Operation "{}" found in step "{}" might be dangerous.'
                    if not step:
                        msg = 'Operation "{}" might be dangerous.'
                    self.operations_warnings.append(
                        {
                            "type": "warning",
                            "message": msg.format(
                                operation.strip(), step if step else None
                            ),
                        }
                    )

    def _validate_not_used_parameters(
        self, workflow_parameters, command_parameters, type_="REANA"
    ):
        """Validate defined workflow parameters which are not being used.

        :param workflow_parameters: Set of parameters in workflow definition.
        :param command_parameters: Set of parameters used inside workflow.
        :param type: Type of workflow parameters, e.g. REANA for input parameters, Yadage
                    for parameters defined in Yadage spec.
        """

        unused_parameters = workflow_parameters.difference(command_parameters)
        for parameter in unused_parameters:
            self.reana_params_warnings.append(
                {
                    "type": "warning",
                    "message": '{} input parameter "{}" does not seem to be used.'.format(
                        type_, parameter
                    ),
                }
            )

    def _validate_not_defined_parameters(
        self, cmd_param_steps_mapping, workflow_parameters, workflow_type
    ):
        """Validate command parameters which are missing in workflow definition.

        :param cmd_param_steps_mapping: Mapping between command parameters and its step.
        :param workflow_parameters: Set of parameters in workflow definition.
        :param workflow_type: Workflow type being checked.
        """
        command_parameters = set(cmd_param_steps_mapping.keys())
        command_parameters_not_defined = command_parameters.difference(
            workflow_parameters
        )
        for parameter in command_parameters_not_defined:
            steps_used = cmd_param_steps_mapping[parameter]
            self.workflow_params_warnings.append(
                {
                    "type": "warning",
                    "message": '{type} parameter "{parameter}" found on step{s} "{steps}" is not defined in input parameters.'.format(
                        type=workflow_type.capitalize(),
                        parameter=parameter,
                        steps=", ".join(steps_used),
                        s="s" if len(steps_used) > 1 else "",
                    ),
                }
            )

    def _validate_misused_parameters_in_steps(
        self, param_steps_mapping, cmd_param_steps_mapping, workflow_type
    ):
        """Validate not used command parameters and not defined input parameters after checking each step of workflow definition.

        :param param_steps_mapping: Mapping between parameters in workflow definition and its step.
        :param cmd_param_steps_mapping: Mapping between command parameters and its step.
        :param workflow_type: Workflow type being checked.
        """
        command_parameters = set(cmd_param_steps_mapping.keys())
        workflow_params = set(param_steps_mapping.keys())
        for parameter in command_parameters:
            cmd_param_steps = cmd_param_steps_mapping[parameter]
            param_steps = param_steps_mapping[parameter]
            steps_diff = cmd_param_steps.difference(param_steps)
            if steps_diff:
                self.workflow_params_warnings.append(
                    {
                        "type": "warning",
                        "message": '{type} parameter "{parameter}" found on step{s} "{steps}" is not defined in input parameters.'.format(
                            type=workflow_type.capitalize(),
                            parameter=parameter,
                            steps=", ".join(steps_diff),
                            s="s" if len(steps_diff) > 1 else "",
                        ),
                    }
                )
        for parameter in workflow_params:
            param_steps = param_steps_mapping[parameter]
            cmd_param_steps = cmd_param_steps_mapping[parameter]
            steps_diff = param_steps.difference(cmd_param_steps)
            if steps_diff:
                self.workflow_params_warnings.append(
                    {
                        "type": "warning",
                        "message": '{type} input parameter "{parameter}" found on step{s} "{steps}" does not seem to be used.'.format(
                            type=workflow_type.capitalize(),
                            parameter=parameter,
                            steps=", ".join(steps_diff),
                            s="s" if len(steps_diff) > 1 else "",
                        ),
                    }
                )


class SerialParameterValidator(ParameterValidatorBase):
    """REANA serial workflow parameter validation."""

    def validate_parameters(self):
        """Validate input parameters for Serial workflows."""
        cmd_param_steps_mapping = defaultdict(set)
        for step in self.steps:
            # validate dangerous operations
            self._validate_dangerous_operations(step["commands"], step=step["name"])
            # Map command params with steps
            for command in step["command_params"]:
                cmd_param_steps_mapping[command].add(step["name"])

        command_parameters = set(cmd_param_steps_mapping.keys())

        # REANA input parameters validation
        self._validate_not_used_parameters(self.input_parameters, command_parameters)

        # Serial command parameters validation
        self._validate_not_defined_parameters(
            cmd_param_steps_mapping, self.input_parameters, "serial"
        )

    def parse_specification(self):
        """Parse serial workflow tree."""

        def parse_command(command):
            return re.findall(r".*?\${(.*?)}.*?", command)

        def parse_commands(commands):
            cmd_list = set()
            for command in commands:
                for cmd in parse_command(command):
                    cmd_list.add(cmd)
            return cmd_list

        steps = []
        for idx, step in enumerate(self.specification.get("steps", [])):
            commands = step["commands"]
            steps.append(
                {
                    "name": step.get("name", str(idx)),
                    "commands": commands,
                    "input_params": [],
                    "command_params": parse_commands(commands),
                }
            )
        return steps


class YadageParameterValidator(ParameterValidatorBase):
    """REANA Yadage workflow parameter validation."""

    def validate_parameters(self):
        """Validate parameters for Yadage workflows."""

        param_steps_mapping = defaultdict(set)
        cmd_param_steps_mapping = defaultdict(set)

        for step in self.steps:
            # Validate dangerous operations
            self._validate_dangerous_operations(step["commands"], step=step["name"])
            # Map input params with steps
            for command in step["input_params"]:
                param_steps_mapping[command].add(step["name"])

            # Map command params with steps
            for command in step["command_params"]:
                cmd_param_steps_mapping[command].add(step["name"])

        workflow_params = set(param_steps_mapping.keys())

        # REANA input parameters validation
        self._validate_not_used_parameters(self.input_parameters, workflow_params)

        # Yadage command and input parameters validation
        self._validate_misused_parameters_in_steps(
            param_steps_mapping, cmd_param_steps_mapping, "Yadage"
        )

    def parse_specification(self):
        """Parse Yadage workflow tree."""

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
            return set(parse_command(str(step_value)))

        def get_publisher_definitions(step, step_key, step_val):
            """Save publisher definitions as command params."""
            params = set()
            if step == "publisher":
                command_params = {
                    "publish": lambda: step_val.keys(),
                    "outputkey": lambda: [step_val],
                }.get(step_key, lambda: [])()
                for command_param in command_params:
                    params.add(command_param)
            return params

        def parse_stage(stage):
            stage_name = stage["name"]
            input_params = set()
            command_params = set()
            commands = []

            # Extract defined stage input params
            if "step" in stage["scheduler"].keys():
                for param in stage["scheduler"]["parameters"]:
                    input_params.add(param["key"])

            # Extract command params used in stage steps
            step = stage["scheduler"].get("step", {})
            for step_key in step.keys():
                for substep_key, substep_val in step[step_key].items():
                    # Parse publisher definitions
                    command_params.update(
                        get_publisher_definitions(step_key, substep_key, substep_val)
                    )
                    # Extract commands to list
                    if substep_key in ["script", "cmd"]:
                        commands.append(substep_val)

                    # Parse command params
                    command_params.update(parse_command_params(substep_val))

            return {
                "name": stage_name,
                "commands": commands,
                "input_params": input_params,
                "command_params": command_params,
            }

        def parse_stages(stages):
            steps = []
            for stage in stages:
                # Handle nested stages
                if "workflow" in stage["scheduler"]:
                    nested_stages = stage["scheduler"]["workflow"].get("stages", [])
                    steps += parse_stages(nested_stages)
                # Parse stage
                steps.append(parse_stage(stage))
            return steps

        return parse_stages(self.specification["stages"])


class CWLParameterValidator(ParameterValidatorBase):
    """REANA CWL workflow parameter validation."""

    def display_messages(self):
        """Display CWL workflow warnings in console."""
        self._display_operations_warnings()

    def parse_specification(self):
        """Parse CWL workflow tree."""
        pass

    def validate_parameters(self):
        """Validate input parameters for CWL workflows."""

        def _check_dangerous_operations(workflow):
            """Check for "baseCommand" and "arguments" in workflow.

            If these keys are found, validate if they have dangerous operations.
            """
            cmd_keys = ["baseCommand", "arguments"]
            for cmd_key in cmd_keys:
                if cmd_key in workflow:
                    commands = (
                        workflow[cmd_key]
                        if isinstance(workflow[cmd_key], list)
                        else [workflow[cmd_key]]
                    )
                    self._validate_dangerous_operations(
                        commands, step=workflow.get("id")
                    )

        from reana_client.utils import run_command

        cwl_main_spec_path = self.reana_yaml["workflow"].get("file")
        if os.path.exists(cwl_main_spec_path):
            run_command(
                "cwltool --validate --strict {}".format(cwl_main_spec_path),
                display=False,
                return_output=True,
                stderr_output=True,
            )
        else:
            raise ParameterValidationError(
                "Workflow path {} is not valid.".format(cwl_main_spec_path)
            )

        workflow = self.specification.get("$graph", self.specification)

        if isinstance(workflow, dict):
            _check_dangerous_operations(workflow)
        elif isinstance(workflow, list):
            for wf in workflow:
                _check_dangerous_operations(wf)


class SnakemakeParameterValidator(ParameterValidatorBase):
    """REANA Snakemake workflow parameter validation."""

    def validate_parameters(self):
        """Validate parameters for Snakemake workflows."""
        param_steps_mapping = defaultdict(set)
        cmd_param_steps_mapping = defaultdict(set)
        for step in self.steps:
            # validate dangerous operations
            self._validate_dangerous_operations(step["commands"], step=step["name"])
            # Map input params with steps
            for command in step["input_params"]:
                param_steps_mapping[command].add(step["name"])

            # Map command params with steps
            for command in step["command_params"]:
                cmd_param_steps_mapping[command].add(step["name"])

        # We skip REANA input parameter validation as we set these parameters via
        # `configfile`, so it's possible to assign the input parameters to Snakemake
        # parameters named differently, thus causing false positives.
        # E.g. `foo=config["bar"]` would warn that `bar` is not being used as we can't
        # guess which config variables are being used. We only have access to Snakemake
        # inputs, outputs and params names.

        # Snakemake command and input parameters validation
        self._validate_misused_parameters_in_steps(
            param_steps_mapping, cmd_param_steps_mapping, "Snakemake"
        )

    def parse_specification(self):
        """Parse Snakemake workflow tree."""

        def parse_command(command):
            return re.findall(r".*?{(?:params|input|output)\.(.*?)}.*?", command)

        def parse_commands(commands):
            cmd_list = set()
            for command in commands:
                for cmd in parse_command(command):
                    cmd_list.add(cmd)
            return cmd_list

        steps = []
        for idx, step in enumerate(self.specification.get("steps", [])):
            commands = step["commands"]
            steps.append(
                {
                    "name": step.get("name", str(idx)),
                    "commands": commands,
                    "input_params": set(
                        [
                            *step.get("params", {}).keys(),
                            *step.get("inputs", {}).keys(),
                            *step.get("outputs", {}).keys(),
                        ]
                    ),
                    "command_params": parse_commands(commands),
                }
            )
        return steps
