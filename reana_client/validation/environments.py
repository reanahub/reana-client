# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2021, 2022 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""REANA client environment validation."""

import os
import sys
import logging
import re
import requests

from reana_commons.config import (
    REANA_DEFAULT_SNAKEMAKE_ENV_IMAGE,
    WORKFLOW_RUNTIME_USER_GID,
    WORKFLOW_RUNTIME_USER_UID,
)
from reana_commons.utils import run_command

from reana_client.errors import EnvironmentValidationError
from reana_client.config import (
    DOCKER_REGISTRY_INDEX_URL,
    DOCKER_REGISTRY_PREFIX,
    ENVIRONMENT_IMAGE_SUSPECTED_TAGS_VALIDATOR,
    GITLAB_CERN_REGISTRY_INDEX_URL,
    GITLAB_CERN_REGISTRY_PREFIX,
    ERROR_MESSAGES,
)
from reana_client.printer import display_message


def validate_environment(reana_yaml, pull=False, access_token=None):
    """Validate environments in REANA specification file according to workflow type.

    :param reana_yaml: Dictionary which represents REANA specification file.
    :param pull: If true, attempt to pull remote environment image to perform GID/UID validation.
    """

    def build_validator(workflow):
        workflow_type = workflow["type"]
        if workflow_type == "serial":
            workflow_steps = workflow["specification"]["steps"]
            return EnvironmentValidatorSerial(
                workflow_steps=workflow_steps, pull=pull, access_token=access_token
            )
        if workflow_type == "yadage":
            workflow_steps = workflow["specification"]["stages"]
            return EnvironmentValidatorYadage(
                workflow_steps=workflow_steps, pull=pull, access_token=access_token
            )
        if workflow_type == "cwl":
            workflow_steps = workflow.get("specification", {}).get("$graph", workflow)
            return EnvironmentValidatorCWL(
                workflow_steps=workflow_steps, pull=pull, access_token=access_token
            )
        if workflow_type == "snakemake":
            workflow_steps = workflow["specification"]["steps"]
            return EnvironmentValidatorSnakemake(
                workflow_steps=workflow_steps,
                pull=pull,
                access_token=access_token,
                workflow_filename=reana_yaml["workflow"]["file"],
                workflow_input_parameters=reana_yaml.get("inputs", {}).get(
                    "parameters", {}
                ),
            )

    workflow = reana_yaml["workflow"]
    validator = build_validator(workflow)
    validator.validate()
    validator.display_messages()


class EnvironmentValidatorBase:
    """REANA workflow environments validation base class."""

    def __init__(
        self,
        workflow_steps=None,
        pull=False,
        access_token=None,
        workflow_filename=None,
        workflow_input_parameters=None,
    ):
        """Validate environments in REANA workflow.

        :param workflow_steps: List of dictionaries which represents different steps involved in workflow.
        :param pull: If true, attempt to pull remote environment image to perform GID/UID validation.
        :param workflow_filename: Path to the main workflow file (e.g. Snakefile).
        :param workflow_input_parameters: The ``inputs.parameters`` dict from the REANA
            specification.  For Snakemake workflows the ``input`` key (if present) is
            the path to a Snakemake configfile; all other keys are direct
            ``config["key"]`` overrides passed at runtime via ``--config key=value``.
        """
        self.workflow_steps = workflow_steps
        self.pull = pull
        self.access_token = access_token
        self.workflow_filename = workflow_filename
        self.workflow_input_parameters = workflow_input_parameters or {}
        self.validated_images = set()
        self.messages = []
        self._vetting_config = None  # cached (vetting_enabled, allowlist); False = skip

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
                msg["message"],
                msg_type=msg["type"],
                indented=True,
            )

    def check_image_authorized(self, image):
        """Checks if an image is authorized for use in workflows.

        :param image: Full image name with tag.
        """
        if self._vetting_config is False:
            return  # There was no token or fetch error, skip

        if not self.access_token:
            self.messages.append(
                {
                    "type": "warning",
                    "message": f'No access token provided - skipping container image authorisation check. {ERROR_MESSAGES["missing_access_token"]}',
                }
            )
            self._vetting_config = False
            return

        if self._vetting_config is None:
            # Vetting config has not been cached yet - fetch and cache
            try:
                from reana_client.api.client import info

                cluster_info = info(self.access_token)
                vetting = cluster_info.get("vetted_container_images_enabled")
                allowlist = cluster_info.get("vetted_container_images_allowlist")
                if vetting is None or allowlist is None:
                    # Server predates vetting support (skip the image vetting check)
                    self._vetting_config = False
                    return
                self._vetting_config = (vetting["value"], allowlist["value"])
            except Exception as e:
                self.messages.append(
                    {
                        "type": "warning",
                        "message": f"Could not check if container images are authorised. Is the cluster running properly? Error: {e}",
                    }
                )
                self._vetting_config = False
                return

        # Validate image against allowlist
        vetting_enabled, allowlist = self._vetting_config
        if vetting_enabled and image not in allowlist:
            raise EnvironmentValidationError(
                f"Environment image is not allowed: {image}"
            )

    def _validate_environment_image(self, image, kubernetes_uid=None):
        """Validate image environment.

        :param image: Full image name with tag if specified. E.g. `reanahub/reana-env-jupyter:2.0.0`.
        :param kubernetes_uid: Kubernetes UID defined in workflow spec.
        """
        if image not in self.validated_images:
            image_name, image_tag = self._validate_image_tag(image)
            self.check_image_authorized(image)
            exists_locally, _ = self._image_exists(image_name, image_tag)
            if exists_locally or self.pull:
                uid, gids = self._get_image_uid_gids(image_name, image_tag)
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
            self._image_exists_in_gitlab_cern
            if image.startswith(GITLAB_CERN_REGISTRY_PREFIX)
            else self._image_exists_in_dockerhub
        )

        exists_locally = self._image_exists_locally(image, tag)
        exists_remotely = image_exists_remotely(image, tag)

        if not any([exists_locally, exists_remotely]):
            raise EnvironmentValidationError(
                "Environment image {} does not exist locally or remotely.".format(
                    self._get_full_image_name(image, tag)
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

    def _validate_image_tag(self, image):
        """Validate if image tag is valid."""
        image_name, image_tag = "", ""
        message = {
            "type": "success",
            "message": "Environment image {} has the correct format.".format(image),
        }
        if " " in image:
            raise EnvironmentValidationError(
                f"Environment image '{image}' contains illegal characters."
            )
        if ":" in image:
            environment = image.split(":", 1)
            image_name, image_tag = environment[0], environment[-1]
            if ":" in image_tag:
                raise EnvironmentValidationError(
                    "Environment image {} has invalid tag '{}'".format(
                        image_name, image_tag
                    )
                )
            elif image_tag in ENVIRONMENT_IMAGE_SUSPECTED_TAGS_VALIDATOR:
                message = {
                    "type": "warning",
                    "message": "Using '{}' tag is not recommended in {} environment image.".format(
                        image_tag, image_name
                    ),
                }
        else:
            message = {
                "type": "warning",
                "message": "Environment image {} does not have an explicit tag.".format(
                    image
                ),
            }
            image_name = image

        self.messages.append(message)
        return image_name, image_tag

    def _image_exists_locally(self, image, tag):
        """Verify if image exists locally."""
        full_image = self._get_full_image_name(image, tag or "latest")
        image_id = run_command(
            f'docker images -q "{full_image}"', display=False, return_output=True
        )
        if image_id:
            self.messages.append(
                {
                    "type": "success",
                    "message": f"Environment image {full_image} exists locally.",
                }
            )
            return True
        else:
            self.messages.append(
                {
                    "type": "warning",
                    "message": f"Environment image {full_image} does not exist locally.",
                }
            )
            return False

    def _image_exists_in_gitlab_cern(self, image, tag):
        """Verify if image exists in GitLab CERN."""
        # Remove registry prefix
        prefixed_image = image
        full_prefixed_image = self._get_full_image_name(image, tag or "latest")
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
            self.messages.append(
                {
                    "type": "error",
                    "message": "Something went wrong when querying {}".format(
                        remote_registry_url
                    ),
                }
            )
            return False

        if not response.ok:
            msg = response.json().get("message")
            self.messages.append(
                {
                    "type": "warning",
                    "message": "Existence of environment image {} in GitLab CERN could not be verified: {}".format(
                        self._get_full_image_name(prefixed_image, tag), msg
                    ),
                }
            )
            return False
        else:
            # If not tag was set, use `latest` (default) to verify.
            tag = tag or "latest"
            tag_exists = any(
                tag_dict["name"] == tag for tag_dict in response.json()[0].get("tags")
            )
            if tag_exists:
                self.messages.append(
                    {
                        "type": "success",
                        "message": "Environment image {} exists in GitLab CERN.".format(
                            full_prefixed_image
                        ),
                    }
                )
                return True
            else:
                self.messages.append(
                    {
                        "type": "warning",
                        "message": 'Environment image {} in GitLab CERN does not exist: Tag "{}" missing.'.format(
                            full_prefixed_image, tag
                        ),
                    }
                )
                return False

    def _image_exists_in_dockerhub(self, image, tag):
        """Verify if image exists in DockerHub."""
        full_image = self._get_full_image_name(image, tag or "latest")
        # remove leading `docker.io/` prefix, if present
        dockerhub_prefix = f"{DOCKER_REGISTRY_PREFIX}/"
        if image.startswith(dockerhub_prefix):
            image = image[len(dockerhub_prefix) :]
        # Some images like `python:2.7-slim` require to specify `library`
        # as a repository in order to work with DockerHub API v2
        repository = "" if "/" in image else "library/"
        docker_registry_url = DOCKER_REGISTRY_INDEX_URL.format(
            repository=repository, image=image, tag=tag
        )
        # Remove traling slash if no tag was specified
        if not tag:
            docker_registry_url = docker_registry_url[:-1]
        try:
            response = requests.get(docker_registry_url)
        except requests.exceptions.RequestException as e:
            logging.error(e)
            self.messages.append(
                {
                    "type": "error",
                    "message": "Something went wrong when querying {}".format(
                        docker_registry_url
                    ),
                }
            )
            return False

        if not response.ok:
            if response.status_code == 404:
                msg = response.json().get("message")
                self.messages.append(
                    {
                        "type": "warning",
                        "message": "Environment image {} does not exist in Docker Hub: {}".format(
                            full_image, msg
                        ),
                    }
                )
                return False
            else:
                self.messages.append(
                    {
                        "type": "warning",
                        "message": "==> WARNING: Existence of environment image {} in Docker Hub could not be verified. Status code: {} {}".format(
                            full_image,
                            response.status_code,
                            response.reason,
                        ),
                    }
                )
                return False
        else:
            self.messages.append(
                {
                    "type": "success",
                    "message": "Environment image {} exists in Docker Hub.".format(
                        full_image
                    ),
                }
            )
            return True

    def _get_image_uid_gids(self, image, tag):
        """Obtain environment image UID and GIDs.

        :returns: A tuple with UID and GIDs.
        """
        from reana_commons.utils import run_command

        # Check if docker is installed.
        run_command("docker version", display=False, return_output=True)
        # Run ``id``` command inside the container.
        uid_gid_output = run_command(
            f'docker run -i -t --rm --entrypoint /bin/sh {self._get_full_image_name(image, tag)} -c "/usr/bin/id -u && /usr/bin/id -G"',
            display=False,
            return_output=True,
        )
        ids = uid_gid_output.splitlines()
        uid, gids = (
            int(ids[-2]),
            [int(gid) for gid in ids[-1].split()],
        )
        return uid, gids

    def _get_full_image_name(self, image, tag=None):
        """Return full image name with tag if is passed."""
        return "{}{}".format(image, ":{}".format(tag) if tag else "")


class EnvironmentValidatorSerial(EnvironmentValidatorBase):
    """REANA serial workflow environments validation."""

    def validate_environment(self):
        """Validate environments in REANA serial workflow."""
        for step in self.workflow_steps:
            image = step["environment"]
            kubernetes_uid = step.get("kubernetes_uid")
            self._validate_environment_image(image, kubernetes_uid=kubernetes_uid)


class EnvironmentValidatorYadage(EnvironmentValidatorBase):
    """REANA yadage workflow environments validation."""

    def _extract_steps_environments(self):
        """Extract environments yadage workflow steps."""
        from reana_commons.validation.images import iter_yadage_environments

        return list(iter_yadage_environments(self.workflow_steps))

    def validate_environment(self):
        """Validate environments in REANA yadage workflow."""

        def _check_environment(environment):
            image = "{}{}".format(
                environment["image"],
                (
                    ":{}".format(environment["imagetag"])
                    if "imagetag" in environment
                    else ""
                ),
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

        steps_environments = self._extract_steps_environments()
        for environment in steps_environments:
            if environment["environment_type"] != "docker-encapsulated":
                raise EnvironmentValidationError(
                    'The only Yadage environment type supported is "docker-encapsulated". Found "{}".'.format(
                        environment["environment_type"]
                    )
                )
            else:
                _check_environment(environment)


class EnvironmentValidatorCWL(EnvironmentValidatorBase):
    """REANA CWL workflow environments validation."""

    def validate_environment(self):
        """Validate environments in REANA CWL workflow."""
        from reana_commons.validation.images import extract_cwl_images

        for image in extract_cwl_images(self.workflow_steps):
            self._validate_environment_image(image)


class EnvironmentValidatorSnakemake(EnvironmentValidatorBase):
    """REANA Snakemake workflow environments validation."""

    def validate_environment(self):
        """Validate environments in REANA Snakemake workflow."""
        for step in self.workflow_steps:
            image = step.get("environment")
            if not image:
                self.messages.append(
                    {
                        "type": "warning",
                        "message": f"Environment image not specified, using {REANA_DEFAULT_SNAKEMAKE_ENV_IMAGE}.",
                    }
                )
                continue
            kubernetes_uid = step.get("kubernetes_uid")
            self._validate_environment_image(image, kubernetes_uid=kubernetes_uid)

        # Extract and validate environments from Snakefile
        self._validate_snakefile_environments()

    def _get_snakemake_config_keys(self):
        """Extract ``config["key"]`` references from the Snakefile and all included files.

        Recursively follows ``include:`` directives so that keys used only in
        sub-Snakefiles are not missed.  A placeholder value is injected for
        each discovered key so the DAG can be built without raising ``KeyError``.
        """
        from pathlib import Path

        visited: set = set()
        keys: set = set()
        self._collect_config_keys_recursive(
            Path(self.workflow_filename).resolve(), visited, keys
        )
        return list(keys)

    def _collect_config_keys_recursive(self, snakefile_path, visited, keys):
        """Collect config["key"] refs from *snakefile_path* and any included files."""
        if snakefile_path in visited:
            return
        visited.add(snakefile_path)
        try:
            content = snakefile_path.read_text()
        except OSError:
            return
        keys.update(re.findall(r"config\[['\"](.*?)['\"]\]", content))
        for include in re.findall(r'include\s*:\s*[\'"]([^\'"]+)[\'"]', content):
            self._collect_config_keys_recursive(
                (snakefile_path.parent / include).resolve(), visited, keys
            )

    def _validate_snakefile_environments(self):
        """Extract and validate images used in the Snakefile."""
        from pathlib import Path

        # Import the Snakemake API in its own block to detect
        # if Snakemake is not installed
        try:
            from snakemake.api import SnakemakeApi
            from snakemake.settings.types import (
                ResourceSettings,
                ConfigSettings,
            )
        except ImportError:
            self.messages.append(
                {
                    "type": "warning",
                    "message": "Snakemake is not installed, skipping image validation.",
                }
            )
            return

        try:
            # We will use the Snakemake API to build the DAG and then extract
            # all the workflow container images to validate. But first, we
            # need to populate the config dict so that Snakemake can properly
            # evaluate the Snakefile without raising KeyError.
            #
            # This config dict can come from inputs.parameters in two ways:
            # - "input": "config.yaml" (keys/values come from the passed file)
            # - "key": value (keys/values are directly entered)
            #
            # In these cases, we can get the real config dict values. But
            # when neither is provided (e.g. the Snakefile uses a configfile
            # directive), we fall back to scanning the Snakefile for
            # config["key"] references and injecting a placeholder value for
            # each one so the DAG can be built without raising a KeyError.

            # Resolve the snakefile path to absolute so it remains valid
            # after we chdir into its parent directory below.
            snakefile_path = Path(self.workflow_filename).resolve()

            configfile = self.workflow_input_parameters.get("input")
            direct_params = {
                k: v for k, v in self.workflow_input_parameters.items() if k != "input"
            }

            if configfile:
                config_settings = ConfigSettings(
                    # Resolve to absolute before chdir so the path stays valid.
                    configfiles=[Path(configfile).resolve()],
                    config=direct_params,
                )
            else:
                config = dict(direct_params)
                for key in self._get_snakemake_config_keys():
                    config.setdefault(key, "fake_value")
                config_settings = ConfigSettings(config=config)

            # Change to the Snakefile's directory before building the DAG so
            # that relative paths declared inside the Snakefile (e.g.
            # ``configfile: "config.yaml"``) resolve against the Snakefile
            # location rather than the repo root where validation is invoked.
            original_dir = os.getcwd()
            try:
                os.chdir(snakefile_path.parent)
                # Load workflow with Snakemake API
                with SnakemakeApi() as snakemake_api:
                    workflow_api = snakemake_api.workflow(
                        resource_settings=ResourceSettings(),
                        config_settings=config_settings,
                        snakefile=snakefile_path,
                    )

                    # Extract all container images
                    wf = workflow_api._workflow
                    images = {
                        rule.container_img for rule in wf.rules if rule.container_img
                    }

                    # Strip the docker:// prefix
                    prefix = "docker://"
                    images = {
                        image[len(prefix) :] if image.startswith(prefix) else image
                        for image in images
                    }

                    # Validate all collected images
                    for image in images:
                        self._validate_environment_image(image)
            finally:
                os.chdir(original_dir)

        except EnvironmentValidationError:
            raise

        except Exception as e:
            self.messages.append(
                {
                    "type": "error",
                    "message": f"Error building Snakemake DAG: {str(e)}",
                }
            )
