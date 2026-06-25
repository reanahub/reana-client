# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2026 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""Tests for raw specification bundle assembly."""

import os

import pytest

from reana_client.api.client import _gather_spec_members


def test_gather_spec_members_workflow_subtree(tmp_path):
    """A workflow file in a sub-directory pulls in its whole sub-tree.

    Co-located includes/imports are bundled, generated artifacts are dropped,
    and unrelated input data / noise outside the sub-tree is left out.
    """
    reana_yaml = tmp_path / "reana.yaml"
    reana_yaml.write_text("workflow:\n  type: snakemake\n  file: workflow/Snakefile\n")
    workflow = tmp_path / "workflow"
    (workflow / "rules").mkdir(parents=True)
    (workflow / "Snakefile").write_text('include: "rules/common.smk"\n')
    (workflow / "rules" / "common.smk").write_text("rule all:\n  shell: 'true'\n")
    (workflow / "__pycache__").mkdir()
    (workflow / "__pycache__" / "x.pyc").write_bytes(b"pyc")
    (workflow / ".coverage").write_text("coverage")
    # Unrelated input data / noise outside the workflow sub-tree must be left out.
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "big.csv").write_text("1,2,3\n")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "lib.py").write_text("x")

    members = _gather_spec_members(str(reana_yaml))

    assert set(members) == {
        "reana.yaml",
        "workflow/Snakefile",
        "workflow/rules/common.smk",
    }


def test_gather_spec_members_serial_bundles_only_spec(tmp_path):
    """A serial workflow has its spec inline, so only reana.yaml is bundled.

    Referenced code/data is uploaded separately as input data, not as part of
    the specification bundle.
    """
    reana_yaml = tmp_path / "myreana.yaml"
    reana_yaml.write_text("workflow:\n  type: serial\n")
    (tmp_path / "analysis.py").write_text("print('ok')\n")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "names.txt").write_text("alice\n")

    members = _gather_spec_members(str(reana_yaml))

    assert set(members) == {"reana.yaml"}
    assert members["reana.yaml"] == str(reana_yaml)


def test_gather_spec_members_includes_parameter_input_file(tmp_path):
    """inputs.parameters.input is bundled even outside the workflow sub-tree."""
    reana_yaml = tmp_path / "reana.yaml"
    reana_yaml.write_text(
        "inputs:\n"
        "  parameters:\n"
        "    input: config/params.yaml\n"
        "workflow:\n"
        "  type: cwl\n"
        "  file: workflow/main.cwl\n"
    )
    (tmp_path / "workflow").mkdir()
    (tmp_path / "workflow" / "main.cwl").write_text("cwlVersion: v1.0\n")
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "params.yaml").write_text("x: 1\n")

    members = _gather_spec_members(str(reana_yaml))

    assert set(members) == {"reana.yaml", "workflow/main.cwl", "config/params.yaml"}


def test_gather_spec_members_top_level_workflow_file(tmp_path):
    """A top-level workflow file is bundled on its own, not the whole directory."""
    reana_yaml = tmp_path / "reana.yaml"
    reana_yaml.write_text("workflow:\n  type: snakemake\n  file: Snakefile\n")
    (tmp_path / "Snakefile").write_text("rule all:\n  shell: 'true'\n")
    (tmp_path / "unrelated.txt").write_text("noise\n")

    members = _gather_spec_members(str(reana_yaml))

    assert set(members) == {"reana.yaml", "Snakefile"}


def test_gather_spec_members_selected_spec_is_canonical(tmp_path):
    """The selected spec is uploaded as reana.yaml even when siblings exist.

    Regression test: directories such as reana-demo-helloworld ship several
    spec files (reana.yaml, reana-snakemake.yaml, ...). Selecting a non-default
    one must not be clobbered by the sibling reana.yaml, otherwise the server
    would validate the wrong (and likely always-valid) specification.
    """
    (tmp_path / "reana.yaml").write_text("workflow:\n  type: serial\n")
    snakemake = tmp_path / "reana-snakemake.yaml"
    snakemake.write_text("workflow:\n  type: snakemake\n  file: Snakefile\n")
    (tmp_path / "Snakefile").write_text("rule all:\n  shell: 'true'\n")

    members = _gather_spec_members(str(snakemake))

    # The canonical member is the selected snakemake spec, not the serial one.
    assert members["reana.yaml"] == str(snakemake)
    # The sibling reana.yaml is not smuggled in under any name.
    assert str(tmp_path / "reana.yaml") not in members.values()
    assert "Snakefile" in members


def test_gather_spec_members_malformed_spec_uploads_canonical_only(tmp_path):
    """A malformed spec is still uploaded so the server reports the real error."""
    reana_yaml = tmp_path / "reana.yaml"
    reana_yaml.write_text("workflow: : : not yaml\n")

    members = _gather_spec_members(str(reana_yaml))

    assert set(members) == {"reana.yaml"}
    assert members["reana.yaml"] == str(reana_yaml)


@pytest.mark.parametrize("escaping", ["../secret.txt", "/etc/passwd"])
def test_gather_spec_members_does_not_read_outside_spec_dir(tmp_path, escaping):
    """A workflow.file escaping the spec directory is never bundled (SNDBX-04).

    A relative ``..`` or absolute path must not be read or walked: only the
    canonical reana.yaml is uploaded, and no out-of-tree file is transmitted.
    """
    project = tmp_path / "project"
    project.mkdir()
    # A secret sitting just outside the spec directory.
    (tmp_path / "secret.txt").write_text("top secret\n")
    reana_yaml = project / "reana.yaml"
    reana_yaml.write_text("workflow:\n  type: snakemake\n  file: {}\n".format(escaping))

    members = _gather_spec_members(str(reana_yaml))

    assert set(members) == {"reana.yaml"}
    assert all("secret" not in m for m in members)
    assert str(tmp_path / "secret.txt") not in members.values()


def test_gather_spec_members_skips_symlinked_workflow_file(tmp_path):
    """A symlinked workflow file (pointing outside) is not followed/bundled."""
    outside = tmp_path / "outside.smk"
    outside.write_text("rule all:\n  shell: 'true'\n")
    project = tmp_path / "project"
    project.mkdir()
    link = project / "Snakefile"
    os.symlink(outside, link)
    reana_yaml = project / "reana.yaml"
    reana_yaml.write_text("workflow:\n  type: snakemake\n  file: Snakefile\n")

    members = _gather_spec_members(str(reana_yaml))

    # The symlink is skipped (not followed), so only the canonical spec remains.
    assert set(members) == {"reana.yaml"}
