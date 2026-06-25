# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2026 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""Tests for containment-safe CWL bundle staging."""

import os

import pytest
import yaml
from unittest.mock import patch

from reana_client.cli.cwl_runner import _create_cwl_workflow, _stage_cwl_member


def test_stage_cwl_member_copies_regular_contained_file(tmp_path):
    """A regular file below basedir is copied under the same bundle path."""
    basedir = tmp_path / "project"
    bundle_dir = tmp_path / "bundle"
    source = basedir / "workflow" / "main.cwl"
    source.parent.mkdir(parents=True)
    bundle_dir.mkdir()
    source.write_text("class: Workflow\n")

    member = _stage_cwl_member(str(bundle_dir), str(basedir), "workflow/main.cwl")

    assert member == os.path.join("workflow", "main.cwl")
    assert (bundle_dir / "workflow" / "main.cwl").read_text() == source.read_text()


@pytest.mark.parametrize("location", ["../outside.cwl", "/tmp/outside.cwl"])
def test_stage_cwl_member_rejects_escaping_paths(tmp_path, location):
    """Absolute and parent-traversing locations cannot escape staging."""
    basedir = tmp_path / "project"
    bundle_dir = tmp_path / "bundle"
    basedir.mkdir()
    bundle_dir.mkdir()

    with pytest.raises(ValueError, match="CWL bundle"):
        _stage_cwl_member(str(bundle_dir), str(basedir), location)


def test_stage_cwl_member_rejects_symlink(tmp_path):
    """A dependency symlink is never followed into or outside the bundle."""
    basedir = tmp_path / "project"
    bundle_dir = tmp_path / "bundle"
    basedir.mkdir()
    bundle_dir.mkdir()
    outside = tmp_path / "outside.cwl"
    outside.write_text("class: CommandLineTool\n")
    (basedir / "linked.cwl").symlink_to(outside)

    with pytest.raises(ValueError, match="symlinked"):
        _stage_cwl_member(str(bundle_dir), str(basedir), "linked.cwl")


def test_create_cwl_workflow_declares_validation_scope(tmp_path):
    """CWL runner declares dependencies and uses the preferred parameter field."""
    basedir = tmp_path / "project"
    (basedir / "workflow").mkdir(parents=True)
    process = basedir / "workflow" / "main.cwl"
    tool = basedir / "workflow" / "tool.cwl"
    job = basedir / "job.yaml"
    process.write_text("$graph: []")
    tool.write_text("class: CommandLineTool")
    job.write_text("answer: 42")
    captured = {}

    def create(bundle_dir, name, access_token):
        with open(os.path.join(bundle_dir, "reana.yaml")) as specification:
            captured["specification"] = yaml.safe_load(specification)
        return {"workflow_id": "id", "workflow_name": name}

    dependencies = [
        {"location": "workflow/main.cwl"},
        {"location": "workflow/tool.cwl"},
    ]
    with patch(
        "reana_client.cli.cwl_runner.get_file_dependencies_obj",
        return_value={},
    ), patch("reana_client.cli.cwl_runner.findfiles", return_value=dependencies), patch(
        "reana_client.api.client.create_workflow_from_bundle_dir",
        side_effect=create,
    ):
        response, parameters = _create_cwl_workflow(
            str(process) + "#selected",
            str(job),
            str(basedir),
            "token",
        )

    assert response["workflow_name"] == "cwl-test"
    assert parameters == {"answer": 42}
    assert captured["specification"] == {
        "workflow": {
            "type": "cwl",
            "file": "workflow/main.cwl#selected",
            "files": ["workflow/tool.cwl"],
            "parameters": {"file": "job.yaml"},
        }
    }
