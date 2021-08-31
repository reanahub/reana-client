# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2017, 2018, 2021 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
"""CWL v1.0 interface CLI implementation."""

import io
import logging
import os
import re
import sys
import traceback
from time import sleep

import click
import yaml
from bravado.exception import HTTPServerError
from cwltool.load_tool import fetch_document
from cwltool.main import printdeps

from reana_client.cli.utils import add_access_token_options
from reana_client.utils import load_workflow_spec
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
    file_dependencies_obj = yaml.load(
        in_memory_buffer.getvalue(), Loader=yaml.FullLoader
    )
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
                        [{"location": location}], basedir, workflow_id, access_token,
                    )
        else:
            with open(abs_file_path, "r") as f:
                upload_file(workflow_id, f, file_path, access_token)
                logging.error("File {} uploaded.".format(file_path))


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
    import json
    from reana_client.utils import get_api_url
    from reana_client.api.client import (
        create_workflow,
        get_workflow_logs,
        start_workflow,
        upload_file,
    )

    logging.basicConfig(
        format="[%(levelname)s] %(message)s",
        stream=sys.stderr,
        level=logging.INFO if quiet else logging.DEBUG,
    )
    try:
        basedir = basedir or os.path.abspath(os.path.dirname(processfile))
        reana_spec = {"workflow": {"type": "cwl"}}
        job = {}
        if jobfile:
            with open(jobfile) as f:
                job = yaml.load(f, Loader=yaml.FullLoader)

        if processfile:
            reana_spec["inputs"] = {"parameters": job}
            reana_spec["workflow"]["specification"] = load_workflow_spec(
                reana_spec["workflow"]["type"], processfile
            )
        reana_spec["workflow"]["specification"] = replace_location_in_cwl_spec(
            reana_spec["workflow"]["specification"]
        )
        logging.info("Connecting to {0}".format(get_api_url()))
        reana_specification = json.loads(json.dumps(reana_spec, sort_keys=True))
        response = create_workflow(reana_specification, "cwl-test", access_token)
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
        response = start_workflow(
            workflow_id, access_token, reana_spec["inputs"]["parameters"]
        )
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
            import ast

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


def replace_location_in_cwl_spec(spec):
    """Replace absolute paths with relative in a workflow.

    Recursively replace absolute paths with relative in a normalized (packed)
    workflow.
    """
    if spec.get("$graph"):
        result = spec.copy()
        result["$graph"] = []
        for tool in spec["$graph"]:
            result["$graph"].append(replace_location_in_cwl_tool(tool))
        return result
    elif spec.get("inputs"):
        return replace_location_in_cwl_tool(spec)
    else:
        return spec


def replace_location_in_cwl_tool(spec):
    """Recursively replace absolute paths with relative."""
    # tools
    inputs_parameters = []
    for param in spec["inputs"]:
        if param["type"] == "File":
            if param.get("default", ""):
                location = "location" if param["default"].get("location") else "path"
                param["default"][location] = param["default"][location].split("/")[-1]
        inputs_parameters.append(param)
    spec["inputs"] = inputs_parameters
    # workflows
    if spec.get("steps"):
        steps = []
        for tool in spec["steps"]:
            tool_inputs = []
            for param in tool["in"]:
                if param.get("default") and type(param["default"]) is dict:
                    if (
                        param["default"].get("class", param["default"].get("type"))
                        == "File"
                    ):
                        location = (
                            "location" if param["default"].get("location") else "path"
                        )
                        param["default"][location] = param["default"][location].split(
                            "/"
                        )[-1]
                tool_inputs.append(param)
            tool["in"] = tool_inputs
            steps.append(tool)
        spec["steps"] = steps
    return spec


if __name__ == "__main__":
    cwl_runner()
