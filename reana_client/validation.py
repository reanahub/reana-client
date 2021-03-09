# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2021 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""REANA client validation functions."""

import datetime
import logging
import re
import subprocess
import sys
import traceback
from collections import defaultdict
from itertools import chain

import click
import requests
from reana_commons.config import WORKFLOW_RUNTIME_USER_GID, WORKFLOW_RUNTIME_USER_UID

from reana_client.config import (
    COMMAND_DANGEROUS_OPERATIONS,
    DOCKER_REGISTRY_INDEX_URL,
    ENVIRONMENT_IMAGE_SUSPECTED_TAGS_VALIDATOR,
)


def validate_environment(reana_yaml):
    """Validate environments in REANA specification file according to workflow type.

    :param reana_yaml: Dictionary which represents REANA specifications file.
    """
    workflow_type = reana_yaml["workflow"]["type"]

    if workflow_type == "serial":
        workflow_steps = reana_yaml["workflow"]["specification"]["steps"]
        _validate_serial_workflow_environment(workflow_steps)
    elif workflow_type == "yadage":
        workflow_steps = reana_yaml["workflow"]["specification"]["stages"]
        _validate_yadage_workflow_environment(workflow_steps)
    elif workflow_type == "cwl":
        workflow_file = reana_yaml["workflow"].get("file")
        _validate_cwl_workflow_environment(workflow_file)


def _validate_yadage_workflow_environment(workflow_steps):
    """Validate environments in REANA yadage workflow.

    :param workflow_steps: List of dictionaries which represents different steps involved in workflow.
    :raises Warning: Warns user if the workflow environment is invalid in yadage workflow steps.
    """

    def traverse_yadage_workflow(stages):
        for stage in stages:
            if "workflow" in stage["scheduler"]:
                nested_stages = stage["scheduler"]["workflow"].get("stages", {})
                traverse_yadage_workflow(nested_stages)
            else:
                environment = stage["scheduler"]["step"]["environment"]
                _check_environment(environment)

    def _check_environment(environment):
        image = "{env[image]}:{env[imagetag]}".format(env=environment)
        image_name, image_tag = _validate_image_tag(image)
        _image_exists(image_name, image_tag)
        uid, gids = _get_image_uid_gids(image_name, image_tag)
        k8s_uid = next(
            (
                resource["kubernetes_uid"]
                for resource in environment.get("resources", [])
                if "kubernetes_uid" in resource
            ),
            None,
        )
        _validate_uid_gids(uid, gids, kubernetes_uid=k8s_uid)

    traverse_yadage_workflow(workflow_steps)


def _validate_cwl_workflow_environment(workflow_file):
    """Validate environments in REANA CWL workflow.

    :param workflow_file: Path to CWL workflow specification.
    :raises Warning: Warns user if the workflow environment is invalid in CWL workflow steps.
    """
    try:
        import cwl_utils.parser_v1_0 as cwl_parser
        from cwl_utils.docker_extract import traverse
    except ImportError as e:
        click.secho(
            "==> ERROR: Cannot validate environment. Please install reana-client on Python 3+ to enable environment validation for CWL workflows.",
            err=True,
            fg="red",
        )
        raise e

    top = cwl_parser.load_document(workflow_file)

    for image in traverse(top):
        image_name, image_tag = _validate_image_tag(image)
        _image_exists(image_name, image_tag)
        uid, gids = _get_image_uid_gids(image_name, image_tag)
        _validate_uid_gids(uid, gids)


def _validate_serial_workflow_environment(workflow_steps):
    """Validate environments in REANA serial workflow.

    :param workflow_steps: List of dictionaries which represents different steps involved in workflow.
    :raises Warning: Warns user if the workflow environment is invalid in serial workflow steps.
    """
    for step in workflow_steps:
        image = step["environment"]
        image_name, image_tag = _validate_image_tag(image)
        _image_exists(image_name, image_tag)
        uid, gids = _get_image_uid_gids(image_name, image_tag)
        _validate_uid_gids(uid, gids, kubernetes_uid=step.get("kubernetes_uid"))


def _validate_image_tag(image):
    """Validate if image tag is valid."""
    image_name, image_tag = "", ""
    has_warnings = False
    if ":" in image:
        environment = image.split(":", 1)
        image_name, image_tag = environment[0], environment[-1]
        if ":" in image_tag:
            click.secho(
                "==> ERROR: Environment image {} has invalid tag '{}'".format(
                    image_name, image_tag
                ),
                err=True,
                fg="red",
            )
            sys.exit(1)
        elif image_tag in ENVIRONMENT_IMAGE_SUSPECTED_TAGS_VALIDATOR:
            click.secho(
                "==> WARNING: Using '{}' tag is not recommended in {} environment image.".format(
                    image_tag, image_name
                ),
                fg="yellow",
            )
            has_warnings = True
    else:
        click.secho(
            "==> WARNING: Environment image {} does not have an explicit tag.".format(
                image
            ),
            fg="yellow",
        )
        has_warnings = True
        image_name = image
    if not has_warnings:
        click.echo(
            click.style(
                "==> Environment image {} has correct format.".format(image),
                fg="green",
            )
        )
    return image_name, image_tag


def _image_exists(image, tag):
    """Verify if image exists."""

    docker_registry_url = DOCKER_REGISTRY_INDEX_URL.format(image=image, tag=tag)
    # Remove traling slash if no tag was specified
    if not tag:
        docker_registry_url = docker_registry_url[:-1]
    try:
        response = requests.get(docker_registry_url)
    except requests.exceptions.RequestException as e:
        logging.error(traceback.format_exc())
        click.secho(
            "==> ERROR: Something went wrong when querying {}".format(
                docker_registry_url
            ),
            err=True,
            fg="red",
        )
        raise e

    if not response.ok:
        if response.status_code == 404:
            msg = response.text
            click.secho(
                "==> ERROR: Environment image {}{} does not exist: {}".format(
                    image, ":{}".format(tag) if tag else "", msg
                ),
                err=True,
                fg="red",
            )
        else:
            click.secho(
                "==> ERROR: Existence of environment image {}{} could not be verified. Status code: {} {}".format(
                    image,
                    ":{}".format(tag) if tag else "",
                    response.status_code,
                    response.reason,
                ),
                err=True,
                fg="red",
            )
        sys.exit(1)
    else:
        click.secho(
            "==> Environment image {}{} exists.".format(
                image, ":{}".format(tag) if tag else ""
            ),
            fg="green",
        )


def _get_image_uid_gids(image, tag):
    """Obtain environment image UID and GIDs.

    :returns: A tuple with UID and GIDs.
    """
    # Check if docker is installed.
    run_command("docker version", display=False, return_output=True)
    # Run ``id``` command inside the container.
    uid_gid_output = run_command(
        'docker run -i -t --rm {}{} bash -c "/usr/bin/id -u && /usr/bin/id -G"'.format(
            image, ":{}".format(tag) if tag else ""
        ),
        display=False,
        return_output=True,
    )
    ids = uid_gid_output.splitlines()
    uid, gids = (
        int(ids[-2]),
        [int(gid) for gid in ids[-1].split()],
    )
    return uid, gids


def _validate_uid_gids(uid, gids, kubernetes_uid=None):
    """Check whether container UID and GIDs are valid."""
    if WORKFLOW_RUNTIME_USER_GID not in gids:
        click.secho(
            "==> ERROR: Environment image GID must be {}. GIDs {} were found.".format(
                WORKFLOW_RUNTIME_USER_GID, gids
            ),
            err=True,
            fg="red",
        )
        sys.exit(1)
    if kubernetes_uid is not None:
        if kubernetes_uid != uid:
            click.secho(
                "==> WARNING: `kubernetes_uid` set to {}. UID {} was found.".format(
                    kubernetes_uid, uid
                ),
                fg="yellow",
            )
    elif uid != WORKFLOW_RUNTIME_USER_UID:
        click.secho(
            "==> WARNING: Environment image UID is recommended to be {}. UID {} was found.".format(
                WORKFLOW_RUNTIME_USER_UID, uid
            ),
            err=True,
            fg="yellow",
        )


def validate_parameters(workflow_type, reana_yaml):
    """Validate the presence of input parameters in workflow step commands and viceversa.

    :param workflow_type: A supported workflow specification type.
    :param reana_yaml: REANA YAML specification.
    """
    validate = {
        "yadage": _validate_yadage_parameters,
        "cwl": lambda *args: None,
        "serial": _validate_serial_parameters,
    }
    """Dictionary to extend with new workflow specification loaders."""
    if "inputs" not in reana_yaml:
        click.secho(
            '==> WARNING: Workflow "inputs" are missing in the REANA specification.',
            fg="yellow",
        )

    return validate[workflow_type](reana_yaml)


def _warn_not_used_params(workflow_parameters, command_parameters, type_="REANA"):
    """Warn user about defined workflow parameter not being used.

    :param workflow_params: Set of parameters in workflow definition.
    :param command_parameters: Set of parameters used inside workflow.
    :param type: Type of workflow parameters, e.g. REANA for input parameters, Yadage
                 for parameters defined in Yadage spec.
    """

    for param in workflow_parameters.difference(command_parameters):
        click.secho(
            '==> WARNING: {} input parameter "{}" is not being used.'.format(
                type_, param
            ),
            fg="yellow",
        )


def _warn_not_defined_params(cmd_param_steps_mapping, workflow_params, workflow_type):
    """Warn user about command parameters missing in workflow definition.

    :param cmd_param_steps_mapping: Mapping between command parameters and its step.
    :param workflow_params: Set of parameters in workflow definition.
    :param workflow_type: Workflow type being checked.
    """
    command_params = set(cmd_param_steps_mapping.keys())

    for param in command_params.difference(workflow_params):
        steps_used = cmd_param_steps_mapping[param]

        click.secho(
            '==> WARNING: {type} parameter "{param}" found on step{s} "{steps}" is not defined in input parameters.'.format(
                type=workflow_type.capitalize(),
                param=param,
                steps=", ".join(steps_used),
                s="s" if len(steps_used) > 1 else "",
            ),
            fg="yellow",
        )


def _validate_serial_parameters(reana_yaml):
    """Validate input parameters for Serial workflows.

    :param reana_yaml: REANA YAML specification.
    """

    def parse_command(command):
        return re.findall(r".*?\${(.*?)}.*?", command)

    # REANA input parameters
    input_parameters = set(reana_yaml.get("inputs", {}).get("parameters", {}).keys())

    cmd_param_steps_mapping = defaultdict(set)
    for idx, step in enumerate(
        reana_yaml["workflow"]["specification"].get("steps", [])
    ):
        step_name = step.get("name", str(idx))
        for command in step["commands"]:
            _validate_dangerous_operations(command, step_name)
            cmd_params = parse_command(command)
            for cmd_param in cmd_params:
                cmd_param_steps_mapping[cmd_param].add(step_name)

    command_parameters = set(cmd_param_steps_mapping.keys())

    _warn_not_used_params(input_parameters, command_parameters)
    _warn_not_defined_params(cmd_param_steps_mapping, input_parameters, "serial")


def _validate_yadage_parameters(reana_yaml):
    """Validate parameters for Yadage workflows.

    :param reana_yaml: REANA YAML specification.
    """

    def parse_command(command):
        return re.findall(r".*?\{+(.*?)\}+.*?", command)

    def parse_command_params(step_value):
        if isinstance(step_value, dict):
            step_value = list(step_value.values())

        if isinstance(step_value, list):
            step_value = [
                value.values() if isinstance(value, dict) else value
                for value in step_value
            ]
        return parse_command(str(step_value))

    def parse_params(stages):
        params = []
        cmd_param_steps_mapping = defaultdict(set)
        for stage in stages:
            step_name = stage["name"]
            if "workflow" in stage["scheduler"]:
                nested_stages = stage["scheduler"]["workflow"].get("stages", {})
                nested_params, nested_cmd_param_steps_mapping = parse_params(
                    nested_stages
                )
                params += nested_params
                for param, steps in nested_cmd_param_steps_mapping.items():
                    cmd_param_steps_mapping[param].update(steps)

            for param in stage["scheduler"]["parameters"]:
                params.append(param["key"])

            for step in stage["scheduler"].get("step", {}).keys():
                for step_key, step_val in stage["scheduler"]["step"][step].items():
                    if step_key == "script":
                        command = step_val
                        _validate_dangerous_operations(command, step_name)
                    step_commands_params = parse_command_params(step_val)
                    for command_param in step_commands_params:
                        cmd_param_steps_mapping[command_param].add(step_name)

        return params, cmd_param_steps_mapping

    # REANA input parameters
    input_parameters = set(reana_yaml["inputs"].get("parameters", {}).keys())

    # Yadage parameters
    workflow_spec = reana_yaml["workflow"]["specification"]
    workflow_params, cmd_param_steps_mapping = parse_params(workflow_spec["stages"])

    workflow_params = set(workflow_params)
    command_params = set(cmd_param_steps_mapping.keys())

    # REANA input parameters validation
    _warn_not_used_params(input_parameters, workflow_params)
    # Yadage parameters validation
    _warn_not_used_params(workflow_params, command_params, type_="Yadage")
    # Yadage command parameters validation
    _warn_not_defined_params(cmd_param_steps_mapping, workflow_params, "yadage")


def _validate_dangerous_operations(command, step):
    """Warn the user if a command has dangerous operations.

    :param command: A workflow step command to validate.
    :param step: The workflow step that contains the given command.
    """
    for operation in COMMAND_DANGEROUS_OPERATIONS:
        if operation in command:
            click.secho(
                '==> WARNING: Operation "{}" found in step "{}" might be dangerous.'.format(
                    operation.strip(), step
                ),
                fg="yellow",
            )


def run_command(cmd, display=True, return_output=False):
    """Run given command on shell in the current directory.

    Exit in case of troubles.

    :param cmd: shell command to run
    :param display: should we display command to run?
    :param return_output: shall the output of the command be returned?
    :type cmd: str
    :type display: bool
    :type return_output: bool
    """
    now = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    if display:
        click.secho("[{0}] ".format(now), bold=True, nl=False, fg="green")
        click.secho("{0}".format(cmd), bold=True)
    try:
        if return_output:
            result = subprocess.check_output(cmd, shell=True)
            return result.decode().rstrip("\r\n")
        else:
            subprocess.check_call(cmd, shell=True)
    except subprocess.CalledProcessError as err:
        if display:
            click.secho("[{0}] ".format(now), bold=True, nl=False, fg="green")
            click.secho("{0}".format(err), bold=True, fg="red")
        sys.exit(err.returncode)
