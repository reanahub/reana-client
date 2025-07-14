# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2026 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""REANA client Snakemake environment validation tests."""

import os
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from reana_client.validation.environments import EnvironmentValidatorSnakemake
from reana_commons.config import REANA_DEFAULT_SNAKEMAKE_ENV_IMAGE


def _make_validator(steps, snakefile_path, pull=False):
    """Return an EnvironmentValidatorSnakemake with a real temp Snakefile path."""
    return EnvironmentValidatorSnakemake(
        workflow_steps=steps,
        pull=pull,
        workflow_filename=str(snakefile_path),
    )


def _make_snakemake_modules(container_imgs):
    """Build a sys.modules patch dict that mimics the Snakemake API.

    Returns ``(modules_dict, api_instance)`` so callers can further configure
    the mock (e.g. make ``workflow()`` raise for DAG-failure tests).
    """
    mock_rules = [MagicMock(container_img=img) for img in container_imgs]
    # Always include a rule that has no container so we can verify it is skipped.
    mock_rules.append(MagicMock(container_img=None))

    mock_wf = MagicMock()
    mock_wf.rules = mock_rules

    mock_workflow_api = MagicMock()
    mock_workflow_api._workflow = mock_wf

    mock_api_instance = MagicMock()
    mock_api_instance.__enter__.return_value = mock_api_instance
    mock_api_instance.__exit__.return_value = False
    mock_api_instance.workflow.return_value = mock_workflow_api

    mock_api_module = MagicMock()
    mock_api_module.SnakemakeApi = MagicMock(return_value=mock_api_instance)

    modules = {
        "snakemake": MagicMock(),
        "snakemake.api": mock_api_module,
        "snakemake.settings": MagicMock(),
        "snakemake.settings.types": MagicMock(),
    }
    return modules, mock_api_instance


# ---------------------------------------------------------------------------
# Step-level environment validation (entries under reana.yaml ``steps:``)
# ---------------------------------------------------------------------------


class TestStepLevelEnvironments:
    """Tests for REANA-spec step-level container image validation."""

    @patch.object(EnvironmentValidatorSnakemake, "_validate_snakefile_environments")
    def test_step_without_environment_warns_and_uses_default(
        self, _mock_snakefile, tmp_path
    ):
        """A step that omits ``environment`` should warn naming the default image."""
        snakefile = tmp_path / "Snakefile"
        snakefile.write_text("")

        validator = _make_validator([{}], snakefile)
        validator.validate_environment()

        warning_texts = [
            m["message"] for m in validator.messages if m["type"] == "warning"
        ]
        assert any(
            REANA_DEFAULT_SNAKEMAKE_ENV_IMAGE in t for t in warning_texts
        ), f"Expected default-image warning, got: {validator.messages}"

    @patch.object(EnvironmentValidatorSnakemake, "_validate_snakefile_environments")
    @patch.object(EnvironmentValidatorSnakemake, "_validate_environment_image")
    def test_step_with_explicit_environment_validates_it(
        self, mock_validate, _mock_snakefile, tmp_path
    ):
        """A step with an explicit ``environment`` should pass that image for validation."""
        snakefile = tmp_path / "Snakefile"
        snakefile.write_text("")

        validator = _make_validator([{"environment": "python:3.11"}], snakefile)
        validator.validate_environment()

        mock_validate.assert_called_once_with("python:3.11", kubernetes_uid=None)

    @patch.object(EnvironmentValidatorSnakemake, "_validate_snakefile_environments")
    @patch.object(EnvironmentValidatorSnakemake, "_validate_environment_image")
    def test_step_kubernetes_uid_forwarded_to_image_validation(
        self, mock_validate, _mock_snakefile, tmp_path
    ):
        """``kubernetes_uid`` from a step should be forwarded to ``_validate_environment_image``."""
        snakefile = tmp_path / "Snakefile"
        snakefile.write_text("")

        validator = _make_validator(
            [{"environment": "python:3.11", "kubernetes_uid": 1000}], snakefile
        )
        validator.validate_environment()

        mock_validate.assert_called_once_with("python:3.11", kubernetes_uid=1000)

    @patch.object(EnvironmentValidatorSnakemake, "_validate_snakefile_environments")
    def test_invalid_image_tag_in_step_causes_fatal_exit(
        self, _mock_snakefile, tmp_path
    ):
        """A step with an invalid image tag (extra colon) should trigger ``sys.exit(1)``."""
        snakefile = tmp_path / "Snakefile"
        snakefile.write_text("")

        # "python:3.11:extra" has two colons — _validate_image_tag will raise.
        validator = _make_validator([{"environment": "python:3.11:extra"}], snakefile)
        with pytest.raises(SystemExit) as exc_info:
            validator.validate()
        assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# Config-key extraction from the Snakefile text
# ---------------------------------------------------------------------------


class TestGetSnakemakeConfigKeys:
    """Tests for ``_get_snakemake_config_keys`` regex extraction."""

    def test_double_quoted_key_extracted(self, tmp_path):
        snakefile = tmp_path / "Snakefile"
        snakefile.write_text('container: docker://config["my_image"]\n')

        v = EnvironmentValidatorSnakemake(
            workflow_steps=[], workflow_filename=str(snakefile)
        )
        assert v._get_snakemake_config_keys() == ["my_image"]

    def test_single_quoted_key_extracted(self, tmp_path):
        snakefile = tmp_path / "Snakefile"
        snakefile.write_text("container: docker://config['my_image']\n")

        v = EnvironmentValidatorSnakemake(
            workflow_steps=[], workflow_filename=str(snakefile)
        )
        assert v._get_snakemake_config_keys() == ["my_image"]

    def test_multiple_keys_extracted(self, tmp_path):
        content = textwrap.dedent("""\
            rule foo:
                params:
                    a=config["param1"],
                    b=config["param2"],
        """)
        snakefile = tmp_path / "Snakefile"
        snakefile.write_text(content)

        v = EnvironmentValidatorSnakemake(
            workflow_steps=[], workflow_filename=str(snakefile)
        )
        assert set(v._get_snakemake_config_keys()) == {"param1", "param2"}

    def test_no_config_references_returns_empty(self, tmp_path):
        snakefile = tmp_path / "Snakefile"
        snakefile.write_text("rule foo:\n    shell: 'echo hi'\n")

        v = EnvironmentValidatorSnakemake(
            workflow_steps=[], workflow_filename=str(snakefile)
        )
        assert v._get_snakemake_config_keys() == []

    def test_included_file_keys_are_found(self, tmp_path):
        """Keys used only in an included Snakefile must be returned."""
        rules_smk = tmp_path / "rules.smk"
        rules_smk.write_text('rule bar:\n    container: config["image"]\n')
        snakefile = tmp_path / "Snakefile"
        snakefile.write_text('include: "rules.smk"\n')

        v = EnvironmentValidatorSnakemake(
            workflow_steps=[], workflow_filename=str(snakefile)
        )
        assert "image" in v._get_snakemake_config_keys()

    def test_transitive_include_keys_are_found(self, tmp_path):
        """Keys used in a transitively included file (A → B → C) are returned."""
        deep = tmp_path / "deep.smk"
        deep.write_text('rule c:\n    container: config["deep_image"]\n')
        mid = tmp_path / "mid.smk"
        mid.write_text('include: "deep.smk"\n')
        snakefile = tmp_path / "Snakefile"
        snakefile.write_text('include: "mid.smk"\n')

        v = EnvironmentValidatorSnakemake(
            workflow_steps=[], workflow_filename=str(snakefile)
        )
        assert "deep_image" in v._get_snakemake_config_keys()

    def test_include_cycle_does_not_infinite_loop(self, tmp_path):
        """A cycle in include directives must not cause infinite recursion."""
        a = tmp_path / "a.smk"
        b = tmp_path / "b.smk"
        a.write_text('include: "b.smk"\ncontainer: config["key_a"]\n')
        b.write_text('include: "a.smk"\ncontainer: config["key_b"]\n')
        snakefile = tmp_path / "Snakefile"
        snakefile.write_text('include: "a.smk"\n')

        v = EnvironmentValidatorSnakemake(
            workflow_steps=[], workflow_filename=str(snakefile)
        )
        keys = set(v._get_snakemake_config_keys())
        assert keys == {"key_a", "key_b"}

    def test_missing_include_does_not_crash(self, tmp_path):
        """A reference to a non-existent include file must be silently skipped."""
        snakefile = tmp_path / "Snakefile"
        snakefile.write_text(
            'include: "nonexistent.smk"\ncontainer: config["top_key"]\n'
        )

        v = EnvironmentValidatorSnakemake(
            workflow_steps=[], workflow_filename=str(snakefile)
        )
        assert v._get_snakemake_config_keys() == ["top_key"]


# ---------------------------------------------------------------------------
# Snakefile-level container image extraction (_validate_snakefile_environments)
# ---------------------------------------------------------------------------


class TestSnakefileEnvironmentExtraction:
    """Tests for ``_validate_snakefile_environments``."""

    @patch.dict(
        "sys.modules",
        {
            "snakemake": None,
            "snakemake.api": None,
            "snakemake.settings": None,
            "snakemake.settings.types": None,
        },
    )
    def test_snakemake_not_installed_emits_warning_not_error(self, tmp_path):
        """When snakemake is not importable the validator should warn, not error."""
        snakefile = tmp_path / "Snakefile"
        snakefile.write_text("")

        v = EnvironmentValidatorSnakemake(
            workflow_steps=[], workflow_filename=str(snakefile)
        )
        v._validate_snakefile_environments()

        types_ = {m["type"] for m in v.messages}
        assert "warning" in types_, "Expected a warning when snakemake is missing"
        assert (
            "error" not in types_
        ), "Expected no error when snakemake is simply absent"
        assert any(
            "not installed" in m["message"]
            for m in v.messages
            if m["type"] == "warning"
        )

    def test_dag_build_exception_emits_error_message(self, tmp_path):
        """An unexpected exception during DAG construction should record an error."""
        snakefile = tmp_path / "Snakefile"
        snakefile.write_text("")

        v = EnvironmentValidatorSnakemake(
            workflow_steps=[], workflow_filename=str(snakefile)
        )

        modules, api_instance = _make_snakemake_modules([])
        api_instance.workflow.side_effect = RuntimeError("syntax error in Snakefile")

        with patch.dict("sys.modules", modules):
            v._validate_snakefile_environments()

        assert any(
            m["type"] == "error" and "DAG" in m["message"] for m in v.messages
        ), f"Expected a DAG-error message, got: {v.messages}"

    def test_workflow_side_import_error_is_an_error_not_not_installed(self, tmp_path):
        """An ImportError raised while evaluating the Snakefile must surface as an
        error, not be downgraded to the "snakemake not installed" warning."""
        snakefile = tmp_path / "Snakefile"
        snakefile.write_text("")

        v = EnvironmentValidatorSnakemake(
            workflow_steps=[], workflow_filename=str(snakefile)
        )

        modules, api_instance = _make_snakemake_modules([])
        api_instance.workflow.side_effect = ImportError("No module named custom_helper")

        with patch.dict("sys.modules", modules):
            v._validate_snakefile_environments()

        assert not any(
            "not installed" in m["message"] for m in v.messages
        ), f"Workflow-side ImportError wrongly reported as not installed: {v.messages}"
        assert any(
            m["type"] == "error" and "DAG" in m["message"] for m in v.messages
        ), f"Expected a DAG-error message, got: {v.messages}"

    def test_invalid_snakefile_image_propagates_and_exits_nonzero(self, tmp_path):
        """An invalid image found in the Snakefile must propagate EnvironmentValidationError
        so that ``validate()`` exits non-zero — not be swallowed into a message."""
        snakefile = tmp_path / "Snakefile"
        snakefile.write_text("")

        v = EnvironmentValidatorSnakemake(
            workflow_steps=[], workflow_filename=str(snakefile)
        )

        modules, _ = _make_snakemake_modules(["docker://bad:image:tag"])
        with patch.dict("sys.modules", modules), pytest.raises(SystemExit) as exc_info:
            v.validate()

        assert exc_info.value.code == 1

    @patch.object(EnvironmentValidatorSnakemake, "_validate_environment_image")
    def test_docker_scheme_stripped_explicit_registry(self, mock_validate, tmp_path):
        """``docker://docker.io/python:3.9`` → ``docker.io/python:3.9``."""
        snakefile = tmp_path / "Snakefile"
        snakefile.write_text("")

        v = EnvironmentValidatorSnakemake(
            workflow_steps=[], workflow_filename=str(snakefile)
        )

        modules, _ = _make_snakemake_modules(["docker://docker.io/python:3.9"])
        with patch.dict("sys.modules", modules):
            v._validate_snakefile_environments()

        mock_validate.assert_called_once_with("docker.io/python:3.9")

    @patch.object(EnvironmentValidatorSnakemake, "_validate_environment_image")
    def test_docker_scheme_stripped_bare_image(self, mock_validate, tmp_path):
        """``docker://python:3.9`` (no registry prefix) → ``python:3.9``."""
        snakefile = tmp_path / "Snakefile"
        snakefile.write_text("")

        v = EnvironmentValidatorSnakemake(
            workflow_steps=[], workflow_filename=str(snakefile)
        )

        modules, _ = _make_snakemake_modules(["docker://python:3.9"])
        with patch.dict("sys.modules", modules):
            v._validate_snakefile_environments()

        mock_validate.assert_called_once_with("python:3.9")

    @patch.object(EnvironmentValidatorSnakemake, "_validate_environment_image")
    def test_docker_scheme_stripped_non_dockerhub_registry(
        self, mock_validate, tmp_path
    ):
        """``docker://ghcr.io/org/image:tag`` → ``ghcr.io/org/image:tag``."""
        snakefile = tmp_path / "Snakefile"
        snakefile.write_text("")

        v = EnvironmentValidatorSnakemake(
            workflow_steps=[], workflow_filename=str(snakefile)
        )

        modules, _ = _make_snakemake_modules(["docker://ghcr.io/org/image:tag"])
        with patch.dict("sys.modules", modules):
            v._validate_snakefile_environments()

        mock_validate.assert_called_once_with("ghcr.io/org/image:tag")

    @patch.object(EnvironmentValidatorSnakemake, "_validate_environment_image")
    def test_rules_without_container_are_not_validated(self, mock_validate, tmp_path):
        """Rules that have no ``container:`` directive (``container_img is None``) must be skipped."""
        snakefile = tmp_path / "Snakefile"
        snakefile.write_text("")

        v = EnvironmentValidatorSnakemake(
            workflow_steps=[], workflow_filename=str(snakefile)
        )

        # _make_snakemake_modules always appends a None-container rule.
        modules, _ = _make_snakemake_modules([])
        with patch.dict("sys.modules", modules):
            v._validate_snakefile_environments()

        mock_validate.assert_not_called()

    @patch.object(EnvironmentValidatorSnakemake, "_validate_environment_image")
    def test_no_configfile_falls_back_to_fake_values(self, _mock_validate, tmp_path):
        """Without a configfile or direct params, ``config["key"]`` references are
        filled with fake placeholders so the DAG can be built without KeyError."""
        content = textwrap.dedent("""\
            rule foo:
                container: config["my_image"]
                output: "out.txt"
                shell: "touch {output}"
        """)
        snakefile = tmp_path / "Snakefile"
        snakefile.write_text(content)

        # No input parameters at all → should fall back to fake-values path.
        v = EnvironmentValidatorSnakemake(
            workflow_steps=[], workflow_filename=str(snakefile)
        )
        assert v.workflow_input_parameters == {}
        assert "my_image" in v._get_snakemake_config_keys()

        modules, _ = _make_snakemake_modules([])
        with patch.dict("sys.modules", modules):
            v._validate_snakefile_environments()

        config_settings_cls = modules["snakemake.settings.types"].ConfigSettings
        assert config_settings_cls.called
        call_kwargs = config_settings_cls.call_args.kwargs
        # No configfile → ConfigSettings must not receive configfiles=
        assert "configfiles" not in call_kwargs
        assert call_kwargs.get("config", {}).get("my_image") == "fake_value"

    @patch.object(EnvironmentValidatorSnakemake, "_validate_environment_image")
    def test_real_configfile_passed_to_config_settings(self, _mock_validate, tmp_path):
        """When ``inputs.parameters.input`` points to a configfile, ``ConfigSettings``
        must receive ``configfiles=[Path(…)]`` and no fake values in ``config``."""
        snakefile = tmp_path / "Snakefile"
        snakefile.write_text("")
        config_yaml = tmp_path / "config.yaml"
        config_yaml.write_text("image: python:3.11\n")

        v = EnvironmentValidatorSnakemake(
            workflow_steps=[],
            workflow_filename=str(snakefile),
            workflow_input_parameters={"input": str(config_yaml)},
        )

        modules, _ = _make_snakemake_modules([])
        with patch.dict("sys.modules", modules):
            v._validate_snakefile_environments()

        config_settings_cls = modules["snakemake.settings.types"].ConfigSettings
        assert config_settings_cls.called
        call_kwargs = config_settings_cls.call_args.kwargs
        assert call_kwargs.get("configfiles") == [config_yaml.resolve()]
        # No direct params alongside the configfile → config overrides must be empty
        assert call_kwargs.get("config") == {}

    @patch.object(EnvironmentValidatorSnakemake, "_validate_environment_image")
    def test_direct_params_used_as_real_config_when_no_configfile(
        self, _mock_validate, tmp_path
    ):
        """Non-``input`` entries in ``inputs.parameters`` are real ``--config`` overrides
        and must be forwarded to ``ConfigSettings`` as-is (not replaced by fake values).
        """
        snakefile = tmp_path / "Snakefile"
        snakefile.write_text('container: config["image"]\n')

        v = EnvironmentValidatorSnakemake(
            workflow_steps=[],
            workflow_filename=str(snakefile),
            workflow_input_parameters={"image": "python:3.11", "num_samples": 10},
        )

        modules, _ = _make_snakemake_modules([])
        with patch.dict("sys.modules", modules):
            v._validate_snakefile_environments()

        config_settings_cls = modules["snakemake.settings.types"].ConfigSettings
        call_kwargs = config_settings_cls.call_args.kwargs
        config_passed = call_kwargs.get("config", {})
        # Real values must be preserved, not replaced with "fake_value".
        assert config_passed["image"] == "python:3.11"
        assert config_passed["num_samples"] == 10

    @patch.object(EnvironmentValidatorSnakemake, "_validate_environment_image")
    def test_direct_params_combined_with_configfile(self, _mock_validate, tmp_path):
        """When both a configfile and direct overrides are present, both are forwarded
        to ``ConfigSettings`` — Snakemake merges them at runtime with overrides winning.
        """
        snakefile = tmp_path / "Snakefile"
        snakefile.write_text("")
        config_yaml = tmp_path / "config.yaml"
        config_yaml.write_text("image: python:3.11\n")

        v = EnvironmentValidatorSnakemake(
            workflow_steps=[],
            workflow_filename=str(snakefile),
            workflow_input_parameters={
                "input": str(config_yaml),
                "extra_flag": "true",
            },
        )

        modules, _ = _make_snakemake_modules([])
        with patch.dict("sys.modules", modules):
            v._validate_snakefile_environments()

        config_settings_cls = modules["snakemake.settings.types"].ConfigSettings
        call_kwargs = config_settings_cls.call_args.kwargs
        assert call_kwargs.get("configfiles") == [config_yaml.resolve()]
        assert call_kwargs.get("config") == {"extra_flag": "true"}

    @patch.object(EnvironmentValidatorSnakemake, "_validate_environment_image")
    def test_included_file_config_key_injected_as_fake_value(
        self, _mock_validate, tmp_path
    ):
        """Keys referenced only in an included Snakefile must be injected as fake
        placeholders so the DAG builds without KeyError ('image')."""
        rules_smk = tmp_path / "rules.smk"
        rules_smk.write_text('rule bar:\n    container: config["image"]\n')
        snakefile = tmp_path / "Snakefile"
        snakefile.write_text('include: "rules.smk"\n')

        v = EnvironmentValidatorSnakemake(
            workflow_steps=[], workflow_filename=str(snakefile)
        )

        modules, _ = _make_snakemake_modules([])
        with patch.dict("sys.modules", modules):
            v._validate_snakefile_environments()

        config_settings_cls = modules["snakemake.settings.types"].ConfigSettings
        call_kwargs = config_settings_cls.call_args.kwargs
        assert call_kwargs.get("config", {}).get("image") == "fake_value", (
            "Key from included file must be injected as fake_value so the DAG "
            "doesn't raise KeyError('image')"
        )

    @patch.object(EnvironmentValidatorSnakemake, "_validate_environment_image")
    def test_direct_params_not_overridden_by_fake_values(
        self, _mock_validate, tmp_path
    ):
        """A config key already supplied via ``inputs.parameters`` must not be
        silently replaced by a fake placeholder."""
        snakefile = tmp_path / "Snakefile"
        # Snakefile references "image" — the key is also in inputs.parameters.
        snakefile.write_text('container: config["image"]\n')

        v = EnvironmentValidatorSnakemake(
            workflow_steps=[],
            workflow_filename=str(snakefile),
            workflow_input_parameters={"image": "python:3.11"},
        )

        modules, _ = _make_snakemake_modules([])
        with patch.dict("sys.modules", modules):
            v._validate_snakefile_environments()

        config_settings_cls = modules["snakemake.settings.types"].ConfigSettings
        config_passed = config_settings_cls.call_args.kwargs.get("config", {})
        assert (
            config_passed["image"] == "python:3.11"
        ), "Real param value must not be overwritten by fake_value"

    @patch.object(EnvironmentValidatorSnakemake, "_validate_environment_image")
    def test_subdirectory_snakefile_chdirs_to_snakefile_parent(
        self, _mock_validate, tmp_path
    ):
        """When the Snakefile is in a subdirectory, validation must chdir into
        that directory before building the DAG so that ``configfile: "x.yaml"``
        inside the Snakefile resolves relative to the Snakefile, not the repo root."""
        subdir = tmp_path / "workflow"
        subdir.mkdir()
        snakefile = subdir / "Snakefile"
        snakefile.write_text("")

        v = EnvironmentValidatorSnakemake(
            workflow_steps=[], workflow_filename=str(snakefile)
        )

        chdir_calls = []
        original_chdir = os.chdir

        def recording_chdir(path):
            chdir_calls.append(Path(path).resolve())
            original_chdir(path)

        modules, _ = _make_snakemake_modules([])
        with patch.dict("sys.modules", modules), patch(
            "os.chdir", side_effect=recording_chdir
        ):
            v._validate_snakefile_environments()

        # First chdir must target the Snakefile's parent; second restores cwd.
        assert (
            len(chdir_calls) == 2
        ), f"Expected exactly 2 chdir calls, got: {chdir_calls}"
        assert chdir_calls[0] == snakefile.parent.resolve()

    @patch.object(EnvironmentValidatorSnakemake, "_validate_environment_image")
    def test_cwd_restored_after_dag_build_exception(self, _mock_validate, tmp_path):
        """The original working directory must be restored even if the DAG
        build raises an exception."""
        subdir = tmp_path / "workflow"
        subdir.mkdir()
        snakefile = subdir / "Snakefile"
        snakefile.write_text("")

        v = EnvironmentValidatorSnakemake(
            workflow_steps=[], workflow_filename=str(snakefile)
        )

        cwd_before = os.getcwd()

        modules, api_instance = _make_snakemake_modules([])
        api_instance.workflow.side_effect = RuntimeError("dag error")
        with patch.dict("sys.modules", modules):
            v._validate_snakefile_environments()

        assert (
            os.getcwd() == cwd_before
        ), "Working directory must be restored after exception"

    def test_validate_environment_wires_input_parameters_from_reana_yaml(
        self, tmp_path
    ):
        """The top-level ``validate_environment`` must pass the full
        ``inputs.parameters`` dict as ``workflow_input_parameters``."""
        from reana_client.validation.environments import validate_environment

        snakefile = tmp_path / "Snakefile"
        snakefile.write_text("")
        config_yaml = tmp_path / "config.yaml"
        config_yaml.write_text("image: python:3.11\n")

        reana_yaml = {
            "inputs": {"parameters": {"input": str(config_yaml), "num_samples": 5}},
            "workflow": {
                "type": "snakemake",
                "file": str(snakefile),
                "specification": {"steps": []},
            },
        }

        captured = {}

        def fake_init(
            self,
            workflow_steps=None,
            pull=False,
            access_token=None,
            workflow_filename=None,
            workflow_input_parameters=None,
        ):
            captured["workflow_input_parameters"] = workflow_input_parameters
            self.workflow_steps = workflow_steps or []
            self.pull = pull
            self.access_token = access_token
            self.workflow_filename = workflow_filename
            self.workflow_input_parameters = workflow_input_parameters or {}
            self.validated_images = set()
            self.messages = []

        with patch.object(
            EnvironmentValidatorSnakemake, "__init__", fake_init
        ), patch.object(EnvironmentValidatorSnakemake, "validate"), patch.object(
            EnvironmentValidatorSnakemake, "display_messages"
        ):
            validate_environment(reana_yaml)

        assert captured["workflow_input_parameters"] == {
            "input": str(config_yaml),
            "num_samples": 5,
        }

    def test_validate_environment_passes_empty_dict_when_no_inputs(self, tmp_path):
        """When ``inputs`` is absent from ``reana_yaml``, ``workflow_input_parameters``
        must be an empty dict (not ``None``)."""
        from reana_client.validation.environments import validate_environment

        snakefile = tmp_path / "Snakefile"
        snakefile.write_text("")

        reana_yaml = {
            "workflow": {
                "type": "snakemake",
                "file": str(snakefile),
                "specification": {"steps": []},
            },
        }

        captured = {}

        def fake_init(
            self,
            workflow_steps=None,
            pull=False,
            access_token=None,
            workflow_filename=None,
            workflow_input_parameters=None,
        ):
            captured["workflow_input_parameters"] = workflow_input_parameters
            self.workflow_steps = workflow_steps or []
            self.pull = pull
            self.access_token = access_token
            self.workflow_filename = workflow_filename
            self.workflow_input_parameters = workflow_input_parameters or {}
            self.validated_images = set()
            self.messages = []

        with patch.object(
            EnvironmentValidatorSnakemake, "__init__", fake_init
        ), patch.object(EnvironmentValidatorSnakemake, "validate"), patch.object(
            EnvironmentValidatorSnakemake, "display_messages"
        ):
            validate_environment(reana_yaml)

        assert captured["workflow_input_parameters"] == {}
