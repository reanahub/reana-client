# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2021 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""reana-client output print configuration."""

import click

from reana_client.config import (
    PRINTER_COLOUR_ERROR,
    PRINTER_COLOUR_INFO,
    PRINTER_COLOUR_SUCCESS,
    PRINTER_COLOUR_WARNING,
)


def display_message(msg, msg_type=None, indented=False):
    """Display messages in console.

    :param msg: Message to display
    :param msg_type: Type of message (info/note/warning/error)
    :param indented: Message indented or not
    :type msg: str
    :type msg_type: str
    :type indented: bool
    """
    msg_color_map = {
        "success": PRINTER_COLOUR_SUCCESS,
        "warning": PRINTER_COLOUR_WARNING,
        "error": PRINTER_COLOUR_ERROR,
        "info": PRINTER_COLOUR_INFO,
    }
    msg_color = msg_color_map.get(msg_type, "")

    if msg_type == "info":
        if indented:
            click.secho(
                "  -> {}: ".format(msg_type.upper()), bold=True, nl=False, fg=msg_color,
            )
            click.secho("{}".format(msg), nl=True)
        else:
            click.secho("==> ", bold=True, nl=False)
            click.secho("{}".format(msg), bold=True, nl=True)
    elif msg_type in ["error", "warning", "success"]:
        prefix_tpl = "  -> {}: " if indented else "==> {}: "
        click.secho(
            prefix_tpl.format(msg_type.upper()),
            bold=True,
            nl=False,
            err=msg_type == "error",
            fg=msg_color,
        )
        click.secho("{}".format(msg), bold=False, err=msg_type == "error", nl=True)
    else:
        click.secho("{}".format(msg), nl=True)
