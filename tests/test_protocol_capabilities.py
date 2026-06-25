# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2026 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""Tests for refusing servers that predate the specification-bundle protocol."""

from unittest.mock import Mock

import pytest

from reana_client.api import client as client_module
from reana_client.api.client import (
    create_workflow_from_bundle,
    create_workflow_from_bundle_dir,
    restart_workflow,
    start_workflow,
    validate_workflow_spec_bundle,
)


@pytest.fixture()
def serial_specification(tmp_path):
    """Write a minimal inline serial specification bundle source."""
    specification = tmp_path / "reana.yaml"
    specification.write_text(
        "workflow:\n  type: serial\n  specification:\n    steps: []\n"
    )
    return specification


def _legacy_ping_client():
    """Return a mock API client whose ping omits ``api_capabilities``."""
    api_client = Mock()
    api_client.api.ping.return_value.result.return_value = (
        {"message": "OK", "status": "200", "reana_server_version": "0.9.4"},
        Mock(status_code=200),
    )
    return api_client


@pytest.mark.parametrize(
    "call",
    [
        pytest.param(
            lambda spec: create_workflow_from_bundle(str(spec), "test", "token"),
            id="create",
        ),
        pytest.param(
            lambda spec: create_workflow_from_bundle_dir(
                str(spec.parent), "test", "token"
            ),
            id="create-from-dir",
        ),
        pytest.param(
            lambda spec: validate_workflow_spec_bundle(str(spec), "token"),
            id="validate",
        ),
        pytest.param(
            lambda spec: restart_workflow("workflow.1", str(spec), "token", {}),
            id="replacement-restart",
        ),
    ],
)
def test_legacy_server_is_refused_before_any_upload(
    monkeypatch, serial_specification, call
):
    """A released server is refused before a bundle is built or uploaded."""
    api_client = _legacy_ping_client()
    monkeypatch.setattr(client_module, "current_rs_api_client", api_client)

    with pytest.raises(RuntimeError) as failure:
        call(serial_specification)

    message = str(failure.value)
    assert "workflow-specification-bundles-v1" in message
    assert "upgrade the REANA cluster" in message
    # The server version is surfaced so the user can tell which side is old.
    assert "0.9.4" in message
    api_client.api.create_workflow.assert_not_called()
    api_client.api.validate_workflow_specification.assert_not_called()
    api_client.api.restart_workflow.assert_not_called()


def test_advertised_capability_allows_the_bundle_upload(
    monkeypatch, serial_specification, arm_bundle_capability
):
    """A capable server proceeds straight through to the generated operation."""
    api_client = arm_bundle_capability(Mock())
    api_client.api.create_workflow.return_value.result.return_value = (
        {"workflow_id": "id", "workflow_name": "test.1"},
        Mock(status_code=201),
    )
    monkeypatch.setattr(client_module, "current_rs_api_client", api_client)

    response = create_workflow_from_bundle(str(serial_specification), "test", "token")

    assert response == {"workflow_id": "id", "workflow_name": "test.1"}
    api_client.api.create_workflow.assert_called_once()


def test_ping_transport_failure_is_surfaced_without_uploading(
    monkeypatch, serial_specification
):
    """A ping that cannot complete fails the command instead of uploading."""
    api_client = Mock()
    api_client.api.ping.return_value.result.side_effect = ConnectionError("no route")
    monkeypatch.setattr(client_module, "current_rs_api_client", api_client)

    with pytest.raises(ConnectionError):
        create_workflow_from_bundle(str(serial_specification), "test", "token")

    api_client.api.create_workflow.assert_not_called()


def test_plain_start_does_not_require_the_capability(monkeypatch):
    """Ordinary start stays on the compatible operation and never pings."""
    api_client = Mock()
    api_client.api.start_workflow.return_value.result.return_value = (
        {"status": "queued"},
        Mock(status_code=200),
    )
    monkeypatch.setattr(client_module, "current_rs_api_client", api_client)

    assert start_workflow("workflow.1", "token", {}) == {"status": "queued"}
    api_client.api.ping.assert_not_called()


def test_restart_without_replacement_does_not_require_the_capability(monkeypatch):
    """Restart without a replacement uses /start and stays compatible."""
    api_client = Mock()
    api_client.api.start_workflow.return_value.result.return_value = (
        {"status": "queued"},
        Mock(status_code=200),
    )
    monkeypatch.setattr(client_module, "current_rs_api_client", api_client)

    # This is exactly what ``reana-client restart`` calls without ``--file``.
    assert start_workflow("workflow.1", "token", {"restart": True}) == {
        "status": "queued"
    }
    api_client.api.ping.assert_not_called()
