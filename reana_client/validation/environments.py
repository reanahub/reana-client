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
inside the container, comparing them against the cluster runtime user. These
checks live where a container runtime and the user's registry credentials
already exist, and all of their findings are advisory.
"""

import shutil
import subprocess

from reana_commons.config import (
    WORKFLOW_RUNTIME_USER_GID,
    WORKFLOW_RUNTIME_USER_UID,
)

#: Default per-image timeout (seconds) for a local ``docker pull``/``run``.
LOCAL_IMAGE_CHECK_TIMEOUT = 600


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
    # Override the entrypoint so the image's own code does not run -- only ``id``.
    inspect = subprocess.run(
        [cli, "run", "--rm", "--entrypoint", "/bin/sh", image, "-c", "id -u && id -G"],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if inspect.returncode != 0:
        raise RuntimeError(
            (inspect.stderr or inspect.stdout).strip() or "inspect failed"
        )
    lines = inspect.stdout.strip().splitlines()
    uid = int(lines[-2])
    gids = [int(gid) for gid in lines[-1].split()]
    return uid, gids


def check_images_locally(
    images,
    runtime_uid=WORKFLOW_RUNTIME_USER_UID,
    runtime_gid=WORKFLOW_RUNTIME_USER_GID,
    timeout=LOCAL_IMAGE_CHECK_TIMEOUT,
):
    """Pull + inspect images locally to check REANA runtime UID/GID compatibility.

    REANA forces every workflow step to run as ``runtime_uid``/``runtime_gid``
    (a non-root UID kept in group 0 by default) regardless of the image's own
    ``USER``. An image whose user is not a member of that group, or that expects
    a different UID, may hit permission errors. This warns about that *before*
    the run.

    :param images: image references (as returned by the server validation).
    :param runtime_uid: UID REANA runs workflow steps as.
    :param runtime_gid: GID REANA runs workflow steps as.
    :returns: list of advisory findings ``{code, message, image}``; never raises.
    """
    findings = []
    images = [image for image in (images or []) if image]
    if not images:
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

    for image in images:
        try:
            uid, gids = _image_uid_gids_local(cli, image, timeout)
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
                    "message": "Could not pull/inspect image '{}': {}".format(image, e),
                }
            )
            continue
        if runtime_gid not in gids:
            findings.append(
                {
                    "code": "image_gid",
                    "image": image,
                    "message": "Image '{}' user is not a member of GID {} (found "
                    "{}); files may be inaccessible when REANA runs the step as "
                    "UID {}/GID {}.".format(
                        image, runtime_gid, gids, runtime_uid, runtime_gid
                    ),
                }
            )
        if uid != runtime_uid:
            findings.append(
                {
                    "code": "image_uid",
                    "image": image,
                    "message": "Image '{}' default UID is {} but REANA runs steps "
                    "as UID {}.".format(image, uid, runtime_uid),
                }
            )
    return findings
