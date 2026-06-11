# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2021, 2022, 2026 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""REANA client validate environments tests."""

from unittest.mock import MagicMock, patch
import pytest

from reana_client.errors import EnvironmentValidationError
from reana_client.validation.environments import (
    EnvironmentValidatorCWL,
    EnvironmentValidatorSerial,
    EnvironmentValidatorSnakemake,
    EnvironmentValidatorYadage,
)


@pytest.mark.parametrize(
    "image, output, exit_",
    [
        ("foo:bar", "has the correct format", False),
        ("foo/bar:baz", "has the correct format", False),
        ("foo/bar", "not have an explicit tag", False),
        ("foo/bar:", "tag is not recommended", False),
        ("foo/bar:latest", "tag is not recommended", False),
        ("foo:master", "tag is not recommended", False),
        ("foo:bar:baz", "has invalid tag", True),
        ("foo:bar:", "has invalid tag", True),
        ("foo:bar ", "contains illegal characters", True),
    ],
)
def test_validate_environment_image_tag(image, output, exit_):
    """Validate workflow environment image tags."""
    validator = EnvironmentValidatorSerial()
    if exit_:
        with pytest.raises(EnvironmentValidationError) as e:
            validator._validate_image_tag(image)
        assert output in str(e)
    else:
        validator._validate_image_tag(image)
        assert output in validator.messages.pop()["message"]


@pytest.mark.parametrize(
    "image, tag, full_image_name",
    [
        ("foo", "bar", "foo:bar"),
        ("foo", "", "foo"),
        ("foo", None, "foo"),
        ("foo", "latest", "foo:latest"),
    ],
)
def test_get_full_image_name(image, tag, full_image_name):
    validator = EnvironmentValidatorSerial()
    assert validator._get_full_image_name(image, tag) == full_image_name


@pytest.mark.parametrize(
    "full_image, expected_url",
    [
        (
            "reanahub/reana-env-aliphysics:vAN-20180614-1",
            "https://hub.docker.com/v2/repositories/reanahub/reana-env-aliphysics/tags/vAN-20180614-1",
        ),
        (
            "docker.io/reanahub/reana-env-aliphysics:vAN-20180614-1",
            "https://hub.docker.com/v2/repositories/reanahub/reana-env-aliphysics/tags/vAN-20180614-1",
        ),
        (
            "python:2.7",
            "https://hub.docker.com/v2/repositories/library/python/tags/2.7",
        ),
    ],
)
def test_image_exists_in_dockerhub(full_image, expected_url):
    """Test that URL is correct when querying DockerHub."""
    validator = EnvironmentValidatorSerial()
    image, tag = validator._validate_image_tag(full_image)
    get_mock = MagicMock()
    get_mock.return_value.ok = True
    with patch("requests.get", get_mock):
        assert validator._image_exists_in_dockerhub(image, tag)
        get_mock.assert_called_once_with(expected_url)


@pytest.mark.parametrize(
    "access_token, vetting_enabled, allowlist, image, expected_message_type, expected_message_content, should_raise",
    [
        # Test case 1: No access token provided
        (
            None,
            True,
            ["python:3.8"],
            "python:3.8",
            "warning",
            "No access token provided",
            False,
        ),
        # Test case 2: Vetting enabled, image in allowlist
        (
            "test_token",
            True,
            ["python:3.8", "ubuntu:20.04"],
            "python:3.8",
            None,
            None,
            False,
        ),
        # Test case 3: Vetting enabled, image not in allowlist
        (
            "test_token",
            True,
            ["python:3.8", "ubuntu:20.04"],
            "nginx:latest",
            None,
            "Environment image is not allowed: nginx:latest",
            True,
        ),
        # Test case 4: Vetting disabled, image not in allowlist (should pass)
        ("test_token", False, ["python:3.8"], "nginx:latest", None, None, False),
        # Test case 5: Vetting enabled, empty allowlist
        (
            "test_token",
            True,
            [],
            "python:3.8",
            None,
            "Environment image is not allowed: python:3.8",
            True,
        ),
    ],
)
def test_check_vetting(
    access_token,
    vetting_enabled,
    allowlist,
    image,
    expected_message_type,
    expected_message_content,
    should_raise,
):
    """Test the check_vetting function with various scenarios."""
    validator = EnvironmentValidatorSerial(access_token=access_token)

    mock_cluster_info = {
        "vetted_container_images_enabled": {"value": vetting_enabled},
        "vetted_container_images_allowlist": {"value": allowlist},
    }

    def _invoke():
        if access_token:
            with patch("reana_client.api.client.info", return_value=mock_cluster_info):
                validator.check_image_authorized(image)
        else:
            validator.check_image_authorized(image)

    if should_raise:
        with pytest.raises(EnvironmentValidationError) as exc_info:
            _invoke()
        assert expected_message_content in str(exc_info.value)
    else:
        _invoke()
        if expected_message_type is None:
            assert len(validator.messages) == 0
        else:
            assert len(validator.messages) == 1
            message = validator.messages[0]
            assert message["type"] == expected_message_type
            assert expected_message_content in message["message"]


def test_check_vetting_api_error():
    """Test check_vetting function when API call fails."""
    validator = EnvironmentValidatorSerial(access_token="test_token")

    # Mock the info function to raise an exception
    with patch(
        "reana_client.api.client.info", side_effect=Exception("API connection failed")
    ):
        validator.check_image_authorized("python:3.8")

    # Check that a warning message was added
    assert len(validator.messages) == 1
    message = validator.messages[0]
    assert message["type"] == "warning"
    assert "Could not check if container images are authorised" in message["message"]
    assert "API connection failed" in message["message"]


def _serial_validator(image):
    steps = [{"environment": image, "kubernetes_uid": None}]
    return EnvironmentValidatorSerial(workflow_steps=steps)


def _snakemake_validator(image):
    steps = [{"environment": image, "kubernetes_uid": None}]
    return EnvironmentValidatorSnakemake(workflow_steps=steps)


def _yadage_validator(image):
    stages = [
        {
            "scheduler": {
                "step": {
                    "environment": {
                        "environment_type": "docker-encapsulated",
                        "image": image,
                    }
                }
            }
        }
    ]
    return EnvironmentValidatorYadage(workflow_steps=stages)


def _cwl_validator(image):
    graph = [{"requirements": {"DockerRequirement": {"dockerPull": image}}}]
    return EnvironmentValidatorCWL(workflow_steps=graph)


@pytest.mark.parametrize(
    "make_validator",
    [_serial_validator, _yadage_validator, _cwl_validator, _snakemake_validator],
    ids=["serial", "yadage", "cwl", "snakemake"],
)
@pytest.mark.parametrize(
    "image",
    [
        "/cvmfs/unpacked.cern.ch/registry.hub.docker.com/reanahub/reana-env-root6:6.18.04",
        "/cvmfs/unpacked.cern.ch/registry.hub.docker.com/reanahub/reana-env-root6",
        "/workspace/images/my_tool.sif",
    ],
)
def test_validate_singularity_environment(make_validator, image):
    """Test that Singularity/Apptainer images skip registry validation.

    The skip logic lives in the shared ``EnvironmentValidatorBase``, so it
    applies to every workflow type (serial, yadage, CWL and Snakemake).
    """
    validator = make_validator(image)
    with patch("requests.get") as get_mock:
        validator.validate_environment()
        get_mock.assert_not_called()
    assert image in validator.validated_images
    assert any("Singularity" in msg["message"] for msg in validator.messages)
