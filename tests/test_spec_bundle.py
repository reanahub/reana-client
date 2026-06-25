# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2026 CERN.

"""Tests for explicit validation-snapshot assembly and ZIP transport."""

import io
import os
import zipfile
from unittest.mock import Mock

import pytest

from reana_client.api import client as client_module
from reana_client.api.client import (
    _gather_spec_members,
    _post_spec_members,
    download_file,
    start_workflow,
    upload_file,
)
from reana_client.errors import FileUploadError
from reana_commons.errors import REANAValidationError


def _write_spec(tmp_path, body, name="reana.yaml"):
    specification = tmp_path / name
    specification.write_text(body)
    return specification


def test_start_workflow_uses_bounded_request_options(monkeypatch):
    """Synchronous server-side validation cannot block a client forever."""
    captured = {}

    class Future:
        def result(self):
            return {"status": "queued"}, Mock(status_code=200)

    def operation(**kwargs):
        captured.update(kwargs)
        return Future()

    api_client = Mock()
    api_client.api.start_workflow.side_effect = operation
    monkeypatch.setattr("reana_client.api.client.current_rs_api_client", api_client)

    assert start_workflow("analysis", "token", {}) == {"status": "queued"}
    assert captured["_request_options"] == {
        "connect_timeout": 10,
        "timeout": 300,
    }


def test_gather_uses_explicit_workflow_scope(tmp_path):
    """Only workflow.file/files/directories and parameters enter validation."""
    (tmp_path / "workflow").mkdir()
    (tmp_path / "workflow" / "Snakefile").write_text("rule all:\n  input: []")
    (tmp_path / "rules").mkdir()
    (tmp_path / "rules" / "common.smk").write_text("rule common:\n  output: 'x'")
    (tmp_path / "shared.yaml").write_text("value: 1")
    (tmp_path / "params.yaml").write_text("answer: 42")
    (tmp_path / "dataset.csv").write_text("large data")
    specification = _write_spec(
        tmp_path,
        """
workflow:
  type: snakemake
  file: workflow/Snakefile
  files: [shared.yaml]
  directories: [rules]
  parameters:
    file: params.yaml
inputs:
  files: [dataset.csv]
""",
    )

    assert set(_gather_spec_members(str(specification))) == {
        "reana.yaml",
        "workflow/Snakefile",
        "rules/common.smk",
        "shared.yaml",
        "params.yaml",
    }


def test_gather_does_not_infer_workflow_file_subtree(tmp_path):
    """Undeclared siblings of workflow.file are not visible to validation."""
    (tmp_path / "workflow").mkdir()
    (tmp_path / "workflow" / "Snakefile").write_text("")
    (tmp_path / "workflow" / "undeclared.smk").write_text("")
    specification = _write_spec(
        tmp_path,
        "workflow:\n  type: snakemake\n  file: workflow/Snakefile\n",
    )
    assert set(_gather_spec_members(str(specification))) == {
        "reana.yaml",
        "workflow/Snakefile",
    }


def test_gather_supports_legacy_parameter_file(tmp_path):
    """The released inputs.parameters.input spelling remains in the snapshot."""
    (tmp_path / "Snakefile").write_text("")
    (tmp_path / "params.yaml").write_text("answer: 42")
    specification = _write_spec(
        tmp_path,
        """
inputs:
  parameters:
    input: params.yaml
workflow:
  type: snakemake
  file: Snakefile
""",
    )
    assert "params.yaml" in _gather_spec_members(str(specification))


@pytest.mark.parametrize("declaration", ["../secret", "/etc/passwd", "C:/secret"])
def test_gather_rejects_escaping_paths(tmp_path, declaration):
    """Unsafe declarations fail rather than being silently omitted."""
    (tmp_path / "Snakefile").write_text("")
    specification = _write_spec(
        tmp_path,
        "workflow:\n"
        "  type: snakemake\n"
        "  file: Snakefile\n"
        "  files:\n"
        f"    - {declaration}\n",
    )
    with pytest.raises(REANAValidationError, match="Unsafe path"):
        _gather_spec_members(str(specification))


def test_gather_rejects_symlinks(tmp_path):
    """Declared symbolic links are never followed."""
    target = tmp_path / "target.smk"
    target.write_text("")
    (tmp_path / "Snakefile").symlink_to(target)
    specification = _write_spec(
        tmp_path, "workflow:\n  type: snakemake\n  file: Snakefile\n"
    )
    with pytest.raises(REANAValidationError, match="Symbolic links"):
        _gather_spec_members(str(specification))


def test_selected_specification_is_canonical(tmp_path):
    """A non-default local filename is transported as canonical reana.yaml."""
    (tmp_path / "Snakefile").write_text("")
    specification = _write_spec(
        tmp_path,
        "workflow:\n  type: snakemake\n  file: Snakefile\n",
        name="reana-snakemake.yaml",
    )
    members = _gather_spec_members(str(specification))
    assert members["reana.yaml"] == str(specification)


@pytest.mark.parametrize(
    "body",
    [
        "workflow: [serial]\n",
        "workflow: serial\n",
        "workflow:\n  type: snakemake\n  parameters: [params.yaml]\n",
        "inputs: [input.csv]\nworkflow: {type: serial}\n",
        "inputs:\n  parameters: [params.yaml]\nworkflow: {type: snakemake}\n",
        "workflow: [\n",
        "- workflow\n- inputs\n",
    ],
)
def test_gather_forwards_only_canonical_spec_when_scope_is_unreadable(tmp_path, body):
    """Wrong-shaped YAML reaches the server's authoritative error handling."""
    specification = _write_spec(tmp_path, body)
    assert _gather_spec_members(str(specification)) == {
        "reana.yaml": str(specification)
    }


def test_post_streams_one_uncompressed_zip(
    monkeypatch, tmp_path, arm_bundle_capability
):
    """Bravado receives one deterministic ZIP_STORED bundle file parameter."""
    specification = _write_spec(
        tmp_path,
        "workflow:\n  type: serial\n  specification:\n    steps: []\n",
    )
    captured = {}

    class Future:
        def result(self):
            filename, stream = captured["bundle"]
            captured["filename"] = filename
            captured["archive"] = stream.read()
            return {"valid": True}, Mock(status_code=200)

    def validate_operation(**kwargs):
        captured.update(kwargs)
        return Future()

    api_client = arm_bundle_capability(Mock())
    api_client.api.validate_workflow_specification.side_effect = validate_operation
    monkeypatch.setattr("reana_client.api.client.current_rs_api_client", api_client)
    _post_spec_members(
        "validate_workflow_specification",
        _gather_spec_members(str(specification)),
        {},
    )

    with zipfile.ZipFile(io.BytesIO(captured["archive"])) as archive:
        assert archive.namelist() == ["reana.yaml"]
        assert archive.getinfo("reana.yaml").compress_type == zipfile.ZIP_STORED
    assert captured["filename"] == "validation-bundle.zip"
    assert captured["_request_options"] == {
        "connect_timeout": 10,
        "timeout": 300,
    }


def test_post_preserves_noncanonical_selected_specification(
    monkeypatch, tmp_path, arm_bundle_capability
):
    """The selected local filename is securely read but archived as reana.yaml."""
    specification = _write_spec(
        tmp_path,
        "workflow:\n  type: serial\n  specification:\n    steps: []\n",
        name="selected.yaml",
    )
    captured = {}

    class Future:
        def result(self):
            _filename, stream = captured["bundle"]
            captured["archive"] = stream.read()
            return {"valid": True}, Mock(status_code=200)

    def validate_operation(**kwargs):
        captured.update(kwargs)
        return Future()

    api_client = arm_bundle_capability(Mock())
    api_client.api.validate_workflow_specification.side_effect = validate_operation
    monkeypatch.setattr(client_module, "current_rs_api_client", api_client)

    _post_spec_members(
        "validate_workflow_specification",
        _gather_spec_members(str(specification)),
        {},
    )

    with zipfile.ZipFile(io.BytesIO(captured["archive"])) as archive:
        assert archive.namelist() == ["reana.yaml"]
        assert archive.read("reana.yaml") == specification.read_bytes()


def test_post_rejects_swapped_source_ancestor(
    monkeypatch, tmp_path, arm_bundle_capability
):
    """Scope discovery cannot be redirected before ZIP construction."""
    (tmp_path / "defs").mkdir()
    (tmp_path / "defs" / "Snakefile").write_text("ORIGINAL")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "Snakefile").write_text("OUTSIDE")
    specification = _write_spec(
        tmp_path,
        "workflow:\n  type: snakemake\n  file: defs/Snakefile\n",
    )
    members = _gather_spec_members(str(specification))
    (tmp_path / "defs").rename(tmp_path / "defs-original")
    (tmp_path / "defs").symlink_to(outside, target_is_directory=True)
    api_client = arm_bundle_capability(Mock())
    monkeypatch.setattr(client_module, "current_rs_api_client", api_client)

    with pytest.raises(REANAValidationError, match="securely open"):
        _post_spec_members("validate_workflow_specification", members, {})
    api_client.api.validate_workflow_specification.assert_not_called()


def test_post_enforces_file_count_before_archive_creation(
    monkeypatch, tmp_path, arm_bundle_capability
):
    """Oversized member sets do not consume client temporary storage."""
    specification = _write_spec(
        tmp_path,
        "workflow:\n  type: serial\n  specification:\n    steps: []\n",
    )
    extra = tmp_path / "extra.yaml"
    extra.write_text("value: 1")
    monkeypatch.setattr(
        client_module, "current_rs_api_client", arm_bundle_capability(Mock())
    )
    monkeypatch.setattr(client_module, "SPECIFICATION_BUNDLE_MAX_FILES", 1)
    with pytest.raises(FileUploadError, match="too many files"):
        _post_spec_members(
            "validate_workflow_specification",
            {"reana.yaml": str(specification), "extra.yaml": str(extra)},
            {},
        )


def test_post_enforces_extracted_bytes_while_archiving(
    monkeypatch, tmp_path, arm_bundle_capability
):
    """Oversized source contents stop before a complete local ZIP is written."""
    specification = _write_spec(
        tmp_path,
        "workflow:\n  type: serial\n  specification:\n    steps: []\n",
    )
    monkeypatch.setattr(
        client_module, "current_rs_api_client", arm_bundle_capability(Mock())
    )
    monkeypatch.setattr(client_module, "SPECIFICATION_BUNDLE_MAX_BYTES", 10)
    with pytest.raises(FileUploadError, match="too large"):
        _post_spec_members(
            "validate_workflow_specification",
            {"reana.yaml": str(specification)},
            {},
        )


def test_upload_file_streams_snapshotted_raw_body(monkeypatch):
    """Workspace uploads stream the initial bytes with an exact length."""
    http_response = Mock(ok=True)
    http_response.json.return_value = {"message": "uploaded"}
    api_client = Mock()
    api_client.api.upload_file.operation.path_name = (
        "/api/workflows/{workflow_id_or_name}/workspace"
    )
    monkeypatch.setattr("reana_client.api.client.current_rs_api_client", api_client)
    monkeypatch.setattr("reana_client.utils.get_api_url", lambda: "https://reana")
    source = io.BytesIO(b"contents")

    def post(url, data, **kwargs):
        source.seek(0, os.SEEK_END)
        source.write(b"-late-growth")
        source.seek(0)
        assert data.read(3) + data.read() == b"contents"
        assert data.read() == b""
        assert kwargs["headers"] == {
            "Content-Type": "application/octet-stream",
            "Content-Length": "8",
        }
        assert kwargs["timeout"] == (10, 300)
        assert kwargs["params"] == {
            "file_name": "data.txt",
            "access_token": "token",
        }
        assert url == "https://reana/api/workflows/workflow.1/workspace"
        return http_response

    monkeypatch.setattr(client_module.requests, "post", post)

    assert upload_file("workflow.1", source, "data.txt", "token") == {
        "message": "uploaded"
    }


def test_snapshot_upload_reader_rejects_a_truncated_source():
    """A file that shrinks after sizing aborts instead of hanging the server."""
    reader = client_module._SnapshotUploadReader(io.BytesIO(b"short"), 10)
    assert reader.read() == b"short"
    with pytest.raises(FileUploadError, match="changed while it was being read"):
        reader.read()


def test_download_file_uses_generated_operation(monkeypatch):
    """Workspace downloads stay on the generated Bravado operation."""
    http_response = Mock(
        status_code=200,
        headers={
            "Content-Disposition": 'attachment; filename="result.txt"',
            "Content-Type": "text/plain",
        },
        raw_bytes=b"result",
    )
    operation = Mock()
    operation.return_value.result.return_value = (None, http_response)
    api_client = Mock()
    api_client.api.download_file = operation
    monkeypatch.setattr("reana_client.api.client.current_rs_api_client", api_client)

    assert download_file("workflow.1", "requested.txt", "token") == (
        b"result",
        "result.txt",
        False,
    )
    operation.assert_called_once_with(
        workflow_id_or_name="workflow.1",
        file_name="requested.txt",
        access_token="token",
        _request_options={"connect_timeout": 10, "timeout": 300},
    )
