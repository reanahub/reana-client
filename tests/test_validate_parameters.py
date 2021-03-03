# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2021 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""REANA client validate parameters tests."""

import yaml

from reana_client.validation import validate_serial_parameters


def test_validate_parameters_serial(create_yaml_workflow_schema, capsys):
    """Validate parameters for Serial workflows."""
    reana_yaml = yaml.load(create_yaml_workflow_schema, Loader=yaml.FullLoader)
    validate_serial_parameters(reana_yaml)
    captured = capsys.readouterr()
    assert not captured.out

    # Input parameter not being used
    reana_yaml["inputs"]["parameters"]["foo"] = "foo"
    validate_serial_parameters(reana_yaml)
    captured = capsys.readouterr()
    assert 'WARNING: Input parameter "foo" is not being used' in captured.out
    del reana_yaml["inputs"]["parameters"]["foo"]

    # Escaped env vars don't trigger validation warning
    reana_yaml["workflow"]["specification"]["steps"].append(
        {"commands": [r"$\{SHELL\} -c echo foo"]}
    )
    validate_serial_parameters(reana_yaml)
    captured = capsys.readouterr()
    assert not captured.out

    # Parameter in unnamed step not defined
    reana_yaml["workflow"]["specification"]["steps"].append(
        {"commands": ["python ${foo} --bar"]}
    )
    validate_serial_parameters(reana_yaml)
    captured = capsys.readouterr()
    assert (
        'WARNING: Parameter "foo" found on step "2" is not defined in inputs parameters'
        in captured.out
    )

    # Parameter not defined in named step
    reana_yaml["workflow"]["specification"]["steps"].append(
        {"commands": ["python ${bar} --foo"], "name": "baz"}
    )
    validate_serial_parameters(reana_yaml)
    captured = capsys.readouterr()
    assert (
        'WARNING: Parameter "bar" found on step "baz" is not defined in inputs parameters'
        in captured.out
    )

    # Parameter not defined in two named steps
    reana_yaml["workflow"]["specification"]["steps"].append(
        {"commands": ["python ${bar} --foo"], "name": "qux"}
    )
    validate_serial_parameters(reana_yaml)
    captured = capsys.readouterr()
    assert (
        'WARNING: Parameter "bar" found on steps "baz, qux" is not defined in inputs parameters'
        in captured.out
    )
