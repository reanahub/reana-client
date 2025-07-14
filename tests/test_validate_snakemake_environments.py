# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2026 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""REANA client Snakemake environment validation tests.

Container images are validated from ``workflow.specification.steps``, which
reana-commons populates by loading the Snakefile (expanding ``include:``
directives and applying the workflow configuration).  These tests therefore
exercise the validator against steps shaped the way reana-commons produces them.
"""

from unittest.mock import patch

import pytest

from reana_client.validation.environments import (
    EnvironmentValidatorSnakemake,
    validate_environment,
)
from reana_commons.config import REANA_DEFAULT_SNAKEMAKE_ENV_IMAGE


def _make_validator(steps):
    """Return a validator over REANA-spec ``steps``."""
    return EnvironmentValidatorSnakemake(workflow_steps=steps)


def _run_validation(validator):
    """Run environment validation, returning the images it validated."""
    images = []
    with patch.object(
        validator,
        "_validate_environment_image",
        side_effect=lambda image, **kwargs: images.append(image),
    ):
        validator.validate_environment()
    return images


def _dynamic_warnings(validator):
    """Return the warnings emitted for skipped dynamic ``container:`` directives."""
    return [
        m["message"]
        for m in validator.messages
        if m["type"] == "warning" and "dynamic container directive" in m["message"]
    ]


# ---------------------------------------------------------------------------
# Step-level environments
# ---------------------------------------------------------------------------


class TestStepLevelEnvironments:
    """Container images recorded on the loaded workflow steps."""

    def test_step_without_environment_warns_with_default(self):
        validator = _make_validator([{"name": "make"}])
        assert _run_validation(validator) == []
        assert any(
            REANA_DEFAULT_SNAKEMAKE_ENV_IMAGE in m["message"]
            for m in validator.messages
            if m["type"] == "warning"
        )

    def test_step_environment_validated_with_uid(self):
        validator = _make_validator(
            [{"name": "make", "environment": "python:3.11", "kubernetes_uid": 1000}]
        )
        with patch.object(validator, "_validate_environment_image") as mock_image:
            validator.validate_environment()
        mock_image.assert_called_once_with("python:3.11", kubernetes_uid=1000)

    def test_every_step_is_validated(self):
        validator = _make_validator(
            [
                {"name": "a", "environment": "python:3.11"},
                {"name": "b", "environment": "reanahub/reana-env-root6:6.18.04"},
            ]
        )
        assert _run_validation(validator) == [
            "python:3.11",
            "reanahub/reana-env-root6:6.18.04",
        ]

    def test_invalid_step_image_exits_nonzero(self):
        # Two colons make ``_validate_image_tag`` raise.
        validator = _make_validator([{"name": "make", "environment": "python:3.11:x"}])
        with pytest.raises(SystemExit) as exc_info:
            validator.validate()
        assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# Dynamic ``container:`` directives resolved per job by Snakemake
# ---------------------------------------------------------------------------


class TestDynamicContainerImages:
    """Per-job container values are skipped with a warning, never validated.

    Snakemake resolves a callable or wildcard-parameterised ``container:`` value
    only once a concrete job's wildcards are known, so the value recorded on the
    step is not a usable image name.  Validating it would fail a working
    workflow, so it is deliberately skipped instead.
    """

    @pytest.mark.parametrize(
        "image",
        [
            "docker://python:{version}",  # wildcard-parameterised
            lambda wildcards: "docker://python:3.11",  # callable
            None,  # unset
        ],
    )
    def test_dynamic_values_classified(self, image):
        assert EnvironmentValidatorSnakemake._is_dynamic_image(image) is True

    @pytest.mark.parametrize("image", ["python:3.11", "ghcr.io/org/image:tag"])
    def test_static_values_classified(self, image):
        assert EnvironmentValidatorSnakemake._is_dynamic_image(image) is False

    def test_wildcard_container_skipped(self):
        validator = _make_validator(
            [{"name": "wild", "environment": "python:{version}"}]
        )
        assert _run_validation(validator) == []
        assert _dynamic_warnings(validator) == [
            "Skipping image validation for 1 rule with a dynamic container "
            "directive: 'wild'."
        ]
        assert not any(m["type"] == "error" for m in validator.messages)

    def test_static_steps_still_validated_alongside_dynamic_ones(self):
        validator = _make_validator(
            [
                {"name": "wild", "environment": "python:{version}"},
                {"name": "static", "environment": "python:3.11"},
            ]
        )
        assert _run_validation(validator) == ["python:3.11"]
        assert len(_dynamic_warnings(validator)) == 1

    def test_global_container_warns_once_for_all_rules(self):
        # A single top-level ``container:`` applies to every rule, so
        # reana-commons puts the same dynamic value on every executable step.
        # That must produce one warning naming the rules, not one warning each.
        validator = _make_validator(
            [
                {"name": name, "environment": "python:{version}"}
                for name in ("a", "b", "c")
            ]
        )
        assert _run_validation(validator) == []
        assert _dynamic_warnings(validator) == [
            "Skipping image validation for 3 rules with a dynamic container "
            "directive: 'a', 'b', 'c'."
        ]

    def test_many_dynamic_rules_are_summarised(self):
        validator = _make_validator(
            [{"name": f"r{i}", "environment": "python:{version}"} for i in range(8)]
        )
        assert _run_validation(validator) == []
        assert _dynamic_warnings(validator) == [
            "Skipping image validation for 8 rules with a dynamic container "
            "directive: 'r0', 'r1', 'r2', 'r3', 'r4' and 3 more."
        ]


# ---------------------------------------------------------------------------
# Wiring from the REANA specification
# ---------------------------------------------------------------------------


class TestValidateEnvironmentWiring:
    """``validate_environment`` must build the validator from the loaded steps."""

    def test_steps_forwarded(self):
        captured = {}

        def fake_validate(self):
            captured["steps"] = self.workflow_steps

        steps = [{"name": "make", "environment": "python:3.11"}]
        reana_yaml = {
            "workflow": {
                "type": "snakemake",
                "file": "Snakefile",
                "specification": {"steps": steps},
            },
        }
        with patch.object(
            EnvironmentValidatorSnakemake, "validate", fake_validate
        ), patch.object(EnvironmentValidatorSnakemake, "display_messages"):
            validate_environment(reana_yaml)
        assert captured["steps"] == steps
