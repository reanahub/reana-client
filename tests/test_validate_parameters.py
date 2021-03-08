# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2021 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""REANA client validate parameters tests."""

import pytest
import yaml

from reana_client.validation import (
    _validate_dangerous_operations,
    _validate_serial_parameters,
)


def test_validate_parameters_serial(create_yaml_workflow_schema, capsys):
    """Validate parameters for Serial workflows."""
    reana_yaml = yaml.load(create_yaml_workflow_schema, Loader=yaml.FullLoader)
    _validate_serial_parameters(reana_yaml)
    captured = capsys.readouterr()
    assert not captured.out

    # Input parameter not being used
    reana_yaml["inputs"]["parameters"]["foo"] = "foo"
    _validate_serial_parameters(reana_yaml)
    captured = capsys.readouterr()
    assert 'WARNING: REANA input parameter "foo" is not being used' in captured.out
    del reana_yaml["inputs"]["parameters"]["foo"]

    # Escaped env vars don't trigger validation warning
    reana_yaml["workflow"]["specification"]["steps"].append(
        {"commands": [r"$\{SHELL\} -c echo foo"]}
    )
    _validate_serial_parameters(reana_yaml)
    captured = capsys.readouterr()
    assert not captured.out

    # Parameter in unnamed step not defined
    reana_yaml["workflow"]["specification"]["steps"].append(
        {"commands": ["python ${foo} --bar"]}
    )
    _validate_serial_parameters(reana_yaml)
    captured = capsys.readouterr()
    assert (
        'WARNING: Serial parameter "foo" found on step "2" is not defined in input parameters'
        in captured.out
    )

    # Parameter not defined in named step
    reana_yaml["workflow"]["specification"]["steps"].append(
        {"commands": ["python ${bar} --foo"], "name": "baz"}
    )
    _validate_serial_parameters(reana_yaml)
    captured = capsys.readouterr()
    assert (
        'WARNING: Serial parameter "bar" found on step "baz" is not defined in input parameters'
        in captured.out
    )

    # Parameter not defined in two named steps
    reana_yaml["workflow"]["specification"]["steps"].append(
        {"commands": ["python ${bar} --foo"], "name": "qux"}
    )
    _validate_serial_parameters(reana_yaml)
    captured = capsys.readouterr()
    assert 'WARNING: Serial parameter "bar" found on steps' in captured.out
    assert "baz, qux" in captured.out or "qux, baz" in captured.out
    assert "is not defined in input parameters" in captured.out


@pytest.mark.parametrize(
    "command, step, warning",
    [
        ("python foo.py", "gendata", ""),
        (
            "sudo python foo.py",
            "fitdata",
            '"sudo" found in step "fitdata" might be dangerous.',
        ),
        (
            'echo "hello world!" && sudo python foo.py',
            "fitdata",
            '"sudo" found in step "fitdata" might be dangerous.',
        ),
        (
            "cd /foo && npm install",
            "installation",
            '"cd /" found in step "installation" might be dangerous.',
        ),
    ],
)
def test_validate_dangerous_operations(command, step, warning, capsys):
    """Validate if dangerous operations in a command trigger a warning."""
    _validate_dangerous_operations(command, step)
    captured = capsys.readouterr()
    assert warning in captured.out
