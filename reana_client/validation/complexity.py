# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2021 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""REANA workflow complexity estimation."""

import os

from reana_client.printer import display_message


def estimate_complexity(workflow_type, reana_yaml):
    """Estimate complexity in REANA workflow.

    :param workflow_type: A supported workflow specification type.
    :param reana_yaml: REANA YAML specification.
    """

    def build_estimator(workflow_type, reana_yaml):
        if workflow_type == "serial":
            return SerialComplexityEstimator(reana_yaml)
        elif workflow_type == "yadage":
            return YadageComplexityEstimator(reana_yaml)
        elif workflow_type == "cwl":
            return CWLComplexityEstimator(reana_yaml)
        else:
            raise Exception(
                "Workflow type '{0}' is not supported".format(workflow_type)
            )

    estimator = build_estimator(workflow_type, reana_yaml)
    complexity = estimator.estimate_complexity()

    display_message(
        "Estimated workflow complexity: \n{0}".format(complexity),
        msg_type="info",
        indented=True,
    )


class ComplexityEstimatorBase:
    """REANA workflow complexity estimator base class."""

    def __init__(self, reana_yaml):
        """Estimate complexity in REANA workflow.

        :param reana_yaml: REANA YAML specification.
        :param initial_step: initial workflow execution step.
        """
        self.reana_yaml = reana_yaml
        self.specification = reana_yaml.get("workflow", {}).get("specification", {})
        self.input_params = reana_yaml.get("inputs", {}).get("parameters", {})

    def parse_specification(self, initial_step):
        """Parse REANA workflow specification tree."""
        raise NotImplementedError

    def estimate_complexity(self, initial_step="init"):
        """Estimate complexity in parsed REANA workflow tree."""
        steps = self.parse_specification(initial_step)
        return self._calculate_complexity(steps)

    def _calculate_complexity(self, steps):
        """Calculate complexity in parsed REANA workflow tree."""
        complexity = []
        for step in steps.values():
            complexity += step["complexity"]
        return complexity

    def _get_number_of_jobs(self, step):
        """Get number of jobs based on compute backend."""
        backend = step.get("compute_backend")
        if backend and backend != "kubernetes":
            return 0
        return 1

    def _get_memory_limit(self, step):
        """Get memory limit value."""
        # TODO: convert memory limit value to bytes (`kubernetes_memory_to_bytes`)
        # TODO: validate memory limit value. Reuse code from (`set_memory_limit` in RJC)
        # TODO: get `default_memory_limit` from config
        default_memory_limit = os.getenv("REANA_KUBERNETES_JOBS_MEMORY_LIMIT", "8Gi")
        return step.get("kubernetes_memory_limit", default_memory_limit)


class SerialComplexityEstimator(ComplexityEstimatorBase):
    """REANA serial workflow complexity estimation."""

    def _parse_steps(self, steps):
        """Parse serial workflow specification tree."""
        tree = []
        for idx, step in enumerate(steps):
            name = step.get("name", str(idx))
            jobs = self._get_number_of_jobs(step)
            memory_limit = self._get_memory_limit(step)
            complexity = [(jobs, memory_limit)]
            tree.append({name: {"complexity": complexity}})
        return tree

    def parse_specification(self, initial_step):
        """Parse and filter out serial workflow specification tree."""
        spec_steps = self.specification.get("steps", [])
        steps = self._parse_steps(spec_steps)
        if initial_step == "init":
            return steps[0] if steps else {}
        return next(filter(lambda step: initial_step in step.keys(), steps), {})


class YadageComplexityEstimator(ComplexityEstimatorBase):
    """REANA Yadage workflow complexity estimation."""

    def _parse_steps(self, stages, initial_step):
        """Parse and filter out Yadage workflow tree."""

        def _is_initial_stage(stage):
            dependencies = stage.get("dependencies", {}).get("expressions", [])

            if dependencies == [initial_step]:
                return True

            if initial_step == "init":
                # Not defined dependencies should be treated as `init`
                return not dependencies
            return False

        def _get_stage_complexity(stage):
            resources = (
                stage.get("scheduler", {})
                .get("step", {})
                .get("environment", {})
                .get("resources", [])
            )
            compute_backend = next(
                filter(lambda r: "compute_backend" in r.keys(), resources), {},
            )
            k8s_memory_limit = next(
                filter(lambda r: "kubernetes_memory_limit" in r.keys(), resources), {},
            )
            jobs = self._get_number_of_jobs(compute_backend)
            memory_limit = self._get_memory_limit(k8s_memory_limit)
            return [(jobs, memory_limit)]

        def _parse_stages(stages):
            tree = {}
            for stage in stages:
                if not _is_initial_stage(stage):
                    continue
                name = stage["name"]
                scheduler = stage.get("scheduler", {})
                parameters = scheduler.get("parameters", [])
                tree[name] = {"params": parameters, "stages": {}, "scatter_params": []}

                # Parse stage complexity
                tree[name]["complexity"] = _get_stage_complexity(stage)

                # Parse nested stages
                if "workflow" in scheduler:
                    nested_stages = scheduler["workflow"].get("stages", [])
                    parsed_stages = _parse_stages(nested_stages)
                    tree[name]["stages"].update(parsed_stages)

                # Parse scatter parameters
                if "scatter" in scheduler and scheduler["scatter"]["method"] == "zip":
                    tree[name]["scatter_params"] = scheduler["scatter"]["parameters"]

            return tree

        return _parse_stages(stages)

    def _populate_parameters(self, stages, parent_params):
        """Populate parsed Yadage workflow tree with parameter values."""

        def _parse_params(stage, parent_params):
            parent_params = parent_params.copy()
            for param in stage["params"]:
                if isinstance(param["value"], list):
                    parent_params[param["key"]] = param["value"]
                elif isinstance(param["value"], dict):
                    # Example: input_file: {step: init, output: files}
                    # In this case `files` values should be taken from
                    # `parent_params` and saved as `input_file`
                    output = param["value"].get("output", "")
                    parent_value = parent_params.get(output, "")
                    parent_params[param["key"]] = parent_value
                else:
                    parent_params[param["key"]] = [param["value"]]
            return parent_params

        def _parse_stages(stages, parent_params):
            stages = stages.copy()
            for stage in stages.keys():
                stage_value = stages[stage]
                # Handle params
                params = _parse_params(stage_value, parent_params)
                stage_value["params"] = params
                # Handle nested stages
                stage_value["stages"] = _parse_stages(stage_value["stages"], params)
            return stages

        return _parse_stages(stages, parent_params)

    def _populate_complexity(self, stages):
        """Calculate number of jobs and memory needed for the parsed Yadage workflow tree."""

        def _parse_stages(stages):
            stages = stages.copy()
            for stage in stages.keys():
                stage_value = stages[stage]
                complexity = stage_value["complexity"]

                # Handle nested stages
                parsed_stages = _parse_stages(stage_value["stages"])
                stage_value["stages"] = parsed_stages
                if parsed_stages:
                    complexity = self._calculate_complexity(parsed_stages)

                # Handle scatter parameters
                if stage_value["scatter_params"]:
                    first_param = stage_value["scatter_params"][0]
                    param_len = len(stage_value["params"].get(first_param, []))
                    complexity = [(item[0] * param_len, item[1]) for item in complexity]

                stage_value["complexity"] = complexity
            return stages

        return _parse_stages(stages)

    def parse_specification(self, initial_step):
        """Parse Yadage workflow specification tree."""
        steps = self._parse_steps(self.specification["stages"], initial_step)
        steps = self._populate_parameters(steps, self.input_params)
        steps = self._populate_complexity(steps)
        return steps


class CWLComplexityEstimator(ComplexityEstimatorBase):
    """REANA CWL workflow complexity estimation."""

    def parse_specification(self, initial_step):
        """Parse CWL workflow specification tree."""
        return {}
