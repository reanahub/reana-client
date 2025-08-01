# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2025 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
"""REANA client login command using Device Code Flow (OAuth2)."""


import sys
import time
from pathlib import Path

import click
import requests
from reana_client.printer import display_message

# IdP configuration
DEVICE_AUTHORIZATION_ENDPOINT = "https://iam-escape.cloud.cnaf.infn.it/devicecode"
TOKEN_ENDPOINT = "https://iam-escape.cloud.cnaf.infn.it/token"
CLIENT_ID = "f671a136-8e92-45e5-83bd-05af1942e396"
SCOPE = "openid profile email"

TOKEN_STORE = Path.home() / ".reana" / "access_token.json"


@click.group()
def auth_group():
    pass


@auth_group.command("auth")
def auth():
    resp = requests.post(
        DEVICE_AUTHORIZATION_ENDPOINT,
        data={
            "client_id": CLIENT_ID,
            "scope": SCOPE,
        },
    )
    resp.raise_for_status()
    device = resp.json()

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

    click.echo("Waiting for you to authorize…")
    click.echo()

    expires_at = time.time() + device.get("expires_in", 600)
    interval = device.get("interval", 5)

    while time.time() < expires_at:
        token_resp = requests.post(
            TOKEN_ENDPOINT,
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device["device_code"],
                "client_id": CLIENT_ID,
            },
            headers={"Accept": "application/json"},
        )

        if token_resp.status_code == 200:
            token = token_resp.json()
            TOKEN_STORE.parent.mkdir(parents=True, exist_ok=True)
            TOKEN_STORE.write_text(token["access_token"])
            display_message("Login successful – token saved.", msg_type="success")
            return

        error = token_resp.json().get("error")
        if error == "authorization_pending":
            time.sleep(interval)
            continue
        if error == "slow_down":
            time.sleep(interval + 5)
            continue

        display_message(f"Authentication failed: {error}", msg_type="error")
        sys.exit(1)

    display_message("Authentication timed out.", msg_type="error")
    sys.exit(1)


def get_jwt_parameter():
    token_file = Path.home() / ".reana" / "access_token.json"
    try:
        return "Bearer " + token_file.read_text().strip()
    except FileNotFoundError:
        raise Exception(
            "Access token file not found. Please run `reana-client auth` first."
        )
