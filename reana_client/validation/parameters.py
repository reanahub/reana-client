# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2021, 2022 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""REANA client parameters validation."""

import sys
from typing import Dict

from reana_commons.validation.parameters import build_parameters_validator
from reana_commons.errors import REANAValidationError

from reana_client.printer import display_message


def validate_parameters(reana_yaml: Dict) -> None:
    """Validate the presence of input parameters in workflow step commands and viceversa.

    :param reana_yaml: REANA YAML specification.
    """

    validator = build_parameters_validator(reana_yaml)
    try:
        validator.validate_parameters()
        display_messages(validator)
    except REANAValidationError as e:
        display_messages(validator)
        display_message(
            str(e),
            msg_type="error",
            indented=True,
        )
        sys.exit(1)


def display_messages(validator) -> None:
    """Display messages in console."""
    _display_reana_params_warnings(validator)
    _display_workflow_params_warnings(validator)
    _display_operations_warnings(validator)


def _display_reana_params_warnings(validator) -> None:
    """Display REANA specification parameter validation warnings."""
    _display_messages_type(
        info_msg="Verifying REANA specification parameters... ",
        success_msg="REANA specification parameters appear valid.",
        messages=validator.reana_params_warnings,
    )


def _display_workflow_params_warnings(validator) -> None:
    """Display REANA workflow parameter and command validation warnings."""
    _display_messages_type(
        info_msg="Verifying workflow parameters and commands... ",
        success_msg="Workflow parameters and commands appear valid.",
        messages=validator.workflow_params_warnings,
    )


def _display_operations_warnings(validator) -> None:
    """Display dangerous workflow operation warnings."""
    _display_messages_type(
        info_msg="Verifying dangerous workflow operations... ",
        success_msg="Workflow operations appear valid.",
        messages=validator.operations_warnings,
    )


def _display_messages_type(info_msg, success_msg, messages) -> None:
    display_message(info_msg, msg_type="info")
    for msg in messages:
        display_message(msg["message"], msg_type=msg["type"], indented=True)
    if not messages:
        display_message(success_msg, msg_type="success", indented=True)
