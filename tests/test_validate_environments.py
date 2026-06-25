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
import subprocess

from reana_client.validation.environments import check_images_locally


def _environment(image, runtime_uid=1000, runtime_gid=0):
    """Build an image environment record returned by the server."""
    return {
        "image": image,
        "runtime_uid": runtime_uid,
        "runtime_gid": runtime_gid,
    }


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
        findings = check_images_locally([_environment("busybox:1.36")])
    assert [f["code"] for f in findings] == ["container_cli_unavailable"]


def test_check_images_locally_uid_mismatch():
    with patch(
        "reana_client.validation.environments._local_container_cli",
        return_value="docker",
    ), patch(
        "reana_client.validation.environments.subprocess.run",
        side_effect=_fake_run(uid_line="0", gid_line="0"),
    ):
        findings = check_images_locally([_environment("busybox:1.36")])
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
        findings = check_images_locally([_environment("busybox:1.36")])
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
        findings = check_images_locally([_environment("does/not:exist")])
    assert [f["code"] for f in findings] == ["image_inspect_failed"]


def test_check_images_locally_no_images():
    assert check_images_locally([]) == []


def test_check_images_locally_checks_same_image_under_each_runtime_uid():
    """Image inspection is reused, but every effective identity is compared."""
    environments = [
        {"image": "busybox:1.36", "runtime_uid": 1000, "runtime_gid": 0},
        {"image": "busybox:1.36", "runtime_uid": 2000, "runtime_gid": 0},
    ]
    with patch(
        "reana_client.validation.environments._local_container_cli",
        return_value="docker",
    ), patch(
        "reana_client.validation.environments.subprocess.run",
        side_effect=_fake_run(uid_line="2000", gid_line="0"),
    ) as run_mock:
        findings = check_images_locally(environments)

    assert [finding["code"] for finding in findings] == ["image_uid"]
    assert "UID 1000" in findings[0]["message"]
    assert run_mock.call_count == 3


def test_timed_out_image_inspection_forces_named_container_cleanup():
    """A timed-out engine client cannot leave its daemon container behind."""
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        if args[1] == "run":
            raise subprocess.TimeoutExpired(args, kwargs["timeout"])
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    with patch(
        "reana_client.validation.environments._local_container_cli",
        return_value="docker",
    ), patch("reana_client.validation.environments.subprocess.run", side_effect=run):
        findings = check_images_locally([_environment("busybox:1.36")], timeout=1)

    run_call = next(call for call in calls if call[1] == "run")
    cleanup_call = next(call for call in calls if call[1:3] == ["rm", "-f"])
    container_name = run_call[run_call.index("--name") + 1]
    assert cleanup_call == ["docker", "rm", "-f", container_name]
    assert [finding["code"] for finding in findings] == ["image_inspect_failed"]
