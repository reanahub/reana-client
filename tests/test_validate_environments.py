# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2021 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""REANA client validate environments tests."""

import pytest

from reana_client.errors import EnvironmentValidationError
from reana_client.validation.environments import SerialEnvironmentValidator


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
    ],
)
def test_validate_environment_image_tag(image, output, exit_):
    """Validate workflow environment image tags."""
    validator = SerialEnvironmentValidator()
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
    validator = SerialEnvironmentValidator()
    assert validator._get_full_image_name(image, tag) == full_image_name
