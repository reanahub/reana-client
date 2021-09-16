# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2017, 2018 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
"""REANA client output related commands."""

import json
import logging
import os
import sys
import traceback

import click
from reana_commons.utils import click_table_printer

from reana_client.printer import display_message
from reana_client.api.utils import get_path_from_operation_id
from reana_client.cli.utils import (
    add_access_token_options,
    add_pagination_options,
    add_workflow_option,
    check_connection,
    format_data,
    human_readable_or_raw_option,
    parse_filter_parameters,
    parse_format_parameters,
)
from reana_client.config import JSON, URL
from reana_client.errors import FileDeletionError, FileUploadError

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
    "Available filters are `name`, `size` and `last-modified`.",
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

    The `ls` command lists workspace files of a workflow specified by the
    environment variable REANA_WORKON or provided as a command-line flag
    `--workflow` or `-w`. The SOURCE argument is optional and specifies a
    pattern matching files and directories.

    Examples: \n
    \t $ reana-client ls --workflow myanalysis.42 \n
    \t $ reana-client ls --workflow myanalysis.42 --human-readable \n
    \t $ reana-client ls --workflow myanalysis.42 'data/*root*' \n
    \t $ reana-client ls --workflow myanalysis.42 --filter name=hello
    """  # noqa: W605
    import tablib
    from reana_client.api.client import current_rs_api_client, list_files

    logging.debug("command: {}".format(ctx.command_path.replace(" ", ".")))
    for p in ctx.params:
        logging.debug("{param}: {value}".format(param=p, value=ctx.params[p]))

    search_filter = None
    headers = ["name", "size", "last-modified"]
    if filters:
        _, search_filter = parse_filter_parameters(filters, headers)
    if _format:
        parsed_format_filters = parse_format_parameters(_format)
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
            tablib_data = tablib.Dataset()
            tablib_data.headers = headers
            for row in data:
                tablib_data.append(row)
            if output_format == URL:
                display_message("\n".join(urls))
            elif _format:
                tablib_data, filtered_headers = format_data(
                    parsed_format_filters, headers, tablib_data
                )
                if output_format == JSON:
                    display_message(json.dumps(tablib_data))
                else:
                    tablib_data = [list(item.values()) for item in tablib_data]
                    click_table_printer(filtered_headers, filtered_headers, tablib_data)
            else:
                if output_format == JSON:
                    display_message(tablib_data.export(output_format))
                else:
                    click_table_printer(headers, _format, data)

        except Exception as e:
            logging.debug(traceback.format_exc())
            logging.debug(str(e))

            display_message(
                "Something went wrong while retrieving file list"
                " for workflow {0}:\n{1}".format(workflow, str(e)),
                msg_type="error",
            )


@files_group.command("download")
@click.argument("filenames", metavar="FILES", nargs=-1)
@add_workflow_option
@check_connection
@click.option(
    "-o",
    "--output-directory",
    default=os.getcwd(),
    help="Path to the directory where files will be downloaded.",
)
@add_access_token_options
@click.pass_context
def download_files(
    ctx, workflow, filenames, output_directory, access_token
):  # noqa: D301
    """Download workspace files.

    The `download` command allows to download workspace files and directories.
    By default, the files specified in the workflow specification as outputs
    are downloaded. You can also specify the individual files you would like
    to download, see examples below.

    Examples: \n
    \t $ reana-client download # download all output files \n
    \t $ reana-client download mydata.tmp outputs/myplot.png
    """
    from reana_client.api.client import download_file, get_workflow_specification

    logging.debug("command: {}".format(ctx.command_path.replace(" ", ".")))
    for p in ctx.params:
        logging.debug("{param}: {value}".format(param=p, value=ctx.params[p]))

    if not filenames:
        reana_spec = get_workflow_specification(workflow, access_token)["specification"]
        if "outputs" in reana_spec:
            filenames = []
            filenames += reana_spec["outputs"].get("files", [])
            filenames += reana_spec["outputs"].get("directories", [])

    if workflow:
        for file_name in filenames:
            try:
                binary_file, file_name = download_file(
                    workflow, file_name, access_token
                )

                logging.info(
                    "{0} binary file downloaded ... writing to {1}".format(
                        file_name, output_directory
                    )
                )

                outputs_file_path = os.path.join(output_directory, file_name)
                if not os.path.exists(os.path.dirname(outputs_file_path)):
                    os.makedirs(os.path.dirname(outputs_file_path))

                with open(outputs_file_path, "wb") as f:
                    f.write(binary_file)
                display_message(
                    "File {0} downloaded to {1}.".format(file_name, output_directory),
                    msg_type="success",
                )
            except OSError as e:
                logging.debug(traceback.format_exc())
                logging.debug(str(e))
                display_message(
                    "File {0} could not be written.".format(file_name),
                    msg_type="error",
                )
            except Exception as e:
                logging.debug(traceback.format_exc())
                logging.debug(str(e))
                display_message(
                    "File {0} could not be downloaded: {1}".format(file_name, e),
                    msg_type="error",
                )


@files_group.command("upload")
@click.argument(
    "filenames",
    metavar="SOURCES",
    type=click.Path(exists=True, resolve_path=True),
    nargs=-1,
)
@add_workflow_option
@check_connection
@add_access_token_options
@click.pass_context
def upload_files(ctx, workflow, filenames, access_token):  # noqa: D301
    """Upload files and directories to workspace.

    The `upload` command allows to upload workflow input files and
    directories. The SOURCES argument can be repeated and specifies which files
    and directories are to be uploaded, see examples below. The default
    behaviour is to upload all input files and directories specified in the
    reana.yaml file.

    Examples: \n
    \t $ reana-client upload -w myanalysis.42 \n
    \t $ reana-client upload -w myanalysis.42 code/mycode.py
    """
    from reana_client.api.client import get_workflow_specification, upload_to_server

    logging.debug("command: {}".format(ctx.command_path.replace(" ", ".")))
    for p in ctx.params:
        logging.debug("{param}: {value}".format(param=p, value=ctx.params[p]))
    if not filenames:
        reana_spec = get_workflow_specification(workflow, access_token)["specification"]
        if "inputs" in reana_spec:
            filenames = []
            filenames += [
                os.path.join(os.getcwd(), f)
                for f in reana_spec["inputs"].get("files") or []
            ]
            filenames += [
                os.path.join(os.getcwd(), d)
                for d in reana_spec["inputs"].get("directories") or []
            ]

    if workflow:
        if filenames:
            for filename in filenames:
                try:
                    response = upload_to_server(workflow, filename, access_token)
                    for file_ in response:
                        if file_.startswith("symlink:"):
                            display_message(
                                "Symlink resolved to {}. "
                                "Uploaded hard copy.".format(file_[len("symlink:") :]),
                                msg_type="success",
                            )
                        else:
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
                    if "invoked_by_subcommand" in ctx.parent.__dict__:
                        sys.exit(1)
                except FileUploadError as e:
                    logging.debug(traceback.format_exc())
                    logging.debug(str(e))
                    display_message(
                        "Something went wrong while uploading {0}.\n"
                        "{1}".format(filename, str(e)),
                        msg_type="error",
                    )
                    if "invoked_by_subcommand" in ctx.parent.__dict__:
                        sys.exit(1)
                except Exception as e:
                    logging.debug(traceback.format_exc())
                    logging.debug(str(e))
                    display_message(
                        "Something went wrong while uploading {}: \n"
                        "{}".format(filename, str(e)),
                        msg_type="error",
                    )
                    if "invoked_by_subcommand" in ctx.parent.__dict__:
                        sys.exit(1)


@files_group.command("rm")
@click.argument("filenames", metavar="SOURCES", nargs=-1)
@add_workflow_option
@check_connection
@add_access_token_options
@click.pass_context
def delete_files(ctx, workflow, filenames, access_token):  # noqa: D301
    """Delete files from workspace.

    The `rm` command allow to delete files and directories from workspace.
    Note that you can use glob to remove similar files.

    Examples:\n
    \t $ reana-client rm -w myanalysis.42 data/mydata.csv \n
    \t $ reana-client rm -w myanalysis.42 'data/*root*'
    """  # noqa: W605
    from reana_client.api.client import delete_file

    logging.debug("command: {}".format(ctx.command_path.replace(" ", ".")))
    for p in ctx.params:
        logging.debug("{param}: {value}".format(param=p, value=ctx.params[p]))

    if workflow:
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
                if freed_space:
                    display_message(
                        f"{freed_space} bytes freed up.", msg_type="success"
                    )
            except FileDeletionError as e:
                display_message(str(e), msg_type="error")
                if "invoked_by_subcommand" in ctx.parent.__dict__:
                    sys.exit(1)
            except Exception as e:
                logging.debug(traceback.format_exc())
                logging.debug(str(e))
                display_message(
                    "Something went wrong while deleting {}".format(filename),
                    msg_type="error",
                )
                if "invoked_by_subcommand" in ctx.parent.__dict__:
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

    The `mv` command allow to move the files within workspace.

    Examples:\n
    \t $ reana-client mv data/input.txt input/input.txt
    """
    from reana_client.api.client import get_workflow_status, list_files, mv_files

    logging.debug("command: {}".format(ctx.command_path.replace(" ", ".")))
    for p in ctx.params:
        logging.debug("{param}: {value}".format(param=p, value=ctx.params[p]))

    if workflow:
        try:
            current_status = get_workflow_status(workflow, access_token).get("status")
            if current_status == "running":
                display_message(
                    "File(s) could not be moved for running workflow", msg_type="error",
                )
                sys.exit(1)
            files = list_files(workflow, access_token)
            current_files = [file["name"] for file in files]
            if not any(source in item for item in current_files):
                display_message(
                    "Source file(s) {} does not exist in "
                    "workspace {}".format(source, current_files),
                    msg_type="error",
                )
                sys.exit(1)
            mv_files(source, target, workflow, access_token)
            display_message(
                "{} was successfully moved to {}.".format(source, target),
                msg_type="success",
            )
        except Exception as e:
            logging.debug(traceback.format_exc())
            logging.debug(str(e))
            display_message("Something went wrong. {}".format(e), msg_type="error")


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
    "Available filters are `name` and `size`.",
)
@human_readable_or_raw_option
@click.pass_context
def workflow_disk_usage(
    ctx, workflow, access_token, summarize, filters, human_readable_or_raw
):  # noqa: D301
    """Get workspace disk usage.

    The `du` command allows to chech the disk usage of given workspace.

    Examples: \n
    \t $ reana-client du -w myanalysis.42 -s \n
    \t $ reana-client du -w myanalysis.42 -s --human-readable \n
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
                "Disk usage could not be retrieved: \n{}".format(e), msg_type="error",
            )
