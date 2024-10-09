# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2019, 2020, 2021, 2024 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
"""REANA client API utils."""

from email.message import Message


def get_path_from_operation_id(paths_dict, operation_id):
    """Find API path based on operation id."""
    paths = paths_dict.keys()
    for path in paths:
        methods = paths_dict[path].keys()
        for method in methods:
            if paths_dict[path][method]["operationId"] == operation_id:
                return path
    return None


def get_content_disposition_filename(content_disposition_header):
    """Retrieve filename from a Content-Disposition like header.

    Using email module instead of cgi.parse header due to https://peps.python.org/pep-0594/#cgi

    Return a filename if found, otherwise a default string.
    """
    msg = Message()
    msg["content-disposition"] = content_disposition_header
    filename = msg.get_filename()

    return filename if filename else "downloaded_file"
