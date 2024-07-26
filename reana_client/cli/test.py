"""REANA client test commands."""

import sys
import click
from reana_client.cli.utils import add_access_token_options, check_connection

from reana_commons.gherkin_parser.parser import (
    parse_and_run_tests,
    AnalysisTestStatus,
)
from reana_commons.gherkin_parser.data_fetcher import DataFetcherInterface
from reana_commons.gherkin_parser.errors import FeatureFileError
from reana_client.printer import display_message
from reana_client.api.client import (
    list_files,
    get_workflow_disk_usage,
    get_workflow_logs,
    get_workflow_status,
    get_workflow_specification,
    download_file,
)
from reana_client.utils import get_reana_yaml_file_path, load_validate_reana_spec


class DataFetcherClient(DataFetcherInterface):
    """Implementation of the DataFetcherInterface using reana_client.api.client methods."""

    def list_files(
        self, workflow, access_token, file_name=None, page=None, size=None, search=None
    ):
        """Return the list of files for a given workflow workspace."""
        return list_files(workflow, access_token, file_name, page, size, search)

    def get_workflow_disk_usage(self, workflow, parameters, access_token):
        """Display disk usage workflow."""
        return get_workflow_disk_usage(workflow, parameters, access_token)

    def get_workflow_logs(
        self, workflow, access_token, steps=None, page=None, size=None
    ):
        """Get logs from a workflow engine, use existing API function."""
        return get_workflow_logs(workflow, access_token, steps, page, size)

    def get_workflow_status(self, workflow, access_token):
        """Get of a previously created workflow."""
        return get_workflow_status(workflow, access_token)

    def get_workflow_specification(self, workflow, access_token):
        """Get specification of previously created workflow."""
        return get_workflow_specification(workflow, access_token)

    def download_file(self, workflow, file_path, access_token):
        """Download the requested file if it exists."""
        return download_file(workflow, file_path, access_token)


@click.group(help="Workflow run test commands")
def test_group():
    """Workflow run test commands."""


@test_group.command("test")
@click.option(
    "-w",
    "--workflow",
    default="workflow",
    help="Name of workflow to be tested, default is 'workflow'",
)
@click.option(
    "-n",
    "--test_file",
    default=None,
    help="Gherkin file for testing properties of a workflow execution. Overrides files in reana.yaml if provided.",
)
@click.option(
    "-f",
    "--file",
    type=click.Path(exists=True, resolve_path=True),
    default=get_reana_yaml_file_path,
    help="REANA specification file describing the workflow to "
    "execute. [default=reana.yaml]",
)
@click.option(
    "--skip-validation",
    is_flag=True,
    help="If set, specifications file is not validated before "
    "submitting its contents to the REANA server.",
)
@click.pass_context
@add_access_token_options
@check_connection
def test(ctx, workflow, test_file, file, skip_validation, access_token):
    r"""
    Test workflow execution, based on a given Gherkin file.

    Multiple files can be specified in the reana specification file (reana.yaml).

    The ``test`` command allows for testing of a workflow execution,
    by assessing whether it meets certain properties specified in a
    chosen feature file.

    Example:
        $ reana-client test -w myanalysis -n test_analysis.feature
        $ reana-client test -w myanalysis
    """

    specification_filename = click.format_filename(file)
    try:
        reana_specification = load_validate_reana_spec(
            specification_filename,
            access_token=access_token,
            skip_validation=skip_validation,
            server_capabilities=True,
        )
    except Exception:
        display_message(f"Error loading {file} specification file.", msg_type="error")
        sys.exit(1)

    if test_file:
        test_files = [test_file]
    else:
        try:
            test_files = reana_specification["tests"]["files"]
        except KeyError:
            display_message(
                "No test files specified in reana.yaml and no -n option provided.",
                msg_type="error",
            )
            sys.exit(1)

    try:
        workflow_status = get_workflow_status(
            workflow=workflow, access_token=access_token
        )
        status = workflow_status["status"]
        id = workflow_status["id"]
    except Exception:
        display_message(f"Could not find workflow ``{workflow}``.", msg_type="error")
        sys.exit(1)

    if status != "finished":
        display_message(
            f"``{workflow}`` is {status}. It must be finished to run tests.",
            msg_type="error",
        )
        sys.exit(1)

    data_fetcher = DataFetcherClient()
    for test_file in test_files:
        click.secho(f"\nUsing test file {test_file}", fg="cyan", bold=True)
        try:
            results = parse_and_run_tests(
                id, test_file, workflow, access_token, data_fetcher
            )
        except FileNotFoundError:
            display_message(f"Test file {test_file} not found.", msg_type="error")
            sys.exit(1)
        except FeatureFileError as e:
            display_message(
                f"Error parsing feature file {test_file}: {e}", msg_type="error"
            )
            sys.exit(1)

        click.secho(f"Summary of {test_file}:", bold=True)
        for scenario in results[1]:
            click.echo(f"Tested {scenario['scenario']}: ", nl=False)
            click.secho(
                f"{scenario['result'].name}",
                fg=(
                    "green"
                    if scenario["result"] == AnalysisTestStatus.passed
                    else "red"
                ),
            )
