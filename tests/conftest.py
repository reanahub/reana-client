# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2017, 2018, 2020, 2021, 2022, 2023 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""Pytest configuration for REANA client."""

from __future__ import absolute_import, print_function

import textwrap

import pytest
from typing import Dict


@pytest.fixture()
def create_yaml_workflow_schema() -> str:
    """Return dummy YAML workflow schema."""
    reana_yaml_schema = """
        version: 0.7.2
        inputs:
          files:
            - code/helloworld.py
            - inputs/names.txt
          parameters:
            sleeptime: 2
            inputfile: inputs/names.txt
            helloworld: code/helloworld.py
            outputfile: outputs/greetings.txt
        outputs:
          files:
           - outputs/greetings.txt
        workflow:
          type: serial
          specification:
            steps:
              - environment: 'python:2.7'
                commands:
                  - python "${helloworld}" --sleeptime ${sleeptime} \
                  --inputfile "${inputfile}" --outputfile "${outputfile}"
        """
    return reana_yaml_schema


@pytest.fixture()
def create_yaml_workflow_schema_with_workspace(create_yaml_workflow_schema: str) -> str:
    """Return dummy YAML workflow schema with `/var/reana` workspace."""
    reana_yaml_schema = f"""
        {create_yaml_workflow_schema}
        workspace:
          root_path: /var/reana
        """
    return reana_yaml_schema


@pytest.fixture()
def get_workflow_specification_with_directory() -> Dict:
    """Return dummy workflow specification with "data" directory listed in inputs."""
    reana_yaml_schema = {
        "inputs": {
            "directories": ["data"],
        },
        "version": "0.3.0",
        "workflow": {
            "specification": {
                "steps": [
                    {"commands": ["echo hello"], "environment": "python:2.7-slim"}
                ]
            },
            "type": "serial",
        },
    }
    return {"specification": reana_yaml_schema}


@pytest.fixture()
def create_cwl_yaml_workflow_schema():
    """Return dummy CWL workflow schema."""
    reana_cwl_yaml_schema = """
        version: 0.7.2
        workflow:
          type: cwl
          file: main.cwl
        outputs:
          files:
            - foo/bar
        """
    return reana_cwl_yaml_schema


@pytest.fixture()
def cwl_workflow_spec_step():
    """Return dummy CWL workflow loaded spec step."""
    cwl_workflow_spec_step = """
        #!/usr/bin/env cwl-runner

        cwlVersion: v1.0
        class: Workflow

        inputs:
          outputfile:
            type: string
            inputBinding:
              prefix: --outputfile

        outputs:
          result:
            type: File
            outputSource: first/result

        steps:
          first:
            run: test.tool
            in:
              outputfile: outputfile
            out: [result]
        """
    return cwl_workflow_spec_step


@pytest.fixture()
def create_snakemake_yaml_external_input_workflow_schema():
    """Return dummy schema for a Snakemake workflow with external parameters."""
    reana_cwl_yaml_schema = """
        inputs:
          parameters:
            input: config.yaml
        workflow:
          type: snakemake
          file: Snakefile
        outputs:
          files:
            - foo.txt
        """
    return reana_cwl_yaml_schema


@pytest.fixture()
def snakemake_workflow_spec_step_param():
    """Return dummy Snakemake workflow loaded spec."""
    snakefile = textwrap.dedent(
        """
        rule foo:
            params:
                param1=config["param1"],
                param2=config["param2"],
            output:
                "foo.txt"
    """
    )
    return snakefile


@pytest.fixture()
def external_parameter_yaml_file():
    """Return dummy external parameter YAML file."""
    config_yaml = """
        param1: 200
        param2: 300
        """
    return config_yaml


@pytest.fixture()
def cwl_workflow_spec_correct_input_param():
    """Return correct dummy CWL workflow loaded spec."""
    cwl_workflow_spec = """
        #!/usr/bin/env cwl-runner

        cwlVersion: v1.0
        class: CommandLineTool

        baseCommand: python

        inputs:
          outputfile:
            type: string
            inputBinding:
              prefix: --outputfile

        outputs:
          result:
            type: File
            outputBinding:
              glob: $(inputs.outputfile)
        """
    return cwl_workflow_spec


@pytest.fixture()
def cwl_workflow_spec_wrong_input_param():
    """Return wrong dummy CWL workflow loaded spec."""
    cwl_workflow_spec = """
        #!/usr/bin/env cwl-runner

        cwlVersion: v1.0
        class: CommandLineTool

        baseCommand: python

        inputs:
          xoutputfile:  # wrong input param
            type: string
            inputBinding:
              prefix: --outputfile

        outputs:
          result:
            type: File
            outputBinding:
              glob: $(inputs.outputfile)
        """
    return cwl_workflow_spec


@pytest.fixture()
def cwl_workflow_spec_loaded():
    """Return dummy CWL workflow loaded spec."""
    cwl_workflow_spec = {
        "workflow": {
            "type": "cwl",
            "specification": {
                "$graph": [
                    {
                        "class": "Workflow",
                        "inputs": [
                            {
                                "type": "string",
                                "inputBinding": {"prefix": "--outputfile"},
                                "id": "#main/outputfile",
                            }
                        ],
                        "outputs": [
                            {
                                "type": "File",
                                "outputSource": "#main/first/result",
                                "id": "#main/result",
                            }
                        ],
                        "steps": [
                            {
                                "run": "#test.tool",
                                "in": [
                                    {
                                        "source": "#main/outputfile",
                                        "id": "#main/first/outputfile",
                                    }
                                ],
                                "out": ["#main/first/result"],
                                "id": "#main/first",
                            }
                        ],
                        "id": "#main",
                    },
                    {
                        "class": "CommandLineTool",
                        "baseCommand": "python",
                        "inputs": [
                            {
                                "type": "string",
                                "inputBinding": {"prefix": "--outputfile"},
                                "id": "#test.tool/outputfile",
                            }
                        ],
                        "outputs": [
                            {
                                "type": "File",
                                "outputBinding": {"glob": "$(inputs.outputfile)"},
                                "id": "#test.tool/result",
                            }
                        ],
                        "id": "#test.tool",
                    },
                ]
            },
        }
    }
    return cwl_workflow_spec


@pytest.fixture()
def spec_without_inputs():
    """REANA specification without `inputs`."""
    return {
        "workflow": {
            "type": "serial",
            "steps": [
                {"environment": "registry.example.org/foo/bar", "commands": ["sleep"]}
            ],
        }
    }
