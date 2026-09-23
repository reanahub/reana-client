# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2026 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
"""REANA client API tests for responses unmarshalled into bravado models."""

import json
import sys
from types import SimpleNamespace

import pytest
from bravado_core.spec import Spec
from mock import Mock

from reana_client.api import client

# Use importlib.resources for Python 3.9+ or importlib_resources backport for 3.8
if sys.version_info >= (3, 9):
    from importlib.resources import files
else:
    from importlib_resources import files

VALIDATION_WARNINGS = [
    {
        "code": "unused_parameter",
        "message": 'Parameter "foo" is defined but not used.',
        "path": "inputs.parameters.foo",
    }
]


def _workflow_submission_response(**fields):
    """Build the model bravado returns for ``WorkflowSubmissionResponse``."""
    spec_file = files("reana_commons") / "openapi_specifications" / "reana_server.json"
    spec = Spec.from_dict(json.loads(spec_file.read_text()))
    return spec.definitions["WorkflowSubmissionResponse"](**fields)


class _Operation:
    """Bravado operation double returning a fixed result."""

    def __init__(self, response):
        """Initialise the operation double."""
        self.response = response

    def __call__(self, **kwargs):
        """Accept any operation arguments."""
        return self

    def result(self):
        """Return the operation result."""
        return self.response, SimpleNamespace(status_code=200)


@pytest.mark.parametrize(
    "operation_id, call",
    [
        (
            "set_workflow_status",
            lambda: client.delete_workflow("wf", True, True, "token"),
        ),
        (
            "set_workflow_status",
            lambda: client.stop_workflow("wf", False, "token"),
        ),
        (
            "start_workflow",
            lambda: client.start_workflow("wf", "token", {}),
        ),
    ],
)
@pytest.mark.parametrize("validation_warnings", [None, VALIDATION_WARNINGS])
def test_workflow_submission_responses_are_plain_dicts(
    monkeypatch, operation_id, call, validation_warnings
):
    """Model responses are returned as dicts callers can ``.get()`` from."""
    model = _workflow_submission_response(
        message="Workflow wf updated.",
        workflow_name="wf",
        validation_warnings=validation_warnings,
    )
    monkeypatch.setattr(
        client,
        "current_rs_api_client",
        SimpleNamespace(api=SimpleNamespace(**{operation_id: _Operation(model)})),
    )

    response = call()

    assert isinstance(response, dict)
    assert response.get("message") == "Workflow wf updated."
    assert response.get("validation_warnings") == validation_warnings


def test_restart_with_replacement_returns_plain_dict(
    monkeypatch, tmp_path, arm_bundle_capability
):
    """Replacement restart converts its model response to a dict."""
    replacement = tmp_path / "replacement.yaml"
    replacement.write_bytes(b"workflow: {type: serial}\n")
    model = _workflow_submission_response(
        message="Workflow wf.2 queued.",
        workflow_name="wf",
        run_number="2",
        validation_warnings=VALIDATION_WARNINGS,
    )
    api_client = arm_bundle_capability(Mock())
    api_client.api.restart_workflow = _Operation(model)
    monkeypatch.setattr(client, "current_rs_api_client", api_client)

    response = client.restart_workflow(
        "wf",
        str(replacement),
        "token",
        {"input_parameters": {}, "operational_options": {}},
    )

    assert isinstance(response, dict)
    assert response.get("message") == "Workflow wf.2 queued."
    assert response.get("validation_warnings") == VALIDATION_WARNINGS
