# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2020, 2022, 2026 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
"""REANA client CLI API docs generation.

The published CLI reference leads with the REANA 0.9 commands and documents
the REANA 0.95 authentication and server commands in separate sections, next
to maintained compatibility prose. Generated content is therefore delimited by
``<!-- BEGIN generated NAME -->`` and ``<!-- END generated NAME -->`` markers,
and ``--check`` compares only those regions, so that the prose around them can
be edited freely.
"""

import argparse
import difflib
import re
import sys
from contextlib import contextmanager
from inspect import cleandoc

import click

from reana_client.cli import cli
from reana_client.cli.ping import server_connection_group

CLI_API_URL = "https://reana-client.readthedocs.io/en/latest/#cli-api"

AUTHENTICATION_COMMANDS = ("login", "logout")
"""Commands documented in the REANA 0.95 authentication section."""

COMMAND_REFERENCE_REGION = "command reference"
SERVER_COMMANDS_REGION = "server command descriptions"

MARKER_RE = re.compile(r"^<!-- (BEGIN|END) generated (\S(?:.*\S)?) -->$")
LOOSE_MARKER_RE = re.compile(r"<!--.*\b(BEGIN|END)\s+generated\b", re.IGNORECASE)


def _code_block(content, lang=""):
    return "```{}\n{}\n```".format(lang, content)


def _command_section(cmd_obj):
    return "### {}\n\n{}".format(cmd_obj.name, cleandoc(cmd_obj.help))


def _region_name(cmd_name):
    return "{} command".format(cmd_name)


@contextmanager
def _hidden_commands(cmd_objs):
    """Temporarily hide commands from the top-level help overview."""
    previous = [(cmd_obj, cmd_obj.hidden) for cmd_obj in cmd_objs]
    try:
        for cmd_obj in cmd_objs:
            cmd_obj.hidden = True
        yield
    finally:
        for cmd_obj, hidden in previous:
            cmd_obj.hidden = hidden


def generate_regions():
    """Generate the CLI reference regions, in their order on the page.

    :returns: A dictionary mapping each region name to its Markdown content.
    """
    reana_095_commands = [cli.commands[name] for name in AUTHENTICATION_COMMANDS]
    reana_095_commands += list(server_connection_group.commands.values())

    with _hidden_commands(reana_095_commands), click.Context(cli) as ctx:
        overview = cli.get_help(ctx)
    command_reference = [
        "The complete `reana-client` CLI API reference guide is available here:",
        "- [{0}]({0})".format(CLI_API_URL),
        _code_block(overview, lang="console"),
    ]
    for cmd_group in cli.cmd_groups:
        cmd_objs = [
            cmd_obj
            for cmd_obj in cmd_group.commands.values()
            if cmd_obj not in reana_095_commands
        ]
        if cmd_objs:
            command_reference.append("## {}".format(cmd_group.help))
            command_reference.extend(_command_section(c) for c in cmd_objs)

    regions = {COMMAND_REFERENCE_REGION: "\n\n".join(command_reference)}
    for name in AUTHENTICATION_COMMANDS:
        regions[_region_name(name)] = _command_section(cli.commands[name])
    regions[SERVER_COMMANDS_REGION] = "\n\n".join(
        _command_section(c) for c in server_connection_group.commands.values()
    )
    return regions


def _wrap_region(name, content):
    return "<!-- BEGIN generated {0} -->\n\n{1}\n\n<!-- END generated {0} -->".format(
        name, content
    )


def generate_cli_docs():
    """Generate the Markdown CLI API reference, with region markers.

    Maintained prose, such as the REANA 0.9 access-token guidance, belongs
    outside the regions and is not generated.
    """
    regions = generate_regions()
    sections = [
        "# reana-client CLI API",
        _wrap_region(COMMAND_REFERENCE_REGION, regions[COMMAND_REFERENCE_REGION]),
        "## Authentication in REANA 0.95",
    ]
    sections.extend(
        _wrap_region(_region_name(name), regions[_region_name(name)])
        for name in AUTHENTICATION_COMMANDS
    )
    sections.append("## {}".format(server_connection_group.help))
    sections.append(
        _wrap_region(SERVER_COMMANDS_REGION, regions[SERVER_COMMANDS_REGION])
    )
    return "\n\n".join(sections)


def extract_regions(document):
    """Extract the generated regions of a Markdown document.

    :param document: The Markdown document.
    :returns: A dictionary mapping each region name to its content.
    :raises ValueError: A region marker is malformed, unbalanced, nested or
        duplicated.
    """
    regions = {}
    current = None
    for number, line in enumerate(document.splitlines(), start=1):
        stripped = line.strip()
        match = MARKER_RE.match(stripped)
        if not match:
            if LOOSE_MARKER_RE.search(stripped):
                raise ValueError(
                    "Line {}: malformed region marker {!r}; expected "
                    "'<!-- BEGIN generated NAME -->' or "
                    "'<!-- END generated NAME -->'.".format(number, stripped)
                )
            if current is not None:
                regions[current].append(line)
            continue
        kind, name = match.groups()
        if kind == "BEGIN":
            if current is not None:
                raise ValueError(
                    "Line {}: region '{}' begins inside region '{}'.".format(
                        number, name, current
                    )
                )
            if name in regions:
                raise ValueError("Line {}: duplicate region '{}'.".format(number, name))
            current = name
            regions[name] = []
        else:
            if name != current:
                raise ValueError(
                    "Line {}: region '{}' ends without beginning.".format(number, name)
                )
            current = None
    if current is not None:
        raise ValueError("Region '{}' is never ended.".format(current))
    return {name: "\n".join(lines) for name, lines in regions.items()}


def _normalise(content):
    """Ignore whitespace and blank lines, which Markdown formatters adjust."""
    return [" ".join(line.split()) for line in content.splitlines() if line.strip()]


def check_cli_docs(document):
    """Compare the generated regions of the documentation with the CLI.

    :param document: The published Markdown CLI API reference.
    :returns: A list of problems; empty when the documentation is current.
    """
    try:
        documented = extract_regions(document)
    except ValueError as error:
        return [str(error)]
    generated = generate_regions()
    problems = []
    for name, content in generated.items():
        if name not in documented:
            problems.append("Region '{}' is missing.".format(name))
            continue
        expected, actual = _normalise(content), _normalise(documented[name])
        if not actual:
            problems.append("Region '{}' is empty.".format(name))
        elif actual != expected:
            diff = difflib.unified_diff(
                actual, expected, "documentation", "reana-client", lineterm=""
            )
            problems.append(
                "Region '{}' differs from the CLI:\n{}".format(name, "\n".join(diff))
            )
    for name in documented:
        if name not in generated:
            problems.append("Region '{}' is not generated by the CLI.".format(name))
    return problems


def main():
    """Print the CLI API reference, or check a copy of it."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        metavar="FILE",
        help="compare the generated regions of FILE with the CLI instead",
    )
    args = parser.parse_args()
    if not args.check:
        print(generate_cli_docs())
        return 0
    with open(args.check) as f:
        problems = check_cli_docs(f.read())
    for problem in problems:
        print(problem, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
