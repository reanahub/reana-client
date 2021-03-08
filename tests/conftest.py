# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2017, 2018 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""Pytest configuration for REANA client."""

from __future__ import absolute_import, print_function

import pytest


@pytest.fixture()
def create_yaml_workflow_schema():
    """Return dummy yaml workflow schema."""
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
def yadage_workflow_spec_loaded():
    """Return dummy Yadage nested workflow spec loaded as dictionary."""
    return {
        "version": "0.7.2",
        "inputs": {
            "files": ["code/foo.C", "code/bar.C"],
            "directories": ["workflow/yadage"],
            "parameters": {"foo": "foo_val", "bar": "bar_val", "baz": "baz_val"},
        },
        "outputs": {"files": ["fitdata/plot.png"]},
        "workflow": {
            "type": "yadage",
            "file": "workflow/yadage/workflow.yaml",
            "specification": {
                "stages": [
                    {
                        "name": "gendata",
                        "dependencies": {
                            "dependency_type": "jsonpath_ready",
                            "expressions": ["init"],
                        },
                        "scheduler": {
                            "scheduler_type": "singlestep-stage",
                            "parameters": [
                                {
                                    "key": "foo",
                                    "value": {
                                        "step": "init",
                                        "output": "foo",
                                        "expression_type": "stage-output-selector",
                                    },
                                },
                                {
                                    "key": "bar",
                                    "value": {
                                        "step": "init",
                                        "output": "bar",
                                        "expression_type": "stage-output-selector",
                                    },
                                },
                            ],
                            "step": {
                                "process": {
                                    "process_type": "interpolated-script-cmd",
                                    "script": "python --foo '{foo}/{bar}'",
                                    "interpreter": "sh",
                                },
                                "publisher": {
                                    "publisher_type": "frompar-pub",
                                    "outputmap": {"data": "outfilename"},
                                },
                                "environment": {
                                    "environment_type": "docker-encapsulated",
                                    "image": "reanahub/reana-env-root6",
                                    "imagetag": "6.18.04",
                                    "resources": [],
                                    "envscript": "",
                                    "env": {},
                                    "workdir": None,
                                    "par_mounts": [],
                                },
                            },
                        },
                    },
                    {
                        "name": "fitdata",
                        "dependencies": {
                            "dependency_type": "jsonpath_ready",
                            "expressions": ["gendata"],
                        },
                        "scheduler": {
                            "scheduler_type": "singlestep-stage",
                            "parameters": [
                                {
                                    "key": "baz",
                                    "value": {
                                        "step": "init",
                                        "output": "baz",
                                        "expression_type": "stage-output-selector",
                                    },
                                },
                                {
                                    "key": "bar",
                                    "value": {
                                        "step": "gendata",
                                        "output": "bar",
                                        "expression_type": "stage-output-selector",
                                    },
                                },
                            ],
                            "step": {
                                "process": {
                                    "process_type": "interpolated-script-cmd",
                                    "script": 'root -b -q \'("{baz}","{bar}")\'',
                                    "interpreter": "sh",
                                },
                                "publisher": {
                                    "publisher_type": "frompar-pub",
                                    "outputmap": {"plot": "outfile"},
                                },
                                "environment": {
                                    "environment_type": "docker-encapsulated",
                                    "image": "reanahub/reana-env-root6",
                                    "imagetag": "6.18.04",
                                    "resources": [],
                                    "envscript": "",
                                    "env": {},
                                    "workdir": None,
                                    "par_mounts": [],
                                },
                            },
                        },
                    },
                    {
                        "name": "parent_step",
                        "dependencies": {
                            "dependency_type": "jsonpath_ready",
                            "expressions": [""],
                        },
                        "scheduler": {
                            "scheduler_type": "singlestep-stage",
                            "parameters": [
                                {
                                    "key": "nested_foo",
                                    "value": {
                                        "step": "init",
                                        "output": "nested_foo",
                                        "expression_type": "stage-output-selector",
                                    },
                                },
                            ],
                            "workflow": {
                                "stages": [
                                    {
                                        "name": "nested_step",
                                        "dependencies": {
                                            "dependency_type": "jsonpath_ready",
                                            "expressions": ["run_mc"],
                                        },
                                        "scheduler": {
                                            "scheduler_type": "singlestep-stage",
                                            "parameters": [
                                                {
                                                    "key": "inputs",
                                                    "value": {
                                                        "stages": "run_mc[*].mergeallvars",
                                                        "output": "mergedfile",
                                                        "expression_type": "stage-output-selector",
                                                    },
                                                },
                                                {
                                                    "key": "mergedfile",
                                                    "value": "{workdir}/merged.root",
                                                },
                                            ],
                                            "step": {
                                                "process": {
                                                    "process_type": "interpolated-script-cmd",
                                                    "interpreter": "bash",
                                                    "script": "source /usr/local/bin/{nested_foo}.sh\nhadd {mergedfile} {inputs}\n",
                                                },
                                                "environment": {
                                                    "environment_type": "docker-encapsulated",
                                                    "image": "reanahub/reana-env-root6",
                                                    "imagetag": "6.18.04",
                                                    "resources": [],
                                                    "envscript": "",
                                                    "env": {},
                                                    "workdir": None,
                                                    "par_mounts": [],
                                                },
                                                "publisher": {
                                                    "publisher_type": "frompar-pub",
                                                    "outputmap": {
                                                        "mergedfile": "mergedfile"
                                                    },
                                                },
                                            },
                                        },
                                    }
                                ]
                            },
                        },
                    },
                ]
            },
        },
    }
