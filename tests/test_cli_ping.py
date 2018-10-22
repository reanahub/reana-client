# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2017, 2018 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""REANA client ping tests."""

from click.testing import CliRunner

from reana_client.cli import cli


def test_ping(click_config_obj):
    """Test ping command."""
    runner = CliRunner()
    result = runner.invoke(cli, ['ping'], obj=click_config_obj)
    assert result.exit_code == 0
