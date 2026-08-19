# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2018, 2021, 2022 CERN.
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


class WorkflowLogsPrunedError(Exception):
    """Workflow logs were removed by the cluster retention policy."""

    def __init__(self, message, logs_pruned_at=None):
        """Store the server message and optional pruning timestamp."""
        super().__init__(message)
        self.logs_pruned_at = logs_pruned_at
