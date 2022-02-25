# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2022 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""REANA client workspace validation."""

import sys
from typing import List, Optional

from reana_commons.errors import REANAValidationError
from reana_commons.validation.utils import validate_workspace

from reana_client.printer import display_message


def _validate_workspace(
    root_path: str, available_workspaces: Optional[List[str]]
) -> None:
    """Validate workspace in REANA specification file.

    :param root_path: workspace root path to be validated.
    :param available_workspaces: a list of the available workspaces.

    :raises ValidationError: Given workspace in REANA spec file does not validate against
        allowed workspaces.
    """
    if root_path:
        display_message(
            "Verifying workspace in REANA specification file...", msg_type="info",
        )
        try:
            validate_workspace(root_path, available_workspaces)
            display_message(
                "Workflow workspace appears valid.", msg_type="success", indented=True,
            )
        except REANAValidationError as e:
            display_message(e.message, msg_type="error")
            sys.exit(1)
