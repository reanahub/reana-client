# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2021 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""REANA client validate environments tests."""

import pytest

from reana_client.utils import _validate_image_tag


@pytest.mark.parametrize(
    "image, output, exit_",
    [
        ("foo:bar", "has correct format", False),
        ("foo/bar:baz", "has correct format", False),
        ("foo/bar", "not have an explicit tag", False),
        ("foo/bar:", "tag is not recommended", False),
        ("foo/bar:latest", "tag is not recommended", False),
        ("foo:master", "tag is not recommended", False),
        ("foo:bar:baz", "has invalid tag", True),
        ("foo:bar:", "has invalid tag", True),
    ],
)
def test_validate_environment_image_tag(image, output, exit_, capsys):
    """Validate workflow environment image tags."""
    if exit_:
        with pytest.raises(SystemExit):
            _validate_image_tag(image)
    else:
        _validate_image_tag(image)
    captured = capsys.readouterr()
    assert output in (captured.err if exit_ else captured.out)
