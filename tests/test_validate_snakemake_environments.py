# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2026 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""REANA client Snakemake environment validation tests.

Snakemake is a hard dependency of ``reana-client`` (via ``reana-commons``), so
these tests build real (tiny) Snakemake workflows on disk and exercise the
validator end to end rather than mocking the Snakemake API.
"""

import os
import textwrap
from unittest.mock import patch

import pytest

from reana_client.validation.environments import (
    EnvironmentValidatorSnakemake,
    validate_environment,
)
from reana_client.errors import EnvironmentValidationError
from reana_commons.config import REANA_DEFAULT_SNAKEMAKE_ENV_IMAGE

try:
    from snakemake.api import SnakemakeApi  # noqa: F401
    from snakemake.settings.types import (  # noqa: F401
        ResourceSettings,
        ConfigSettings,
    )

    HAS_SNAKEMAKE_API = True
except ImportError:
    HAS_SNAKEMAKE_API = False

# Building the Snakemake DAG to extract container images relies on the Snakemake
# 8+ API (``snakemake.api``).  On older Python versions (<3.11) only Snakemake 7
# is installable, where the validator gracefully skips image extraction; the
# tests that assert images are extracted are therefore skipped there too.
requires_snakemake_api = pytest.mark.skipif(
    not HAS_SNAKEMAKE_API,
    reason="Snakemake DAG image extraction requires the Snakemake 8+ API",
)


def _make_validator(tmp_path, snakefile, *, params=None, steps=None, files=None):
    """Write a Snakefile (plus any extra ``files``) on disk and return a validator.

    :param snakefile: contents of the main ``Snakefile`` (dedented automatically).
    :param params: ``inputs.parameters`` dict for the workflow.
    :param steps: REANA-spec ``steps`` list.
    :param files: mapping of ``filename -> contents`` written next to the
        Snakefile (e.g. included rules or config files).
    """
    for name, content in (files or {}).items():
        (tmp_path / name).write_text(textwrap.dedent(content))
    snakefile_path = tmp_path / "Snakefile"
    snakefile_path.write_text(textwrap.dedent(snakefile))
    return EnvironmentValidatorSnakemake(
        workflow_steps=steps or [],
        workflow_filename=str(snakefile_path),
        workflow_input_parameters=params or {},
    )


def _validated_images(validator):
    """Run Snakefile validation, returning the images handed to image validation."""
    images = []
    with patch.object(
        validator,
        "_validate_environment_image",
        side_effect=lambda image, **kwargs: images.append(image),
    ):
        validator._validate_snakefile_environments()
    return images


def _rule(name, image=None, container_expr=None):
    """Return the text of a minimal Snakemake rule.

    :param image: a literal image string, rendered as ``container: "<image>"``.
    :param container_expr: a raw container expression (e.g. ``config["image"]``),
        rendered verbatim as ``container: <expr>``.
    """
    if image is not None:
        container_line = f'    container: "{image}"\n'
    elif container_expr is not None:
        container_line = f"    container: {container_expr}\n"
    else:
        container_line = ""
    return (
        f"rule {name}:\n"
        f"{container_line}"
        f'    output: "{name}_out.txt"\n'
        f'    shell: "touch {{output}}"\n'
    )


# ---------------------------------------------------------------------------
# Step-level environments (entries under the REANA spec ``steps:``)
# ---------------------------------------------------------------------------


class TestStepLevelEnvironments:
    """Container images declared directly in the REANA spec steps."""

    @patch.object(EnvironmentValidatorSnakemake, "_validate_snakefile_environments")
    def test_step_without_environment_warns_with_default(self, _skip, tmp_path):
        validator = _make_validator(tmp_path, "", steps=[{}])
        validator.validate_environment()
        assert any(
            REANA_DEFAULT_SNAKEMAKE_ENV_IMAGE in m["message"]
            for m in validator.messages
            if m["type"] == "warning"
        )

    @patch.object(EnvironmentValidatorSnakemake, "_validate_snakefile_environments")
    @patch.object(EnvironmentValidatorSnakemake, "_validate_environment_image")
    def test_step_environment_validated_with_uid(self, mock_image, _skip, tmp_path):
        validator = _make_validator(
            tmp_path,
            "",
            steps=[{"environment": "python:3.11", "kubernetes_uid": 1000}],
        )
        validator.validate_environment()
        mock_image.assert_called_once_with("python:3.11", kubernetes_uid=1000)

    @patch.object(EnvironmentValidatorSnakemake, "_validate_snakefile_environments")
    def test_invalid_step_image_exits_nonzero(self, _skip, tmp_path):
        # Two colons make ``_validate_image_tag`` raise.
        validator = _make_validator(
            tmp_path, "", steps=[{"environment": "python:3.11:extra"}]
        )
        with pytest.raises(SystemExit) as exc_info:
            validator.validate()
        assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# Image extraction from the Snakemake DAG
# ---------------------------------------------------------------------------


@requires_snakemake_api
class TestSnakefileImageExtraction:
    """Images declared via ``container:`` directives in the Snakefile(s)."""

    def test_static_container_validated(self, tmp_path):
        validator = _make_validator(
            tmp_path, _rule("make", image="docker://python:3.11")
        )
        assert _validated_images(validator) == ["python:3.11"]

    def test_rule_without_container_skipped(self, tmp_path):
        validator = _make_validator(tmp_path, _rule("make"))
        assert _validated_images(validator) == []

    def test_docker_prefix_stripped_for_any_registry(self, tmp_path):
        validator = _make_validator(
            tmp_path,
            _rule("a", image="docker://python:3.11")
            + _rule("b", image="docker://docker.io/library/python:3.9")
            + _rule("c", image="docker://ghcr.io/org/image:tag"),
        )
        assert set(_validated_images(validator)) == {
            "python:3.11",
            "docker.io/library/python:3.9",
            "ghcr.io/org/image:tag",
        }

    def test_included_subworkflow_images_validated(self, tmp_path):
        validator = _make_validator(
            tmp_path,
            'include: "rules.smk"\nrule all:\n    input: "make_out.txt"\n',
            files={
                "rules.smk": _rule(
                    "make", image="docker://reanahub/reana-env-root6:6.18.04"
                )
            },
        )
        assert _validated_images(validator) == ["reanahub/reana-env-root6:6.18.04"]


# ---------------------------------------------------------------------------
# Resolving images that come from the workflow ``config``
# ---------------------------------------------------------------------------


@requires_snakemake_api
class TestConfigDrivenImages:
    """Images selected through ``config[...]`` values from various sources."""

    def test_nested_config_from_configfile_directive(self, tmp_path):
        validator = _make_validator(
            tmp_path,
            'configfile: "config.yaml"\n'
            + _rule("make", container_expr='config["images"]["tool"]'),
            files={"config.yaml": "images:\n  tool: docker://python:3.11\n"},
        )
        assert _validated_images(validator) == ["python:3.11"]

    def test_config_from_input_parameter_file(self, tmp_path):
        validator = _make_validator(
            tmp_path,
            _rule("make", container_expr='config["image"]'),
            files={"config.yaml": "image: docker://python:3.11\n"},
            params={"input": str(tmp_path / "config.yaml")},
        )
        assert _validated_images(validator) == ["python:3.11"]

    def test_config_from_direct_parameter(self, tmp_path):
        validator = _make_validator(
            tmp_path,
            _rule("make", container_expr='config["image"]'),
            params={"image": "docker://python:3.11"},
        )
        assert _validated_images(validator) == ["python:3.11"]

    def test_relative_configfile_in_subdirectory_resolves(self, tmp_path):
        workdir = tmp_path / "workflow"
        workdir.mkdir()
        (workdir / "config.yaml").write_text("image: docker://python:3.11\n")
        (workdir / "Snakefile").write_text(
            textwrap.dedent(
                'configfile: "config.yaml"\n'
                "rule make:\n"
                '    container: config["image"]\n'
                '    output: "out.txt"\n'
                '    shell: "touch {output}"\n'
            )
        )
        validator = EnvironmentValidatorSnakemake(
            workflow_steps=[], workflow_filename=str(workdir / "Snakefile")
        )
        cwd_before = os.getcwd()
        assert _validated_images(validator) == ["python:3.11"]
        assert os.getcwd() == cwd_before  # restored after building the DAG


# ---------------------------------------------------------------------------
# Failure modes: validation must surface errors and exit non-zero
# ---------------------------------------------------------------------------


class TestFailureModes:
    """A workflow that cannot be validated must fail, not silently pass."""

    @requires_snakemake_api
    def test_unresolved_config_key_fails_validation(self, tmp_path):
        # ``config["image"]`` is provided by no configfile nor input parameter.
        validator = _make_validator(
            tmp_path, _rule("make", container_expr='config["image"]')
        )
        with pytest.raises(EnvironmentValidationError) as exc_info:
            validator._validate_snakefile_environments()
        assert "DAG" in str(exc_info.value)

    @requires_snakemake_api
    def test_broken_snakefile_exits_nonzero(self, tmp_path):
        validator = _make_validator(
            tmp_path,
            "rule make:\n"
            '    output: "out.txt"\n'
            '    shell: "touch {output}"\n'
            "    threads: 1\n",  # keyword after shell is a hard Snakemake error
        )
        with pytest.raises(SystemExit) as exc_info:
            validator.validate()
        assert exc_info.value.code == 1

    @requires_snakemake_api
    def test_cwd_restored_after_dag_failure(self, tmp_path):
        workdir = tmp_path / "workflow"
        workdir.mkdir()
        (workdir / "Snakefile").write_text(
            textwrap.dedent(
                "rule make:\n"
                '    container: config["missing"]\n'
                '    output: "out.txt"\n'
                '    shell: "touch {output}"\n'
            )
        )
        validator = EnvironmentValidatorSnakemake(
            workflow_steps=[], workflow_filename=str(workdir / "Snakefile")
        )
        cwd_before = os.getcwd()
        with pytest.raises(EnvironmentValidationError):
            validator._validate_snakefile_environments()
        assert os.getcwd() == cwd_before

    @requires_snakemake_api
    def test_invalid_snakefile_image_exits_nonzero(self, tmp_path):
        validator = _make_validator(
            tmp_path, _rule("make", image="docker://bad:image:tag")
        )
        with pytest.raises(SystemExit) as exc_info:
            validator.validate()
        assert exc_info.value.code == 1

    def test_snakemake_not_installed_warns_without_error(self, tmp_path):
        validator = _make_validator(tmp_path, "")
        with patch.dict(
            "sys.modules",
            {
                "snakemake": None,
                "snakemake.api": None,
                "snakemake.settings": None,
                "snakemake.settings.types": None,
            },
        ):
            validator._validate_snakefile_environments()
        assert any(
            "not installed" in m["message"]
            for m in validator.messages
            if m["type"] == "warning"
        )
        assert not any(m["type"] == "error" for m in validator.messages)


# ---------------------------------------------------------------------------
# Wiring from the REANA specification
# ---------------------------------------------------------------------------


class TestValidateEnvironmentWiring:
    """``validate_environment`` must forward the spec into the validator."""

    def _capture_params(self, reana_yaml):
        captured = {}

        def fake_validate(self):
            captured["params"] = self.workflow_input_parameters

        with patch.object(
            EnvironmentValidatorSnakemake, "validate", fake_validate
        ), patch.object(EnvironmentValidatorSnakemake, "display_messages"):
            validate_environment(reana_yaml)
        return captured["params"]

    def test_input_parameters_forwarded(self, tmp_path):
        snakefile = tmp_path / "Snakefile"
        snakefile.write_text("")
        reana_yaml = {
            "inputs": {"parameters": {"input": "config.yaml", "n": 5}},
            "workflow": {
                "type": "snakemake",
                "file": str(snakefile),
                "specification": {"steps": []},
            },
        }
        assert self._capture_params(reana_yaml) == {"input": "config.yaml", "n": 5}

    def test_missing_inputs_forwarded_as_empty_dict(self, tmp_path):
        snakefile = tmp_path / "Snakefile"
        snakefile.write_text("")
        reana_yaml = {
            "workflow": {
                "type": "snakemake",
                "file": str(snakefile),
                "specification": {"steps": []},
            },
        }
        assert self._capture_params(reana_yaml) == {}
