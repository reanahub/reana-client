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
from click.testing import CliRunner

from reana_client.utils import cwl_load
from reana_client.validation.parameters import (
    SerialParameterValidator,
    validate_parameters,
)


def test_validate_parameters_cwl(
    create_cwl_yaml_workflow_schema,
    cwl_workflow_spec_step,
    cwl_workflow_spec_correct_input_param,
    cwl_workflow_spec_wrong_input_param,
    capsys,
):
    """Validate parameters for CWL workflows."""
    runner = CliRunner()
    workflow_type = "cwl"

    def get_loaded_yaml(step_spec, input_spec):
        with open("main.cwl", "w") as f:
            f.write(step_spec)
        with open("test.tool", "w") as g:
            g.write(input_spec)
        reana_yaml = yaml.load(create_cwl_yaml_workflow_schema, Loader=yaml.FullLoader)
        reana_yaml["workflow"]["specification"] = cwl_load(
            reana_yaml["workflow"].get("file")
        )
        return reana_yaml

    with runner.isolated_filesystem():
        reana_yaml = get_loaded_yaml(
            cwl_workflow_spec_step, cwl_workflow_spec_correct_input_param
        )
        validate_parameters(workflow_type, reana_yaml)
        captured = capsys.readouterr()
        assert "SUCCESS: Workflow operations appear valid." in captured.out

    # Wrong Input parameter used
    with runner.isolated_filesystem():
        reana_yaml = get_loaded_yaml(
            cwl_workflow_spec_step, cwl_workflow_spec_wrong_input_param
        )
        with pytest.raises(SystemExit) as exc_info:
            validate_parameters(workflow_type, reana_yaml)
        assert (
            "Step is missing required parameter 'xoutputfile'" in exc_info.value.args[0]
        )

    # Wrong file path used
    reana_yaml = yaml.load(create_cwl_yaml_workflow_schema, Loader=yaml.FullLoader)
    with pytest.raises(SystemExit) as exc_info:
        validate_parameters(workflow_type, reana_yaml)
    captured = capsys.readouterr()
    assert "ERROR: Workflow path main.cwl is not valid." in captured.err


def test_validate_parameters_serial(create_yaml_workflow_schema, capsys):
    """Validate parameters for Serial workflows."""
    reana_yaml = yaml.load(create_yaml_workflow_schema, Loader=yaml.FullLoader)
    workflow_type = "serial"
    validate_parameters(workflow_type, reana_yaml)
    captured = capsys.readouterr()
    assert "Workflow parameters and commands appear valid." in captured.out

    # Input parameter not being used
    reana_yaml["inputs"]["parameters"]["foo"] = "foo"
    validate_parameters(workflow_type, reana_yaml)
    captured = capsys.readouterr()
    assert (
        'WARNING: REANA input parameter "foo" does not seem to be used' in captured.out
    )
    del reana_yaml["inputs"]["parameters"]["foo"]

    # Escaped env vars don't trigger validation warning
    reana_yaml["workflow"]["specification"]["steps"].append(
        {"commands": [r"$\{SHELL\} -c echo foo"]}
    )
    validate_parameters(workflow_type, reana_yaml)
    captured = capsys.readouterr()
    assert "Workflow parameters and commands appear valid." in captured.out

    # Parameter in unnamed step not defined
    reana_yaml["workflow"]["specification"]["steps"].append(
        {"commands": ["python ${foo} --bar"]}
    )
    validate_parameters(workflow_type, reana_yaml)
    captured = capsys.readouterr()
    assert (
        'WARNING: Serial parameter "foo" found on step "2" is not defined in input parameters'
        in captured.out
    )

    # Parameter not defined in named step
    reana_yaml["workflow"]["specification"]["steps"].append(
        {"commands": ["python ${bar} --foo"], "name": "baz"}
    )
    validate_parameters(workflow_type, reana_yaml)
    captured = capsys.readouterr()
    assert (
        'WARNING: Serial parameter "bar" found on step "baz" is not defined in input parameters'
        in captured.out
    )

    # Parameter not defined in two named steps
    reana_yaml["workflow"]["specification"]["steps"].append(
        {"commands": ["python ${bar} --foo"], "name": "qux"}
    )
    validate_parameters(workflow_type, reana_yaml)
    captured = capsys.readouterr()
    assert 'WARNING: Serial parameter "bar" found on steps' in captured.out
    assert "baz, qux" in captured.out or "qux, baz" in captured.out
    assert "is not defined in input parameters" in captured.out


def test_validate_parameters_yadage(yadage_workflow_spec_loaded, capsys):
    """Validate parameters for Yadage workflows."""
    reana_yaml = yadage_workflow_spec_loaded
    workflow_type = "yadage"
    validate_parameters(workflow_type, reana_yaml)
    captured = capsys.readouterr()
    assert "Workflow parameters and commands appear valid." in captured.out

    # REANA input parameter not being used.
    reana_yaml["inputs"]["parameters"]["qux"] = "qux_val"
    validate_parameters(workflow_type, reana_yaml)
    captured = capsys.readouterr()
    assert (
        'WARNING: REANA input parameter "qux" does not seem to be used' in captured.out
    )
    del reana_yaml["inputs"]["parameters"]["qux"]

    # Yadage parameter not being used.
    reana_yaml["workflow"]["specification"]["stages"][0]["scheduler"][
        "parameters"
    ].append(
        {
            "key": "qux",
            "value": {
                "step": "init",
                "output": "qux",
                "expression_type": "stage-output-selector",
            },
        }
    )
    validate_parameters(workflow_type, reana_yaml)
    captured = capsys.readouterr()
    assert (
        'WARNING: Yadage input parameter "qux" found on step "gendata" does not seem to be used.'
        in captured.out
    )
    reana_yaml["workflow"]["specification"]["stages"][0]["scheduler"][
        "parameters"
    ].pop()

    # Parameter not defined in step
    process = reana_yaml["workflow"]["specification"]["stages"][0]["scheduler"]["step"][
        "process"
    ]
    process["script"] += " && ./run-job {my_job}"

    validate_parameters(workflow_type, reana_yaml)
    captured = capsys.readouterr()
    assert (
        'WARNING: Yadage parameter "my_job" found on step "gendata" is not defined in input parameters'
        in captured.out
    )

    # Parameter not defined in two steps
    process = reana_yaml["workflow"]["specification"]["stages"][1]["scheduler"]["step"][
        "process"
    ]
    process["script"] += " && ./run-job {my_job}"

    validate_parameters(workflow_type, reana_yaml)
    captured = capsys.readouterr()
    assert 'WARNING: Yadage parameter "my_job" found on steps' in captured.out
    assert "gendata, fitdata" in captured.out or "fitdata, gendata" in captured.out
    assert "is not defined in input parameters" in captured.out

    # Yadage parameter defined in sub-step not being used.
    subworkflow = reana_yaml["workflow"]["specification"]["stages"][2]["scheduler"]
    subworkflow["workflow"]["stages"][0]["scheduler"]["parameters"].append(
        {"key": "subfoo", "value": "subfoo_val"}
    )
    validate_parameters(workflow_type, reana_yaml)
    captured = capsys.readouterr()
    assert (
        'WARNING: Yadage input parameter "subfoo" found on step "nested_step" does not seem to be used.'
        in captured.out
    )

    # Use previous parameter in command
    process = subworkflow["workflow"]["stages"][0]["scheduler"]["step"]["process"]
    process["script"] += " && go run {subfoo}"
    validate_parameters(workflow_type, reana_yaml)
    captured = capsys.readouterr()
    assert "subfoo" not in captured.out

    # Parameter not defined in sub-step
    process = subworkflow["workflow"]["stages"][0]["scheduler"]["step"]["process"]
    process["script"] += " && go run {subbar}"
    validate_parameters(workflow_type, reana_yaml)
    captured = capsys.readouterr()
    assert (
        'WARNING: Yadage parameter "subbar" found on step "nested_step" is not defined in input parameters'
        in captured.out
    )

    # Parameter defined in one stage, but forgotten in the other one
    process = reana_yaml["workflow"]["specification"]["stages"][1]["scheduler"]["step"][
        "process"
    ]
    process["script"] += " && ./run-job {foo}"
    validate_parameters(workflow_type, reana_yaml)
    captured = capsys.readouterr()
    assert (
        'WARNING: Yadage parameter "foo" found on step "fitdata" is not defined in input parameters.'
        in captured.out
    )


@pytest.mark.parametrize(
    "commands, step, warning",
    [
        (["python foo.py"], "gendata", ""),
        (
            ["python foo.py", "sudo python foo.py"],
            "fitdata",
            '"sudo" found in step "fitdata" might be dangerous.',
        ),
        (
            ['echo "hello world!" && sudo python foo.py'],
            "fitdata",
            '"sudo" found in step "fitdata" might be dangerous.',
        ),
        (
            ["cd /foo && npm install", 'echo "hello world!"'],
            "installation",
            '"cd /" found in step "installation" might be dangerous.',
        ),
        (["sudo npm install"], None, '"sudo" might be dangerous.',),
    ],
)
def test_validate_dangerous_operations(commands, step, warning, capsys):
    """Validate if dangerous operations in a command trigger a warning."""
    validator = SerialParameterValidator({})
    validator._validate_dangerous_operations(commands, step=step)
    warnings = validator.operations_warnings
    assert warning in (warnings.pop()["message"] if warnings else "")
