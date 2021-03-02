# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2021 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""REANA client validation functions."""

import re
from collections import defaultdict
from itertools import chain

import click


def validate_parameters(workflow_type, reana_yaml):
    """Validate the presence of input parameters in workflow step commands and viceversa.

    :param workflow_type: A supported workflow specification type.
    :param reana_yaml: REANA YAML specification.
    """
    validate = {
        "yadage": None,
        "cwl": None,
        "serial": validate_serial_parameters,
    }
    """Dictionary to extend with new workflow specification loaders."""

    return validate[workflow_type](reana_yaml)


def validate_serial_parameters(reana_yaml):
    """Validate input parameters for Serial workflows.

    :param reana_yaml: REANA YAML specification.
    """
    input_parameters = set(reana_yaml["inputs"].get("parameters", {}).keys())

    param_steps_mapping = defaultdict(list)
    for step in reana_yaml["workflow"]["specification"].get("steps", []):
        for command in step["commands"]:
            cmd_params = re.findall(r".*?\${(.*?)}.*?", command)
            for cmd_param in cmd_params:
                param_steps_mapping[cmd_param].append(step.get("name", "Unnamed"))

    command_parameters = set(param_steps_mapping.keys())

    for param in input_parameters.difference(command_parameters):
        click.secho(
            '==> WARNING: Input parameter "{}" is not being used.'.format(param),
            fg="yellow",
        )

    for param in command_parameters.difference(input_parameters):
        steps_used = param_steps_mapping[param]
        click.secho(
            '==> WARNING: Parameter "{param}" found on step{s} "{steps}" is not defined in inputs parameters.'.format(
                param=param,
                steps=", ".join(steps_used),
                s="s" if len(steps_used) > 1 else "",
            ),
            fg="yellow",
        )
