# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2017, 2018, 2021 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""Pytest configuration for REANA client."""

from __future__ import absolute_import, print_function

import pytest


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
