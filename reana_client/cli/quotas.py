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
    add_access_token_options,
    check_connection,
    NotRequiredIf,
)

health_color = {"healthy": "green", "warning": "yellow", "critical": "red"}


def usage_percentage(usage, limit):
    """Usage percentage."""
    if limit == 0:
        return ""
    return "({:.1%})".format(float(usage) / float(limit))


@click.group(help="Quota commands")
def quota_group():
    """Quota commands."""
    pass


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
@quota_group.command("quota-show")
@click.pass_context
@add_access_token_options
@check_connection
def quota_show(ctx, access_token, resource, resources, report):  # noqa: D301
    """Show user quota.

    The `quota-show"` command displays quota usage for the user.

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
            return click.echo("\n".join(quota.keys()))

        if resource not in quota.keys():
            click.echo(
                click.style(
                    "Error: resource '{}' is not valid.\nAvailable resources are: '{}'.".format(
                        resource, "', '".join(sorted(quota.keys())),
                    ),
                    fg="red",
                ),
                err=True,
            )
            sys.exit(1)

        if not report:
            usage = quota[resource]["usage"]
            limit = quota[resource]["limit"]
            health = quota[resource]["health"]
            percentage = usage_percentage(usage["raw"], limit["raw"])
            limit_str = (
                "out of {} used".format(limit["human_readable"])
                if limit["raw"] > 0
                else ""
            )
            return click.echo(
                click.style(
                    "{} {} {}".format(usage["human_readable"], limit_str, percentage),
                    fg=health_color.get(health),
                )
            )

        result = quota[resource][report]["human_readable"]
        return click.echo(result)

    except Exception as e:
        logging.debug(str(e), exc_info=True)
        click.echo(
            click.style(
                "Something went wrong while retreiving quota related data", fg="red"
            ),
            err=True,
        )
