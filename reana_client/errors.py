# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2018 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""REANA-Client errors."""


class FileUploadError(Exception):
    """File upload didn't succeed."""


class FileDeletionError(Exception):
    """File deletion didn't succeed."""


class EnvironmentValidationError(Exception):
    """REANA workflow environment validation didn't succeed."""


class ParameterValidationError(Exception):
    """REANA workflow parameter validation didn't succeed."""
