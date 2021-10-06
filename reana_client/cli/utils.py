# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2018 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
"""Common click options."""

import functools
import json
import os
import shlex
import sys
from typing import Callable, NoReturn, Optional, Union

import click

from reana_client.config import (
    ERROR_MESSAGES,
    RUN_STATUSES,
    JOB_STATUS_TO_MSG_COLOR,
)
from reana_client.printer import display_message
from reana_client.utils import workflow_uuid_or_name


def _access_token_option_decorator(func: Callable, required: bool) -> Callable:
    """Add access token related options to click commands."""

    @click.option(
        "-t",
        "--access-token",
        default=os.getenv("REANA_ACCESS_TOKEN"),
        callback=lambda ctx, _, access_token: access_token_check(
            ctx, _, access_token, required
        ),
        help="Access token of the current user.",
    )
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)

    return wrapper


add_access_token_options = functools.partial(
    _access_token_option_decorator, required=True
)
add_access_token_options_not_required = functools.partial(
    _access_token_option_decorator, required=False
)


def human_readable_or_raw_option(func):
    """Add human readable option to click commands."""

    @click.option(
        "-h",
        "--human-readable",
        "human_readable_or_raw",
        is_flag=True,
        default=False,
        callback=lambda ctx, param, value: "human_readable" if value else "raw",
        help="Show disk size in human readable format.",
    )
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)

    return wrapper


def access_token_check(
    ctx: click.core.Context,
    _: click.core.Option,
    access_token: Optional[str],
    required: bool,
) -> Union[str, NoReturn]:
    """Check if access token is present."""
    if not access_token and required:
        display_message(ERROR_MESSAGES["missing_access_token"], msg_type="error")
        ctx.exit(1)
    else:
        return access_token


def check_connection(func):
    """Check if connected to any REANA cluster."""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        from reana_client.utils import get_api_url

        api_url = get_api_url()
        if not api_url:
            display_message(
                "REANA client is not connected to any REANA cluster.", msg_type="error",
            )
            sys.exit(1)
        return func(*args, **kwargs)

    return wrapper


def add_workflow_option(func):
    """Add workflow related option to click commands."""

    @click.option(
        "-w",
        "--workflow",
        default=os.environ.get("REANA_WORKON", None),
        callback=workflow_uuid_or_name,
        help="Name or UUID of the workflow. Overrides value of "
        "REANA_WORKON environment variable.",
    )
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)

    return wrapper


def add_pagination_options(func):
    """Add pagination related options to click commands."""

    @click.option(
        "--page",
        default=1,
        type=int,
        help="Results page number (to be used with --size).",
    )
    @click.option(
        "--size", type=int, help="Size of results per page (to be used with --page).",
    )
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)

    return wrapper


def parse_format_parameters(_format):
    """Return parsed filter parameters."""
    try:
        parsed_filters = []
        filters = " ".join(_format).replace(",", " ")
        for item in shlex.split(filters):
            if "=" in item:
                filter_item = {
                    "column_name": item.split("=")[0].lower(),
                    "column_value": item.split("=")[1],
                }
            else:
                filter_item = {"column_name": item.lower(), "column_value": None}
            parsed_filters.append(filter_item)
        return parsed_filters
    except ValueError as e:
        display_message(
            "Wrong filter format \n{0}".format(e.message), msg_type="error",
        )


def parse_filter_parameters(filters, filter_names):
    """Return parsed filter parameters."""
    try:
        status_filters = []
        search_filters = {}
        filters = list(filters)
        for item in filters:
            if "=" in item:
                filter_name = item.split("=")[0].lower()
                filter_value = item.split("=")[1]
                if filter_name == "status" and filter_name in filter_names:
                    if filter_value in RUN_STATUSES:
                        status_filters.append(filter_value)
                    else:
                        display_message(
                            "Input status value {} is not valid. ".format(filter_value),
                            msg_type="error",
                        ),
                        sys.exit(1)
                elif filter_name in filter_names:
                    if search_filters.get(filter_name):
                        search_filters[filter_name].append(filter_value)
                    else:
                        search_filters[filter_name] = [filter_value]
                else:
                    display_message(
                        "Filter {} is not valid.".format(filter_name), msg_type="error",
                    ),
                    sys.exit(1)
            else:
                raise click.BadParameter(
                    "Wrong input format. Please use --filter filter_name=filter_value"
                )
        if not search_filters:
            search_filters = None
        else:
            search_filters = json.dumps(search_filters)
        return status_filters, search_filters
    except ValueError as e:
        display_message(
            "Wrong filter format \n{0}".format(e.message), msg_type="error",
        )


def format_data(parsed_filters, headers, tablib_data):
    """Return filtered data."""
    parsed_filters = [i for i in parsed_filters if i["column_name"] in headers]
    column_headers = [i["column_name"] for i in parsed_filters] or None
    tablib_data = tablib_data.subset(rows=None, cols=column_headers)
    tablib_data = json.loads(tablib_data.export("json"))
    filtered_data = list(tablib_data)
    for item in filtered_data:
        for filter_ in parsed_filters:
            if (
                filter_["column_value"] is not None
                and filter_["column_value"] != item[filter_["column_name"]]
            ):
                tablib_data.remove(item)
                break
    return tablib_data, column_headers or []


def format_session_uri(reana_server_url, path, access_token):
    """Format interactive session URI."""
    return "{reana_server_url}{path}?token={access_token}".format(
        reana_server_url=reana_server_url, path=path, access_token=access_token
    )


def get_formatted_progress(progress):
    """Return workflow progress in format of finished/total jobs."""
    total_jobs = progress.get("total", {}).get("total") or "-"
    finished_jobs = progress.get("finished", {}).get("total") or "-"
    return "{0}/{1}".format(finished_jobs, total_jobs)


def validate_workflow_name(ctx, _, workflow_name):
    """Validate workflow name."""
    not_allowed_characters = ["."]
    if workflow_name:
        for item in not_allowed_characters:
            if item in workflow_name:
                display_message(
                    "Workflow name {} contains illegal "
                    'character "{}"'.format(workflow_name, item),
                    msg_type="error",
                )
                sys.exit(1)
    return workflow_name


def key_value_to_dict(ctx, param, value):
    """Convert tuple params to dictionary. e.g `(foo=bar)` to `{'foo': 'bar'}`.

    :param options: A tuple with CLI operational options.
    :returns: A dictionary representation of the given options.
    """
    try:
        return dict(op.split("=") for op in value)
    except ValueError:
        display_message(
            'Input parameter "{0}" is not valid. '
            'It must follow format "param=value".'.format(" ".join(value)),
            msg_type="error",
        ),
        sys.exit(1)


def requires_environments(ctx, param, value):
    """Require passing ``--environments`` flag."""
    if value and not ctx.params.get("environments"):
        display_message(
            "`{}` flag requires `--environments` flag.".format(param.opts[0]),
            msg_type="error",
        )
        sys.exit(1)
    return value


class NotRequiredIf(click.Option):
    """Allow only one of two arguments to be missing."""

    def __init__(self, *args, **kwargs):
        """."""
        self.not_required_if = kwargs.pop("not_required_if")
        assert self.not_required_if, "'not_required_if' parameter required"
        super(NotRequiredIf, self).__init__(*args, **kwargs)

    def handle_parse_result(self, ctx, opts, args):
        """Overwritten click method."""
        argument_present = self.name in opts
        other_argument_present = self.not_required_if in opts
        if not argument_present and not other_argument_present:
            display_message(
                "At least one of the options: `{}` or `{}` "
                "is required\n".format(self.name, self.not_required_if)
                + ctx.get_help(),
                msg_type="error",
            )
            sys.exit(1)

        return super(NotRequiredIf, self).handle_parse_result(ctx, opts, args)


def output_user_friendly_logs(workflow_logs, steps):
    """Output workflow logs in a user-friendly manner.

    :param workflow_logs: Dictionary representing the workflow logs as they
        are returned from the REST API.
    :param steps: List of steps to show logs for.
    """
    key_to_description_mapping = {
        "workflow_uuid": "Workflow ID",
        "compute_backend": "Compute backend",
        "backend_job_id": "Job ID",
        "docker_img": "Docker image",
        "cmd": "Command",
        "status": "Status",
        "started_at": "Started",
        "finished_at": "Finished",
    }
    leading_mark = "==>"

    # REANA Workflow Engine logs
    if workflow_logs.get("workflow_logs"):
        click.secho(f"{leading_mark} Workflow engine logs", bold=True, fg="yellow")
        click.echo(workflow_logs["workflow_logs"])

    if workflow_logs.get("engine_specific"):
        click.echo("\n")
        click.secho(f"{leading_mark} Engine internal logs", fg="yellow")
        click.secho(workflow_logs["engine_specific"])

    returned_step_names = set(
        workflow_logs["job_logs"][item]["job_name"]
        for item in workflow_logs["job_logs"].keys()
    )
    if steps:
        missing_steps = set(steps).difference(returned_step_names)
        if missing_steps:
            display_message(
                "The logs of step(s) {} were not found, "
                "check for spelling mistakes in the step "
                "names.".format(",".join(missing_steps)),
                msg_type="error",
            )
    # Job logs
    if workflow_logs["job_logs"]:
        click.echo("\n")
        click.secho("{} Job logs".format(leading_mark), bold=True, fg="yellow")
    for job_id, logs_info in workflow_logs["job_logs"].items():
        if logs_info:
            job_name_or_id = logs_info["job_name"] or job_id

            click.secho(
                f"{leading_mark} Step: {job_name_or_id}",
                bold=True,
                fg=JOB_STATUS_TO_MSG_COLOR.get(logs_info["status"]),
            )
            logs_output = logs_info["logs"]
            # extract already used fields
            del logs_info["logs"]
            del logs_info["job_name"]

            for key, value in logs_info.items():
                if value:
                    title = click.style(
                        f"{leading_mark} {key_to_description_mapping[key]}:",
                        fg=JOB_STATUS_TO_MSG_COLOR.get(logs_info["status"]),
                    )
                    click.echo(f"{title} {value}")
            # show actual log content
            if logs_output:
                click.secho(
                    f"{leading_mark} Logs:",
                    fg=JOB_STATUS_TO_MSG_COLOR.get(logs_info["status"]),
                )
                click.secho(logs_output)
            else:
                display_message(
                    f"Step {job_name_or_id} emitted no logs.", msg_type="info",
                )
