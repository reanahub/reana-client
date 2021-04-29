# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2021 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""REANA client validation utils."""

import datetime
import logging
import subprocess
import sys

import click
import requests

from reana_client.errors import EnvironmentValidationError
from reana_client.config import (
    DOCKER_REGISTRY_INDEX_URL,
    ENVIRONMENT_IMAGE_SUSPECTED_TAGS_VALIDATOR,
    GITLAB_CERN_REGISTRY_INDEX_URL,
)


def _validate_image_tag(image):
    """Validate if image tag is valid."""
    image_name, image_tag = "", ""
    message = {
        "type": "success",
        "message": "Environment image {} has the correct format.".format(image),
    }
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

    return image_name, image_tag, message


def _image_exists_locally(image, tag):
    """Verify if image exists locally."""
    full_image = _get_full_image_name(image, tag or "latest")
    local_images = _get_local_docker_images()
    if full_image in local_images:
        message = {
            "type": "success",
            "message": "Environment image {} exists locally.".format(full_image),
        }
        return True, message
    else:
        message = {
            "type": "warning",
            "message": "Environment image {} does not exist locally.".format(
                full_image
            ),
        }
        return False, message


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
        message = {
            "type": "error",
            "message": "Something went wrong when querying {}".format(
                remote_registry_url
            ),
        }
        return False, message

    if not response.ok:
        msg = response.json().get("message")
        message = {
            "type": "warning",
            "message": "Existence of environment image {} in GitLab CERN could not be verified: {}".format(
                _get_full_image_name(prefixed_image, tag), msg
            ),
        }
        return False, message
    else:
        # If not tag was set, use `latest` (default) to verify.
        tag = tag or "latest"
        tag_exists = any(
            tag_dict["name"] == tag for tag_dict in response.json()[0].get("tags")
        )
        if tag_exists:
            message = {
                "type": "success",
                "message": "Environment image {} exists in GitLab CERN.".format(
                    full_prefixed_image
                ),
            }
            return True, message
        else:
            message = {
                "type": "warning",
                "message": 'Environment image {} in GitLab CERN does not exist: Tag "{}" missing.'.format(
                    full_prefixed_image, tag
                ),
            }
            return False, message


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
        message = {
            "type": "error",
            "message": "Something went wrong when querying {}".format(
                docker_registry_url
            ),
        }
        return False, message

    if not response.ok:
        if response.status_code == 404:
            msg = response.text
            message = {
                "type": "warning",
                "message": "Environment image {} does not exist in Docker Hub: {}".format(
                    full_image, msg
                ),
            }
            return False, message
        else:
            message = {
                "type": "warning",
                "message": "==> WARNING: Existence of environment image {} in Docker Hub could not be verified. Status code: {} {}".format(
                    full_image, response.status_code, response.reason,
                ),
            }
            return False, message
    else:
        message = {
            "type": "success",
            "message": "Environment image {} exists in Docker Hub.".format(full_image),
        }
        return True, message


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


def _get_full_image_name(image, tag=None):
    """Return full image name with tag if is passed."""
    return "{}{}".format(image, ":{}".format(tag) if tag else "")


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
