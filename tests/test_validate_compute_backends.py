# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2022 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""REANA client validate compute backends tests."""

import pytest
import yaml

from reana_commons.errors import REANAValidationError
from reana_commons.validation.compute_backends import (
    ComputeBackendValidatorSerial,
    ComputeBackendValidatorYadage,
    ComputeBackendValidatorSnakemake,
    ComputeBackendValidatorCWL,
)

from reana_client.validation.compute_backends import validate_compute_backends


@pytest.mark.parametrize(
    "compute_backend, supported_backends, valid",
    [
        ("kubernetes", ["kubernetes", "htcondorcern"], True),
        ("kubernetes", ["kubernetes"], True),
        ("slurmcern", ["kubernetes", "slurmcern"], True),
        ("slurmcern", ["kubernetes", "htcondorcern"], False),
        ("htcondorcern", ["kubernetes"], False),
    ],
)
def test_validate_compute_backends_serial(
    compute_backend, supported_backends, valid, create_yaml_workflow_schema, capsys
):
    """Validate compute backends for Serial workflows."""
    reana_yaml = yaml.load(create_yaml_workflow_schema, Loader=yaml.FullLoader)
    workflow_steps = reana_yaml["workflow"]["specification"]["steps"]
    workflow_steps[0]["compute_backend"] = compute_backend

    if valid:
        validate_compute_backends(reana_yaml, supported_backends)
        captured = capsys.readouterr()
        assert "SUCCESS: Workflow compute backends appear to be valid." in captured.out
    else:
        validator = ComputeBackendValidatorSerial(
            workflow_steps=workflow_steps, supported_backends=supported_backends
        )
        with pytest.raises(REANAValidationError) as e:
            validator.validate()
        assert "is not supported." in e.value.message


@pytest.mark.parametrize(
    "compute_backend, supported_backends, valid",
    [
        ("kubernetes", ["kubernetes", "htcondorcern"], True),
        ("kubernetes", ["kubernetes"], True),
        ("slurmcern", ["kubernetes", "slurmcern"], True),
        ("slurmcern", ["kubernetes", "htcondorcern"], False),
        ("htcondorcern", ["kubernetes"], False),
    ],
)
def test_validate_compute_backends_yadage(
    compute_backend, supported_backends, valid, yadage_workflow_spec_loaded, capsys
):
    """Validate compute backends for Yadage workflows."""
    reana_yaml = yadage_workflow_spec_loaded
    workflow_steps = reana_yaml["workflow"]["specification"]["stages"]
    workflow_steps[1]["scheduler"]["step"]["environment"]["resources"].append(
        {"compute_backend": compute_backend}
    )

    if valid:
        validate_compute_backends(reana_yaml, supported_backends)
        captured = capsys.readouterr()
        assert "SUCCESS: Workflow compute backends appear to be valid." in captured.out
    else:
        validator = ComputeBackendValidatorYadage(
            workflow_steps=workflow_steps, supported_backends=supported_backends
        )
        with pytest.raises(REANAValidationError) as e:
            validator.validate()
        assert "is not supported." in e.value.message


@pytest.mark.parametrize(
    "compute_backend, supported_backends, valid",
    [
        ("kubernetes", ["kubernetes", "htcondorcern"], True),
        ("kubernetes", ["kubernetes"], True),
        ("slurmcern", ["kubernetes", "slurmcern"], True),
        ("slurmcern", ["kubernetes", "htcondorcern"], False),
        ("htcondorcern", ["kubernetes"], False),
    ],
)
def test_validate_compute_backends_snakemake(
    compute_backend, supported_backends, valid, snakemake_workflow_spec_loaded, capsys
):
    """Validate compute backends for Snakemake workflows."""
    reana_yaml = snakemake_workflow_spec_loaded
    workflow_steps = reana_yaml["workflow"]["specification"]["steps"]
    workflow_steps[0]["compute_backend"] = compute_backend

    if valid:
        validate_compute_backends(reana_yaml, supported_backends)
        captured = capsys.readouterr()
        assert "SUCCESS: Workflow compute backends appear to be valid." in captured.out
    else:
        validator = ComputeBackendValidatorSnakemake(
            workflow_steps=workflow_steps, supported_backends=supported_backends
        )
        with pytest.raises(REANAValidationError) as e:
            validator.validate()
        assert "is not supported." in e.value.message


@pytest.mark.parametrize(
    "compute_backend, supported_backends, valid",
    [
        ("kubernetes", ["kubernetes", "htcondorcern"], True),
        ("kubernetes", ["kubernetes"], True),
        ("slurmcern", ["kubernetes", "slurmcern"], True),
        ("slurmcern", ["kubernetes", "htcondorcern"], False),
        ("htcondorcern", ["kubernetes"], False),
    ],
)
def test_validate_compute_backends_cwl(
    compute_backend,
    supported_backends,
    valid,
    cwl_workflow_spec_loaded,
    capsys,
):
    """Validate compute backends for CWL workflows."""
    reana_yaml = cwl_workflow_spec_loaded
    workflow_steps = reana_yaml["workflow"]["specification"]["$graph"]
    workflow_steps[0]["steps"][0]["hints"] = [
        {"class": "reana", "compute_backend": compute_backend}
    ]

    if valid:
        validate_compute_backends(reana_yaml, supported_backends)
        captured = capsys.readouterr()
        assert "SUCCESS: Workflow compute backends appear to be valid." in captured.out
    else:
        validator = ComputeBackendValidatorCWL(
            workflow_steps=workflow_steps, supported_backends=supported_backends
        )
        with pytest.raises(REANAValidationError) as e:
            validator.validate()
        assert "is not supported." in e.value.message
