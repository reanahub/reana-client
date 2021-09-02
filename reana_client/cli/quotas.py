# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2020 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
"""REANA client quotas related commands."""

import logging
import sys

import click

from reana_client.cli.utils import (
    NotRequiredIf,
    add_access_token_options,
    check_connection,
    human_readable_or_raw_option,
)
from reana_client.config import HEALTH_TO_MSG_TYPE
from reana_client.printer import display_message


def usage_percentage(usage, limit):
    """Usage percentage."""
    if limit == 0:
        return ""
    return "({:.0%})".format(usage / limit)


@click.group(help="Quota commands")
def quota_group():
    """Quota commands."""
    pass


@quota_group.command("quota-show")
@click.option(
    "--resource",
    "resource",
    cls=NotRequiredIf,
    not_required_if="resources",
    help="Specify quota resource. e.g. cpu, disk.",
)
@click.option(
    "--resources",
    "resources",
    is_flag=True,
    cls=NotRequiredIf,
    not_required_if="resource",
    help="Print available resources",
)
@click.option(
    "--report",
    "report",
    type=click.Choice(["limit", "usage"], case_sensitive=False),
    help="Specify quota report type. e.g. limit, usage.",
)
@human_readable_or_raw_option
@add_access_token_options
@click.pass_context
@check_connection
def quota_show(
    ctx, access_token, resource, resources, report, human_readable_or_raw
):  # noqa: D301
    """Show user quota.

    The `quota-show` command displays quota usage for the user.

    Examples: \n
    \t $ reana-client quota-show --resource disk --report limit\n
    \t $ reana-client quota-show --resource disk --report usage\n
    \t $ reana-client quota-show --resource disk\n
    \t $ reana-client quota-show --resources
    """
    from reana_client.api.client import get_user_quota

    logging.debug("command: {}".format(ctx.command_path.replace(" ", ".")))

    for p in ctx.params:
        logging.debug("{param}: {value}".format(param=p, value=ctx.params[p]))

    try:
        quota = get_user_quota(access_token)

        if resources:
            return display_message("\n".join(quota.keys()))

        if resource not in quota.keys():
            display_message(
                "Error: resource '{}' is not valid.\n"
                "Available resources are: '{}'.".format(
                    resource, "', '".join(sorted(quota.keys())),
                ),
                msg_type="error",
            )
            sys.exit(1)
        if not report:
            human_readable_or_raw = (
                "human_readable"  # when no report always show human readable
            )
            usage = quota[resource].get("usage")
            limit = quota[resource].get("limit")
            limit_str = ""
            percentage = ""
            msg_type = None
            if limit and limit.get("raw", 0) > 0:
                health = quota[resource].get("health")
                percentage = usage_percentage(usage.get("raw"), limit.get("raw"))
                limit_str = "out of {} used".format(limit.get(human_readable_or_raw))
                msg_type = HEALTH_TO_MSG_TYPE.get(health)
            else:
                limit_str = "used"

            return display_message(
                "{} {} {}".format(usage[human_readable_or_raw], limit_str, percentage),
                msg_type=msg_type,
            )

        result = (
            quota[resource][report][human_readable_or_raw]
            if quota[resource].get(report)
            and quota[resource].get(report).get("raw", 0) > 0
            else "No {}.".format(report)
        )
        return display_message(result)

    except Exception as e:
        logging.debug(str(e), exc_info=True)
        display_message(
            "Something went wrong while retrieving quota related data",
            msg_type="error",
        )
