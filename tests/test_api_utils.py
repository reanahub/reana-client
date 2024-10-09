# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2024 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""REANA API utils tests."""

import pytest

from reana_client.api.utils import get_content_disposition_filename


@pytest.mark.parametrize(
    "content_disposition_header, expected_filename",
    [
        ("inline", "downloaded_file"),
        ("attachment", "downloaded_file"),
        ('attachment; filename="example.txt"', "example.txt"),
        ("attachment; filename*=UTF-8''example.txt", "example.txt"),
        ("attachment; filename=folder", "folder"),
        ('attachment; filename="folder/*/example.txt"', "folder/*/example.txt"),
    ],
)
def test_get_content_disposition_filename(
    content_disposition_header, expected_filename
):
    assert (
        get_content_disposition_filename(content_disposition_header)
        == expected_filename
    )
