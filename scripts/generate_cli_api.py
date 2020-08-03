# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2020 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
"""REANA client CLI API docs generation."""

import click

from reana_client.cli import cli

CLI_API_URL = "https://reana-client.readthedocs.io/en/latest/#cli-api"


def _print_code_block(content, lang=""):
    print("```{}".format(lang))
    print(content)
    print("```")


def generate_cli_docs():
    """Generate Markdown friendly CLI API documentation."""
    print("# reana-client CLI API\n")
    print("The complete `reana-client` CLI API reference guide is available here:\n")
    print(f"- [{CLI_API_URL}]({CLI_API_URL})\n")
    with click.Context(cli) as ctx:
        _print_code_block(cli.get_help(ctx), lang="console")

    for cmd_group in cli.cmd_groups:
        print("\n## {}".format(cmd_group.help))
        for cmd_obj in cmd_group.commands.values():
            print("\n### {}\n".format(cmd_obj.name))
            print(cmd_obj.help)


if __name__ == "__main__":
    generate_cli_docs()
