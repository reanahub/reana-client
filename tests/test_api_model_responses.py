# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2026 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
"""REANA client API tests for responses unmarshalled into bravado models."""

import json
from importlib.resources import files
from types import SimpleNamespace

import pytest
from bravado_core.spec import Spec

from reana_client.api import client


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
            "start_workflow",
            lambda: client.start_workflow("wf", "token", {}),
        ),
    ],
)
def test_workflow_submission_responses_are_plain_dicts(monkeypatch, operation_id, call):
    """Model responses are returned as dicts callers can ``.get()`` from."""
    model = _workflow_submission_response(
        message="All workflows named wf successfully deleted.",
        workflow_name="wf",
    )
    monkeypatch.setattr(
        client,
        "current_rs_api_client",
        SimpleNamespace(api=SimpleNamespace(**{operation_id: _Operation(model)})),
    )

    response = call()

    assert isinstance(response, dict)
    assert response.get("message") == "All workflows named wf successfully deleted."
    assert response.get("validation_warnings") is None
