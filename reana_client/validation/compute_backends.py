# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2022 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""REANA client compute backend validation."""

import sys
from typing import Dict, List, Optional

from reana_commons.errors import REANAValidationError
from reana_commons.validation.compute_backends import build_compute_backends_validator

from reana_client.printer import display_message


def validate_compute_backends(
    reana_yaml: Dict, supported_backends: Optional[List[str]]
) -> None:
    """Validate compute backends in REANA specification file according to workflow type.

    :param reana_yaml: dictionary which represents REANA specification file.
    :param supported_backends: a list of the supported compute backends.
    """

    validator = build_compute_backends_validator(reana_yaml, supported_backends)
    try:
        validator.validate()
    except REANAValidationError as e:
        display_message(
            str(e), msg_type="error", indented=True,
        )
        sys.exit(1)
    display_message(
        "Workflow compute backends appear to be valid.",
        msg_type="success",
        indented=True,
    )
