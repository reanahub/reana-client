# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2017, 2018 CERN.
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

import click
from jsonschema.exceptions import ValidationError
from reana_commons.config import INTERACTIVE_SESSION_TYPES, REANA_COMPUTE_BACKENDS
from reana_commons.errors import REANAValidationError
from reana_commons.operational_options import validate_operational_options
from reana_commons.utils import click_table_printer

from reana_client.cli.files import get_files, upload_files
from reana_client.cli.utils import (
    add_access_token_options,
    add_access_token_options_not_required,
    add_pagination_options,
    add_workflow_option,
    check_connection,
    format_data,
    format_session_uri,
    get_formatted_progress,
    human_readable_or_raw_option,
    key_value_to_dict,
    parse_filter_parameters,
    parse_format_parameters,
    requires_environments,
    validate_workflow_name,
)
from reana_client.config import ERROR_MESSAGES, RUN_STATUSES, TIMECHECK
from reana_client.printer import display_message
from reana_client.utils import (
    get_reana_yaml_file_path,
    get_workflow_name_and_run_number,
    get_workflow_status_change_msg,
    is_uuid_v4,
    load_reana_spec,
    validate_input_parameters,
    workflow_uuid_or_name,
)


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


@workflow_management_group.command("list")
@click.option(
    "-w", "--workflow", default=None, help="List all runs of the given workflow.",
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
    count=True,
    default=True,
    help="Show all workflows including deleted ones.",
)
@click.option(
    "-v",
    "--verbose",
    count=True,
    help="Print out extra information: workflow id, user id, disk usage.",
)
@human_readable_or_raw_option
@click.option(
    "--sort",
    "sort_columm_name",
    default="CREATED",
    help="Sort the output by specified column",
)
@click.option(
    "--filter",
    "filters",
    multiple=True,
    help="Filter workflow that contains certain filtering criteria. "
    "Use `--filter <columm_name>=<column_value>` pairs. "
    "Available filters are `name` and `status`.",
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
@add_access_token_options
@add_pagination_options
@check_connection
@click.pass_context
def workflow_workflows(  # noqa: C901
    ctx,
    workflow,
    sessions,
    _format,
    output_format,
    access_token,
    show_all,
    verbose,
    human_readable_or_raw,
    sort_columm_name,
    page,
    size,
    filters,
    include_progress,
    include_workspace_size,
):  # noqa: D301
    """List all workflows and sessions.

    The `list` command lists workflows and sessions. By default, the list of
    workflows is returned. If you would like to see the list of your open
    interactive sessions, you need to pass the `--sessions` command-line
    option.

    Example: \n
    \t $ reana-client list --all \n
    \t $ reana-client list --sessions \n
    \t $ reana-client list --verbose --bytes
    """
    import tablib
    from reana_client.api.client import get_workflows

    logging.debug("command: {}".format(ctx.command_path.replace(" ", ".")))
    for p in ctx.params:
        logging.debug("{param}: {value}".format(param=p, value=ctx.params[p]))
    type = "interactive" if sessions else "batch"

    status_filter = None
    search_filter = None
    if filters:
        filter_names = ["name", "status"]
        status_filter, search_filter = parse_filter_parameters(filters, filter_names)
    if _format:
        parsed_format_filters = parse_format_parameters(_format)
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
        )
        verbose_headers = ["id", "user"]
        workspace_size_header = ["size"]
        progress_header = ["progress"]
        headers = {
            "batch": ["name", "run_number", "created", "started", "ended", "status"],
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
        data = []
        for workflow in response:
            workflow["size"] = workflow["size"][human_readable_or_raw]
            if workflow["status"] == "deleted" and not show_all:
                continue
            name, run_number = get_workflow_name_and_run_number(workflow["name"])
            workflow["name"] = name
            workflow["run_number"] = run_number
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
                if not value:
                    value = workflow.get(header)
                row.append(value)
            data.append(row)
        sort_column_id = 2
        if sort_columm_name.lower() in headers[type]:
            sort_column_id = headers[type].index(sort_columm_name.lower())
        data = sorted(data, key=lambda x: x[sort_column_id], reverse=True)
        workflow_ids = ["{0}.{1}".format(w[0], w[1]) for w in data]
        if os.getenv("REANA_WORKON", "") in workflow_ids:
            active_workflow_idx = workflow_ids.index(os.getenv("REANA_WORKON", ""))
            for idx, row in enumerate(data):
                if idx == active_workflow_idx:
                    run_number = str(data[idx][headers[type].index("run_number")])
                    run_number += " *"
        tablib_data = tablib.Dataset()
        tablib_data.headers = headers[type]
        for row in data:
            tablib_data.append(row=row, tags=row)

        if _format:
            tablib_data, filtered_headers = format_data(
                parsed_format_filters, headers[type], tablib_data
            )
            if output_format:
                display_message(json.dumps(tablib_data))
            else:
                tablib_data = [list(item.values()) for item in tablib_data]
                click_table_printer(filtered_headers, filtered_headers, tablib_data)
        else:
            if output_format:
                display_message(tablib_data.export(output_format))
            else:
                click_table_printer(headers[type], _format, data)

    except Exception as e:
        logging.debug(traceback.format_exc())
        logging.debug(str(e))
        display_message(
            "Workflow list could not be retrieved: \n{}".format(str(e)),
            msg_type="error",
        )


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
    callback=validate_workflow_name,
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

    The `create` command allows to create a new workflow from reana.yaml
    specifications file. The file is expected to be located in the current
    working directory, or supplied via command-line -f option, see examples
    below.

    Examples: \n
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
    try:
        reana_specification = load_reana_spec(
            click.format_filename(file),
            access_token=access_token,
            skip_validation=skip_validation,
        )
        logging.info("Connecting to {0}".format(get_api_url()))
        response = create_workflow(reana_specification, name, access_token)
        click.echo(click.style(response["workflow_name"], fg="green"))
        # check if command is called from wrapper command
        if "invoked_by_subcommand" in ctx.parent.__dict__:
            ctx.parent.workflow_name = response["workflow_name"]
    except Exception as e:
        logging.debug(traceback.format_exc())
        logging.debug(str(e))
        display_message(
            "Cannot create workflow {}: \n{}".format(name, str(e)), msg_type="error"
        )
        if "invoked_by_subcommand" in ctx.parent.__dict__:
            sys.exit(1)


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

    The `start` command allows to start previously created workflow. The
    workflow execution can be further influenced by passing input prameters
    using `-p` or `--parameters` flag and by setting additional operational
    options using `-o` or `--options`.  The input parameters and operational
    options can be repetitive. For example, to disable caching for the Serial
    workflow engine, you can set `-o CACHE=off`.

    Examples: \n
    \t $ reana-client start -w myanalysis.42 -p sleeptime=10 -p myparam=4 \n
    \t $ reana-client start -w myanalysis.42 -p myparam1=myvalue1 -o CACHE=off
    """
    from reana_client.utils import get_api_url
    from reana_client.api.client import (
        get_workflow_parameters,
        get_workflow_status,
        start_workflow,
    )

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
        try:
            logging.info("Connecting to {0}".format(get_api_url()))
            response = start_workflow(workflow, access_token, parsed_parameters)
            current_status = get_workflow_status(workflow, access_token).get("status")
            display_message(
                get_workflow_status_change_msg(workflow, current_status),
                msg_type="success",
            )
            if follow:
                while "running" in current_status:
                    time.sleep(TIMECHECK)
                    current_status = get_workflow_status(workflow, access_token).get(
                        "status"
                    )
                    display_message(
                        get_workflow_status_change_msg(workflow, current_status),
                        msg_type="success",
                    )
                    if "finished" in current_status:
                        if follow:
                            display_message(
                                "Listing workflow output files...", msg_type="info",
                            )
                            ctx.invoke(
                                get_files,
                                workflow=workflow,
                                access_token=access_token,
                                output_format="url",
                            )
                        sys.exit(0)
                    elif "failed" in current_status or "stopped" in current_status:
                        sys.exit(1)
        except Exception as e:
            logging.debug(traceback.format_exc())
            logging.debug(str(e))
            display_message(
                "Cannot start workflow {}: \n{}".format(workflow, str(e)),
                msg_type="error",
            )
            if "invoked_by_subcommand" in ctx.parent.__dict__:
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

    The `restart` command allows to restart a previous workflow on the same
    workspace.

    Note that workflow restarting can be used in a combination with operational
    options ``FROM`` and ``TARGET``. You can also pass a modified workflow
    specification with ``-f`` or `--file`` flag.

    You can furthermore use modified input prameters using `-p` or
    `--parameters` flag and by setting additional operational options using
    `-o` or `--options`.  The input parameters and operational options can be
    repetitive.

    Examples: \n
    \t $ reana-client restart -w myanalysis.42 -p sleeptime=10 -p myparam=4 \n
    \t $ reana-client restart -w myanalysis.42 -p myparam=myvalue\n
    \t $ reana-client restart -w myanalysis.42 -o TARGET=gendata\n
    \t $ reana-client restart -w myanalysis.42 -o FROM=fitdata
    """
    from reana_client.utils import get_api_url
    from reana_client.api.client import (
        get_workflow_parameters,
        get_workflow_status,
        start_workflow,
    )

    logging.debug("command: {}".format(ctx.command_path.replace(" ", ".")))
    for p in ctx.params:
        logging.debug("{param}: {value}".format(param=p, value=ctx.params[p]))

    parsed_parameters = {
        "input_parameters": parameters,
        "operational_options": options,
        "restart": True,
    }
    if file:
        parsed_parameters["reana_specification"] = load_reana_spec(
            click.format_filename(file)
        )
    if workflow:
        if parameters or options:
            try:
                if "reana_specification" in parsed_parameters:
                    workflow_type = parsed_parameters["reana_specification"][
                        "workflow"
                    ]["type"]
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
            if "invoked_by_subcommand" in ctx.parent.__dict__:
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
@add_access_token_options
@check_connection
@click.option("-v", "--verbose", count=True, help="Set status information verbosity.")
@click.pass_context
def workflow_status(  # noqa: C901
    ctx, workflow, _format, output_format, access_token, verbose
):  # noqa: D301
    """Get status of a workflow.

    The `status` command allow to retrieve status of a workflow. The status can
    be created, queued, running, failed, etc. You can increase verbosity or
    filter retrieved information by passing appropriate command-line options.

    Examples: \n
    \t $ reana-client status -w myanalysis.42 \n
    \t $ reana-client status -w myanalysis.42 -v --json
    """
    import tablib
    from reana_client.api.client import get_workflow_status

    def render_progress(finished_jobs, total_jobs):
        if total_jobs:
            return "{0}/{1}".format(finished_jobs, total_jobs)
        else:
            return "-/-"

    def add_data_from_reponse(row, data, headers):
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
    if workflow:
        try:
            if _format:
                parsed_filters = parse_format_parameters(_format)
                _format = [item["column_name"] for item in parsed_filters]
            response = get_workflow_status(workflow, access_token)
            headers = ["name", "run_number", "created", "status"]
            verbose_headers = ["id", "user", "command"]
            data = []
            if not isinstance(response, list):
                response = [response]
            for workflow in response:
                add_data_from_reponse(workflow, data, headers)
                if verbose:
                    headers += verbose_headers
                    add_verbose_data_from_response(
                        workflow, verbose_headers, headers, data
                    )

            if output_format:
                tablib_data = tablib.Dataset()
                tablib_data.headers = headers
                for row in data:
                    tablib_data.append(row)

                if _format:
                    tablib_data = tablib_data.subset(rows=None, cols=list(_format))

                display_message(tablib_data.export(output_format))
            else:
                click_table_printer(headers, _format, data)

        except Exception as e:
            logging.debug(traceback.format_exc())
            logging.debug(str(e))
            display_message(
                "Cannot retrieve the status of a workflow {}: \n"
                "{}".format(workflow, str(e)),
                msg_type="error",
            )


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
@add_pagination_options
@check_connection
@click.pass_context
def workflow_logs(
    ctx,
    workflow,
    access_token,
    json_format,
    steps=None,
    filters=None,
    page=None,
    size=None,
):  # noqa: D301
    """Get  workflow logs.

    The `logs` command allows to retrieve logs of running workflow. Note that
    only finished steps of the workflow are returned, the logs of the currently
    processed step is not returned until it is finished.

    Examples: \n
    \t $ reana-client logs -w myanalysis.42
    \t $ reana-client logs -w myanalysis.42 -s 1st_step
    """
    from reana_client.api.client import get_workflow_logs

    available_filters = {
        "step": "job_name",
        "compute_backend": "compute_backend",
        "docker_img": "docker_img",
        "status": "status",
    }
    steps = []
    chosen_filters = dict()

    logging.debug("command: {}".format(ctx.command_path.replace(" ", ".")))
    for p in ctx.params:
        logging.debug("{param}: {value}".format(param=p, value=ctx.params[p]))
    if workflow:
        if filters:
            try:
                for f in filters:
                    key, value = f.split("=")
                    if key not in available_filters:
                        display_message(
                            "Filter '{}' is not valid.\n"
                            "Available filters are '{}'.".format(
                                key, "' '".join(sorted(available_filters.keys())),
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
            response = get_workflow_logs(
                workflow,
                access_token,
                steps=None if not steps else list(set(steps)),
                page=page,
                size=size,
            )
            workflow_logs = json.loads(response["logs"])
            if filters:
                for key, value in chosen_filters.items():
                    unwanted_steps = [
                        k
                        for k, v in workflow_logs["job_logs"].items()
                        if v[available_filters[key]] != value
                    ]
                    for job_id in unwanted_steps:
                        del workflow_logs["job_logs"][job_id]

            if json_format:
                display_message(json.dumps(workflow_logs, indent=2))
                sys.exit(0)
            else:
                from reana_client.cli.utils import output_user_friendly_logs

            output_user_friendly_logs(
                workflow_logs, None if not steps else list(set(steps))
            )
        except Exception as e:
            logging.debug(traceback.format_exc())
            logging.debug(str(e))
            display_message(
                "Cannot retrieve the logs of a workflow {}: \n"
                "{}".format(workflow, str(e)),
                msg_type="error",
            )


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

    The `validate` command allows to check syntax and validate the reana.yaml
    workflow specification file.

    Examples: \n
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
        load_reana_spec(
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

    The `stop` command allows to hard-stop the running workflow process. Note
    that soft-stopping of the workflow is currently not supported. This command
    should be therefore used with care, only if you are absolutely sure that
    there is no point in continuing the running the workflow.

    Example: \n
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
                get_workflow_status_change_msg(workflow, "stopped"), msg_type="success",
            )
        except Exception as e:
            logging.debug(traceback.format_exc())
            logging.debug(str(e))
            display_message(
                "Cannot stop workflow {}: \n{}".format(workflow, str(e)),
                msg_type="error",
            )


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
    callback=validate_workflow_name,
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

    The `run` command allows to create a new workflow, upload its input files
    and start it in one command.

    Examples: \n
    \t $ reana-client run -w myanalysis-test-small -p myparam=mysmallvalue \n
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
        filenames=None,
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
    "workspace",
    is_flag=True,
    help="Delete workspace from REANA.",
)
@add_workflow_option
@add_access_token_options
@check_connection
@click.pass_context
def workflow_delete(ctx, workflow, all_runs, workspace, access_token):  # noqa: D301
    """Delete a workflow.

    The `delete` command allows to remove workflow runs from the database and
    the workspace. By default, the command removes the workflow and all its
    cached information and hides the workflow from the workflow list. Note that
    workflow workspace will still be accessible until you use
    `--include-workspace` flag. Note also that you can remove all past runs of
    a workflow by specifying `--include-all-runs` flag.

    Example: \n
    \t $ reana-client delete -w myanalysis.42 \n
    \t $ reana-client delete -w myanalysis.42 --include-all-runs \n
    \t $ reana-client delete -w myanalysis.42 --include-workspace
    """
    from reana_client.api.client import delete_workflow
    from reana_client.utils import get_api_url

    logging.debug("command: {}".format(ctx.command_path.replace(" ", ".")))
    for p in ctx.params:
        logging.debug("{param}: {value}".format(param=p, value=ctx.params[p]))

    if workflow:
        try:
            logging.info("Connecting to {0}".format(get_api_url()))
            delete_workflow(workflow, all_runs, workspace, access_token)
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

    The `diff` command allows to compare two workflows, the workflow_a and
    workflow_b, which must be provided as arguments. The output will show the
    difference in workflow run parameters, the generated files, the logs, etc.

    Examples: \n
    \t $ reana-client diff myanalysis.42 myotheranalysis.43 \n
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

    The `open` command allows to open interactive session processes on top of
    the workflow workspace, such as Jupyter notebooks. This is useful to
    quickly inspect and analyse the produced files while the workflow is stlil
    running.

    Examples:\n
    \t $ reana-client open -w myanalysis.42 jupyter
    """
    from reana_client.api.client import open_interactive_session

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
        except Exception as e:
            logging.debug(traceback.format_exc())
            logging.debug(str(e))
            display_message(
                "Interactive session could not be opened: \n{}".format(str(e)),
                msg_type="error",
            )
    else:
        display_message("Cannot find workflow {}".format(workflow), msg_type="error")


@interactive_group.command("close")
@add_workflow_option
@add_access_token_options
@check_connection
def workflow_close_interactive_session(workflow, access_token):  # noqa: D301
    """Close an interactive session.

    The `close` command allows to shut down any interactive sessions that you
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
    else:
        display_message("Cannot find workflow {} ".format(workflow), msg_type="error")
