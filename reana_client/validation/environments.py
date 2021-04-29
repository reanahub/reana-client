# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2021 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""REANA client environment validation."""

import sys

from reana_commons.config import WORKFLOW_RUNTIME_USER_GID, WORKFLOW_RUNTIME_USER_UID

from reana_client.errors import EnvironmentValidationError
from reana_client.config import GITLAB_CERN_REGISTRY_PREFIX

from reana_client.validation.utils import (
    _validate_image_tag,
    _image_exists_locally,
    _image_exists_in_gitlab_cern,
    _image_exists_in_dockerhub,
    _get_image_uid_gids,
    _get_full_image_name,
)

from reana_client.printer import display_message


def validate_environment(reana_yaml, pull=False):
    """Validate environments in REANA specification file according to workflow type.

    :param reana_yaml: Dictionary which represents REANA specifications file.
    :param pull: If true, attempt to pull remote environment image to perform GID/UID validation.
    """

    def build_validator(workflow):
        workflow_type = workflow["type"]
        if workflow_type == "serial":
            workflow_steps = workflow["specification"]["steps"]
            return SerialEnvironmentValidator(workflow_steps=workflow_steps, pull=pull)
        if workflow_type == "yadage":
            workflow_steps = workflow["specification"]["stages"]
            return YadageEnvironmentValidator(workflow_steps=workflow_steps, pull=pull)
        if workflow_type == "cwl":
            workflow_file = workflow.get("file")
            return CWLEnvironmentValidator(workflow_file=workflow_file, pull=pull)

    workflow = reana_yaml["workflow"]
    validator = build_validator(workflow)
    validator.validate()
    validator.display_messages()


class EnvironmentValidatorBase:
    """REANA workflow environments validation base class."""

    def __init__(self, workflow_steps=None, workflow_file=None, pull=False):
        """Validate environments in REANA workflow.

        :param workflow_steps: List of dictionaries which represents different steps involved in workflow.
        :param workflow_file: Path to workflow specification.
        :param pull: If true, attempt to pull remote environment image to perform GID/UID validation.
        """
        self.workflow_steps = workflow_steps
        self.workflow_file = workflow_file
        self.pull = pull
        self.validated_images = set()
        self.messages = []

    def validate(self):
        """Validate REANA workflow environments."""
        try:
            self.validate_environment()
        except EnvironmentValidationError as e:
            self.messages.append({"type": "error", "message": str(e)})
            self.display_messages()
            sys.exit(1)

    def validate_environment(self):
        """Validate environments in REANA workflow."""
        raise NotImplementedError

    def display_messages(self):
        """Display messages in console."""
        for msg in self.messages:
            display_message(
                msg["message"], msg_type=msg["type"], indented=True,
            )

    def _validate_environment_image(self, image, kubernetes_uid=None):
        """Validate image environment.

        :param image: Full image name with tag if specified.
        :param kubernetes_uid: Kubernetes UID defined in workflow spec.
        """

        if image not in self.validated_images:
            image_name, image_tag, message = _validate_image_tag(image)
            self.messages.append(message)
            exists_locally, _ = self._image_exists(image_name, image_tag)
            if exists_locally or self.pull:
                uid, gids = _get_image_uid_gids(image_name, image_tag)
                self._validate_uid_gids(uid, gids, kubernetes_uid=kubernetes_uid)
            else:
                self.messages.append(
                    {
                        "type": "warning",
                        "message": "UID/GIDs validation skipped, specify `--pull` to enable it.",
                    }
                )
        self.validated_images.add(image)

    def _image_exists(self, image, tag):
        """Verify if image exists locally or remotely.

        :returns: A tuple with two boolean values: image exists locally, image exists remotely.
        """

        image_exists_remotely = (
            _image_exists_in_gitlab_cern
            if image.startswith(GITLAB_CERN_REGISTRY_PREFIX)
            else _image_exists_in_dockerhub
        )

        exists_locally, message = _image_exists_locally(image, tag)
        self.messages.append(message)

        exists_remotely, message = image_exists_remotely(image, tag)
        self.messages.append(message)

        if not any([exists_locally, exists_remotely]):
            raise EnvironmentValidationError(
                "Environment image {} does not exist locally or remotely.".format(
                    _get_full_image_name(image, tag)
                )
            )
        return exists_locally, exists_remotely

    def _validate_uid_gids(self, uid, gids, kubernetes_uid=None):
        """Check whether container UID and GIDs are valid."""
        if WORKFLOW_RUNTIME_USER_GID not in gids:
            if kubernetes_uid is None:
                raise EnvironmentValidationError(
                    "Environment image GID must be {}. GIDs {} were found.".format(
                        WORKFLOW_RUNTIME_USER_GID, gids
                    )
                )
            else:
                self.messages.append(
                    {
                        "type": "warning",
                        "message": "Environment image GID is recommended to be {}. GIDs {} were found.".format(
                            WORKFLOW_RUNTIME_USER_GID, gids
                        ),
                    }
                )
        if kubernetes_uid is not None:
            if kubernetes_uid != uid:
                self.messages.append(
                    {
                        "type": "warning",
                        "message": "`kubernetes_uid` set to {}. UID {} was found.".format(
                            kubernetes_uid, uid
                        ),
                    }
                )
        elif uid != WORKFLOW_RUNTIME_USER_UID:
            self.messages.append(
                {
                    "type": "info",
                    "message": "Environment image uses UID {} but will run as UID {}.".format(
                        uid, WORKFLOW_RUNTIME_USER_UID
                    ),
                }
            )


class SerialEnvironmentValidator(EnvironmentValidatorBase):
    """REANA serial workflow environments validation."""

    def validate_environment(self):
        """Validate environments in REANA serial workflow."""
        for step in self.workflow_steps:
            image = step["environment"]
            kubernetes_uid = step.get("kubernetes_uid")
            self._validate_environment_image(image, kubernetes_uid=kubernetes_uid)


class YadageEnvironmentValidator(EnvironmentValidatorBase):
    """REANA yadage workflow environments validation."""

    def validate_environment(self):
        """Validate environments in REANA yadage workflow."""

        def traverse_yadage_workflow(stages):
            for stage in stages:
                if "workflow" in stage["scheduler"]:
                    nested_stages = stage["scheduler"]["workflow"].get("stages", {})
                    traverse_yadage_workflow(nested_stages)
                else:
                    environment = stage["scheduler"]["step"]["environment"]
                    if environment["environment_type"] != "docker-encapsulated":
                        raise EnvironmentValidationError(
                            'The only Yadage environment type supported is "docker-encapsulated". Found "{}".'.format(
                                environment["environment_type"]
                            )
                        )
                    else:
                        _check_environment(environment)

        def _check_environment(environment):
            image = "{}{}".format(
                environment["image"],
                ":{}".format(environment["imagetag"])
                if "imagetag" in environment
                else "",
            )
            k8s_uid = next(
                (
                    resource["kubernetes_uid"]
                    for resource in environment.get("resources", [])
                    if "kubernetes_uid" in resource
                ),
                None,
            )
            self._validate_environment_image(image, kubernetes_uid=k8s_uid)

        traverse_yadage_workflow(self.workflow_steps)


class CWLEnvironmentValidator(EnvironmentValidatorBase):
    """REANA CWL workflow environments validation."""

    def validate_environment(self):
        """Validate environments in REANA CWL workflow."""

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

        top = cwl_parser.load_document(self.workflow_file)

        for image in traverse(top):
            self._validate_environment_image(image)
