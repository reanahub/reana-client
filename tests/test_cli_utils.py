# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2026 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""REANA client CLI utils tests."""

import pytest

from reana_client.config import MAX_RUN_LABELS_SHOWN
from reana_client.cli.utils import (
    parse_workflow_run_number,
    get_run_number_major_key,
    format_run_number_label,
    format_run_label_list,
)

import json
from unittest.mock import Mock, patch

import click
import tablib
from click.testing import CliRunner

from reana_client.config import (
    ERROR_MESSAGES,
    RUN_STATUSES,
    CLI_LOGS_FOLLOW_DEFAULT_INTERVAL,
)
import reana_client.cli.utils as cli_utils


@pytest.mark.parametrize(
    "full_name, expected",
    [
        ("", (None, None, None)),
        (None, (None, None, None)),
        ("name", ("name", None, None)),
        ("name.7", ("name", "7", None)),
        ("name.7.1", ("name", "7", "1")),
        ("name.7.1.2", ("name", "7", "1.2")),
        ("my.flow.3.2", ("my.flow", "3", "2")),
        ("7.1", (None, "7", "1")),
    ],
)
def test_parse_workflow_run_number(full_name, expected):
    assert parse_workflow_run_number(full_name) == expected


@pytest.mark.parametrize(
    "full_name, expected",
    [
        ("helloworld-demo.1", "helloworld-demo.1"),
        ("helloworld-demo.1.1", "helloworld-demo.1"),
        ("helloworld-demo.1.2.3", "helloworld-demo.1"),
        ("my.flow.3.2", "my.flow.3"),
        ("name", None),
        ("", None),
        (None, None),
        ("7.1", None),  # numeric-only has no base name
    ],
)
def test_get_run_number_major_key(full_name, expected):
    assert get_run_number_major_key(full_name) == expected


@pytest.mark.parametrize(
    "full_name, expected",
    [
        ("name.7", "#7"),
        ("name.7.1", "#7.1"),
        ("name.7.1.2", "#7.1.2"),
        ("my.flow.3.2", "#3.2"),
        ("name", "name"),
        ("", ""),
    ],
)
def test_format_run_number_label(full_name, expected):
    assert format_run_number_label(full_name) == expected


def test_format_run_label_list_filters_falsy_items():
    assert format_run_label_list([None, "", "#3", "0", False]) == "#3, 0"


def test_format_run_label_list_empty_and_none():
    assert format_run_label_list([]) == ""
    assert format_run_label_list(None) == ""


def test_format_run_label_list_no_truncation():
    assert format_run_label_list(["#1", "#2"], max_labels=10) == "#1, #2"


def test_format_run_label_list_truncation():
    labels = ["#1", "#2", "#3", "#4", "#5", "#6", "#7"]
    assert (
        format_run_label_list(labels, max_labels=6) == "#1, #2, #3, #4, #5, #6, +1 more"
    )


def test_format_run_label_list_uses_default_max():
    labels = [f"#{i}" for i in range(1, MAX_RUN_LABELS_SHOWN + 3)]  # +2 beyond max
    out = format_run_label_list(labels)  # use default
    # Should include first MAX_RUN_LABELS_SHOWN labels and "+2 more"
    expected_prefix = ", ".join(labels[:MAX_RUN_LABELS_SHOWN])
    assert out == f"{expected_prefix}, +2 more"


def test_access_token_required_option_exits_when_missing(monkeypatch):
    monkeypatch.delenv("REANA_ACCESS_TOKEN", raising=False)

    @click.command()
    @cli_utils.add_access_token_options
    def cmd(access_token):
        click.echo(access_token)

    runner = CliRunner()
    result = runner.invoke(cmd, [])
    assert result.exit_code == 1
    assert ERROR_MESSAGES["missing_access_token"] in result.output


def test_access_token_not_required_option_allows_missing(monkeypatch):
    monkeypatch.delenv("REANA_ACCESS_TOKEN", raising=False)

    @click.command()
    @cli_utils.add_access_token_options_not_required
    def cmd(access_token):
        click.echo(str(access_token))

    runner = CliRunner()
    result = runner.invoke(cmd, [])
    assert result.exit_code == 0
    assert "None" in result.output


def test_human_readable_or_raw_option():
    @click.command()
    @cli_utils.human_readable_or_raw_option
    def cmd(human_readable_or_raw):
        click.echo(human_readable_or_raw)

    runner = CliRunner()
    assert runner.invoke(cmd, []).output.strip() == "raw"
    assert runner.invoke(cmd, ["-h"]).output.strip() == "human_readable"
    assert runner.invoke(cmd, ["--human-readable"]).output.strip() == "human_readable"


def test_check_connection_exits_when_not_connected(monkeypatch):
    # check_connection imports get_api_url at runtime
    monkeypatch.setattr("reana_client.utils.get_api_url", lambda: None)

    @click.command()
    @cli_utils.check_connection
    def cmd():
        click.echo("OK")

    runner = CliRunner()
    result = runner.invoke(cmd, [])
    assert result.exit_code == 1
    assert "not connected to any REANA cluster" in result.output


def test_add_workflow_option_uses_callback(monkeypatch):
    # Avoid real workflow_uuid_or_name behaviour
    monkeypatch.setattr(
        cli_utils, "workflow_uuid_or_name", lambda ctx, param, v: f"CB:{v}"
    )
    monkeypatch.delenv("REANA_WORKON", raising=False)

    @click.command()
    @cli_utils.add_workflow_option
    def cmd(workflow):
        click.echo(workflow)

    runner = CliRunner()
    result = runner.invoke(cmd, ["-w", "myflow.1"])
    assert result.exit_code == 0
    assert result.output.strip() == "CB:myflow.1"


def test_add_pagination_options_defaults():
    @click.command()
    @cli_utils.add_pagination_options
    def cmd(page, size):
        click.echo(f"{page}:{size}")

    runner = CliRunner()
    result = runner.invoke(cmd, [])
    assert result.exit_code == 0
    assert result.output.strip() == "1:None"


def test_parse_format_parameters_supports_quotes_and_commas():
    # input resembles click's multiple option tuple
    parsed = cli_utils.parse_format_parameters(
        ('name="hello world",status=finished', "size")
    )
    assert {"column_name": "name", "column_value": "hello world"} in parsed
    assert {"column_name": "status", "column_value": "finished"} in parsed
    assert {"column_name": "size", "column_value": None} in parsed


def test_parse_filter_parameters_status_and_search_json():
    valid_status = "finished" if "finished" in RUN_STATUSES else RUN_STATUSES[0]
    status_filters, search_filters = cli_utils.parse_filter_parameters(
        (f"status={valid_status}", "user=alice", "user=bob"),
        filter_names=["status", "user"],
    )
    assert status_filters == [valid_status]
    assert json.loads(search_filters) == {"user": ["alice", "bob"]}


def test_parse_filter_parameters_invalid_status_exits():
    with patch.object(cli_utils, "display_message") as dm:
        with pytest.raises(SystemExit) as e:
            cli_utils.parse_filter_parameters(
                ("status=NOT_A_STATUS",), filter_names=["status"]
            )
        assert e.value.code == 1
        assert dm.called


def test_parse_filter_parameters_invalid_filter_name_exits():
    with patch.object(cli_utils, "display_message") as dm:
        with pytest.raises(SystemExit) as e:
            cli_utils.parse_filter_parameters(("nope=1",), filter_names=["status"])
        assert e.value.code == 1
        assert dm.called


def test_parse_filter_parameters_missing_equals_raises_badparameter():
    with pytest.raises(click.BadParameter):
        cli_utils.parse_filter_parameters(("status",), filter_names=["status"])


def test_format_data_filters_rows_and_columns():
    headers = ["name", "status"]
    ds = tablib.Dataset(headers=headers)
    ds.append(["a", "ok"])
    ds.append(["b", "fail"])

    parsed_filters = [{"column_name": "status", "column_value": "ok"}]
    filtered, filtered_headers = cli_utils.format_data(parsed_filters, headers, ds)

    assert filtered_headers == ["status"]
    assert filtered == [{"status": "ok"}]


def test_display_formatted_output_json_no_format(monkeypatch):
    seen = {}

    def fake_display_message(msg, *args, **kwargs):
        seen["msg"] = msg

    monkeypatch.setattr(cli_utils, "display_message", fake_display_message)

    cli_utils.display_formatted_output(
        data=[["a", "ok"]],
        headers=["name", "status"],
        _format=(),
        output_format=cli_utils.JSON,
    )
    assert '"headers"' in seen["msg"] or '"name"' in seen["msg"]


def test_display_formatted_output_table_with_format(monkeypatch):
    calls = []

    monkeypatch.setattr(
        cli_utils, "click_table_printer", lambda *a, **k: calls.append((a, k))
    )
    monkeypatch.setattr(cli_utils, "display_message", lambda *a, **k: None)

    cli_utils.display_formatted_output(
        data=[["a", "ok"], ["b", "fail"]],
        headers=["name", "status"],
        _format=("status=ok",),
        output_format=None,
    )
    assert calls, "click_table_printer should have been called"
    # printer called with filtered headers for both header args
    assert calls[0][0][0] == ["status"]


def test_format_session_uri_and_progress():
    assert (
        cli_utils.format_session_uri("https://reana", "/path", "tok")
        == "https://reana/path?token=tok"
    )
    assert (
        cli_utils.get_formatted_progress(
            {"total": {"total": 10}, "finished": {"total": 3}}
        )
        == "3/10"
    )
    assert cli_utils.get_formatted_progress({}) == "-/-"


def test_key_value_to_dict_valid_and_invalid():
    assert cli_utils.key_value_to_dict(None, None, ("a=1", "b=2")) == {
        "a": "1",
        "b": "2",
    }

    with patch.object(cli_utils, "display_message") as dm:
        with pytest.raises(SystemExit) as e:
            cli_utils.key_value_to_dict(
                None,
                None,
                (
                    "a=1",
                    "b",
                ),
            )
        assert e.value.code == 1
        assert dm.called


def test_requires_environments_exits_when_flag_missing():
    @click.command()
    @click.option("--environments", is_flag=True, default=False)
    @click.option("--foo", is_flag=True, callback=cli_utils.requires_environments)
    def cmd(environments, foo):
        click.echo("OK")

    runner = CliRunner()
    result = runner.invoke(cmd, ["--foo"])
    assert result.exit_code == 1
    assert "requires `--environments`" in result.output

    result2 = runner.invoke(cmd, ["--environments", "--foo"])
    assert result2.exit_code == 0


def test_not_required_if_requires_one_option(monkeypatch):
    # Make the error message visible without depending on formatting
    monkeypatch.setattr(cli_utils, "display_message", lambda msg, **k: click.echo(msg))

    @click.command()
    @click.option("--foo", cls=cli_utils.NotRequiredIf, not_required_if="bar")
    @click.option("--bar")
    def cmd(foo, bar):
        click.echo("OK")

    runner = CliRunner()
    res = runner.invoke(cmd, [])
    assert res.exit_code == 1
    assert "At least one of the options" in res.output

    assert runner.invoke(cmd, ["--foo", "x"]).exit_code == 0
    assert runner.invoke(cmd, ["--bar", "y"]).exit_code == 0


def test_output_user_friendly_logs_basic_output(capsys):
    workflow_logs = {
        "workflow_logs": "ENGINE LOG\n",
        "engine_specific": "INTERNAL LOG\n",
        "job_logs": {
            "1": {
                "job_name": "step1",
                "logs": "JOB LOG\n",
                "status": "finished",
                "workflow_uuid": "uuid",
                "compute_backend": "k8s",
                "backend_job_id": "backend-1",
                "docker_img": "img",
                "cmd": "echo hi",
                "started_at": "t0",
                "finished_at": "t1",
            }
        },
    }
    cli_utils.output_user_friendly_logs(workflow_logs, steps=None)
    out = capsys.readouterr().out
    assert "Workflow engine logs" in out
    assert "Engine internal logs" in out
    assert "Job logs" in out
    assert "Step: step1" in out


def test_retrieve_workflow_logs_calls_output_user_friendly_logs(monkeypatch):
    payload = {
        "workflow_logs": "W",
        "engine_specific": "",
        "job_logs": {
            "1": {
                "job_name": "s1",
                "logs": "L1",
                "status": "finished",
                "compute_backend": "k8s",
            },
            "2": {
                "job_name": "s2",
                "logs": "L2",
                "status": "finished",
                "compute_backend": "htcondor",
            },
        },
    }
    monkeypatch.setattr(
        "reana_client.api.client.get_workflow_logs",
        lambda *a, **k: {"logs": json.dumps(payload)},
    )
    out = Mock()
    monkeypatch.setattr(cli_utils, "output_user_friendly_logs", out)

    cli_utils.retrieve_workflow_logs(
        workflow="wf",
        access_token="tok",
        json_format=False,
        filters=True,
        steps=None,
        chosen_filters={"compute_backend": "k8s"},
        available_filters={"compute_backend": "compute_backend"},
        page=None,
        size=None,
    )
    assert out.called
    filtered_payload = out.call_args[0][0]
    assert list(filtered_payload["job_logs"].keys()) == ["1"]


def test_retrieve_workflow_logs_json_format_exits(monkeypatch):
    payload = {"workflow_logs": "W", "engine_specific": "", "job_logs": {}}
    monkeypatch.setattr(
        "reana_client.api.client.get_workflow_logs",
        lambda *a, **k: {"logs": json.dumps(payload)},
    )
    monkeypatch.setattr(cli_utils, "display_message", lambda *a, **k: None)

    with pytest.raises(SystemExit) as e:
        cli_utils.retrieve_workflow_logs(
            workflow="wf",
            access_token="tok",
            json_format=True,
            filters=False,
            steps=None,
            chosen_filters={},
            available_filters={},
        )
    assert e.value.code == 0


def test_follow_workflow_logs_exits_when_finished(monkeypatch):
    # Capture emitted messages
    msgs = []

    def fake_display_message(msg, msg_type=None):
        msgs.append((msg, msg_type))

    monkeypatch.setattr(cli_utils, "display_message", fake_display_message)
    monkeypatch.setattr(cli_utils.time, "sleep", lambda *a, **k: None)

    monkeypatch.setattr(
        "reana_client.api.client.get_workflow_logs",
        lambda *a, **k: {
            "live_logs_enabled": True,
            "logs": json.dumps({"workflow_logs": "line1\nline2\n", "job_logs": {}}),
        },
    )
    monkeypatch.setattr(
        "reana_client.api.client.get_workflow_status",
        lambda *a, **k: {"status": "finished"},
    )

    cli_utils.follow_workflow_logs(
        workflow="wf",
        access_token="tok",
        interval=0,  # triggers reset warning path
        steps=[],
    )

    # warning about interval reset + logs + completion info
    assert any(m[1] == "warning" for m in msgs)
    assert any("line1" in m[0] for m in msgs)
    assert any(m[1] == "info" and "has completed" in m[0] for m in msgs)


def test_follow_workflow_logs_live_logs_disabled(monkeypatch):
    msgs = []

    monkeypatch.setattr(
        cli_utils, "display_message", lambda msg, t=None: msgs.append((msg, t))
    )
    monkeypatch.setattr(
        "reana_client.api.client.get_workflow_logs",
        lambda *a, **k: {"live_logs_enabled": False, "logs": json.dumps({})},
    )
    # should return early
    cli_utils.follow_workflow_logs(
        "wf", "tok", interval=CLI_LOGS_FOLLOW_DEFAULT_INTERVAL, steps=[]
    )
    assert any(t == "error" and "Live logs are not enabled" in m for m, t in msgs)
