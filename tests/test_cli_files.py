# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2018, 2019, 2020, 2021, 2022 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""REANA client files tests."""

import hashlib
import io
import json
import os
import zipfile

from click.testing import CliRunner
from mock import Mock, patch
from pytest_reana.test_utils import make_mock_api_client
from reana_client.cli import cli


def test_list_files_server_not_reachable():
    """Test list workflow workspace files when not connected to any cluster."""
    reana_token = "000000"
    message = "REANA client is not connected to any REANA cluster."
    runner = CliRunner()
    result = runner.invoke(cli, ["ls", "-t", reana_token, "-w", "workflow.1"])
    assert result.exit_code == 1
    assert message in result.output


def test_list_files_server_no_token():
    """Test list workflow workspace files when access token is not set."""
    message = "Please provide your access token"
    env = {"REANA_SERVER_URL": "localhost"}
    runner = CliRunner(env=env)
    result = runner.invoke(cli, ["ls", "-w", "workflow.1"])
    assert result.exit_code == 1
    assert message in result.output


def test_list_files_ok():
    """Test list workflow workspace files successfull."""
    status_code = 200
    response = {
        "items": [
            {
                "last-modified": "string",
                "name": "string",
                "size": {"raw": 0, "human_readable": "0 Bytes"},
            }
        ]
    }
    env = {"REANA_SERVER_URL": "localhost"}
    mock_http_response, mock_response = Mock(), Mock()
    mock_http_response.status_code = status_code
    mock_response = response
    reana_token = "000000"
    runner = CliRunner(env=env)
    with runner.isolation():
        with patch(
            "reana_client.api.client.current_rs_api_client",
            make_mock_api_client("reana-server")(mock_response, mock_http_response),
        ):
            result = runner.invoke(
                cli, ["ls", "-t", reana_token, "--workflow", "mytest.1", "--json"]
            )
            json_response = json.loads(result.output)
            assert result.exit_code == 0
            assert isinstance(json_response, list)
            assert len(json_response) == 1
            assert json_response[0]["name"] in response["items"][0]["name"]


def test_list_files_url():
    """Test list workflow workspace files' urls."""
    status_code = 200
    response = {
        "items": [
            {
                "last-modified": "string",
                "name": "string",
                "size": {"raw": 0, "human_readable": "0 Bytes"},
            }
        ]
    }
    env = {"REANA_SERVER_URL": "localhost"}
    mock_http_response, mock_response = Mock(), Mock()
    mock_http_response.status_code = status_code
    mock_response = response
    workflow_name = "mytest"
    reana_token = "000000"
    runner = CliRunner(env=env)
    with runner.isolation():
        with patch(
            "reana_client.api.client.current_rs_api_client",
            make_mock_api_client("reana-server")(mock_response, mock_http_response),
        ):
            result = runner.invoke(
                cli, ["ls", "-t", reana_token, "--workflow", workflow_name, "--url"]
            )
            assert result.exit_code == 0
            assert workflow_name in result.output
            assert response["items"][0]["name"] in result.output


def test_download_file():
    """Test file downloading."""
    status_code = 200
    response = "Content of file to download"
    env = {"REANA_SERVER_URL": "localhost"}
    file = "dummy_file.txt"
    mock_http_response = Mock()
    mock_http_response.status_code = status_code
    mock_http_response.content = str(response).encode()
    mock_http_response.headers = {
        "Content-Disposition": "attachment; filename={}".format(file),
        "Content-Type": "multipart/form-data",
    }
    mock_requests = Mock()
    mock_requests.get = Mock(return_value=mock_http_response)

    reana_token = "000000"
    response_md5 = hashlib.md5(response.encode("utf-8")).hexdigest()
    message = "File {0} downloaded to".format(file)
    runner = CliRunner(env=env)
    with runner.isolation():
        with patch("reana_client.api.client.requests", mock_requests):
            result = runner.invoke(
                cli, ["download", "-t", reana_token, "--workflow", "mytest.1", file]
            )
            assert result.exit_code == 0
            assert os.path.isfile(file) is True
            file_md5 = hashlib.md5(open(file, "rb").read()).hexdigest()
            assert file_md5 == response_md5
            assert message in result.output
            os.remove(file)


def test_download_file_stdout():
    """Test writing a single file to stdout."""
    env = {"REANA_SERVER_URL": "localhost"}
    filename = "dummy_file.txt"
    file_content = "Content of file to download"
    mock_http_response = Mock()
    mock_http_response.status_code = 200
    mock_http_response.content = file_content.encode()
    mock_http_response.headers = {
        "Content-Disposition": "attachment; filename={}".format(filename),
        "Content-Type": "multipart/form-data",
    }
    mock_requests = Mock()
    mock_requests.get = Mock(return_value=mock_http_response)

    reana_token = "000000"
    runner = CliRunner(env=env)
    with runner.isolation():
        with patch("reana_client.api.client.requests", mock_requests):
            result = runner.invoke(
                cli,
                [
                    "download",
                    "-t",
                    reana_token,
                    "--workflow",
                    "mytest.1",
                    filename,
                    "-o",
                    "-",
                ],
            )
            assert result.exit_code == 0
            assert result.output == file_content


def test_download_multiple_files_stdout():
    """Test writing multiple files to stdout."""
    env = {"REANA_SERVER_URL": "localhost"}
    files = [
        ("dir1/dummy1.txt", "Content of dummy1.txt"),
        ("dir1/dummy2.txt", "Content of dummy2.txt"),
    ]
    # Create zip file
    return_file = io.BytesIO()
    with zipfile.ZipFile(return_file, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for filename, content in files:
            zip_file.writestr(filename, content)

    mock_http_response = Mock()
    mock_http_response.status_code = 200
    mock_http_response.content = return_file.getvalue()
    mock_http_response.headers = {
        "Content-Disposition": "attachment; filename=files.zip",
        "Content-Type": "application/zip",
    }
    mock_requests = Mock()
    mock_requests.get = Mock(return_value=mock_http_response)

    reana_token = "000000"
    runner = CliRunner(env=env)
    with runner.isolation():
        with patch("reana_client.api.client.requests", mock_requests):
            result = runner.invoke(
                cli,
                [
                    "download",
                    "-t",
                    reana_token,
                    "--workflow",
                    "mytest.1",
                    "-o",
                    "-",
                    "dir1",
                ],
            )
            assert result.exit_code == 0
            assert result.output == "".join([content for _, content in files])


def test_upload_file(create_yaml_workflow_schema):
    """Test upload file."""
    reana_token = "000000"
    file = "file.txt"
    env = {"REANA_SERVER_URL": "http://localhost"}
    message = "was successfully uploaded."
    runner = CliRunner(env=env)
    with runner.isolation():
        with patch("reana_client.api.client.requests.post") as post_request:
            with runner.isolated_filesystem():
                with open(file, "w") as f:
                    f.write("test")
                with open("reana.yaml", "w") as reana_schema:
                    reana_schema.write(create_yaml_workflow_schema)
                result = runner.invoke(
                    cli, ["upload", "-t", reana_token, "--workflow", "mytest.1", file]
                )
                post_request.assert_called_once()
                assert result.exit_code == 0
                assert message in result.output


def test_upload_file_with_test_files_from_spec(
    get_workflow_specification_with_directory,
):
    """Test upload file with test files from the specification, not from the command line."""
    reana_token = "000000"
    file = "upload-this-test.feature"
    env = {"REANA_SERVER_URL": "http://localhost"}
    runner = CliRunner(env=env)

    with patch(
        "reana_client.api.client.get_workflow_specification"
    ) as mock_specification, patch("reana_client.api.client.requests.post"):
        with runner.isolated_filesystem():
            with open(file, "w") as f:
                f.write("Scenario: Test scenario")

            get_workflow_specification_with_directory["specification"]["tests"] = {
                "files": [file]
            }
            mock_specification.return_value = get_workflow_specification_with_directory
            result = runner.invoke(
                cli, ["upload", "-t", reana_token, "--workflow", "test-workflow.1"]
            )
            assert result.exit_code == 0
            assert (
                "upload-this-test.feature was successfully uploaded." in result.output
            )


def test_upload_file_respect_gitignore(
    get_workflow_specification_with_directory,
):
    """If .gitignore exists and is not empty, respect it's rules."""
    reana_token = "000000"
    env = {"REANA_SERVER_URL": "http://localhost"}
    runner = CliRunner(env=env)
    mock_specification = Mock(return_value=get_workflow_specification_with_directory)
    with runner.isolation():
        with patch(
            "reana_client.api.client.get_workflow_specification", mock_specification
        ), patch("reana_client.api.client.requests.post") as post_request:
            with runner.isolated_filesystem():
                with open(".gitignore", "w") as f:
                    f.write("data/should_not_upload.txt\n")

                os.mkdir("data")
                with open("data/should_not_upload.txt", "w") as f:
                    f.write("This file should not be uploaded.")

                result = runner.invoke(
                    cli, ["upload", "-t", reana_token, "--workflow", "mytest.1"]
                )

                assert (
                    "==> Detected .gitignore file. Some files might get ignored."
                    in result.output
                )
                post_request.assert_not_called()
                assert result.exit_code == 0


def test_upload_file_skip_empty_git_and_reana_ignore_files(
    get_workflow_specification_with_directory,
):
    """If .reanaignore or .gitignore files are empty, ignore them.

    This is edge case. We do not expect this to happen.
    """
    reana_token = "000000"
    env = {"REANA_SERVER_URL": "http://localhost"}
    runner = CliRunner(env=env)
    mock_specification = Mock(return_value=get_workflow_specification_with_directory)
    with runner.isolation():
        with patch(
            "reana_client.api.client.get_workflow_specification", mock_specification
        ), patch("reana_client.api.client.requests.post") as post_request:
            with runner.isolated_filesystem():
                with open(".gitignore", "w") as f:
                    f.write("\n")

                with open(".reanaignore", "w") as f:
                    f.write("\n")

                os.mkdir("data")
                with open("data/should_upload.txt", "w") as f:
                    f.write("This file should be uploaded.")

                result = runner.invoke(
                    cli, ["upload", "-t", reana_token, "--workflow", "mytest.1"]
                )

                assert (
                    "==> Detected .gitignore file. Some files might get ignored."
                    in result.output
                )
                assert (
                    "==> Detected .reanaignore file. Some files might get ignored."
                    in result.output
                )
                post_request.assert_called_once()
                assert "should_upload.txt" in result.output
                assert result.exit_code == 0


def test_upload_file_respect_reanaignore_and_gitignore(
    get_workflow_specification_with_directory,
):
    """Check if file upload respect both reana and git ignore files with input.directories."""
    reana_token = "000000"
    env = {"REANA_SERVER_URL": "http://localhost"}
    runner = CliRunner(env=env)
    mock_specification = Mock(return_value=get_workflow_specification_with_directory)
    with runner.isolation():
        with patch(
            "reana_client.api.client.get_workflow_specification", mock_specification
        ), patch("reana_client.api.client.requests.post"):
            with runner.isolated_filesystem():
                with open(".gitignore", "w") as f:
                    f.write("data/ignored_in_gitignore.txt\n")

                with open(".reanaignore", "w") as f:
                    f.write("ignored_in_reanaignore.txt\n")

                os.mkdir("data")
                os.mkdir("data/another_directory")
                with open("data/ignored_in_gitignore.txt", "w") as f:
                    f.write("This file should not be uploaded.")

                with open("data/ignored_in_reanaignore.txt", "w") as f:
                    f.write("This file should not be uploaded.")

                with open("data/should_be_uploaded.txt", "w") as f:
                    f.write("This file will be uploaded.")

                with open("data/another_directory/should_be_uploaded.txt", "w") as f:
                    f.write("This file will be uploaded.")

                result = runner.invoke(
                    cli, ["upload", "-t", reana_token, "--workflow", "mytest.1"]
                )

                assert (
                    "==> Detected .gitignore file. Some files might get ignored."
                    in result.output
                )
                assert (
                    "==> Detected .reanaignore file. Some files might get ignored."
                    in result.output
                )
                assert "ignored_in_gitignore.txt" not in result.output
                assert "ignored_in_reanaignore.txt" not in result.output

                assert "data/should_be_uploaded.txt" in result.output
                assert "data/another_directory/should_be_uploaded.txt" in result.output
                assert result.exit_code == 0


def test_delete_file():
    """Test delete file."""
    status_code = 200
    reana_token = "000000"
    filename1 = "file1"
    filename2 = "problematic_file"
    filename2_error_message = "{} could not be deleted.".format(filename2)
    response = {
        "deleted": {filename1: {"size": 19}},
        "failed": {filename2: {"error": filename2_error_message}},
    }
    message1 = "file1 was successfully deleted"
    mock_http_response = Mock()
    mock_http_response.status_code = status_code
    mock_http_response.raw_bytes = str(response).encode()
    mock_response = response
    env = {"REANA_SERVER_URL": "localhost"}
    runner = CliRunner(env=env)
    with runner.isolation():
        with patch(
            "reana_client.api.client.current_rs_api_client",
            make_mock_api_client("reana-server")(mock_response, mock_http_response),
        ):
            with runner.isolated_filesystem():
                result = runner.invoke(
                    cli, ["rm", "-t", reana_token, "--workflow", "mytest.1", filename1]
                )
                assert result.exit_code == 1
                assert message1 in result.output
                assert filename2_error_message in result.output


def test_delete_non_existing_file():
    """Test delete non existing file."""
    status_code = 200
    reana_token = "000000"
    filename = "file11"
    response = {"deleted": {}, "failed": {}}
    message = "{} did not match any existing file.".format(filename)
    mock_http_response = Mock()
    mock_http_response.status_code = status_code
    mock_http_response.raw_bytes = str(response).encode()
    mock_response = response
    env = {"REANA_SERVER_URL": "localhost"}
    runner = CliRunner(env=env)
    with runner.isolation():
        with patch(
            "reana_client.api.client.current_rs_api_client",
            make_mock_api_client("reana-server")(mock_response, mock_http_response),
        ):
            with runner.isolated_filesystem():
                result = runner.invoke(
                    cli, ["rm", "-t", reana_token, "--workflow", "mytest.1", filename]
                )
                assert result.exit_code == 1
                assert message in result.output


def test_move_files():
    """Test move files."""
    reana_token = "000000"
    workflow = "mytest.1"
    source = "file1"
    target = "file2"

    mock_http_response = Mock()
    mock_http_response.status_code = 200
    mock_http_response.raw_bytes = "{}".encode()
    mock_client = Mock()
    mock_result = mock_client.api.move_files.return_value
    mock_result.result.return_value = ({}, mock_http_response)

    runner = CliRunner(env={"REANA_SERVER_URL": "localhost"})
    with runner.isolation():
        with patch("reana_client.api.client.current_rs_api_client", mock_client):
            result = runner.invoke(
                cli,
                ["mv", "-t", reana_token, "--workflow", workflow, source, target],
            )

            mock_client.api.move_files.assert_called_once_with(
                source=source,
                target=target,
                workflow_id_or_name=workflow,
                access_token=reana_token,
            )
            assert result.exit_code == 0
            assert "successfully" in result.output


def test_list_files_filter():
    """Test list workflow workspace files with filter."""
    status_code = 200
    response = {
        "items": [
            {
                "last-modified": "2021-06-14T10:20:13",
                "name": "data/names.txt",
                "size": {"human_readable": "20 Bytes", "raw": 20},
            },
        ]
    }
    env = {"REANA_SERVER_URL": "localhost"}
    mock_http_response, mock_response = Mock(), Mock()
    mock_http_response.status_code = status_code
    mock_response = response
    reana_token = "000000"
    runner = CliRunner(env=env)
    with runner.isolation():
        with patch(
            "reana_client.api.client.current_rs_api_client",
            make_mock_api_client("reana-server")(mock_response, mock_http_response),
        ):
            result = runner.invoke(
                cli,
                [
                    "ls",
                    "-t",
                    reana_token,
                    "--workflow",
                    "mytest.1",
                    "--filter",
                    "name=names",
                    "--filter",
                    "size=20",
                    "--json",
                ],
            )
            json_response = json.loads(result.output)
            assert result.exit_code == 0
            assert isinstance(json_response, list)
            assert len(json_response) == 1
            assert "names" in json_response[0]["name"]


def test_list_disk_usage_with_valid_filter():
    """Test list disk usage info with valid filter."""
    status_code = 200
    response = {
        "disk_usage_info": [
            {
                "name": "/merge/_packtivity",
                "size": {"human_readable": "4 KiB", "raw": 4096},
            }
        ],
        "user": "00000000-0000-0000-0000-000000000000",
        "workflow_id": "7767678-766787",
        "workflow_name": "workflow",
    }
    env = {"REANA_SERVER_URL": "localhost"}
    mock_http_response, mock_response = Mock(), Mock()
    mock_http_response.status_code = status_code
    mock_response = response
    reana_token = "000000"
    runner = CliRunner(env=env)
    with runner.isolation():
        with patch(
            "reana_client.api.client.current_rs_api_client",
            make_mock_api_client("reana-server")(mock_response, mock_http_response),
        ):
            result = runner.invoke(
                cli,
                [
                    "du",
                    "-t",
                    reana_token,
                    "--workflow",
                    "workflow.1",
                    "--filter",
                    "name=merge",
                ],
            )
            assert result.exit_code == 0
            assert "merge" in result.output
            assert "4096" in result.output


def test_list_disk_usage_with_invalid_filter():
    """Test list disk usage info with invalid filter."""
    status_code = 200
    response = {
        "disk_usage_info": [],
        "user": "00000000-0000-0000-0000-000000000000",
        "workflow_id": "7767678-766787",
        "workflow_name": "workflow",
    }
    env = {"REANA_SERVER_URL": "localhost"}
    mock_http_response, mock_response = Mock(), Mock()
    mock_http_response.status_code = status_code
    mock_response = response
    reana_token = "000000"
    runner = CliRunner(env=env)
    with runner.isolation():
        with patch(
            "reana_client.api.client.current_rs_api_client",
            make_mock_api_client("reana-server")(mock_response, mock_http_response),
        ):
            result = runner.invoke(
                cli,
                [
                    "du",
                    "-t",
                    reana_token,
                    "--workflow",
                    "workflow.1",
                    "--filter",
                    "name=not_valid",
                ],
            )
            assert result.exit_code == 1
            assert "No files matching filter criteria." in result.output


def test_list_files_filter_with_filename():
    """Test list workflow workspace files with filter and filename."""
    status_code = 200
    response = {
        "items": [
            {
                "last-modified": "2021-06-14T10:20:14",
                "name": "workflow/cwl/helloworld-slurmcern.cwl",
                "size": {"human_readable": "965 Bytes", "raw": 965},
            },
            {
                "last-modified": "2021-06-14T10:20:14",
                "name": "workflow/cwl/helloworld-job.yml",
                "size": {"human_readable": "122 Bytes", "raw": 122},
            },
            {
                "last-modified": "2021-06-14T10:20:14",
                "name": "workflow/cwl/helloworld.cwl",
                "size": {"human_readable": "867 Bytes", "raw": 867},
            },
        ]
    }
    env = {"REANA_SERVER_URL": "localhost"}
    mock_http_response, mock_response = Mock(), Mock()
    mock_http_response.status_code = status_code
    mock_response = response
    reana_token = "000000"
    runner = CliRunner(env=env)
    with runner.isolation():
        with patch(
            "reana_client.api.client.current_rs_api_client",
            make_mock_api_client("reana-server")(mock_response, mock_http_response),
        ):
            result = runner.invoke(
                cli,
                [
                    "ls",
                    "-t",
                    reana_token,
                    "--workflow",
                    "mytest.1",
                    "**/*.cwl",
                    "--filter",
                    "last-modified=2021-06-14",
                    "--json",
                ],
            )
            json_response = json.loads(result.output)
            assert result.exit_code == 0
            assert isinstance(json_response, list)
            assert len(json_response) == 3
            assert json_response[0]["name"] in response["items"][0]["name"]
            assert "2021-06-14" in json_response[1]["last-modified"]


def test_prune_workspace():
    """Test prune workspace files."""
    status_code = 200
    response = {
        "message": "The workspace has been correctly pruned.",
        "workflow_id": "string",
        "workflow_name": "string",
    }
    env = {"REANA_SERVER_URL": "localhost"}
    mock_http_response, mock_response = Mock(), Mock()
    mock_http_response.status_code = status_code
    mock_response = response
    reana_token = "000000"
    runner = CliRunner(env=env)
    with runner.isolation():
        with patch(
            "reana_client.api.client.current_rs_api_client",
            make_mock_api_client("reana-server")(mock_response, mock_http_response),
        ):
            result = runner.invoke(
                cli,
                [
                    "prune",
                    "-t",
                    reana_token,
                    "--workflow",
                    "test-worflow.1",
                    "--include-outputs",
                ],
            )
            assert result.exit_code == 0
            assert response["message"] in result.output
