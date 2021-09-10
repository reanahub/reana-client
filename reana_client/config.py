# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2017, 2018 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
"""REANA client configuration."""

import os

import pkg_resources

reana_yaml_valid_file_names = ["reana.yaml", "reana.yml"]
"""REANA specification valid file names."""

reana_yaml_schema_file_path = pkg_resources.resource_filename(
    __name__, "schemas/reana_analysis_schema.json"
)
"""REANA specification schema location."""

default_user = "00000000-0000-0000-0000-000000000000"
"""Default user to use when submitting workflows to REANA Server."""

ERROR_MESSAGES = {
    "missing_access_token": "Please provide your access token by using"
    " the -t/--access-token flag, or by setting the"
    " REANA_ACCESS_TOKEN environment variable."
}

JSON = "json"
"""Json output format."""

TIMECHECK = 5
"""Time between workflow status check."""

URL = "url"
"""Url output format."""

RUN_STATUSES = [
    "created",
    "running",
    "finished",
    "failed",
    "deleted",
    "stopped",
    "queued",
    "pending",
]
"""Available run statuses."""

ENVIRONMENT_IMAGE_SUSPECTED_TAGS_VALIDATOR = ["latest", "master", ""]
"""Warns user if above environment image tags are used."""

DOCKER_REGISTRY_INDEX_URL = "https://index.docker.io/v1/repositories/{image}/tags/{tag}"
"""Docker Hub registry index URL."""

GITLAB_CERN_REGISTRY_INDEX_URL = (
    "https://gitlab.cern.ch/api/v4/projects/{image}/registry/repositories?tags=1"
)
"""GitLab CERN registry index URL."""

GITLAB_CERN_REGISTRY_PREFIX = "gitlab-registry.cern.ch"
"""Prefix for GitLab image registry at CERN."""

COMMAND_DANGEROUS_OPERATIONS = ["sudo ", "cd /"]
"""Operations in workflow commands considered dangerous."""

PRINTER_COLOUR_SUCCESS = "green"
"""Default colour for success messages on terminal."""

PRINTER_COLOUR_WARNING = "yellow"
"""Default colour for warning messages on terminal."""

PRINTER_COLOUR_ERROR = "red"
"""Default colour for error messages on terminal."""

PRINTER_COLOUR_INFO = "cyan"
"""Default colour for info messages on terminal."""

HEALTH_TO_MSG_TYPE = {
    "critical": "error",
    "healthy": "success",
    "warning": "warning",
}

JOB_STATUS_TO_MSG_COLOR = {
    "failed": "red",
    "finished": "green",
    "running": "bright_blue",
}
