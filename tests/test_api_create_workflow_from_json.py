# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2026 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""Compatibility tests for the deprecated ``create_workflow_from_json()`` API."""

import io
import os
import zipfile
from unittest.mock import Mock

import pytest
import yaml

from reana_client.api import client as client_module


@pytest.fixture(autouse=True)
def server_url(monkeypatch):
    """The historical API requires a configured server URL."""
    monkeypatch.setenv("REANA_SERVER_URL", "https://reana.example.org")


@pytest.fixture()
def delegated(monkeypatch):
    """Capture the raw specification handed to the authoritative bundle path."""
    calls = []

    def create_workflow_from_bundle(reana_file, name, access_token):
        with open(reana_file) as specification:
            calls.append(
                {
                    "reana_file": reana_file,
                    "reana_yaml": yaml.safe_load(specification),
                    "name": name,
                    "access_token": access_token,
                }
            )
        return {"workflow_id": "id", "workflow_name": name}

    monkeypatch.setattr(
        client_module, "create_workflow_from_bundle", create_workflow_from_bundle
    )
    return calls


WORKFLOW_JSON = {
    "steps": [
        {
            "environment": "docker.io/library/busybox:1.36",
            "commands": ["echo hello"],
        }
    ]
}


def test_public_import_is_retained():
    """The documented Python API entry point remains importable."""
    from reana_client.api.client import create_workflow_from_json

    assert callable(create_workflow_from_json)


def test_documented_serial_call_delegates_to_the_bundle_path(delegated):
    """The documented inline serial call produces the expected raw mapping."""
    with pytest.deprecated_call():
        response = client_module.create_workflow_from_json(
            name="my-analysis",
            access_token="token",
            workflow_json=WORKFLOW_JSON,
            parameters={"files": ["file.txt"], "parameters": {"key": "value"}},
            outputs={"files": ["results.txt"]},
            workflow_engine="serial",
        )

    assert response == {"workflow_id": "id", "workflow_name": "my-analysis"}
    assert len(delegated) == 1
    call = delegated[0]
    assert call["name"] == "my-analysis"
    assert call["access_token"] == "token"
    assert call["reana_yaml"] == {
        "workflow": {"type": "serial", "specification": WORKFLOW_JSON},
        "inputs": {"files": ["file.txt"], "parameters": {"key": "value"}},
        "outputs": {"files": ["results.txt"]},
    }
    assert os.path.basename(call["reana_file"]) == "reana.yaml"


def test_translated_bundle_contains_only_the_specification(
    monkeypatch, arm_bundle_capability
):
    """The real gather/archive path uploads exactly the temporary reana.yaml."""
    captured = {}

    class Future:
        def result(self):
            _filename, stream = captured["bundle"]
            captured["archive"] = stream.read()
            return (
                {"workflow_id": "id", "workflow_name": "my-analysis"},
                Mock(status_code=201),
            )

    def create_operation(**kwargs):
        captured.update(kwargs)
        return Future()

    api_client = arm_bundle_capability(Mock())
    api_client.api.create_workflow.side_effect = create_operation
    monkeypatch.setattr(client_module, "current_rs_api_client", api_client)

    with pytest.deprecated_call():
        client_module.create_workflow_from_json(
            name="my-analysis",
            access_token="token",
            workflow_json=WORKFLOW_JSON,
            # Legacy data inputs must not become loader dependencies: with no
            # workflow.file they stay outside the validation scope, so the
            # bundle must not try to read a file that is not beside the
            # temporary specification.
            parameters={"files": ["nonexistent-input.txt"]},
            workflow_engine="serial",
        )

    with zipfile.ZipFile(io.BytesIO(captured["archive"])) as archive:
        assert archive.namelist() == ["reana.yaml"]
        bundled = yaml.safe_load(archive.read("reana.yaml"))
    assert bundled["workflow"] == {"type": "serial", "specification": WORKFLOW_JSON}
    assert bundled["inputs"] == {"files": ["nonexistent-input.txt"]}
    assert captured["workflow_name"] == "my-analysis"
    assert captured["access_token"] == "token"


def test_deprecation_warning_points_at_the_caller(delegated):
    """The warning is attributed to the caller, not to the client internals."""
    with pytest.warns(DeprecationWarning, match="create_workflow_from_bundle"):
        client_module.create_workflow_from_json(
            name="my-analysis",
            access_token="token",
            workflow_json=WORKFLOW_JSON,
            workflow_engine="serial",
        )


def test_temporary_specification_is_removed_on_success(delegated):
    """No temporary bundle directory survives a successful creation."""
    with pytest.deprecated_call():
        client_module.create_workflow_from_json(
            name="my-analysis",
            access_token="token",
            workflow_json=WORKFLOW_JSON,
            workflow_engine="serial",
        )

    reana_file = delegated[0]["reana_file"]
    assert not os.path.exists(reana_file)
    assert not os.path.exists(os.path.dirname(reana_file))


def test_temporary_specification_is_removed_on_failure(monkeypatch):
    """A failing delegation still cleans up the temporary bundle directory."""
    seen = {}

    def failing_create(reana_file, name, access_token):
        seen["reana_file"] = reana_file
        raise RuntimeError("server refused")

    monkeypatch.setattr(client_module, "create_workflow_from_bundle", failing_create)

    with pytest.deprecated_call(), pytest.raises(RuntimeError, match="server refused"):
        client_module.create_workflow_from_json(
            name="my-analysis",
            access_token="token",
            workflow_json=WORKFLOW_JSON,
            workflow_engine="serial",
        )

    assert not os.path.exists(os.path.dirname(seen["reana_file"]))


def test_default_yadage_call_fails_with_migration_guidance(delegated):
    """The historical default engine is no longer translatable."""
    with pytest.deprecated_call(), pytest.raises(ValueError) as failure:
        client_module.create_workflow_from_json(
            name="my-analysis",
            access_token="token",
            workflow_json=WORKFLOW_JSON,
        )

    message = str(failure.value)
    assert "workflow_engine='yadage'" in message
    assert "workflow.files/workflow.directories" in message
    assert "create_workflow_from_bundle()" in message
    assert delegated == []


def test_workflow_file_overrides_workflow_json_for_error_selection(delegated):
    """``workflow_file`` keeps precedence and fails instead of submitting a dict."""
    with pytest.deprecated_call(), pytest.raises(ValueError) as failure:
        client_module.create_workflow_from_json(
            name="my-analysis",
            access_token="token",
            workflow_json=WORKFLOW_JSON,
            workflow_file="workflow/Snakefile",
            workflow_engine="serial",
        )

    message = str(failure.value)
    assert "workflow_file='workflow/Snakefile'" in message
    assert delegated == []


@pytest.mark.parametrize("workflow_engine", ["cwl", "snakemake", "yadage"])
def test_non_serial_engines_fail_before_contacting_the_server(
    delegated, workflow_engine
):
    """Engines whose loader needs files on disk are refused locally."""
    with pytest.deprecated_call(), pytest.raises(ValueError):
        client_module.create_workflow_from_json(
            name="my-analysis",
            access_token="token",
            workflow_json=WORKFLOW_JSON,
            workflow_engine=workflow_engine,
        )

    assert delegated == []


def test_unknown_engine_keeps_the_historical_error(delegated):
    """An unsupported engine name still reports the known-engines list."""
    with pytest.deprecated_call(), pytest.raises(Exception, match="not found"):
        client_module.create_workflow_from_json(
            name="my-analysis",
            access_token="token",
            workflow_json=WORKFLOW_JSON,
            workflow_engine="nextflow",
        )

    assert delegated == []


def test_missing_access_token_is_reported(delegated):
    """The historical access-token validation is preserved."""
    with pytest.deprecated_call(), pytest.raises(Exception, match="access token"):
        client_module.create_workflow_from_json(
            name="my-analysis",
            access_token="",
            workflow_json=WORKFLOW_JSON,
            workflow_engine="serial",
        )

    assert delegated == []


def test_uuid_workflow_name_is_rejected(delegated):
    """A UUIDv4 name stays disallowed, as before."""
    with pytest.deprecated_call(), pytest.raises(ValueError, match="UUIDv4"):
        client_module.create_workflow_from_json(
            name="6cd613eb-f2fb-411b-9601-c89599925759",
            access_token="token",
            workflow_json=WORKFLOW_JSON,
            workflow_engine="serial",
        )

    assert delegated == []


def test_non_json_native_values_are_normalised(delegated):
    """Tuples from caller code survive instead of breaking the YAML dump."""
    with pytest.deprecated_call():
        client_module.create_workflow_from_json(
            name="my-analysis",
            access_token="token",
            workflow_json={"steps": ({"commands": ("echo hello",)},)},
            workflow_engine="serial",
        )

    assert delegated[0]["reana_yaml"]["workflow"]["specification"] == {
        "steps": [{"commands": ["echo hello"]}]
    }
