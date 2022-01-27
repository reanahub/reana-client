# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2022 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""REANA client compute backend validation."""

import sys
from typing import Dict, List, Optional

from reana_client.printer import display_message


def validate_compute_backends(
    reana_yaml: Dict, supported_backends: Optional[List[str]]
) -> None:
    """Validate compute backends in REANA specification file according to workflow type.

    :param reana_yaml: dictionary which represents REANA specification file.
    :param supported_backends: a list of the supported compute backends.
    """

    def build_validator(workflow: Dict) -> None:
        workflow_type = workflow["type"]
        if workflow_type == "serial":
            workflow_steps = workflow["specification"]["steps"]
            return SerialComputeBackendValidator(
                workflow_steps=workflow_steps, supported_backends=supported_backends
            )
        if workflow_type == "yadage":
            workflow_steps = workflow["specification"]["stages"]
            return YadageComputeBackendValidator(
                workflow_steps=workflow_steps, supported_backends=supported_backends
            )
        if workflow_type == "cwl":
            workflow_steps = workflow.get("specification", {}).get("$graph", workflow)
            return CWLComputeBackendValidator(
                workflow_steps=workflow_steps, supported_backends=supported_backends
            )
        if workflow_type == "snakemake":
            workflow_steps = workflow["specification"]["steps"]
            return SnakemakeComputeBackendValidator(
                workflow_steps=workflow_steps, supported_backends=supported_backends
            )

    workflow = reana_yaml["workflow"]
    validator = build_validator(workflow)
    validator.validate()
    display_message(
        "Workflow compute backends appear to be valid.",
        msg_type="success",
        indented=True,
    )


class ComputeBackendValidatorBase:
    """REANA workflow compute backend validation base class."""

    def __init__(
        self,
        workflow_steps: Optional[List[Dict]] = None,
        supported_backends: Optional[List[str]] = [],
    ):
        """Validate compute backends in REANA workflow steps.

        :param workflow_steps: list of dictionaries which represents different steps involved in workflow.
        :param supported_backends: a list of the supported compute backends.
        """
        self.workflow_steps = workflow_steps
        self.supported_backends = supported_backends
        self.messages = []

    def validate(self) -> None:
        """Validate compute backends in REANA workflow."""
        raise NotImplementedError

    def display_error_message(self, compute_backend: str, step_name: str) -> None:
        """Display validation error message and exit."""
        message = (
            f'Compute backend "{compute_backend}" found in step "{step_name}" is not supported. '
            f'List of supported compute backends: "{", ".join(self.supported_backends)}"'
        )
        display_message(message, msg_type="error", indented=True)
        sys.exit(1)


class SerialComputeBackendValidator(ComputeBackendValidatorBase):
    """REANA serial workflow compute backend validation."""

    def validate(self) -> None:
        """Validate compute backends in REANA serial workflow."""
        for step in self.workflow_steps:
            backend = step.get("compute_backend")
            if backend and backend not in self.supported_backends:
                self.display_error_message(backend, step.get("name"))


class YadageComputeBackendValidator(ComputeBackendValidatorBase):
    """REANA Yadage workflow compute backend validation."""

    def validate(self) -> None:
        """Validate compute backends in REANA Yadage workflow."""

        def parse_stages(stages: Optional[List[Dict]]) -> None:
            """Extract compute backends in Yadage workflow steps."""
            for stage in stages:
                if "workflow" in stage["scheduler"]:
                    nested_stages = stage["scheduler"]["workflow"].get("stages", {})
                    parse_stages(nested_stages)
                else:
                    environment = stage["scheduler"]["step"]["environment"]
                    backend = next(
                        (
                            resource["compute_backend"]
                            for resource in environment.get("resources", [])
                            if "compute_backend" in resource
                        ),
                        None,
                    )
                    if backend and backend not in self.supported_backends:
                        self.display_error_message(backend, stage["name"])

        return parse_stages(self.workflow_steps)


class CWLComputeBackendValidator(ComputeBackendValidatorBase):
    """REANA CWL workflow compute backend validation."""

    def validate(self) -> None:
        """Validate compute backends in REANA CWL workflow."""

        def _validate_compute_backends(workflow: Dict) -> None:
            """Validate compute backends in REANA CWL workflow steps."""
            steps = workflow.get("steps", [])
            for step in steps:
                hints = step.get("hints", [{}]).pop()
                backend = hints.get("compute_backend")
                if backend and backend not in self.supported_backends:
                    self.display_error_message(backend, step.get("id"))

        workflow = self.workflow_steps
        if isinstance(workflow, dict):
            _validate_compute_backends(workflow)
        elif isinstance(workflow, list):
            for wf in workflow:
                _validate_compute_backends(wf)


class SnakemakeComputeBackendValidator(ComputeBackendValidatorBase):
    """REANA Snakemake workflow compute backend validation."""

    def validate(self) -> None:
        """Validate compute backends in REANA Snakemake workflow."""
        for idx, step in enumerate(self.workflow_steps):
            backend = step.get("compute_backend")
            if backend and backend not in self.supported_backends:
                step_name = step.get("name", str(idx))
                self.display_error_message(backend, step_name)
