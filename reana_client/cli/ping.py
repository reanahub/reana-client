# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2017, 2018, 2019, 2020, 2021, 2022, 2026 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
"""REANA client configuration commands."""

import json
import logging
import sys
import traceback

import click
import requests
from reana_client.auth.diagnostics import connection_error
from reana_client.auth.oidc import (
    AuthenticationError,
    login_with_device_flow,
    login_with_loopback,
    logout as oidc_logout,
)
from reana_client.auth.storage import CredentialStoreError
from reana_client.auth.storage import get_active_server, normalize_server_url
from reana_client.cli.utils import add_access_token_options, check_connection
from reana_client.config import JSON, NO_SERVER, connection_scope, tls_status
from reana_client.printer import display_message
from reana_client.utils import build_cpu_quota_period_info
from reana_client.version import __version__


@click.group(help="Configuration commands")
def configuration_group():
    """Configuration commands."""
    pass


@configuration_group.command("login")
@click.option(
    "--server-url",
    help="REANA server URL to authenticate against.",
)
@click.option("--server", help="REANA server URL (alias for --server-url).")
@click.option(
    "--tls-verify", is_flag=True, help="Verify and save the server certificate policy."
)
@click.option(
    "--no-tls-verify",
    is_flag=True,
    help="Disable certificate verification for this server and save the choice.",
)
@click.option(
    "--headless",
    is_flag=True,
    default=False,
    help="Use device login instead of opening a local browser. "
    "Use this on machines without a browser (e.g. over SSH).",
)
@click.pass_context
def login(ctx, server_url, server, headless, tls_verify, no_tls_verify):  # noqa: D301
    """Authenticate against REANA server using OIDC.

    By default the browser-based loopback flow (authorization code with PKCE)
    is used. On headless machines pass ``--headless`` to use the device flow.

    TLS certificate verification is enabled by default. An explicit TLS flag
    applies during login and is saved only after success. Later logins inherit
    the saved setting. REANA_SERVER_CA_CERTS supplies a trusted CA bundle and
    takes precedence. Identity providers on other HTTPS origins stay verified.
    """
    from reana_client.config import tls_verify as resolve_tls

    selected = None
    source = "login option" if server or server_url else "saved login"
    try:
        if (
            server
            and server_url
            and normalize_server_url(server) != normalize_server_url(server_url)
        ):
            raise ValueError("--server and --server-url specify different servers.")
        if tls_verify and no_tls_verify:
            raise ValueError(
                "--tls-verify and --no-tls-verify cannot be used together."
            )
        selected = server or server_url or get_active_server()
        if not selected:
            raise ValueError(NO_SERVER)
        selected = normalize_server_url(selected)
        choice = True if tls_verify else False if no_tls_verify else None
        with connection_scope(selected, choice, source):
            resolve_tls(selected, warn=False)
            if headless:
                _device_login(selected)
            else:
                _browser_login(selected)
            display_message(
                f"Logged in to {selected}\nTLS verification: {tls_status(selected)}"
            )
    except (AuthenticationError, CredentialStoreError, ValueError) as e:
        message = str(e)
        if isinstance(e, AuthenticationError) and selected and selected not in message:
            message = f"REANA server: {selected} (from {source})\n{message}"
        display_message(message, msg_type="error")
        ctx.exit(1)


def _browser_login(server_url):
    """Run the loopback authorization-code + PKCE login flow."""

    def display_url(authorization_url):
        display_message(
            "Opening your browser to authenticate. If it does not open "
            f"automatically, visit:\n{authorization_url}"
        )

    login_with_loopback(server_url, display_url)


def _device_login(server_url):
    """Run the OIDC device login flow."""

    def display_device_prompt(device_response):
        verification_uri_complete = device_response.get("verification_uri_complete")
        if verification_uri_complete:
            display_message(
                "Open the following URL to authenticate:\n"
                f"{verification_uri_complete}"
            )
        else:
            display_message(
                "Open the following URL to authenticate:\n"
                f"{device_response.get('verification_uri')}\n"
                f"Code: {device_response.get('user_code')}"
            )

    login_with_device_flow(server_url, display_device_prompt)


@configuration_group.command("logout")
@click.pass_context
def logout(ctx):  # noqa: D301
    """Logout from the active REANA server."""
    try:
        server_url = get_active_server()
        warning = oidc_logout(server_url)
        if warning:
            display_message(warning, msg_type="warning")
        display_message(f"Logged out from {server_url}")
    except (AuthenticationError, CredentialStoreError, ValueError) as e:
        display_message(str(e), msg_type="error")
        ctx.exit(1)


@configuration_group.command("ping")
@click.pass_context
@add_access_token_options
@check_connection
def ping(ctx, access_token):  # noqa: D301
    """Check connection to REANA server.

    The ``ping`` command allows to test connection to REANA server.

    Examples:\n
    \t $ reana-client ping
    """
    try:
        from reana_client.api.client import ping as rs_ping
        from reana_client.utils import get_api_url

        logging.info("Connecting to {0}".format(get_api_url()))
        response = rs_ping(access_token)
        error = response.get("error")
        msg_color = "red" if error else "green"
        click.secho(
            "REANA server: {0}\n"
            "REANA server version: {1}\n"
            "REANA client version: {2}\n"
            "Authenticated as: {3} <{4}>\n"
            "Status: {5}".format(
                get_api_url(),
                response.get("reana_server_version", ""),
                __version__,
                response.get("full_name", ""),
                response.get("email"),
                response.get("status"),
            ),
            fg=msg_color,
        )
        click.echo(f"TLS verification: {tls_status()}")
        logging.debug("Server response:\n{}".format(response))
        if error:
            sys.exit(1)
    except Exception as e:
        from reana_client.config import server_description

        server = get_api_url()
        if isinstance(e, requests.RequestException):
            message = connection_error(server, server, e)
        else:
            message = f"REANA server: {server_description(server)}\nCould not complete ping: {e}"
        display_message(message, msg_type="error")
        ctx.exit(1)


@configuration_group.command("version")
@click.pass_context
def version(ctx):  # noqa: D301
    """Show version.

    The ``version`` command shows REANA client version.

    Examples:\n
    \t $ reana-client version
    """
    display_message(__version__)


@configuration_group.command("info")
@click.option(
    "--json",
    "output_format",
    flag_value="json",
    default=None,
    help="Get output in JSON format.",
)
@click.pass_context
@add_access_token_options
@check_connection
def info(ctx, access_token: str, output_format: str):  # noqa: D301
    """List cluster general information.

    The ``info`` command lists general information about the cluster.

    Lists all the available workspaces. It also returns the default workspace
    defined by the admin.

    Examples:\n
    \t $ reana-client info
    """
    try:
        from reana_client.api.client import get_user_quota, info

        response = info(access_token)
        try:
            response.update(build_cpu_quota_period_info(get_user_quota(access_token)))
        except (KeyError, ValueError) as e:
            logging.debug(
                "Could not enrich cluster info with quota period details: %s", str(e)
            )
        if output_format == JSON:
            display_message(json.dumps(response))
        else:
            for item in response.values():
                if not item:
                    continue
                value = item.get("value")
                value = ", ".join(value) if isinstance(value, list) else value
                display_message(f"{item.get('title')}: {value}")

    except requests.RequestException as e:
        from reana_client.utils import get_api_url

        server = get_api_url()
        display_message(connection_error(server, server, e), msg_type="error")
        ctx.exit(1)
    except Exception as e:
        logging.debug(traceback.format_exc())
        logging.debug(str(e))
        display_message("Could not list cluster info:\n{0}".format(e), msg_type="error")
        ctx.exit(1)


@click.group(help="Server connection management commands")
def server_connection_group():
    """Server connection management commands."""
    pass


@server_connection_group.command("server-add")
@click.argument("url")
@click.option(
    "--tls-verify", is_flag=True, help="Save certificate verification as enabled."
)
@click.option(
    "--no-tls-verify", is_flag=True, help="Save certificate verification as disabled."
)
@click.pass_context
def server_add(ctx, url, tls_verify, no_tls_verify):
    """Save a server without authenticating or selecting it.

    Verification is enabled by default. Existing records are not overwritten;
    use login --server URL to authenticate and update their TLS settings.
    """
    from reana_client.auth.servers import add_server

    try:
        if tls_verify and no_tls_verify:
            raise ValueError(
                "--tls-verify and --no-tls-verify cannot be used together."
            )
        choice = True if tls_verify else False if no_tls_verify else None
        server = add_server(url, choice)
        display_message(f"Saved REANA server: {server} (not selected)")
    except (CredentialStoreError, ValueError, OSError) as error:
        display_message(str(error), msg_type="error")
        ctx.exit(1)


@server_connection_group.command("server-list")
@click.pass_context
def server_list(ctx):
    """List saved server connections.

    Show the current selection and effective TLS verification. This command
    does not contact servers or refresh credentials.
    """
    from reana_client.auth.servers import list_servers

    try:
        servers = list_servers()
        if not servers:
            display_message("No saved REANA servers.")
        for entry in servers:
            marker = "*" if entry["active"] else " "
            display_message(
                f"{marker} {entry['server']}  TLS verification: {entry['tls_verification']}"
            )
    except (CredentialStoreError, ValueError, OSError) as error:
        display_message(str(error), msg_type="error")
        ctx.exit(1)


@server_connection_group.command("server-use")
@click.argument("url")
@click.pass_context
def server_use(ctx, url):
    """Select a saved server without authenticating.

    Credentials and TLS settings are retained. The next command refreshes
    credentials or asks for login when necessary.
    """
    from reana_client.auth.servers import use_server

    try:
        server = use_server(url)
        display_message(f"Selected REANA server: {server}")
    except (CredentialStoreError, ValueError, OSError) as error:
        display_message(str(error), msg_type="error")
        ctx.exit(1)


@server_connection_group.command("server-remove")
@click.argument("url")
@click.option(
    "--local-only",
    is_flag=True,
    help="Remove locally without revoking credentials at the identity provider.",
)
@click.pass_context
def server_remove(ctx, url, local_only):
    """Revoke credentials and remove a saved server.

    Revocation failure preserves the record. Use --local-only to forget an
    unreachable server without revoking its tokens. Removing the selected
    server leaves no selection; no other server is selected automatically.
    """
    from reana_client.auth.servers import remove_server

    try:
        server, unrevoked = remove_server(url, local_only)
        if unrevoked:
            click.echo("[WARNING] Remote credentials were not revoked.", err=True)
        display_message(f"Removed saved REANA server: {server}")
    except (AuthenticationError, CredentialStoreError, ValueError, OSError) as error:
        display_message(str(error), msg_type="error")
        ctx.exit(1)
