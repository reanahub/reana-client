# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2021, 2022, 2023, 2025 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""REANA client validate environments tests."""

from types import SimpleNamespace
from unittest.mock import patch

from reana_client.validation.environments import check_images_locally


def _fake_run(uid_line="0", gid_line="0", pull_rc=0, run_rc=0):
    """Build a subprocess.run stub for a (pull, id) command pair."""

    def runner(args, **kwargs):
        if args[1] == "pull":
            return SimpleNamespace(returncode=pull_rc, stdout="", stderr="err")
        return SimpleNamespace(
            returncode=run_rc, stdout=f"{uid_line}\n{gid_line}\n", stderr="err"
        )

    return runner


def test_check_images_locally_no_container_engine():
    with patch(
        "reana_client.validation.environments._local_container_cli",
        return_value=None,
    ):
        findings = check_images_locally(["busybox:1.36"], 1000, 0)
    assert [f["code"] for f in findings] == ["container_cli_unavailable"]


def test_check_images_locally_uid_mismatch():
    with patch(
        "reana_client.validation.environments._local_container_cli",
        return_value="docker",
    ), patch(
        "reana_client.validation.environments.subprocess.run",
        side_effect=_fake_run(uid_line="0", gid_line="0"),
    ):
        findings = check_images_locally(["busybox:1.36"], 1000, 0)
    # UID 0 != 1000 -> uid warning; GID 0 present -> no gid warning.
    assert [f["code"] for f in findings] == ["image_uid"]


def test_check_images_locally_gid_not_member():
    with patch(
        "reana_client.validation.environments._local_container_cli",
        return_value="docker",
    ), patch(
        "reana_client.validation.environments.subprocess.run",
        side_effect=_fake_run(uid_line="1000", gid_line="1000"),
    ):
        findings = check_images_locally(["busybox:1.36"], 1000, 0)
    # UID matches but GID 0 absent -> gid warning only.
    assert [f["code"] for f in findings] == ["image_gid"]


def test_check_images_locally_inspect_failure():
    # A best-effort pull failure is ignored; the failure surfaces at `docker run`
    # (e.g. a missing image, or one without /bin/sh).
    with patch(
        "reana_client.validation.environments._local_container_cli",
        return_value="docker",
    ), patch(
        "reana_client.validation.environments.subprocess.run",
        side_effect=_fake_run(pull_rc=1, run_rc=1),
    ):
        findings = check_images_locally(["does/not:exist"], 1000, 0)
    assert [f["code"] for f in findings] == ["image_inspect_failed"]


def test_check_images_locally_no_images():
    assert check_images_locally([], 1000, 0) == []
