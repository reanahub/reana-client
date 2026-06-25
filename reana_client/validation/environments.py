# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2021, 2022, 2023, 2024, 2025 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""Local container-engine runtime-environment checks for ``reana-client validate --pull``.

Specification loading and validation now happen server-side, so the client no
longer parses engine-specific specifications or talks to remote registries. The
only environment checks left run on the machine where reana-client runs: for
``reana-client validate --pull`` they pull each image the *server* reported from
the loaded specification and read its real default UID/GIDs by running ``id``
inside the container, comparing them against every effective step runtime
identity. These checks live where a container runtime and the user's registry
credentials already exist, and all of their findings are advisory.
"""

import shutil
import subprocess
import uuid

#: Default per-image timeout (seconds) for a local ``docker pull``/``run``.
LOCAL_IMAGE_CHECK_TIMEOUT = 600
LOCAL_IMAGE_CLEANUP_TIMEOUT = 30


def _local_container_cli():
    """Return an available container CLI (``docker`` or ``podman``) or ``None``."""
    for cli in ("docker", "podman"):
        if shutil.which(cli):
            return cli
    return None


def _image_uid_gids_local(cli, image, timeout):
    """Pull and run ``id`` in ``image`` to obtain its default UID and GIDs.

    :raises RuntimeError: if the image cannot be inspected.
    """
    # Best-effort refresh of the image. Failures are ignored: a locally-built
    # image may not exist in any registry, and ``docker run`` below still uses
    # the local copy (and auto-pulls a missing remote image). The run is the
    # authority on whether the image is usable.
    subprocess.run(
        [cli, "pull", image],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    # Ignore the configured entrypoint and deliberately use the image-provided
    # shell and ``id`` binaries to inspect the identity seen at runtime.
    container_name = "reana-validation-{}".format(uuid.uuid4().hex)
    try:
        inspect = subprocess.run(
            [
                cli,
                "run",
                "--name",
                container_name,
                "--rm",
                "--entrypoint",
                "/bin/sh",
                image,
                "-c",
                "id -u && id -G",
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    finally:
        # Killing the CLI on timeout does not necessarily stop the daemon-owned
        # container. Remove only the collision-resistant name from this call.
        try:
            subprocess.run(
                [cli, "rm", "-f", container_name],
                capture_output=True,
                text=True,
                timeout=LOCAL_IMAGE_CLEANUP_TIMEOUT,
            )
        except (OSError, subprocess.SubprocessError):
            pass
    if inspect.returncode != 0:
        raise RuntimeError(
            (inspect.stderr or inspect.stdout).strip() or "inspect failed"
        )
    lines = inspect.stdout.strip().splitlines()
    uid = int(lines[-2])
    gids = [int(gid) for gid in lines[-1].split()]
    return uid, gids


def check_images_locally(
    environments,
    timeout=LOCAL_IMAGE_CHECK_TIMEOUT,
):
    """Pull + inspect images locally to check REANA runtime UID/GID compatibility.

    Each input record carries the effective identity of the step that uses the
    image, including any per-step ``kubernetes_uid`` override.

    :param environments: ``{image, runtime_uid, runtime_gid}`` records.
    :returns: list of advisory findings ``{code, message, image}``; never raises.
    """
    findings = []
    image_environments = []
    seen_environments = set()
    for environment in environments or []:
        image = environment.get("image")
        if not image:
            continue
        key = (
            image,
            int(environment["runtime_uid"]),
            int(environment["runtime_gid"]),
        )
        if key not in seen_environments:
            seen_environments.add(key)
            image_environments.append(key)

    if not image_environments:
        return findings

    cli = _local_container_cli()
    if not cli:
        findings.append(
            {
                "code": "container_cli_unavailable",
                "image": "",
                "message": "No local container engine (docker/podman) was found, "
                "so the --pull image checks were skipped.",
            }
        )
        return findings

    inspected_images = {}
    failed_images = set()
    for image, effective_uid, effective_gid in image_environments:
        if image not in inspected_images and image not in failed_images:
            try:
                inspected_images[image] = _image_uid_gids_local(cli, image, timeout)
            except (
                RuntimeError,
                subprocess.SubprocessError,
                OSError,
                ValueError,
                IndexError,
            ) as e:
                findings.append(
                    {
                        "code": "image_inspect_failed",
                        "image": image,
                        "message": "Could not pull/inspect image '{}': {}".format(
                            image, e
                        ),
                    }
                )
                failed_images.add(image)
        if image in failed_images:
            continue

        uid, gids = inspected_images[image]
        if effective_gid not in gids:
            findings.append(
                {
                    "code": "image_gid",
                    "image": image,
                    "message": "Image '{}' user is not a member of GID {} (found "
                    "{}); files may be inaccessible when REANA runs the step as "
                    "UID {}/GID {}.".format(
                        image, effective_gid, gids, effective_uid, effective_gid
                    ),
                }
            )
        if uid != effective_uid:
            findings.append(
                {
                    "code": "image_uid",
                    "image": image,
                    "message": "Image '{}' default UID is {} but REANA runs steps "
                    "as UID {}.".format(image, uid, effective_uid),
                }
            )
    return findings
