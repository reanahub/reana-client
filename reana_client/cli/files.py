# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2018, 2019, 2020, 2021, 2022 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
"""REANA client output related commands."""

import io
import logging
import os
import sys
import traceback
import zipfile
from typing import List, Tuple

import click
import pathspec

from reana_commons.utils import click_table_printer

from reana_client.printer import display_message
from reana_client.api.utils import get_path_from_operation_id
from reana_client.cli.utils import (
    add_access_token_options,
    add_pagination_options,
    add_workflow_option,
    check_connection,
    display_formatted_output,
    human_readable_or_raw_option,
    parse_filter_parameters,
)
from reana_client.config import JSON, STD_OUTPUT_CHAR, URL
from reana_client.errors import FileDeletionError
from reana_client.utils import is_regular_path

FILES_BLACKLIST = (".git/", "/.git/")


@click.group(help="Workspace file management commands")
@click.pass_context
def files_group(ctx):
    """Top level wrapper for files related interactions."""
    logging.debug(ctx.info_name)


@files_group.command("ls")
@add_workflow_option
@check_connection
@click.option(
    "--format",
    "_format",
    multiple=True,
    help="Format output according to column titles or column values. "
    "Use `<column_name>=<column_value>` format. For "
    "E.g. display FILES named data.txt "
    "`--format name=data.txt`.",
)
@click.option(
    "--json",
    "output_format",
    flag_value="json",
    default=None,
    help="Get output in JSON format.",
)
@click.option(
    "--url",
    "output_format",
    flag_value="url",
    default=None,
    help="Get URLs of output files.",
)
@click.option(
    "--filter",
    "filters",
    multiple=True,
    help="Filter results to show only files that match certain filtering "
    "criteria such as file name, size or modification date."
    "Use `--filter <columm_name>=<column_value>` pairs. "
    "Available filters are ``name``, ``size`` and ``last-modified``.",
)
@click.argument("filename", metavar="SOURCE", nargs=1, required=False)
@human_readable_or_raw_option
@add_access_token_options
@add_pagination_options
@click.pass_context
def get_files(
    ctx,
    workflow,
    _format,
    filters,
    output_format,
    filename,
    access_token,
    page,
    size,
    human_readable_or_raw,
):  # noqa: D301
    """List workspace files.

    The ``ls`` command lists workspace files of a workflow specified by the
    environment variable REANA_WORKON or provided as a command-line flag
    ``--workflow`` or ``-w``. The SOURCE argument is optional and specifies a
    pattern matching files and directories.

    Examples:\n
    \t $ reana-client ls --workflow myanalysis.42\n
    \t $ reana-client ls --workflow myanalysis.42 --human-readable\n
    \t $ reana-client ls --workflow myanalysis.42 'data/*root*'\n
    \t $ reana-client ls --workflow myanalysis.42 --filter name=hello
    """  # noqa: W605
    from reana_client.api.client import current_rs_api_client, list_files

    logging.debug("command: {}".format(ctx.command_path.replace(" ", ".")))
    for p in ctx.params:
        logging.debug("{param}: {value}".format(param=p, value=ctx.params[p]))

    search_filter = None
    headers = ["name", "size", "last-modified"]
    if filters:
        _, search_filter = parse_filter_parameters(filters, headers)
    if workflow:
        logging.info('Workflow "{}" selected'.format(workflow))
        try:
            response = list_files(
                workflow, access_token, filename, page, size, search_filter
            )
            data = []
            file_path = get_path_from_operation_id(
                current_rs_api_client.swagger_spec.spec_dict["paths"], "download_file"
            )
            urls = []
            for file_ in response:
                if not file_["name"].startswith(FILES_BLACKLIST):
                    data.append(
                        list(
                            map(
                                str,
                                [
                                    file_["name"],
                                    file_["size"][human_readable_or_raw],
                                    file_["last-modified"],
                                ],
                            )
                        )
                    )
                    urls.append(
                        ctx.obj.reana_server_url
                        + file_path.format(
                            workflow_id_or_name=workflow, file_name=file_["name"]
                        )
                    )
            if output_format == URL:
                display_message("\n".join(urls))
            else:
                display_formatted_output(data, headers, _format, output_format)

        except Exception as e:
            logging.debug(traceback.format_exc())
            logging.debug(str(e))

            display_message(
                "Something went wrong while retrieving file list"
                " for workflow {0}:\n{1}".format(workflow, str(e)),
                msg_type="error",
            )
            sys.exit(1)


@files_group.command("download")
@click.argument("filenames", metavar="FILES", nargs=-1)
@add_workflow_option
@check_connection
@click.option(
    "-o",
    "--output-directory",
    default=os.getcwd(),
    help="Path to the directory where files will be downloaded. "
    "If ``-`` is specified as path, the files will be written to the standard output.",
)
@add_access_token_options
@click.pass_context
def download_files(
    ctx, workflow, filenames, output_directory, access_token
):  # noqa: D301
    """Download workspace files.

    The ``download`` command allows to download workspace files and directories.
    By default, the files specified in the workflow specification as outputs
    are downloaded. You can also specify the individual files you would like
    to download, see examples below.

    Examples:\n
    \t $ reana-client download # download all output files\n
    \t $ reana-client download mydata.tmp outputs/myplot.png\n
    \t $ reana-client download -o - data.txt # write data.txt to stdout
    """
    from reana_client.api.client import download_file, get_workflow_specification

    def display_files_content(binary_file: bytes, multiple_files_zipped: bool) -> None:
        """Write file(s) content to the standard output.

        :param binary_file: The file(s) to print to the standard output.
        :param multiple_files_zipped: Flag to determine if ``binary_file`` is a single
            file or a zip archive containing multiple files.
        """
        if multiple_files_zipped:
            with zipfile.ZipFile(io.BytesIO(binary_file)) as zip_file:
                for entry in zip_file.infolist():
                    if not entry.is_dir():
                        click.echo(zip_file.read(entry), nl=False)
        else:
            click.echo(binary_file, nl=False)

    logging.debug("command: {}".format(ctx.command_path.replace(" ", ".")))
    for p in ctx.params:
        logging.debug("{param}: {value}".format(param=p, value=ctx.params[p]))

    if not filenames:
        try:
            reana_spec = get_workflow_specification(workflow, access_token)[
                "specification"
            ]
        except Exception as e:
            logging.debug(str(e), exc_info=True)
            display_message(
                "Workflow {} could not be retrieved: {}".format(workflow, e),
                msg_type="error",
            )
            sys.exit(1)

        if reana_spec.get("outputs"):
            filenames = []
            filenames += reana_spec["outputs"].get("files") or []
            filenames += reana_spec["outputs"].get("directories") or []

    if workflow:
        download_failed = False
        for file_name in filenames:
            try:
                binary_file, file_name, multiple_files_zipped = download_file(
                    workflow, file_name, access_token
                )

                logging.info(
                    "{0} binary file downloaded ... writing to {1}".format(
                        file_name, output_directory
                    )
                )

                if output_directory == STD_OUTPUT_CHAR:
                    display_files_content(binary_file, multiple_files_zipped)
                else:
                    outputs_file_path = os.path.join(output_directory, file_name)
                    if not os.path.exists(os.path.dirname(outputs_file_path)):
                        os.makedirs(os.path.dirname(outputs_file_path))

                    with open(outputs_file_path, "wb") as f:
                        f.write(binary_file)
                    display_message(
                        f"File {file_name} downloaded to {output_directory}.",
                        msg_type="success",
                    )
            except OSError as e:
                logging.debug(traceback.format_exc())
                logging.debug(str(e))
                display_message(
                    "File {0} could not be written.".format(file_name),
                    msg_type="error",
                )
                download_failed = True
            except Exception as e:
                logging.debug(traceback.format_exc())
                logging.debug(str(e))
                display_message(
                    "File {0} could not be downloaded: {1}".format(file_name, e),
                    msg_type="error",
                )
                download_failed = True
        if download_failed:
            sys.exit(1)


@files_group.command("upload")
@click.argument(
    "filenames",
    metavar="SOURCES",
    type=click.Path(exists=True),
    nargs=-1,
)
@add_workflow_option
@check_connection
@add_access_token_options
@click.pass_context
def upload_files(  # noqa: C901
    ctx, workflow: str, filenames: Tuple[str], access_token: str
):  # noqa: D301
    """Upload files and directories to workspace.

    The ``upload`` command allows to upload workflow input files and
    directories. The SOURCES argument can be repeated and specifies which files
    and directories are to be uploaded, see examples below. The default
    behaviour is to upload all input files and directories specified in the
    reana.yaml file.

    Examples:\n
    \t $ reana-client upload -w myanalysis.42\n
    \t $ reana-client upload -w myanalysis.42 code/mycode.py
    """
    from reana_client.api.client import get_workflow_specification, upload_to_server

    logging.debug("command: {}".format(ctx.command_path.replace(" ", ".")))
    for p in ctx.params:
        logging.debug("{param}: {value}".format(param=p, value=ctx.params[p]))

    if not filenames:
        try:
            reana_spec = get_workflow_specification(workflow, access_token)[
                "specification"
            ]
        except Exception as e:
            logging.debug(str(e), exc_info=True)
            display_message(
                "Workflow {} could not be retrieved: {}".format(workflow, e),
                msg_type="error",
            )
            sys.exit(1)

        if reana_spec.get("inputs"):
            filenames = []

            # collect all files in input.files
            for f in reana_spec["inputs"].get("files") or []:
                # check for directories in files
                if os.path.isdir(f):
                    display_message(
                        f"Found directory in `inputs.files`: {f}",
                        msg_type="error",
                    )
                    sys.exit(1)
                filenames.append(os.path.join(os.getcwd(), f))

            # collect all files in input.directories
            files_from_directories = []
            directories = reana_spec["inputs"].get("directories") or []
            for directory_path in directories:
                # check for files in directories
                if os.path.isfile(directory_path):
                    display_message(
                        f"Found file in `inputs.directories`: {directory_path}",
                        msg_type="error",
                    )
                    sys.exit(1)
                for root, _, dir_filenames in os.walk(directory_path):
                    filenames_full_path = [
                        os.path.join(root, file) for file in dir_filenames
                    ]
                    files_from_directories.extend(filenames_full_path)

            def _filter_files(
                files: List[str], paths_spec: pathspec.PathSpec
            ) -> List[str]:
                return [file for file in files if not paths_spec.match_file(file)]

            try:
                with open(".gitignore") as f:
                    gitignore_spec = pathspec.PathSpec.from_lines("gitwildmatch", f)
                display_message(
                    "Detected .gitignore file. Some files might get ignored.",
                    msg_type="info",
                )
            except FileNotFoundError:
                pass
            else:
                files_from_directories = _filter_files(
                    files_from_directories, gitignore_spec
                )

            try:
                with open(".reanaignore") as f:
                    reanaignore_spec = pathspec.PathSpec.from_lines("gitwildmatch", f)
                display_message(
                    "Detected .reanaignore file. Some files might get ignored.",
                    msg_type="info",
                )
            except FileNotFoundError:
                pass
            else:
                files_from_directories = _filter_files(
                    files_from_directories, reanaignore_spec
                )

            filenames += [
                os.path.join(os.getcwd(), file) for file in files_from_directories
            ]

    # collect and filter out all the unique filepaths
    filepaths = set()
    for filepath in filenames:
        if os.path.isfile(filepath):
            filepaths.add(filepath)
        else:
            for root, _, files in os.walk(filepath):
                filepaths.update([os.path.join(root, file) for file in files])

    upload_failed = False
    for filename in filepaths:
        try:
            if not is_regular_path(filename):
                display_message(f"Ignoring symlink {filepath}", msg_type="info")
                continue

            filepath = os.path.abspath(filename)
            response = upload_to_server(workflow, filepath, access_token)
            for file_ in response:
                display_message(
                    "File {} was successfully uploaded.".format(file_),
                    msg_type="success",
                )
        except FileNotFoundError as e:
            logging.debug(traceback.format_exc())
            logging.debug(str(e))
            display_message(
                "File {0} could not be uploaded: "
                "{0} does not exist.".format(filename),
                msg_type="error",
            )
            upload_failed = True
        except Exception as e:
            logging.debug(traceback.format_exc())
            logging.debug(str(e))
            display_message(
                "Something went wrong while uploading {}: \n"
                "{}".format(filename, str(e)),
                msg_type="error",
            )
            upload_failed = True
    if upload_failed:
        sys.exit(1)


@files_group.command("rm")
@click.argument("filenames", metavar="SOURCES", nargs=-1)
@add_workflow_option
@check_connection
@add_access_token_options
@click.pass_context
def delete_files(ctx, workflow, filenames, access_token):  # noqa: D301
    """Delete files from workspace.

    The ``rm`` command allow to delete files and directories from workspace.
    Note that you can use glob to remove similar files.

    Examples:\n
    \t $ reana-client rm -w myanalysis.42 data/mydata.csv\n
    \t $ reana-client rm -w myanalysis.42 'data/*root*'
    """  # noqa: W605
    from reana_client.api.client import delete_file

    logging.debug("command: {}".format(ctx.command_path.replace(" ", ".")))
    for p in ctx.params:
        logging.debug("{param}: {value}".format(param=p, value=ctx.params[p]))

    if workflow:
        delete_failed = False
        for filename in filenames:
            try:
                response = delete_file(workflow, filename, access_token)
                freed_space = 0
                for file_ in response["deleted"]:
                    freed_space += response["deleted"][file_]["size"]
                    display_message(
                        f"File {file_} was successfully deleted.", msg_type="success"
                    )
                for file_ in response["failed"]:
                    display_message(
                        "Something went wrong while deleting {}.\n"
                        "{}".format(file_, response["failed"][file_]["error"]),
                        msg_type="error",
                    )
                    delete_failed = True
                if freed_space:
                    display_message(
                        f"{freed_space} bytes freed up.", msg_type="success"
                    )
            except FileDeletionError as e:
                display_message(str(e), msg_type="error")
                delete_failed = True
            except Exception as e:
                logging.debug(traceback.format_exc())
                logging.debug(str(e))
                display_message(
                    "Something went wrong while deleting {}".format(filename),
                    msg_type="error",
                )
                delete_failed = True
        if delete_failed:
            sys.exit(1)


@files_group.command("mv")
@click.argument("source")
@click.argument("target")
@add_workflow_option
@check_connection
@add_access_token_options
@click.pass_context
def move_files(ctx, source, target, workflow, access_token):  # noqa: D301
    """Move files within workspace.

    The ``mv`` command allows to move files within a workspace. Note that the
    workflow might fail if files are moved during its execution.

    Examples:\n
    \t $ reana-client mv data/input.txt input/input.txt
    """
    from reana_client.api.client import get_workflow_status, list_files, mv_files

    logging.debug("command: {}".format(ctx.command_path.replace(" ", ".")))
    for p in ctx.params:
        logging.debug("{param}: {value}".format(param=p, value=ctx.params[p]))

    try:
        mv_files(source, target, workflow, access_token)
        display_message(
            "{} was successfully moved to {}.".format(source, target),
            msg_type="success",
        )
    except Exception as e:
        logging.debug(traceback.format_exc())
        logging.debug(str(e))
        display_message("Something went wrong. {}".format(e), msg_type="error")
        sys.exit(1)


@files_group.command("prune")
@check_connection
@add_workflow_option
@add_access_token_options
@click.option(
    "--include-inputs",
    "include_inputs",
    is_flag=True,
    help="Delete also the input files of the workflow. Note that this includes the workflow specification file.",
)
@click.option(
    "--include-outputs",
    "include_outputs",
    is_flag=True,
    help="Delete also the output files of the workflow.",
)
@click.pass_context
def prune_files(
    ctx, workflow, access_token, include_inputs, include_outputs
):  # noqa: D301
    """Prune workspace files.

    The ``prune`` command deletes all the intermediate files of a given workflow that are not present
    in the input or output section of the workflow specification.

    Examples:\n
    \t $ reana-client prune -w myanalysis.42\n
    \t $ reana-client prune -w myanalysis.42 --include-inputs
    """
    from reana_client.api.client import prune_workspace

    logging.debug("command: {}".format(ctx.command_path.replace(" ", ".")))
    for p in ctx.params:
        logging.debug("{param}: {value}".format(param=p, value=ctx.params[p]))

    try:
        response = prune_workspace(
            workflow, include_inputs, include_outputs, access_token
        )
        display_message(response["message"], msg_type="success")
    except Exception as e:
        logging.debug(traceback.format_exc())
        logging.debug(str(e))
        display_message(
            "Workspace could not be pruned: \n{}".format(e),
            msg_type="error",
        )
        sys.exit(1)


@files_group.command("du")
@add_workflow_option
@check_connection
@add_access_token_options
@click.option("-s", "--summarize", is_flag=True, help="Display total.")
@click.option(
    "--filter",
    "filters",
    multiple=True,
    help="Filter results to show only files that match certain filtering "
    "criteria such as file name or size."
    "Use `--filter <columm_name>=<column_value>` pairs. "
    "Available filters are ``name`` and ``size``.",
)
@human_readable_or_raw_option
@click.pass_context
def workflow_disk_usage(
    ctx, workflow, access_token, summarize, filters, human_readable_or_raw
):  # noqa: D301
    """Get workspace disk usage.

    The ``du`` command allows to check the disk usage of given workspace.

    Examples:\n
    \t $ reana-client du -w myanalysis.42 -s\n
    \t $ reana-client du -w myanalysis.42 -s --human-readable\n
    \t $ reana-client du -w myanalysis.42 --filter name=data/
    """
    from reana_client.api.client import get_workflow_disk_usage

    logging.debug("command: {}".format(ctx.command_path.replace(" ", ".")))
    for p in ctx.params:
        logging.debug("{param}: {value}".format(param=p, value=ctx.params[p]))

    search_filter = None
    headers = ["size", "name"]
    if filters:
        _, search_filter = parse_filter_parameters(filters, headers)
    if workflow:
        try:
            parameters = {"summarize": summarize, "search": search_filter}
            response = get_workflow_disk_usage(workflow, parameters, access_token)
            if not response["disk_usage_info"]:
                display_message("No files matching filter criteria.", msg_type="error")
                sys.exit(1)
            data = []
            for disk_usage_info in response["disk_usage_info"]:
                if not disk_usage_info["name"].startswith(FILES_BLACKLIST):
                    data.append(
                        [
                            disk_usage_info["size"][human_readable_or_raw],
                            ".{}".format(disk_usage_info["name"]),
                        ]
                    )
            click_table_printer(headers, [], data)
        except Exception as e:
            logging.debug(traceback.format_exc())
            logging.debug(str(e))
            display_message(
                "Disk usage could not be retrieved: \n{}".format(e),
                msg_type="error",
            )
            sys.exit(1)
