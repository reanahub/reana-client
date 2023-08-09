# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2021, 2022 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""REANA client validate environments tests."""

from unittest.mock import MagicMock, patch
import pytest

from reana_client.errors import EnvironmentValidationError
from reana_client.validation.environments import EnvironmentValidatorSerial


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
