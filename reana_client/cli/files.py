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

from reana_client.api.utils import get_path_from_operation_id
from reana_client.cli.utils import (
    add_access_token_options,
    add_pagination_options,
    add_workflow_option,
    check_connection,
    filter_data,
    parse_parameters,
)
from reana_client.config import ERROR_MESSAGES, JSON, URL
from reana_client.errors import FileDeletionError, FileUploadError
from reana_client.utils import get_reana_yaml_file_path, workflow_uuid_or_name
from reana_commons.utils import click_table_printer


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
    "_filter",
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
@click.argument("filename", metavar="SOURCE", nargs=1, required=False)
@add_access_token_options
@add_pagination_options
@click.pass_context
def get_files(
    ctx, workflow, _filter, output_format, filename, access_token, page, size
):  # noqa: D301
    """List workspace files.

    The `ls` command lists workspace files of a workflow specified by the
    environment variable REANA_WORKON or provided as a command-line flag
    `--workflow` or `-w`.

    Examples: \n
    \t $ reana-client ls --workflow myanalysis.42 \n
    \t $ reana-client ls --workflow myanalysis.42 'code/\*'
    """  # noqa: W605
    import tablib
    from reana_client.api.client import current_rs_api_client, list_files

    logging.debug("command: {}".format(ctx.command_path.replace(" ", ".")))
    for p in ctx.params:
        logging.debug("{param}: {value}".format(param=p, value=ctx.params[p]))

    if _filter:
        parsed_filters = parse_parameters(_filter)
    if workflow:
        logging.info('Workflow "{}" selected'.format(workflow))
        try:
            response = list_files(workflow, access_token, filename, page, size)
            headers = ["name", "size", "last-modified"]
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
                                [file_["name"], file_["size"], file_["last-modified"]],
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
                click.echo("\n".join(urls))
            elif _filter:
                tablib_data, filtered_headers = filter_data(
                    parsed_filters, headers, tablib_data
                )
                if output_format == JSON:
                    click.echo(json.dumps(tablib_data))
                else:
                    tablib_data = [list(item.values()) for item in tablib_data]
                    click_table_printer(filtered_headers, filtered_headers, tablib_data)
            else:
                if output_format == JSON:
                    click.echo(tablib_data.export(output_format))
                else:
                    click_table_printer(headers, _filter, data)

        except Exception as e:
            logging.debug(traceback.format_exc())
            logging.debug(str(e))

            click.echo(
                click.style(
                    "Something went wrong while retrieving file list"
                    " for workflow {0}:\n{1}".format(workflow, str(e)),
                    fg="red",
                ),
                err=True,
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

    The `download` command allows to download workspace files. By default, the
    files specified in the workflow specification as outputs are downloaded.
    You can also specify the individual files you would like to download, see
    examples below. Note that downloading directories is not yet supported.

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
            filenames = reana_spec["outputs"].get("files") or []

    if workflow:
        for file_name in filenames:
            try:
                binary_file = download_file(workflow, file_name, access_token)

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
                click.secho(
                    "File {0} downloaded to {1}.".format(file_name, output_directory),
                    fg="green",
                )
            except OSError as e:
                logging.debug(traceback.format_exc())
                logging.debug(str(e))
                click.echo(
                    click.style(
                        "File {0} could not be written.".format(file_name), fg="red"
                    ),
                    err=True,
                )
            except Exception as e:
                logging.debug(traceback.format_exc())
                logging.debug(str(e))
                click.echo(
                    click.style(
                        "File {0} could not be downloaded: {1}".format(file_name, e),
                        fg="red",
                    ),
                    err=True,
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
                            click.echo(
                                click.style(
                                    "Symlink resolved to {}. Uploaded"
                                    " hard copy.".format(file_[len("symlink:") :]),
                                    fg="green",
                                )
                            )
                        else:
                            click.echo(
                                click.style(
                                    "File {} was successfully "
                                    "uploaded.".format(file_),
                                    fg="green",
                                )
                            )
                except FileNotFoundError as e:
                    logging.debug(traceback.format_exc())
                    logging.debug(str(e))
                    click.echo(
                        click.style(
                            "File {0} could not be uploaded: {0} does not"
                            " exist.".format(filename),
                            fg="red",
                        ),
                        err=True,
                    )
                    if "invoked_by_subcommand" in ctx.parent.__dict__:
                        sys.exit(1)
                except FileUploadError as e:
                    logging.debug(traceback.format_exc())
                    logging.debug(str(e))
                    click.echo(
                        click.style(
                            "Something went wrong while uploading {0}.\n{1}".format(
                                filename, str(e)
                            ),
                            fg="red",
                        ),
                        err=True,
                    )
                    if "invoked_by_subcommand" in ctx.parent.__dict__:
                        sys.exit(1)
                except Exception as e:
                    logging.debug(traceback.format_exc())
                    logging.debug(str(e))
                    click.echo(
                        click.style(
                            "Something went wrong while uploading {}: \n{}".format(
                                filename, str(e)
                            ),
                            fg="red",
                        ),
                        err=True,
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
    \t $ reana-client rm -w myanalysis.42 'code/\*'
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
                    click.echo(
                        click.style(
                            "File {} was successfully deleted.".format(file_),
                            fg="green",
                        )
                    )
                for file_ in response["failed"]:
                    click.echo(
                        click.style(
                            "Something went wrong while deleting {}.\n{}".format(
                                file_, response["failed"][file_]["error"]
                            ),
                            fg="red",
                        ),
                        err=True,
                    )
                if freed_space:
                    click.echo(
                        click.style(
                            "{} bytes freed up.".format(freed_space), fg="green"
                        )
                    )
            except FileDeletionError as e:
                click.echo(click.style(str(e), fg="red"), err=True)
                if "invoked_by_subcommand" in ctx.parent.__dict__:
                    sys.exit(1)
            except Exception as e:
                logging.debug(traceback.format_exc())
                logging.debug(str(e))
                click.echo(
                    click.style(
                        "Something went wrong while deleting {}".format(filename),
                        fg="red",
                    ),
                    err=True,
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
                click.echo(
                    click.style(
                        "File(s) could not be moved for running " "workflow", fg="red"
                    ),
                    err=True,
                )
                sys.exit(1)
            files = list_files(workflow, access_token)
            current_files = [file["name"] for file in files]
            if not any(source in item for item in current_files):
                click.echo(
                    click.style(
                        "Source file(s) {} does not exist in "
                        "workspace {}".format(source, current_files),
                        fg="red",
                    ),
                    err=True,
                )
                sys.exit(1)
            mv_files(source, target, workflow, access_token)
            click.echo(
                click.style(
                    "{} was successfully moved to {}.".format(source, target),
                    fg="green",
                )
            )
        except Exception as e:
            logging.debug(traceback.format_exc())
            logging.debug(str(e))
            click.echo(
                click.style("Something went wrong. {}".format(e), fg="red"), err=True
            )


@files_group.command("du")
@add_workflow_option
@check_connection
@add_access_token_options
@click.option("-s", "--summarize", is_flag=True, help="Display total.")
@click.option(
    "-b", "--bytes", "block_size", flag_value="b", help="Print size in bytes."
)
@click.option(
    "-k", "--kilobytes", "block_size", flag_value="k", help="Print size in kilobytes."
)
@click.pass_context
def workflow_disk_usage(
    ctx, workflow, access_token, summarize, block_size
):  # noqa: D301
    """Get workspace disk usage.

    The `du` command allows to chech the disk usage of given workspace.

    Examples: \n
    \t $ reana-client du -w myanalysis.42 -s \n
    \t $ reana-client du -w myanalysis.42 --bytes
    """
    from reana_client.api.client import get_workflow_disk_usage

    logging.debug("command: {}".format(ctx.command_path.replace(" ", ".")))
    for p in ctx.params:
        logging.debug("{param}: {value}".format(param=p, value=ctx.params[p]))

    if workflow:
        try:
            parameters = {"summarize": summarize, "block_size": block_size}
            response = get_workflow_disk_usage(workflow, parameters, access_token)
            headers = ["size", "name"]
            data = []
            for disk_usage_info in response["disk_usage_info"]:
                if not disk_usage_info["name"].startswith(FILES_BLACKLIST):
                    data.append(
                        [disk_usage_info["size"], ".{}".format(disk_usage_info["name"])]
                    )
            click_table_printer(headers, [], data)
        except Exception as e:
            logging.debug(traceback.format_exc())
            logging.debug(str(e))
            click.echo(
                click.style(
                    "Disk usage could not be retrieved: \n{}".format(str(e)), fg="red"
                ),
                err=True,
            )
