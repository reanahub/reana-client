# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2021, 2022, 2023, 2025 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""REANA client validation utilities."""

import sys
from typing import NoReturn, Union

import click

from reana_commons.validation.utils import validate_workflow_name


from reana_client.printer import display_message


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
