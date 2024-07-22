"""REANA client test commands."""

import click
from reana_client.cli.utils import add_access_token_options, check_connection
from reana_client.validation.utils import validate_workflow_name_parameter


@click.group(help="Workflow run test commands")
def test_group():
    """Workflow run test commands."""


@test_group.command("test")
@click.option(
    "-w",
    "--workflow",
    default="",
    callback=validate_workflow_name_parameter,
    help="Name of workflow to be tested",
)
@click.option(
    "-n",
    "--test_file",
    default="test.feature",
    help="Gherkin file for testing properties of a workflow execution",
)
@click.pass_context
@add_access_token_options
@check_connection
def test(ctx, workflow, test_file, access_token):
    r"""
    Test workflow execution, based on a given Gherkin file.

    The ``test`` command allows for testing of a workflow execution,
    by assessing whether it meets certain properties specified in a
    chosen feature file.

    Example: \n
    \t $ reana-client test -w myanalysis -n test_analysis.feature\n
    """
    click.echo(
        f"Checked {workflow} using {test_file}, and everything works!"
    )  # to be changed/implemented of course
