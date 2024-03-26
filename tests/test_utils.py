# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2022, 2024 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""REANA client utils tests."""

from unittest.mock import Mock, patch
from datetime import datetime

from reana_client.utils import get_workflow_duration


def test_duration_pending_workflow():
    workflow = {
        "progress": {
            "run_started_at": None,
            "run_finished_at": None,
        }
    }
    assert get_workflow_duration(workflow) is None


def test_duration_finished_workflow():
    workflow = {
        "progress": {
            "run_started_at": "2022-06-16T14:42:11",
            "run_finished_at": "2022-06-16T14:43:22",
        }
    }
    assert get_workflow_duration(workflow) == 60 + 11


def test_duration_stopped_workflow():
    workflow = {
        "progress": {
            "run_started_at": "2022-06-16T14:42:11",
            "run_stopped_at": "2022-06-16T14:43:22",
            "run_finished_at": None,
        }
    }
    assert get_workflow_duration(workflow) == 60 + 11


def test_duration_running_workflow():
    workflow = {
        "progress": {
            "run_started_at": "2022-07-16T14:42:11",
            "run_finished_at": None,
        }
    }
    mock_datetime = Mock(wraps=datetime)
    mock_datetime.utcnow.return_value = datetime(2022, 7, 16, 14, 43, 22)
    with patch("reana_client.utils.datetime", mock_datetime):
        assert get_workflow_duration(workflow) == 60 + 11
