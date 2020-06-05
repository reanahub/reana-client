# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2019 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
"""REANA client API utils."""


def get_path_from_operation_id(paths_dict, operation_id):
    """Find API path based on operation id."""
    paths = paths_dict.keys()
    for path in paths:
        methods = paths_dict[path].keys()
        for method in methods:
            if paths_dict[path][method]["operationId"] == operation_id:
                return path
    return None
