# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
"""REANA client workflow related commands."""

import json
import logging
import os
import sys
import time
import traceback
from pathlib import Path

import click
import requests
import yaml
from jsonschema.exceptions import ValidationError
from reana_client.cli.files import get_files, upload_files
from reana_client.cli.utils import (
    add_access_token_options,
    add_access_token_options_not_required,
    add_pagination_options,
    add_workflow_option,
    check_connection,
    display_formatted_output,
    format_session_uri,
    get_formatted_progress,
    human_readable_or_raw_option,
    key_value_to_dict,
    parse_filter_parameters,
    requires_environments,
    retrieve_workflow_logs,
    follow_workflow_logs,
)
from reana_client.config import (
    ERROR_MESSAGES,
    RUN_STATUSES,
    TIMECHECK,
    CLI_LOGS_FOLLOW_DEFAULT_INTERVAL,
)
from reana_client.printer import display_message
from reana_client.utils import (
    get_reana_yaml_file_path,
    get_workflow_duration,
    get_workflow_name_and_run_number,
    get_workflow_status_change_msg,
    is_uuid_v4,
    load_validate_reana_spec,
    workflow_uuid_or_name,
)
from reana_client.validation.utils import (
    validate_input_parameters,
    validate_workflow_name_parameter,
)
from reana_commons.config import INTERACTIVE_SESSION_TYPES, REANA_COMPUTE_BACKENDS
from reana_commons.errors import REANAValidationError
from reana_commons.validation.operational_options import validate_operational_options


@click.group(help="Workflow management commands")
@click.pass_context
def workflow_management_group(ctx):
    """Top level wrapper for workflow management."""
    logging.debug(ctx.info_name)


@click.group(help="Workflow execution commands")
@click.pass_context
def workflow_execution_group(ctx):
    """Top level wrapper for execution related interaction."""
    logging.debug(ctx.info_name)


@click.group(help="Workflow sharing commands")
@click.pass_context
def workflow_sharing_group(ctx):
    """Top level wrapper for workflow sharing."""
    logging.debug(ctx.info_name)


@workflow_management_group.command("list")
@click.option(
    "-w",
    "--workflow",
    default=None,
    help="List all runs of the given workflow.",
)
@click.option(
    "-s", "--sessions", is_flag=True, help="List all open interactive sessions."
)
@click.option(
    "--format",
    "_format",
    multiple=True,
    help="Format output according to column titles or column values. "
    "Use `<columm_name>=<column_value>` format. "
    "E.g. display workflow with failed status and named test_workflow "
    "`--format status=failed,name=test_workflow`.",
)
@click.option(
    "--json",
    "output_format",
    flag_value="json",
    default=None,
    help="Get output in JSON format.",
)
@click.option(
    "--all",
    "show_all",
    is_flag=True,
    default=False,
    help="Show all workflows including deleted ones.",
)
@click.option(
    "-v",
    "--verbose",
    count=True,
    help="Print out extra information: workflow id, user id, disk usage, "
    "progress, duration.",
)
@human_readable_or_raw_option
@click.option(
    "--sort",
    "sort_column_name",
    default="CREATED",
    help="Sort the output by specified column",
)
@click.option(
    "--filter",
    "filters",
    multiple=True,
    help="Filter workflow that contains certain filtering criteria. "
    "Use `--filter <columm_name>=<column_value>` pairs. "
    "Available filters are ``name`` and ``status``.",
)
@click.option(
    "--include-duration",
    "include_duration",
    is_flag=True,
    default=False,
    help="Include the duration of the workflows in seconds. In case a workflow is in "
    "progress, its duration as of now will be shown.",
)
@click.option(
    "--include-progress",
    "include_progress",
    is_flag=True,
    default=None,
    help="Include progress information of the workflows.",
)
@click.option(
    "--include-workspace-size",
    "include_workspace_size",
    is_flag=True,
    default=None,
    help="Include size information of the workspace.",
)
@click.option(
    "--show-deleted-runs",
    "show_deleted_runs",
    is_flag=True,
    default=False,
    help="Include deleted workflows in the output.",
)
@click.option(
    "--shared",
    "shared",
    is_flag=True,
    default=False,
    help="List all shared (owned and unowned) workflows.",
)
@click.option(
    "--shared-by",
    "shared_by",
    default=None,
    help="List workflows shared by the specified user.",
)
@click.option(
    "--shared-with",
    "shared_with",
    default=None,
    help="List workflows shared with the specified user.",
)
@add_access_token_options
@add_pagination_options
@check_connection
@click.pass_context
def workflows_list(  # noqa: C901
    ctx,
    workflow,
    sessions,
    _format,
    output_format,
    access_token,
    show_all,
    verbose,
    human_readable_or_raw,
    sort_column_name,
    page,
    size,
    filters,
    include_duration: bool,
    include_progress,
    include_workspace_size,
    show_deleted_runs: bool,
    shared,
    shared_by,
    shared_with,
):  # noqa: D301
    """List all workflows and sessions.

    The ``list`` command lists workflows and sessions. By default, the list of
    workflows is returned. If you would like to see the list of your open
    interactive sessions, you need to pass the ``--sessions`` command-line
    option. If you would like to see the list of all workflows, including those
    shared with you, you need to pass the ``--shared`` command-line option.

    Along with specific user emails, you can pass the following special values
    to the ``--shared-by`` and ``--shared-with`` command-line options:\n
    \t - ``--shared-by anybody``: list workflows shared with you by anybody.\n
    \t - ``--shared-with anybody``: list your shared workflows exclusively.\n
    \t - ``--shared-with nobody``: list your unshared workflows exclusively.\n
    \t - ``--shared-with bob@cern.ch``: list workflows shared with bob@cern.ch

    Examples:\n
    \t $ reana-client list --all\n
    \t $ reana-client list --sessions\n
    \t $ reana-client list --verbose --bytes\n
    \t $ reana-client list --shared\n
    \t $ reana-client list --shared-by bob@cern.ch\n
    \t $ reana-client list --shared-with anybody
    """
    from reana_client.api.client import get_workflows

    if shared_by and shared_with:
        display_message(
            "Please provide either --shared-by or --shared-with, not both.",
            msg_type="error",
        )
        sys.exit(1)

    logging.debug("command: {}".format(ctx.command_path.replace(" ", ".")))
    for p in ctx.params:
        logging.debug("{param}: {value}".format(param=p, value=ctx.params[p]))
    type = "interactive" if sessions else "batch"

    status_filter = RUN_STATUSES.copy()
    if not show_deleted_runs and not show_all:
        status_filter.remove("deleted")

    search_filter = None
    if filters:
        filter_names = ["name", "status"]
        provided_status_filter, search_filter = parse_filter_parameters(
            filters, filter_names
        )
        if provided_status_filter:
            status_filter = provided_status_filter

    try:
        response = get_workflows(
            access_token,
            type,
            verbose=bool(verbose),
            page=page,
            size=size,
            status=status_filter,
            search=search_filter,
            include_progress=include_progress,
            include_workspace_size=include_workspace_size,
            workflow=workflow,
            shared=shared,
            shared_by=shared_by,
            shared_with=shared_with,
        )
        verbose_headers = ["id", "user"]
        workspace_size_header = ["size"]
        progress_header = ["progress"]
        duration_header = ["duration"]
        headers = {
            "batch": [
                "name",
                "run_number",
                "created",
                "started",
                "ended",
                "status",
            ],
            "interactive": [
                "name",
                "run_number",
                "created",
                "session_type",
                "session_uri",
                "session_status",
            ],
        }
        if verbose:
            headers[type] += verbose_headers
        if verbose or include_workspace_size:
            headers[type] += workspace_size_header
        if verbose or include_progress:
            headers[type] += progress_header
        if verbose or include_duration:
            headers[type] += duration_header

        if shared:
            headers[type] += ["shared_with", "shared_by"]
        else:
            if shared_with:
                headers[type] += ["shared_with"]
            if shared_by:
                headers[type] += ["shared_by"]

        data = []
        for workflow in response:
            name, run_number = get_workflow_name_and_run_number(workflow["name"])
            workflow["name"] = name
            workflow["run_number"] = run_number
            workflow["duration"] = get_workflow_duration(workflow)
            if type == "interactive":
                workflow["session_uri"] = format_session_uri(
                    reana_server_url=ctx.obj.reana_server_url,
                    path=workflow["session_uri"],
                    access_token=access_token,
                )
            row = []
            for header in headers[type]:
                value = None
                if header in progress_header:
                    value = get_formatted_progress(workflow.get("progress"))
                elif header in ["started", "ended"]:
                    _key = (
                        "run_started_at" if header == "started" else "run_finished_at"
                    )
                    value = workflow.get("progress", {}).get(_key) or "-"
                if header == "shared_by":
                    value = workflow.get("owner_email")
                if header == "shared_with":
                    value = ", ".join(workflow.get("shared_with", []))
                if not value:
                    value = workflow.get(header)
                row.append(value)
            data.append(row)

        sort_column_id = 2
        sort_column_name = sort_column_name.lower()
        if sort_column_name in headers[type]:
            sort_column_id = headers[type].index(sort_column_name)

        # Sort by given column, making sure that `None` is at the bottom of the list.
        def get_sort_key(x, column_id):
            if headers[type][column_id] == "run_number":
                return list(map(int, x[column_id].split(".")))
            elif headers[type][column_id] in workspace_size_header:
                return x[column_id]["raw"]
            return x[column_id] is not None, x[column_id]

        data = sorted(
            data,
            key=lambda x: get_sort_key(x, sort_column_id),
            reverse=True,
        )

        for row in data:
            for i, value in enumerate(row):
                # Substitute `None` with "-"
                content = value or "-"
                # Replace raw size with human-readable size if requested
                if headers[type][i] in workspace_size_header:
                    content = value.get(human_readable_or_raw)
                row[i] = content

        workflow_ids = ["{0}.{1}".format(w[0], w[1]) for w in data]
        if os.getenv("REANA_WORKON", "") in workflow_ids:
            active_workflow_idx = workflow_ids.index(os.getenv("REANA_WORKON", ""))
            data[active_workflow_idx][headers[type].index("run_number")] += " *"

        display_formatted_output(data, headers[type], _format, output_format)

    except Exception as e:
        logging.debug(traceback.format_exc())
        logging.debug(str(e))
        display_message(
            "Workflow list could not be retrieved: \n{}".format(str(e)),
            msg_type="error",
        )
        sys.exit(1)


@workflow_management_group.command("create")
@click.option(
    "-f",
    "--file",
    type=click.Path(exists=True, resolve_path=True),
    default=get_reana_yaml_file_path,
    help="REANA specification file describing the workflow to "
    "execute. [default=reana.yaml]",
)
@click.option(
    "-n",
    "--name",
    "-w",
    "--workflow",
    default="",
    callback=validate_workflow_name_parameter,
    help='Optional name of the workflow. [default is "workflow"]',
)
@click.option(
    "--skip-validation",
    is_flag=True,
    help="If set, specifications file is not validated before "
    "submitting it's contents to REANA server.",
)
@add_access_token_options
@check_connection
@click.pass_context
def workflow_create(ctx, file, name, skip_validation, access_token):  # noqa: D301
    """Create a new workflow.

    The ``create`` command allows to create a new workflow from reana.yaml
    specifications file. The file is expected to be located in the current
    working directory, or supplied via command-line -f option, see examples
    below.

    Examples:\n
    \t $ reana-client create\n
    \t $ reana-client create -w myanalysis\n
    \t $ reana-client create -w myanalysis -f myreana.yaml\n
    """
    from reana_client.api.client import create_workflow
    from reana_client.utils import get_api_url

    logging.debug("command: {}".format(ctx.command_path.replace(" ", ".")))
    for p in ctx.params:
        logging.debug("{param}: {value}".format(param=p, value=ctx.params[p]))

    # Check that name is not an UUIDv4.
    # Otherwise it would mess up `--workflow` flag usage because no distinction
    # could be made between the name and actual UUID of workflow.
    if is_uuid_v4(name):
        display_message("Workflow name cannot be a valid UUIDv4", msg_type="error")
        sys.exit(1)

    specification_filename = click.format_filename(file)

    try:
        reana_specification = load_validate_reana_spec(
            specification_filename,
            access_token=access_token,
            skip_validation=skip_validation,
            server_capabilities=True,
        )
        logging.info("Connecting to {0}".format(get_api_url()))
        response = create_workflow(reana_specification, name, access_token)
        workflow_name = response["workflow_name"]

        click.echo(click.style(workflow_name, fg="green"))
        # check if command is called from wrapper command
        if "invoked_by_subcommand" in ctx.parent.__dict__:
            ctx.parent.workflow_name = workflow_name
    except Exception as e:
        logging.debug(traceback.format_exc())
        logging.debug(str(e))
        display_message(
            "Cannot create workflow {}: \n{}".format(name, str(e)), msg_type="error"
        )
        sys.exit(1)

    # upload specification file by default
    ctx.invoke(
        upload_files,
        workflow=workflow_name,
        filenames=(specification_filename,),
        access_token=access_token,
    )


@workflow_execution_group.command("start")
@add_workflow_option
@add_access_token_options
@check_connection
@click.option(
    "-p",
    "--parameter",
    "parameters",
    multiple=True,
    callback=key_value_to_dict,
    help="Additional input parameters to override "
    "original ones from reana.yaml. "
    "E.g. -p myparam1=myval1 -p myparam2=myval2.",
)
@click.option(
    "-o",
    "--option",
    "options",
    multiple=True,
    callback=key_value_to_dict,
    help="Additional operational options for the workflow execution. "
    "E.g. CACHE=off. (workflow engine - serial) "
    "E.g. --debug (workflow engine - cwl)",
)
@click.option(
    "--follow",
    "follow",
    is_flag=True,
    default=False,
    help="If set, follows the execution of the workflow until termination.",
)
@click.pass_context
def workflow_start(
    ctx, workflow, access_token, parameters, options, follow
):  # noqa: D301
    """Start previously created workflow.

    The ``start`` command allows to start previously created workflow. The
    workflow execution can be further influenced by passing input prameters
    using ``-p`` or ``--parameters`` flag and by setting additional operational
    options using ``-o`` or ``--options``.  The input parameters and operational
    options can be repetitive. For example, to disable caching for the Serial
    workflow engine, you can set ``-o CACHE=off``.

    Examples:\n
    \t $ reana-client start -w myanalysis.42 -p sleeptime=10 -p myparam=4\n
    \t $ reana-client start -w myanalysis.42 -p myparam1=myvalue1 -o CACHE=off
    """
    from reana_client.api.client import (
        get_workflow_parameters,
        get_workflow_status,
        start_workflow,
    )
    from reana_client.utils import get_api_url

    def display_status(workflow: str, current_status: str):
        """Display the current status of the workflow."""
        status_msg = get_workflow_status_change_msg(workflow, current_status)
        if current_status in ["deleted", "failed", "stopped"]:
            display_message(status_msg, msg_type="error")
            sys.exit(1)
        else:
            display_message(status_msg, msg_type="success")

    logging.debug("command: {}".format(ctx.command_path.replace(" ", ".")))
    for p in ctx.params:
        logging.debug("{param}: {value}".format(param=p, value=ctx.params[p]))

    parsed_parameters = {"input_parameters": parameters, "operational_options": options}
    if workflow:
        if parameters or options:
            try:
                response = get_workflow_parameters(workflow, access_token)
                workflow_type = response["type"]
                original_parameters = response["parameters"]
                validate_operational_options(
                    workflow_type, parsed_parameters["operational_options"]
                )

                parsed_parameters["input_parameters"] = validate_input_parameters(
                    parsed_parameters["input_parameters"], original_parameters
                )
            except REANAValidationError as e:
                display_message(e.message, msg_type="error")
                sys.exit(1)
            except Exception as e:
                display_message(
                    "Could not apply given input parameters: "
                    "{0} \n{1}".format(parameters, str(e)),
                    msg_type="error",
                )
                sys.exit(1)
        try:
            logging.info("Connecting to {0}".format(get_api_url()))
            response = start_workflow(workflow, access_token, parsed_parameters)
            current_status = get_workflow_status(workflow, access_token).get("status")
            display_status(workflow, current_status)

            if follow:
                # keep printing the current status of the workflow
                while current_status in ["pending", "queued", "running"]:
                    time.sleep(TIMECHECK)
                    current_status = get_workflow_status(workflow, access_token).get(
                        "status"
                    )
                    display_status(workflow, current_status)

                    if current_status == "finished":
                        display_message(
                            "Listing workflow output files...", msg_type="info"
                        )
                        ctx.invoke(
                            get_files,
                            workflow=workflow,
                            access_token=access_token,
                            output_format="url",
                            human_readable_or_raw="raw",
                        )
        except Exception as e:
            logging.debug(traceback.format_exc())
            logging.debug(str(e))
            display_message(
                "Cannot start workflow {}: \n{}".format(workflow, str(e)),
                msg_type="error",
            )
            sys.exit(1)


@workflow_execution_group.command("restart")
@add_workflow_option
@add_access_token_options
@check_connection
@click.option(
    "-p",
    "--parameter",
    "parameters",
    multiple=True,
    callback=key_value_to_dict,
    help="Additional input parameters to override "
    "original ones from reana.yaml. "
    "E.g. -p myparam1=myval1 -p myparam2=myval2.",
)
@click.option(
    "-o",
    "--option",
    "options",
    multiple=True,
    callback=key_value_to_dict,
    help="Additional operational options for the workflow execution. "
    "E.g. CACHE=off. (workflow engine - serial) "
    "E.g. --debug (workflow engine - cwl)",
)
@click.option(
    "-f",
    "--file",
    type=click.Path(exists=True, resolve_path=True),
    help="REANA specification file describing the workflow to "
    "execute. [default=reana.yaml]",
)
@click.pass_context
def workflow_restart(
    ctx, workflow, access_token, parameters, options, file
):  # noqa: D301
    """Restart previously run workflow.

    The ``restart`` command allows to restart a previous workflow on the same
    workspace.

    Note that workflow restarting can be used in a combination with operational
    options ``FROM`` and ``TARGET``. You can also pass a modified workflow
    specification with ``-f`` or ``--file`` flag.

    You can furthermore use modified input prameters using ``-p`` or
    ``--parameters`` flag and by setting additional operational options using
    ``-o`` or ``--options``.  The input parameters and operational options can be
    repetitive.

    Examples:\n
    \t $ reana-client restart -w myanalysis.42 -p sleeptime=10 -p myparam=4\n
    \t $ reana-client restart -w myanalysis.42 -p myparam=myvalue\n
    \t $ reana-client restart -w myanalysis.42 -o TARGET=gendata\n
    \t $ reana-client restart -w myanalysis.42 -o FROM=fitdata
    """
    from reana_client.api.client import (
        get_workflow_parameters,
        get_workflow_status,
        start_workflow,
    )
    from reana_client.utils import get_api_url

    logging.debug("command: {}".format(ctx.command_path.replace(" ", ".")))
    for p in ctx.params:
        logging.debug("{param}: {value}".format(param=p, value=ctx.params[p]))

    parsed_parameters = {
        "input_parameters": parameters,
        "operational_options": options,
        "restart": True,
    }
    if file:
        specification_filename = click.format_filename(file)
        parsed_parameters["reana_specification"] = load_validate_reana_spec(
            click.format_filename(file)
        )
        # upload new specification
        ctx.invoke(
            upload_files,
            workflow=workflow,
            filenames=(specification_filename,),
            access_token=access_token,
        )

    if parameters or options:
        try:
            if "reana_specification" in parsed_parameters:
                workflow_type = parsed_parameters["reana_specification"]["workflow"][
                    "type"
                ]
                original_parameters = (
                    parsed_parameters["reana_specification"]
                    .get("inputs", {})
                    .get("parameters", {})
                )
            else:
                response = get_workflow_parameters(workflow, access_token)
                workflow_type = response["type"]
                original_parameters = response["parameters"]

            parsed_parameters["operational_options"] = validate_operational_options(
                workflow_type, parsed_parameters["operational_options"]
            )
            parsed_parameters["input_parameters"] = validate_input_parameters(
                parsed_parameters["input_parameters"], original_parameters
            )

        except REANAValidationError as e:
            display_message(e.message, msg_type="error")
            sys.exit(1)
        except Exception as e:
            display_message(
                "Could not apply given input parameters: "
                "{0} \n{1}".format(parameters, str(e)),
                msg_type="error",
            )
            sys.exit(1)

    try:
        logging.info("Connecting to {0}".format(get_api_url()))
        response = start_workflow(workflow, access_token, parsed_parameters)
        workflow = response["workflow_name"] + "." + str(response["run_number"])
        current_status = get_workflow_status(workflow, access_token).get("status")
        display_message(
            get_workflow_status_change_msg(workflow, current_status),
            msg_type="success",
        )
    except Exception as e:
        logging.debug(traceback.format_exc())
        logging.debug(str(e))
        display_message(
            "Cannot start workflow {}: \n{}".format(workflow, str(e)),
            msg_type="error",
        )
        sys.exit(1)


@workflow_execution_group.command("status")
@add_workflow_option
@click.option(
    "--format",
    "_format",
    multiple=True,
    help="Format output by displaying only certain columns. "
    "E.g. --format name,status.",
)
@click.option(
    "--json",
    "output_format",
    flag_value="json",
    default=None,
    help="Get output in JSON format.",
)
@click.option(
    "--include-duration",
    "include_duration",
    is_flag=True,
    default=False,
    help="Include the duration of the workflow in seconds. In case the workflow is in "
    "progress, its duration as of now will be shown.",
)
@add_access_token_options
@check_connection
@click.option("-v", "--verbose", count=True, help="Set status information verbosity.")
@click.pass_context
def workflow_status(  # noqa: C901
    ctx, workflow, _format, output_format, include_duration, access_token, verbose
):  # noqa: D301
    """Get status of a workflow.

    The ``status`` command allow to retrieve status of a workflow. The status can
    be created, queued, running, failed, etc. You can increase verbosity or
    filter retrieved information by passing appropriate command-line options.

    Examples:\n
    \t $ reana-client status -w myanalysis.42\n
    \t $ reana-client status -w myanalysis.42 -v --json
    """
    from reana_client.api.client import get_workflow_status

    def render_progress(finished_jobs, total_jobs):
        if total_jobs:
            return "{0}/{1}".format(finished_jobs, total_jobs)
        else:
            return "-/-"

    def add_data_from_response(row, data, headers):
        name, run_number = get_workflow_name_and_run_number(row["name"])
        total_jobs = row["progress"].get("total")
        if total_jobs:
            total_jobs = total_jobs.get("total")
        else:
            total_jobs = 0
        finished_jobs = row["progress"].get("finished")
        if finished_jobs:
            finished_jobs = finished_jobs.get("total")
        else:
            finished_jobs = 0

        parsed_response = list(
            map(str, [name, run_number, row["created"], row["status"]])
        )
        if row["progress"]["total"].get("total") or 0 > 0:
            if "progress" not in headers:
                headers += ["progress"]
                parsed_response.append(render_progress(finished_jobs, total_jobs))

        if row["status"] in ["running", "finished", "failed", "stopped"]:
            started_at = row["progress"].get("run_started_at")
            finished_at = row["progress"].get("run_finished_at")
            if started_at:
                after_created_pos = headers.index("created") + 1
                headers.insert(after_created_pos, "started")
                parsed_response.insert(after_created_pos, started_at)
                if finished_at:
                    after_started_pos = headers.index("started") + 1
                    headers.insert(after_started_pos, "ended")
                    parsed_response.insert(after_started_pos, finished_at)

        data.append(parsed_response)
        return data

    def add_verbose_data_from_response(response, verbose_headers, headers, data):
        for k in verbose_headers:
            if k == "command":
                current_command = response["progress"]["current_command"]
                if current_command:
                    if current_command.startswith('bash -c "cd '):
                        current_command = current_command[
                            current_command.index(";") + 2 : -2
                        ]
                    data[-1] += [current_command]
                else:
                    if "current_step_name" in response["progress"] and response[
                        "progress"
                    ].get("current_step_name"):
                        current_step_name = response["progress"].get(
                            "current_step_name"
                        )
                        data[-1] += [current_step_name]
                    else:
                        headers.remove("command")
            else:
                data[-1] += [response.get(k)]
        return data

    logging.debug("command: {}".format(ctx.command_path.replace(" ", ".")))
    for p in ctx.params:
        logging.debug("{param}: {value}".format(param=p, value=ctx.params[p]))
    try:
        workflow_response = get_workflow_status(workflow, access_token)
        headers = ["name", "run_number", "created", "status"]
        verbose_headers = ["id", "user", "command"]
        data = []
        add_data_from_response(workflow_response, data, headers)
        if verbose:
            headers += verbose_headers
            add_verbose_data_from_response(
                workflow_response, verbose_headers, headers, data
            )
        if verbose or include_duration:
            headers += ["duration"]
            data[-1] += [get_workflow_duration(workflow_response) or "-"]

        display_formatted_output(data, headers, _format, output_format)

    except Exception as e:
        logging.debug(traceback.format_exc())
        logging.debug(str(e))
        display_message(
            "Cannot retrieve the status of a workflow {}: \n"
            "{}".format(workflow, str(e)),
            msg_type="error",
        )
        sys.exit(1)


@workflow_execution_group.command("logs")
@add_workflow_option
@click.option("--json", "json_format", count=True, help="Get output in JSON format.")
@add_access_token_options
@click.option(
    "--filter",
    "filters",
    multiple=True,
    help="Filter job logs to include only those steps that match certain filtering criteria. Use --filter name=value pairs. Available filters are compute_backend, docker_img, status and step.",
)
@click.option(
    "--follow",
    "follow",
    is_flag=True,
    default=False,
    help="Follow the logs of a running workflow or job (similar to tail -f).",
)
@click.option(
    "-i",
    "--interval",
    "interval",
    default=CLI_LOGS_FOLLOW_DEFAULT_INTERVAL,
    help=f"Sleep time in seconds between log polling if log following is enabled. [default={CLI_LOGS_FOLLOW_DEFAULT_INTERVAL}]",
)
@add_pagination_options
@check_connection
@click.pass_context
def workflow_logs(
    ctx,
    workflow,
    access_token,
    json_format,
    follow,
    interval,
    filters=None,
    page=None,
    size=None,
):  # noqa: D301
    """Get workflow logs.

    The ``logs`` command allows to retrieve logs of a running workflow.

    Examples:\n
    \t $ reana-client logs -w myanalysis.42\n
    \t $ reana-client logs -w myanalysis.42 --json\n
    \t $ reana-client logs -w myanalysis.42 --filter status=running\n
    \t $ reana-client logs -w myanalysis.42 --filter step=myfit --follow\n
    """
    logging.debug("command: {}".format(ctx.command_path.replace(" ", ".")))
    for p in ctx.params:
        logging.debug("{param}: {value}".format(param=p, value=ctx.params[p]))

    if json_format and follow:
        display_message(
            "Ignoring --json as it cannot be used together with --follow.",
            msg_type="warning",
        )

    available_filters = {
        "step": "job_name",
        "compute_backend": "compute_backend",
        "docker_img": "docker_img",
        "status": "status",
    }
    steps = []
    chosen_filters = dict()

    if filters:
        try:
            for f in filters:
                key, value = f.split("=")
                if key not in available_filters:
                    display_message(
                        "Filter '{}' is not valid.\n"
                        "Available filters are '{}'.".format(
                            key,
                            "' '".join(sorted(available_filters.keys())),
                        ),
                        msg_type="error",
                    )
                    sys.exit(1)
                elif key == "step":
                    steps.append(value)
                else:
                    # Case insensitive for compute backends
                    if (
                        key == "compute_backend"
                        and value.lower() in REANA_COMPUTE_BACKENDS
                    ):
                        value = REANA_COMPUTE_BACKENDS[value.lower()]
                    elif key == "status" and value not in RUN_STATUSES:
                        display_message(
                            "Input status value {} is not valid. ".format(value),
                            msg_type="error",
                        ),
                        sys.exit(1)
                    chosen_filters[key] = value
        except Exception as e:
            logging.debug(traceback.format_exc())
            logging.debug(str(e))
            display_message(
                "Please provide complete --filter name=value pairs, "
                "for example --filter status=running.\n"
                "Available filters are '{}'.".format(
                    "' '".join(sorted(available_filters.keys()))
                ),
                msg_type="error",
            )
            sys.exit(1)

    try:
        if follow:
            follow_workflow_logs(workflow, access_token, interval, steps)
        else:
            retrieve_workflow_logs(
                workflow,
                access_token,
                json_format,
                filters,
                steps,
                chosen_filters,
                available_filters,
                page,
                size,
            )
    except Exception as e:
        logging.debug(traceback.format_exc())
        logging.debug(str(e))
        display_message(
            "Cannot retrieve logs for workflow {}: \n{}".format(workflow, str(e)),
            msg_type="error",
        )
        sys.exit(1)


@workflow_execution_group.command("validate")
@click.option(
    "-f",
    "--file",
    type=click.Path(exists=True, resolve_path=True),
    default=get_reana_yaml_file_path,
    help="REANA specification file describing the workflow to "
    "execute. [default=reana.yaml]",
)
@click.option(
    "--environments",
    is_flag=True,
    default=False,
    help="If set, check all runtime environments specified in REANA "
    "specification file. [default=False]",
)
@click.option(
    "--pull",
    is_flag=True,
    default=False,
    callback=requires_environments,
    help="If set, try to pull remote environment image from registry to perform "
    "validation locally. Requires ``--environments`` flag. [default=False]",
)
@click.option(
    "--server-capabilities",
    is_flag=True,
    default=False,
    help="If set, check the server capabilities such as workspace validation. "
    "[default=False]",
)
@add_access_token_options_not_required
@click.pass_context
def workflow_validate(
    ctx, file, environments, pull, server_capabilities, access_token
):  # noqa: D301
    """Validate workflow specification file.

    The ``validate`` command allows to check syntax and validate the reana.yaml
    workflow specification file.

    Examples:\n
    \t $ reana-client validate -f reana.yaml
    """
    if server_capabilities:
        if access_token:
            check_connection(lambda: None)()
        else:
            display_message(ERROR_MESSAGES["missing_access_token"], msg_type="error")
            ctx.exit(1)
    logging.debug("command: {}".format(ctx.command_path.replace(" ", ".")))
    for p in ctx.params:
        logging.debug("{param}: {value}".format(param=p, value=ctx.params[p]))
    try:
        load_validate_reana_spec(
            click.format_filename(file),
            access_token=access_token,
            skip_validate_environments=not environments,
            pull_environment_image=pull,
            server_capabilities=server_capabilities,
        )

    except (ValidationError, REANAValidationError) as e:
        logging.debug(traceback.format_exc())
        logging.debug(str(e))
        display_message(
            "{0} is not a valid REANA specification:\n{1}".format(
                click.format_filename(file), e.message
            ),
            msg_type="error",
        )
        sys.exit(1)
    except yaml.parser.ParserError as e:
        logging.debug(traceback.format_exc())
        display_message(
            "{0} is not a valid YAML file:\n{1}".format(
                click.format_filename(file, shorten=True), e
            ),
            msg_type="error",
        )
        sys.exit(1)
    except Exception as e:
        logging.debug(traceback.format_exc())
        logging.debug(str(e))
        display_message(
            "Something went wrong when trying to validate {}".format(file),
            msg_type="error",
        )
        sys.exit(1)


@workflow_execution_group.command("stop")
@click.option(
    "--force",
    "force_stop",
    is_flag=True,
    default=False,
    help="Stop a workflow without waiting for jobs to finish.",
)
@add_workflow_option
@add_access_token_options
@check_connection
@click.pass_context
def workflow_stop(ctx, workflow, force_stop, access_token):  # noqa: D301
    """Stop a running workflow.

    The ``stop`` command allows to hard-stop the running workflow process. Note
    that soft-stopping of the workflow is currently not supported. This command
    should be therefore used with care, only if you are absolutely sure that
    there is no point in continuing the running the workflow.

    Example:\n
    \t $ reana-client stop -w myanalysis.42 --force
    """
    from reana_client.api.client import stop_workflow

    if not force_stop:
        display_message(
            "Graceful stop not implement yet. If you really want to "
            "stop your workflow without waiting for jobs to finish"
            " use: --force option",
            msg_type="error",
        )
        raise click.Abort()

    if workflow:
        try:
            logging.info("Sending a request to stop workflow {}".format(workflow))
            stop_workflow(workflow, force_stop, access_token)
            display_message(
                get_workflow_status_change_msg(workflow, "stopped"),
                msg_type="success",
            )
        except Exception as e:
            logging.debug(traceback.format_exc())
            logging.debug(str(e))
            display_message(
                "Cannot stop workflow {}: \n{}".format(workflow, str(e)),
                msg_type="error",
            )
            sys.exit(1)


@workflow_execution_group.command("run")
@click.option(
    "-f",
    "--file",
    type=click.Path(exists=True, resolve_path=True),
    default=get_reana_yaml_file_path,
    help="REANA specification file describing the workflow to "
    "execute. [default=reana.yaml]",
)
@click.option(
    "-n",
    "--name",
    "-w",
    "--workflow",
    default="",
    callback=validate_workflow_name_parameter,
    help='Optional name of the workflow. [default is "workflow"]',
)
@click.option(
    "--skip-validation",
    is_flag=True,
    help="If set, specifications file is not validated before "
    "submitting it's contents to REANA server.",
)
@click.option(
    "-p",
    "--parameter",
    "parameters",
    multiple=True,
    callback=key_value_to_dict,
    help="Additional input parameters to override "
    "original ones from reana.yaml. "
    "E.g. -p myparam1=myval1 -p myparam2=myval2.",
)
@click.option(
    "-o",
    "--option",
    "options",
    multiple=True,
    callback=key_value_to_dict,
    help="Additional operational options for the workflow execution. "
    "E.g. CACHE=off.",
)
@click.option(
    "--follow",
    "follow",
    is_flag=True,
    default=False,
    help="If set, follows the execution of the workflow until termination.",
)
@add_access_token_options
@check_connection
@click.pass_context
def workflow_run(
    ctx, file, name, skip_validation, access_token, parameters, options, follow
):  # noqa: D301
    """Shortcut to create, upload, start a new workflow.

    The ``run`` command allows to create a new workflow, upload its input files
    and start it in one command.

    Examples:\n
    \t $ reana-client run -w myanalysis-test-small -p myparam=mysmallvalue\n
    \t $ reana-client run -w myanalysis-test-big -p myparam=mybigvalue
    """
    # set context parameters for subcommand
    ctx.invoked_by_subcommand = True
    ctx.workflow_name = ""
    display_message("Creating a workflow...", msg_type="info")
    ctx.invoke(
        workflow_create,
        file=file,
        name=name,
        skip_validation=skip_validation,
        access_token=access_token,
    )
    display_message("Uploading files...", msg_type="info")
    ctx.invoke(
        upload_files,
        workflow=ctx.workflow_name,
        access_token=access_token,
    )
    display_message("Starting workflow...", msg_type="info")
    ctx.invoke(
        workflow_start,
        workflow=ctx.workflow_name,
        access_token=access_token,
        parameters=parameters,
        options=options,
        follow=follow,
    )


@workflow_management_group.command("delete")
@click.option(
    "--include-all-runs",
    "all_runs",
    is_flag=True,
    help="Delete all runs of a given workflow.",
)
@click.option(
    "--include-workspace",
    "should_delete_workspace",
    is_flag=True,
    help="Delete workspace from REANA.",
)
@add_workflow_option
@add_access_token_options
@check_connection
@click.pass_context
def workflow_delete(
    ctx, workflow: str, all_runs: bool, should_delete_workspace: bool, access_token: str
):  # noqa: D301
    """Delete a workflow.

    The ``delete`` command removes workflow run(s) from the database.
    Note that the workspace and any open session attached to it will always be
    deleted, even when ``--include-workspace`` is not specified.
    Note also that you can remove all past runs of a workflow by specifying ``--include-all-runs`` flag.

    Example:\n
    \t $ reana-client delete -w myanalysis.42\n
    \t $ reana-client delete -w myanalysis.42 --include-all-runs
    """
    from reana_client.api.client import delete_workflow
    from reana_client.utils import get_api_url

    should_delete_workspace = True

    logging.debug("command: {}".format(ctx.command_path.replace(" ", ".")))
    for p in ctx.params:
        logging.debug("{param}: {value}".format(param=p, value=ctx.params[p]))

    if workflow:
        try:
            logging.info("Connecting to {0}".format(get_api_url()))
            delete_workflow(workflow, all_runs, should_delete_workspace, access_token)
            if all_runs:
                message = "All workflows named '{}' have been deleted.".format(
                    workflow.split(".")[0]
                )
            else:
                message = get_workflow_status_change_msg(workflow, "deleted")
            display_message(message, msg_type="success")

        except Exception as e:
            logging.debug(traceback.format_exc())
            logging.debug(str(e))
            display_message(
                "Cannot delete workflow {} \n{}".format(workflow, str(e)),
                msg_type="error",
            )
            sys.exit(1)


@workflow_management_group.command("diff")
@click.argument(
    "workflow_a",
    default=os.environ.get("REANA_WORKON", None),
    callback=workflow_uuid_or_name,
)
@click.argument("workflow_b", callback=workflow_uuid_or_name)
@click.option(
    "-q",
    "--brief",
    is_flag=True,
    help="If not set, differences in the contents of the files in the two "
    "workspaces are shown.",
)
@click.option(
    "-u",
    "-U",
    "--unified",
    "context_lines",
    type=int,
    default=5,
    help="Sets number of context lines for workspace diff output.",
)
@add_access_token_options
@check_connection
@click.pass_context
def workflow_diff(
    ctx, workflow_a, workflow_b, brief, access_token, context_lines
):  # noqa: D301
    """Show diff between two workflows.

    The ``diff`` command allows to compare two workflows, the workflow_a and
    workflow_b, which must be provided as arguments. The output will show the
    difference in workflow run parameters, the generated files, the logs, etc.

    Examples:\n
    \t $ reana-client diff myanalysis.42 myotheranalysis.43\n
    \t $ reana-client diff myanalysis.42 myotheranalysis.43 --brief
    """
    from reana_client.api.client import diff_workflows

    logging.debug("command: {}".format(ctx.command_path.replace(" ", ".")))
    for p in ctx.params:
        logging.debug("{param}: {value}".format(param=p, value=ctx.params[p]))

    def print_color_diff(lines):
        for line in lines:
            line_color = None
            if line[0] == "@":
                line_color = "cyan"
            elif line[0] == "-":
                line_color = "red"
            elif line[0] == "+":
                line_color = "green"
            click.secho(line, fg=line_color)

    leading_mark = "==>"
    try:
        response = diff_workflows(
            workflow_a, workflow_b, brief, access_token, str(context_lines)
        )
        if response.get("reana_specification"):
            specification_diff = json.loads(response["reana_specification"])
            nonempty_sections = {k: v for k, v in specification_diff.items() if v}
            if not nonempty_sections:
                click.secho(
                    "{} No differences in REANA specifications.".format(leading_mark),
                    bold=True,
                    fg="yellow",
                )
            # Rename section workflow -> specification
            if "workflow" in nonempty_sections:
                nonempty_sections["specification"] = nonempty_sections.pop("workflow")
            for section, content in nonempty_sections.items():
                click.secho(
                    "{} Differences in workflow {}".format(leading_mark, section),
                    bold=True,
                    fg="yellow",
                )
                print_color_diff(content)
        display_message("")  # Leave 1 line for separation
        workspace_diff = json.loads(response.get("workspace_listing"))
        if workspace_diff:
            workspace_diff = workspace_diff.splitlines()
            click.secho(
                "{} Differences in workflow workspace".format(leading_mark),
                bold=True,
                fg="yellow",
            )
            print_color_diff(workspace_diff)

    except Exception as e:
        logging.debug(traceback.format_exc())
        logging.debug(str(e))
        display_message(
            "Something went wrong when trying to get diff:\n{}".format(str(e)),
            msg_type="error",
        )
        sys.exit(1)


@click.group(help="Workspace interactive commands")
def interactive_group():
    """Workspace interactive commands."""
    pass


@interactive_group.command("open")
@add_workflow_option
@click.argument(
    "interactive-session-type",
    metavar="interactive-session-type",
    default=INTERACTIVE_SESSION_TYPES[0],
    type=click.Choice(INTERACTIVE_SESSION_TYPES),
)
@click.option(
    "-i",
    "--image",
    help="Docker image which will be used to spawn the interactive session. "
    "Overrides the default image for the selected type.",
)
@add_access_token_options
@check_connection
@click.pass_context
def workflow_open_interactive_session(
    ctx, workflow, interactive_session_type, image, access_token
):  # noqa: D301
    """Open an interactive session inside the workspace.

    The ``open`` command allows to open interactive session processes on top of
    the workflow workspace, such as Jupyter notebooks. This is useful to
    quickly inspect and analyse the produced files while the workflow is still
    running.

    Examples:\n
    \t $ reana-client open -w myanalysis.42 jupyter
    """
    from reana_client.api.client import info, open_interactive_session

    if workflow:
        try:
            logging.info("Opening an interactive session on {}".format(workflow))
            interactive_session_configuration = {
                "image": image or None,
            }
            path = open_interactive_session(
                workflow,
                access_token,
                interactive_session_type,
                interactive_session_configuration,
            )
            display_message(
                "Interactive session opened successfully", msg_type="success"
            )
            click.secho(
                format_session_uri(
                    reana_server_url=ctx.obj.reana_server_url,
                    path=path,
                    access_token=access_token,
                ),
                fg="green",
            )
            display_message(
                "It could take several minutes to start the interactive session."
            )
            reana_info = info(access_token)
            max_inactivity_days_entry = (
                reana_info.get("maximum_interactive_session_inactivity_period") or {}
            )
            max_inactivity_days = max_inactivity_days_entry.get("value")
            if max_inactivity_days:
                display_message(
                    f"Please note that it will be automatically closed after {max_inactivity_days} days of inactivity."
                )
        except Exception as e:
            logging.debug(traceback.format_exc())
            logging.debug(str(e))
            display_message(
                "Interactive session could not be opened: \n{}".format(str(e)),
                msg_type="error",
            )
            sys.exit(1)
    else:
        display_message("Cannot find workflow {}".format(workflow), msg_type="error")


@interactive_group.command("close")
@add_workflow_option
@add_access_token_options
@check_connection
def workflow_close_interactive_session(workflow, access_token):  # noqa: D301
    """Close an interactive session.

    The ``close`` command allows to shut down any interactive sessions that you
    may have running. You would typically use this command after you finished
    exploring data in the Jupyter notebook and after you have transferred any
    code created in your interactive session.

    Examples:\n
    \t $ reana-client close -w myanalysis.42
    """
    from reana_client.api.client import close_interactive_session

    if workflow:
        try:
            logging.info("Closing an interactive session on {}".format(workflow))
            close_interactive_session(workflow, access_token)
            display_message(
                "Interactive session for workflow {}"
                " was successfully closed".format(workflow),
                msg_type="success",
            )
        except Exception as e:
            logging.debug(traceback.format_exc())
            logging.debug(str(e))
            display_message(
                "Interactive session could not be closed: \n{}".format(str(e)),
                msg_type="error",
            )
            sys.exit(1)
    else:
        display_message("Cannot find workflow {} ".format(workflow), msg_type="error")


@workflow_sharing_group.command("share-add")
@check_connection
@add_workflow_option
@add_access_token_options
@click.option(
    "-u",
    "--user",
    "users",
    multiple=True,
    help="Users to share the workflow with.",
    required=True,
)
@click.option(
    "-m",
    "--message",
    help="Optional message that is sent to the user(s) with the sharing invitation.",
)
@click.option(
    "--valid-until",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    help="Optional date when access to the workflow will expire for the given user(s) (format: YYYY-MM-DD).",
)
@click.pass_context
def workflow_share_add(
    ctx, workflow, access_token, users, message, valid_until
):  # noqa D412
    """Share a workflow with other users (read-only).

    The `share-add` command allows sharing a workflow with other users. The
    users will be able to view the workflow but not modify it.

    Examples:

    \t $ reana-client share-add -w myanalysis.42 --user bob@example.org

    \t $ reana-client share-add -w myanalysis.42 --user bob@example.org --user cecile@example.org --message "Please review my analysis" --valid-until 2025-12-31
    """
    from reana_client.api.client import share_workflow

    share_errors = []
    shared_users = []

    if valid_until:
        valid_until = valid_until.strftime("%Y-%m-%d")

    for user in users:
        try:
            logging.info(f"Sharing workflow {workflow} with user {user}")
            share_workflow(
                workflow,
                user,
                access_token,
                message=message,
                valid_until=valid_until,
            )
            shared_users.append(user)
        except Exception as e:
            share_errors.append(f"Failed to share {workflow} with {user}: {str(e)}")
            logging.debug(traceback.format_exc())

    if shared_users:
        display_message(
            f"{workflow} is now read-only shared with {', '.join(shared_users)}",
            msg_type="success",
        )

    for error in share_errors:
        display_message(error, msg_type="error")

    if share_errors:
        sys.exit(1)


@workflow_sharing_group.command("share-remove")
@check_connection
@add_workflow_option
@add_access_token_options
@click.option(
    "-u",
    "--user",
    "users",
    multiple=True,
    help="Users to unshare the workflow with.",
    required=True,
)
@click.pass_context
def share_workflow_remove(ctx, workflow, access_token, users):  # noqa D412
    """Unshare a workflow.

    The `share-remove` command allows for unsharing a workflow. The workflow
    will no longer be visible to the users with whom it was shared.

    Example:

        $ reana-client share-remove -w myanalysis.42 --user bob@example.org
    """
    from reana_client.api.client import unshare_workflow

    unshare_errors = []
    unshared_users = []

    for user in users:
        try:
            logging.info(f"Unsharing workflow {workflow} with user {user}")
            unshare_workflow(workflow, user, access_token)
            unshared_users.append(user)
        except Exception as e:
            unshare_errors.append(f"Failed to unshare {workflow} with {user}: {str(e)}")
            logging.debug(traceback.format_exc())

    if unshared_users:
        display_message(
            f"{workflow} is no longer shared with {', '.join(unshared_users)}",
            msg_type="success",
        )
    if unshare_errors:
        for error in unshare_errors:
            display_message(error, msg_type="error")
        sys.exit(1)


@workflow_sharing_group.command("share-status")
@check_connection
@add_workflow_option
@add_access_token_options
@click.option(
    "--format",
    "format_",
    multiple=True,
    default=None,
    help="Format output according to column titles or column "
    "values. Use <columm_name>=<column_value> format.",
)
@click.option(
    "--json",
    "output_format",
    flag_value="json",
    default=None,
    help="Get output in JSON format.",
)
@click.pass_context
def share_workflow_status(
    ctx, workflow, format_, output_format, access_token
):  # noqa D412
    """Show with whom a workflow is shared.

    The `share-status` command allows for checking with whom a workflow is
    shared.

    Example:

        $ reana-client share-status -w myanalysis.42
    """
    from reana_client.api.client import get_workflow_sharing_status

    try:
        sharing_status = get_workflow_sharing_status(workflow, access_token)
    except Exception as e:
        logging.debug(traceback.format_exc())
        logging.debug(str(e))
        display_message(
            "An error occurred while checking workflow sharing status:\n{}".format(
                str(e)
            ),
            msg_type="error",
        )
        sys.exit(1)

    shared_with = sharing_status.get("shared_with", [])
    if shared_with:
        headers = ["user_email", "valid_until"]
        data = [
            [
                entry["user_email"],
                (entry["valid_until"] if entry["valid_until"] is not None else "-"),
            ]
            for entry in shared_with
        ]

        display_formatted_output(data, headers, format_, output_format)
    else:
        display_message(
            f"Workflow {workflow} is not shared with anyone.", msg_type="info"
        )
