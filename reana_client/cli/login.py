# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2025 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
"""REANA client login command using Device Code Flow (OAuth2)."""
import os
import sys
import time

import click
import requests

from reana_client.cli.utils import check_connection
from reana_client.config_utils import set_server_config
from reana_client.api.client import get_openid_configuration


@click.group(help="REANA login commands")
def login_group():
    """Login command group for REANA authentication."""
    pass


@login_group.command("login")
@check_connection
def login():
    r"""
    Login to REANA using Device Code Flow (OAuth2).

    The ``login`` command authenticates users with REANA using the OAuth2 Device Code Flow.
    This authentication method allows users to authenticate using a web browser on any device,
    making it suitable for headless environments and remote access scenarios.

    The command will:
    1. Request a device code from the REANA server
    2. Display a verification URL and user code
    3. Wait for the user to complete authentication in their browser
    4. Store the access token for future use

    The REANA_SERVER_URL environment variable must be set before running this command.
    """
    try:
        openid_configuration = get_openid_configuration()
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    try:
        resp = requests.post(
            openid_configuration["device_authorization_endpoint"],
            data={
                "client_id": openid_configuration["reana_client_id"],
                "scope": "openid profile email",
            },
        )
        resp.raise_for_status()
        device = resp.json()
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    uri_complete = device.get("verification_uri_complete")
    uri_base = device.get("verification_uri") or uri_complete

    click.echo()

    # ---------- Option A: link + code ----------
    click.echo("1) Go to:")
    click.echo(uri_base)
    click.echo("2) Enter this code:")
    click.echo(device["user_code"])
    click.echo()

    # ---------- Option B: direct, one-click URL ----------
    if uri_complete and uri_complete != uri_base:
        click.echo("Or open this link directly:")
        click.echo(uri_complete)
        click.echo()

    click.echo("Waiting for authentication...")
    while True:
        token_resp = requests.post(
            openid_configuration["token_endpoint"],
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device["device_code"],
                "client_id": openid_configuration["reana_client_id"],
            },
            headers={"Accept": "application/json"},
        )

        if token_resp.status_code == 200:
            token_data = token_resp.json()
            access_token = token_data["access_token"]
            server_url = os.environ.get("REANA_SERVER_URL")

            set_server_config(access_token)

            click.echo("Successfully authenticated!")
            click.echo(f"Access token has been stored for {server_url}")
            break

        if token_resp.status_code == 400:
            error = token_resp.json().get("error")
            if error == "authorization_pending":
                time.sleep(device.get("interval", 5))
                continue
            elif error == "expired_token":
                click.echo("Authentication timed out. Please try again.")
                sys.exit(1)
            else:
                click.echo(f"Authentication failed: {error}")
                sys.exit(1)
        else:
            click.echo("Authentication failed. Please try again.")
            sys.exit(1)
