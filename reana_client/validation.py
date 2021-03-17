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
from collections import defaultdict
from itertools import chain
import os

import click
import requests
from reana_commons.config import WORKFLOW_RUNTIME_USER_GID, WORKFLOW_RUNTIME_USER_UID

from reana_client.config import (
    COMMAND_DANGEROUS_OPERATIONS,
    DOCKER_REGISTRY_INDEX_URL,
    ENVIRONMENT_IMAGE_SUSPECTED_TAGS_VALIDATOR,
    GITLAB_CERN_REGISTRY_INDEX_URL,
    GITLAB_CERN_REGISTRY_PREFIX,
)

from reana_client.printer import display_message


def validate_environment(reana_yaml, pull=False):
    """Validate environments in REANA specification file according to workflow type.

    :param reana_yaml: Dictionary which represents REANA specifications file.
    :param pull: If true, attempt to pull remote environment image to perform GID/UID validation.
    """
    workflow_type = reana_yaml["workflow"]["type"]

    if workflow_type == "serial":
        workflow_steps = reana_yaml["workflow"]["specification"]["steps"]
        _validate_serial_workflow_environment(workflow_steps, pull=pull)
    elif workflow_type == "yadage":
        workflow_steps = reana_yaml["workflow"]["specification"]["stages"]
        _validate_yadage_workflow_environment(workflow_steps, pull=pull)
    elif workflow_type == "cwl":
        workflow_file = reana_yaml["workflow"].get("file")
        _validate_cwl_workflow_environment(workflow_file, pull=pull)


def _validate_environment_image(image, kubernetes_uid=None, pull=False):
    """Validate image environment.

    :param image: Full image name with tag if specified.
    :param kubernetes_uid: Kubernetes UID defined in workflow spec.
    :param pull: If true, attempt to pull remote environment image to perform GID/UID validation.
    """
    image_name, image_tag = _validate_image_tag(image)
    exists_locally, _ = _image_exists(image_name, image_tag)
    if exists_locally or pull:
        uid, gids = _get_image_uid_gids(image_name, image_tag)
        _validate_uid_gids(uid, gids, kubernetes_uid=kubernetes_uid)
    else:
        display_message(
            "UID/GIDs validation skipped, specify `--pull` to enable it.",
            msg_type="warning",
            indented=True,
        )


def _validate_yadage_workflow_environment(workflow_steps, pull=False):
    """Validate environments in REANA yadage workflow.

    :param workflow_steps: List of dictionaries which represents different steps involved in workflow.
    :param pull: If true, attempt to pull remote environment image to perform GID/UID validation.
    :raises Warning: Warns user if the workflow environment is invalid in yadage workflow steps.
    """

    def traverse_yadage_workflow(stages):
        for stage in stages:
            if "workflow" in stage["scheduler"]:
                nested_stages = stage["scheduler"]["workflow"].get("stages", {})
                traverse_yadage_workflow(nested_stages)
            else:
                environment = stage["scheduler"]["step"]["environment"]
                if environment["environment_type"] != "docker-encapsulated":
                    display_message(
                        'The only Yadage environment type supported is "docker-encapsulated". Found "{}".'.format(
                            environment["environment_type"]
                        ),
                        msg_type="error",
                        indented=True,
                    )
                    sys.exit(1)
                else:
                    _check_environment(environment)

    def _check_environment(environment):
        image = "{}{}".format(
            environment["image"],
            ":{}".format(environment["imagetag"]) if "imagetag" in environment else "",
        )
        k8s_uid = next(
            (
                resource["kubernetes_uid"]
                for resource in environment.get("resources", [])
                if "kubernetes_uid" in resource
            ),
            None,
        )
        _validate_environment_image(image, kubernetes_uid=k8s_uid, pull=pull)

    traverse_yadage_workflow(workflow_steps)


def _validate_cwl_workflow_environment(workflow_file, pull=False):
    """Validate environments in REANA CWL workflow.

    :param workflow_file: Path to CWL workflow specification.
    :param pull: If true, attempt to pull remote environment image to perform GID/UID validation.
    :raises Warning: Warns user if the workflow environment is invalid in CWL workflow steps.
    """
    try:
        import cwl_utils.parser_v1_0 as cwl_parser
        from cwl_utils.docker_extract import traverse
    except ImportError as e:
        display_message(
            "Cannot validate environment. Please install reana-client on Python 3+ to enable environment validation for CWL workflows.",
            msg_type="error",
            indented=True,
        )
        raise e

    top = cwl_parser.load_document(workflow_file)

    for image in traverse(top):
        _validate_environment_image(image, pull=pull)


def _validate_serial_workflow_environment(workflow_steps, pull=False):
    """Validate environments in REANA serial workflow.

    :param workflow_steps: List of dictionaries which represents different steps involved in workflow.
    :param pull: If true, attempt to pull remote environment image to perform GID/UID validation.
    :raises Warning: Warns user if the workflow environment is invalid in serial workflow steps.
    """
    for step in workflow_steps:
        image = step["environment"]
        _validate_environment_image(
            image, kubernetes_uid=step.get("kubernetes_uid"), pull=pull
        )


def _validate_image_tag(image):
    """Validate if image tag is valid."""
    image_name, image_tag = "", ""
    has_warnings = False
    if ":" in image:
        environment = image.split(":", 1)
        image_name, image_tag = environment[0], environment[-1]
        if ":" in image_tag:
            display_message(
                "Environment image {} has invalid tag '{}'".format(
                    image_name, image_tag
                ),
                msg_type="error",
                indented=True,
            )
            sys.exit(1)
        elif image_tag in ENVIRONMENT_IMAGE_SUSPECTED_TAGS_VALIDATOR:
            display_message(
                "Using '{}' tag is not recommended in {} environment image.".format(
                    image_tag, image_name
                ),
                msg_type="warning",
                indented=True,
            )
            has_warnings = True
    else:
        display_message(
            "Environment image {} does not have an explicit tag.".format(image),
            msg_type="warning",
            indented=True,
        )
        has_warnings = True
        image_name = image
    if not has_warnings:
        display_message(
            "Environment image {} has the correct format.".format(image),
            msg_type="success",
            indented=True,
        )

    return image_name, image_tag


def _image_exists(image, tag):
    """Verify if image exists locally or remotely.

    :returns: A tuple with two boolean values: image exists locally, image exists remotely.
    """

    image_exists_remotely = (
        _image_exists_in_gitlab_cern
        if image.startswith(GITLAB_CERN_REGISTRY_PREFIX)
        else _image_exists_in_dockerhub
    )

    exists_locally, exists_remotely = (
        _image_exists_locally(image, tag),
        image_exists_remotely(image, tag),
    )
    if not any([exists_locally, exists_remotely]):
        display_message(
            "Environment image {} does not exist locally or remotely.".format(
                _get_full_image_name(image, tag)
            ),
            msg_type="error",
            indented=True,
        )
        sys.exit(1)
    return exists_locally, exists_remotely


def _get_full_image_name(image, tag=None):
    """Return full image name with tag if is passed."""
    return "{}{}".format(image, ":{}".format(tag) if tag else "")


def _image_exists_in_dockerhub(image, tag):
    """Verify if image exists in DockerHub."""
    full_image = _get_full_image_name(image, tag or "latest")
    docker_registry_url = DOCKER_REGISTRY_INDEX_URL.format(image=image, tag=tag)
    # Remove traling slash if no tag was specified
    if not tag:
        docker_registry_url = docker_registry_url[:-1]
    try:
        response = requests.get(docker_registry_url)
    except requests.exceptions.RequestException as e:
        logging.error(e)
        display_message(
            "Something went wrong when querying {}".format(docker_registry_url),
            msg_type="error",
            indented=True,
        )
        return False

    if not response.ok:
        if response.status_code == 404:
            msg = response.text
            display_message(
                "Environment image {} does not exist in Docker Hub: {}".format(
                    full_image, msg
                ),
                msg_type="warning",
                indented=True,
            )
        else:
            display_message(
                "==> WARNING: Existence of environment image {} in Docker Hub could not be verified. Status code: {} {}".format(
                    full_image, response.status_code, response.reason,
                ),
                msg_type="warning",
                indented=True,
            )
        return False
    else:
        display_message(
            "Environment image {} exists in Docker Hub.".format(full_image),
            msg_type="success",
            indented=True,
        )
        return True


def _image_exists_in_gitlab_cern(image, tag):
    """Verify if image exists in GitLab CERN."""
    # Remove registry prefix
    prefixed_image = image
    full_prefixed_image = _get_full_image_name(image, tag or "latest")
    image = image.split("/", 1)[-1]
    # Encode image name slashes
    remote_registry_url = GITLAB_CERN_REGISTRY_INDEX_URL.format(
        image=requests.utils.quote(image, safe="")
    )
    try:
        # FIXME: if image is private we can't access it, we'd
        # need to pass a GitLab API token generated from the UI.
        response = requests.get(remote_registry_url)
    except requests.exceptions.RequestException as e:
        logging.error(e)
        display_message(
            "Something went wrong when querying {}".format(remote_registry_url),
            msg_type="error",
            indented=True,
        )
        return False

    if not response.ok:
        msg = response.json().get("message")
        display_message(
            "Existence of environment image {} in GitLab CERN could not be verified: {}".format(
                _get_full_image_name(prefixed_image, tag), msg
            ),
            msg_type="warning",
            indented=True,
        )
        return False
    else:
        # If not tag was set, use `latest` (default) to verify.
        tag = tag or "latest"
        tag_exists = any(
            tag_dict["name"] == tag for tag_dict in response.json()[0].get("tags")
        )
        if tag_exists:
            display_message(
                "Environment image {} exists in GitLab CERN.".format(
                    full_prefixed_image
                ),
                msg_type="success",
                indented=True,
            )
            return True
        else:
            display_message(
                'Environment image {} in GitLab CERN does not exist: Tag "{}" missing.'.format(
                    full_prefixed_image, tag
                ),
                msg_type="warning",
                indented=True,
            )
            return False


def _image_exists_locally(image, tag):
    """Verify if image exists locally."""
    full_image = _get_full_image_name(image, tag or "latest")
    local_images = _get_local_docker_images()
    if full_image in local_images:
        display_message(
            "Environment image {} exists locally.".format(full_image),
            msg_type="success",
            indented=True,
        )
        return True
    else:
        display_message(
            "Environment image {} does not exist locally.".format(full_image),
            msg_type="warning",
            indented=True,
        )
        return False


def _get_local_docker_images():
    """Return a list with local docker images."""
    # Check if docker is installed.
    run_command("docker version", display=False, return_output=True)
    docker_images = run_command(
        'docker images --format "{{ .Repository }}:{{ .Tag }}"',
        display=False,
        return_output=True,
    )
    return docker_images.splitlines()


def _get_image_uid_gids(image, tag):
    """Obtain environment image UID and GIDs.

    :returns: A tuple with UID and GIDs.
    """
    # Check if docker is installed.
    run_command("docker version", display=False, return_output=True)
    # Run ``id``` command inside the container.
    uid_gid_output = run_command(
        'docker run -i -t --rm {} sh -c "/usr/bin/id -u && /usr/bin/id -G"'.format(
            _get_full_image_name(image, tag)
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
        if kubernetes_uid is None:
            display_message(
                "Environment image GID must be {}. GIDs {} were found.".format(
                    WORKFLOW_RUNTIME_USER_GID, gids
                ),
                msg_type="error",
                indented=True,
            )
            sys.exit(1)
        else:
            display_message(
                "Environment image GID is recommended to be {}. GIDs {} were found.".format(
                    WORKFLOW_RUNTIME_USER_GID, gids
                ),
                msg_type="warning",
                indented=True,
            )
    if kubernetes_uid is not None:
        if kubernetes_uid != uid:
            display_message(
                "`kubernetes_uid` set to {}. UID {} was found.".format(
                    kubernetes_uid, uid
                ),
                msg_type="warning",
                indented=True,
            )
    elif uid != WORKFLOW_RUNTIME_USER_UID:
        display_message(
            "Environment image UID is recommended to be {}. UID {} was found.".format(
                WORKFLOW_RUNTIME_USER_UID, uid
            ),
            msg_type="warning",
            indented=True,
        )


def validate_parameters(workflow_type, reana_yaml):
    """Validate the presence of input parameters in workflow step commands and viceversa.

    :param workflow_type: A supported workflow specification type.
    :param reana_yaml: REANA YAML specification.
    """
    validate = {
        "yadage": _validate_yadage_parameters,
        "cwl": _validate_cwl_parameters,
        "serial": _validate_serial_parameters,
    }
    """Dictionary to extend with new workflow specification loaders."""
    if "inputs" not in reana_yaml:
        display_message(
            'Workflow "inputs" are missing in the REANA specification.',
            msg_type="warning",
            indented=True,
        )

    return validate[workflow_type](reana_yaml)


def _warn_not_used_parameters(workflow_parameters, command_parameters, type_="REANA"):
    """Warn user about defined workflow parameter not being used.

    :param workflow_parameters: Set of parameters in workflow definition.
    :param command_parameters: Set of parameters used inside workflow.
    :param type: Type of workflow parameters, e.g. REANA for input parameters, Yadage
                 for parameters defined in Yadage spec.
    :returns: Set of command parameters not referenced by workflow parameters.
    """

    for parameter in workflow_parameters.difference(command_parameters):
        display_message(
            '{} input parameter "{}" does not seem to be used.'.format(
                type_, parameter
            ),
            msg_type="warning",
            indented=True,
        )
    return command_parameters.difference(workflow_parameters)


def _warn_not_defined_parameters(
    cmd_param_steps_mapping, workflow_parameters, workflow_type
):
    """Warn user about command parameters missing in workflow definition.

    :param cmd_param_steps_mapping: Mapping between command parameters and its step.
    :param workflow_parameters: Set of parameters in workflow definition.
    :param workflow_type: Workflow type being checked.
    """
    command_parameters = set(cmd_param_steps_mapping.keys())

    for parameter in command_parameters.difference(workflow_parameters):
        steps_used = cmd_param_steps_mapping[parameter]

        display_message(
            '{type} parameter "{parameter}" found on step{s} "{steps}" is not defined in input parameters.'.format(
                type=workflow_type.capitalize(),
                parameter=parameter,
                steps=", ".join(steps_used),
                s="s" if len(steps_used) > 1 else "",
            ),
            msg_type="warning",
            indented=True,
        )


def _validate_cwl_parameters(reana_yaml):
    """Validate input parameters for CWL workflows.

    :param reana_yaml: REANA YAML specification.
    """
    cwl_main_spec_path = reana_yaml["workflow"].get("file")
    if os.path.exists(cwl_main_spec_path):
        run_command(
            "cwltool --validate --strict {}".format(cwl_main_spec_path),
            display=False,
            return_output=True,
            stderr_output=True,
        )
    else:
        display_message(
            "Workflow path {} is not valid.".format(cwl_main_spec_path),
            msg_type="error",
            indented=True,
        )
        sys.exit(1)

    def _check_dangerous_operations(workflow):
        """Check for "baseCommand" and "arguments" in workflow.

        If these keys are found, validate if they have dangerous operations.
        """
        cmd_keys = ["baseCommand", "arguments"]
        for cmd_key in cmd_keys:
            if cmd_key in workflow:
                cmd_values = (
                    workflow[cmd_key]
                    if isinstance(workflow[cmd_key], list)
                    else [workflow[cmd_key]]
                )
                for cmd_value in cmd_values:
                    _validate_dangerous_operations(
                        str(cmd_value), step=workflow.get("id")
                    )

    workflow = reana_yaml["workflow"]["specification"].get(
        "$graph", reana_yaml["workflow"]["specification"]
    )
    if isinstance(workflow, dict):
        _check_dangerous_operations(workflow)
    elif isinstance(workflow, list):
        for wf in workflow:
            _check_dangerous_operations(wf)


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
            _validate_dangerous_operations(command, step=step_name)
            cmd_params = parse_command(command)
            for cmd_param in cmd_params:
                cmd_param_steps_mapping[cmd_param].add(step_name)

    command_parameters = set(cmd_param_steps_mapping.keys())

    _warn_not_used_parameters(input_parameters, command_parameters)
    _warn_not_defined_parameters(cmd_param_steps_mapping, input_parameters, "serial")


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

    def get_publisher_definitions(
        step, step_name, step_key, step_val,
    ):
        """Save publisher definitions as command params."""
        publisher_cmd_param_steps_mapping = defaultdict(set)
        if step == "publisher":
            command_params = {
                "publish": lambda: step_val.keys(),
                "outputkey": lambda: [step_val],
            }.get(step_key, lambda: [])()
            for command_param in command_params:
                publisher_cmd_param_steps_mapping[command_param].add(step_name)
        return publisher_cmd_param_steps_mapping

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
                if isinstance(param["value"], dict) and "output" in param["value"]:
                    params.append(param["value"]["output"])

            for step in stage["scheduler"].get("step", {}).keys():
                for step_key, step_val in stage["scheduler"]["step"][step].items():
                    publisher_cmd_param_steps_mapping = get_publisher_definitions(
                        step, step_name, step_key, step_val
                    )
                    cmd_param_steps_mapping.update(publisher_cmd_param_steps_mapping)
                    if step_key == "script":
                        command = step_val
                        _validate_dangerous_operations(command, step=step_name)
                    step_commands_params = parse_command_params(step_val)
                    for command_param in step_commands_params:
                        cmd_param_steps_mapping[command_param].add(step_name)

        return params, cmd_param_steps_mapping

    # REANA input parameters
    input_params = set(reana_yaml["inputs"].get("parameters", {}).keys())

    # Yadage parameters
    workflow_spec = reana_yaml["workflow"]["specification"]
    workflow_params, cmd_param_steps_mapping = parse_params(workflow_spec["stages"])

    workflow_params = set(workflow_params)
    command_params = set(cmd_param_steps_mapping.keys())

    # REANA input parameters validation
    rest_workflow_params = _warn_not_used_parameters(input_params, workflow_params)
    # Yadage parameters validation
    _warn_not_used_parameters(rest_workflow_params, command_params, type_="Yadage")
    # Yadage command parameters validation
    _warn_not_defined_parameters(cmd_param_steps_mapping, workflow_params, "yadage")


def _validate_dangerous_operations(command, step=None):
    """Warn the user if a command has dangerous operations.

    :param command: A workflow step command to validate.
    :param step: The workflow step that contains the given command.
    """
    for operation in COMMAND_DANGEROUS_OPERATIONS:
        if operation in command:
            msg = 'Operation "{}" found in step "{}" might be dangerous.'
            if not step:
                msg = 'Operation "{}" might be dangerous.'
            display_message(
                msg.format(operation.strip(), step if step else None),
                msg_type="warning",
                indented=True,
            )


def run_command(cmd, display=True, return_output=False, stderr_output=False):
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
            stderr_flag_val = subprocess.STDOUT if stderr_output else None
            result = subprocess.check_output(cmd, stderr=stderr_flag_val, shell=True)
            return result.decode().rstrip("\r\n")
        else:
            subprocess.check_call(cmd, shell=True)
    except subprocess.CalledProcessError as err:
        if display:
            click.secho("[{0}] ".format(now), bold=True, nl=False, fg="green")
            click.secho("{0}".format(err), bold=True, fg="red")
        if stderr_output:
            sys.exit(err.output.decode())
        sys.exit(err.returncode)
