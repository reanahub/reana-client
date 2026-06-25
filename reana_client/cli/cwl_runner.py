# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2018, 2019, 2020, 2021, 2022, 2023 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
"""CWL v1.0 interface CLI implementation."""

import io
import logging
import os
import re
import shutil
import sys
import tempfile
import traceback
from time import sleep

import click
import yaml
from bravado.exception import HTTPServerError
from cwltool.load_tool import fetch_document
from cwltool.main import printdeps

from reana_client.cli.utils import add_access_token_options
from reana_client.utils import is_regular_path
from reana_client.version import __version__


def findfiles(wo, fn=None):
    """Return a list CWL workflow files."""
    if fn is None:
        fn = []
    if isinstance(wo, dict):
        if wo.get("class") == "File":
            fn.append(wo)
            findfiles(wo.get("secondaryFiles"), fn)
        elif wo.get("class") == "Directory":
            fn.append(wo)
            findfiles(wo.get("secondaryFiles"), fn)
        else:
            for w in wo.values():
                findfiles(w, fn)
    elif isinstance(wo, list):
        for w in wo:
            findfiles(w, fn)
    return fn


def get_file_dependencies_obj(cwl_obj, basedir):
    """Return a dictionary which contains the CWL workflow file dependencies.

    :param cwl_obj: A CWL tool or job which might contain file dependencies.
    :param basedir: Workflow base dir.
    :returns: A dictionary composed of valid CWL file dependencies.
    """
    # Load the document
    # remove filename additions (e.g. 'v1.0/conflict-wf.cwl#collision')
    document = cwl_obj.split("#")[0]
    document_loader, workflow_obj, uri = fetch_document(document)
    in_memory_buffer = io.StringIO()
    # Get dependencies
    printdeps(
        workflow_obj,
        document_loader.loader,
        in_memory_buffer,
        "primary",
        uri,
        basedir=basedir,
    )
    file_dependencies_obj = yaml.safe_load(in_memory_buffer.getvalue())
    in_memory_buffer.close()
    return file_dependencies_obj


def upload_files(files, basedir, workflow_id, access_token):
    """Upload file or directory to REANA server."""
    from reana_client.api.client import upload_file

    for cwl_file_object in files:
        file_path = cwl_file_object.get("location")
        abs_file_path = os.path.join(basedir, file_path)

        if os.path.isdir(abs_file_path):
            for root, dirs, files in os.walk(abs_file_path, topdown=False):
                for next_path in files + dirs:
                    location = os.path.join(root, next_path).replace(basedir + "/", "")
                    upload_files(
                        [{"location": location}],
                        basedir,
                        workflow_id,
                        access_token,
                    )
        else:
            with open(abs_file_path, "r") as f:
                upload_file(workflow_id, f, file_path, access_token)
                logging.error("File {} uploaded.".format(file_path))


def _stage_cwl_member(bundle_dir, basedir, location):
    """Copy one CWL bundle member after enforcing source/destination containment.

    CWL dependency locations are untrusted document input. Absolute paths,
    parent traversal, symlinks (including symlinked parents), missing files, and
    any source outside ``basedir`` are rejected before opening or creating a
    destination. The same normalized relative path is then checked under the
    temporary bundle directory before copying.

    :returns: the normalized bundle-relative path.
    :raises ValueError: if ``location`` is not a safe regular file.
    """
    if not isinstance(location, str) or not location or os.path.isabs(location):
        raise ValueError("Unsafe CWL bundle member path: {!r}".format(location))

    relative_path = os.path.normpath(location)
    if relative_path in (".", "..") or relative_path.startswith(".." + os.sep):
        raise ValueError("CWL bundle member escapes --basedir: {}".format(location))

    basedir = os.path.abspath(basedir)
    source = os.path.abspath(os.path.join(basedir, relative_path))
    if os.path.commonpath([basedir, source]) != basedir:
        raise ValueError("CWL bundle member escapes --basedir: {}".format(location))
    if not is_regular_path(source) or not os.path.isfile(source):
        raise ValueError(
            "CWL bundle member is missing, not regular, or symlinked: {}".format(
                location
            )
        )

    bundle_dir = os.path.abspath(bundle_dir)
    destination = os.path.abspath(os.path.join(bundle_dir, relative_path))
    if os.path.commonpath([bundle_dir, destination]) != bundle_dir:
        raise ValueError("CWL bundle destination escapes staging: {}".format(location))

    os.makedirs(os.path.dirname(destination), exist_ok=True)
    shutil.copyfile(source, destination)
    return relative_path


def _create_cwl_workflow(processfile, jobfile, basedir, access_token):
    """Bundle a CWL workflow and its file dependencies and create it server-side.

    The workflow file (optionally selecting a tool via a ``#fragment``), its CWL
    file dependencies, and the job file are staged into a self-contained bundle
    directory which is uploaded; the server loads and validates it in the
    sandbox, so the CWL spec is never loaded on the client.

    :returns: ``(response, job)`` where ``job`` is the parsed job parameters.
    """
    from reana_client.api.client import create_workflow_from_bundle_dir

    # A '#fragment' on the process file selects a specific tool within it.
    basedir = os.path.abspath(basedir)
    document, _, fragment = processfile.partition("#")
    workflow_rel = os.path.relpath(document, basedir)
    workflow_file = workflow_rel + ("#" + fragment if fragment else "")

    job = {}
    job_rel = None
    if jobfile:
        with open(jobfile) as f:
            job = yaml.safe_load(f)
        job_rel = os.path.relpath(jobfile, basedir)

    cwl_dependencies = findfiles([get_file_dependencies_obj(processfile, basedir)])
    bundle_dir = tempfile.mkdtemp()
    try:
        _stage_cwl_member(bundle_dir, basedir, workflow_rel)
        workflow_dependencies = []
        for dependency in cwl_dependencies:
            dependency_path = _stage_cwl_member(
                bundle_dir, basedir, dependency.get("location")
            )
            if dependency_path != workflow_rel:
                workflow_dependencies.append(dependency_path)
        if job_rel:
            _stage_cwl_member(bundle_dir, basedir, job_rel)

        reana_spec = {"workflow": {"type": "cwl", "file": workflow_file}}
        if workflow_dependencies:
            reana_spec["workflow"]["files"] = sorted(set(workflow_dependencies))
        if job_rel:
            reana_spec["workflow"]["parameters"] = {"file": job_rel}
        with open(os.path.join(bundle_dir, "reana.yaml"), "w") as bundle_yaml:
            yaml.dump(reana_spec, bundle_yaml)

        response = create_workflow_from_bundle_dir(bundle_dir, "cwl-test", access_token)
    finally:
        shutil.rmtree(bundle_dir, ignore_errors=True)
    return response, job


@click.command()
@click.version_option(version=__version__)
@click.option("--quiet", is_flag=True, help="No diagnostic output")
@click.option(
    "--outdir",
    type=click.Path(),
    help="Output directory, defaults to the current directory",
)
@click.option("--basedir", type=click.Path(), help="Base directory.")
@add_access_token_options
@click.argument("processfile")
@click.argument("jobfile", required=False)
@click.pass_context
def cwl_runner(ctx, quiet, outdir, basedir, processfile, jobfile, access_token):
    """Run CWL files in a standard format <workflow.cwl> <job.json>."""
    from reana_client.utils import get_api_url
    from reana_client.api.client import (
        get_workflow_logs,
        start_workflow,
    )

    logging.basicConfig(
        format="[%(levelname)s] %(message)s",
        stream=sys.stderr,
        level=logging.INFO if quiet else logging.DEBUG,
    )
    try:
        basedir = basedir or os.path.abspath(os.path.dirname(processfile))
        logging.info("Connecting to {0}".format(get_api_url()))

        response, job = _create_cwl_workflow(
            processfile, jobfile, basedir, access_token
        )

        logging.error(response)
        workflow_name = response["workflow_name"]
        workflow_id = response["workflow_id"]
        logging.info(
            "Workflow {0}/{1} has been created.".format(workflow_name, workflow_id)
        )
        file_dependencies_list = []
        for cwlobj in [processfile, jobfile]:
            if not cwlobj:
                continue
            file_dependencies_obj = get_file_dependencies_obj(cwlobj, basedir)
            file_dependencies_list.append(file_dependencies_obj)
        files_to_upload = findfiles(file_dependencies_list)
        upload_files(files_to_upload, basedir, workflow_id, access_token)
        response = start_workflow(workflow_id, access_token, job)
        logging.error(response)

        first_logs = ""
        while True:
            sleep(1)
            logging.error("Polling workflow logs")
            response = get_workflow_logs(workflow_id, access_token)
            logs = response["logs"]
            if logs != first_logs:
                logging.error(logs[len(first_logs) :])
                first_logs = logs

            if (
                "Final process status" in logs
                or "Traceback (most recent call last)" in logs
            ):
                # click.echo(response['status'])
                break
        try:
            out = (
                re.search(r"FinalOutput[\s\S]*?FinalOutput", logs)
                .group()
                .replace("FinalOutput", "")
            )
            json_output = out.encode("utf8").decode("unicode_escape")
        except AttributeError:
            logging.error("Workflow execution failed")
            sys.exit(1)
        except Exception:
            logging.error(traceback.format_exc())
            sys.exit(1)
        sys.stdout.write(json_output)
        sys.stdout.write("\n")
        sys.stdout.flush()

    except HTTPServerError as e:
        logging.error(traceback.print_exc())
        logging.error(e)
    except Exception:
        logging.error(traceback.print_exc())


if __name__ == "__main__":
    cwl_runner()
