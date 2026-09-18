# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2026 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
"""Manage saved server records independently of authentication."""

import logging
import os
from contextlib import contextmanager

from reana_client.auth import storage
from reana_client.auth.oidc import AuthenticationError, revoke_credentials
from reana_client.config import (
    CA_CERTS_ENV,
    connection_scope,
    resolve_tls_verify,
    same_https_origin,
)


def _require_server(config, server):
    """Reject unknown destinations without changing the selection."""
    if server not in config["servers"]:
        raise ValueError(
            f"No saved REANA server {server}. "
            f"Run `reana-client login --server {server}` or `reana-client server-add {server}`."
        )


def add_server(server_url, verify=None):
    """Save a new connection without selecting it or obtaining credentials."""
    server = storage.normalize_server_url(server_url)
    with storage.credential_store_lock():
        config = storage.load_config()
        if server in config["servers"]:
            raise ValueError(
                f"REANA server {server} is already saved. "
                "Use `login --server` to update its TLS settings."
            )
        resolve_tls_verify({}, verify, server)
        config["servers"][server] = (
            {"tls": {"verify": verify}} if verify is not None else {}
        )
        storage.save_config(config)
    return server


def list_servers():
    """Return only public connection fields from one store snapshot."""
    with storage.credential_store_lock():
        config = storage.load_config()
        return [
            {
                "server": server,
                "active": server == config["active_server"],
                "tls_verification": _saved_tls_status(
                    config["servers"][server], server
                ),
            }
            for server in sorted(config["servers"])
        ]


def _saved_tls_status(entry, server):
    """Keep malformed TLS records visible for inspection and removal."""
    try:
        return (
            "disabled"
            if resolve_tls_verify(entry, server_url=server) is False
            else "enabled"
        )
    except (ValueError, AttributeError):
        return "invalid"


def use_server(server_url):
    """Select a saved server without touching its credentials or settings."""
    server = storage.normalize_server_url(server_url)
    with storage.credential_store_lock():
        config = storage.load_config()
        _require_server(config, server)
        config["active_server"] = server
        storage.save_config(config)
    return server


@contextmanager
def _removal_lock(server):
    """Wait for token rotation before taking the store lock for removal."""
    lock = storage._open_refresh_lock_file(server)
    try:
        storage._acquire_file_lock(lock)
        try:
            yield
        finally:
            storage._release_file_lock(lock)
    finally:
        lock.close()


def remove_server(server_url, local_only=False):
    """Revoke then forget a server, retaining the record on revocation failure."""
    server = storage.normalize_server_url(server_url)
    with _removal_lock(server), storage.credential_store_lock():
        config = storage.load_config()
        _require_server(config, server)
        entry = config["servers"][server]
        if not local_only and entry.get("refresh_token"):
            if not entry.get("revocation_endpoint") or not entry.get("client_id"):
                raise AuthenticationError(
                    "Cannot revoke saved credentials: revocation metadata is missing. "
                    "Use --local-only to remove the record without revocation."
                )
            if same_https_origin(server, entry["revocation_endpoint"]):
                verify = resolve_tls_verify(entry, server_url=server)
            else:
                verify = os.getenv(CA_CERTS_ENV) or True
            if verify is False:
                logging.warning(
                    "TLS certificate verification is disabled for %s.", server
                )
            # Bind diagnostics to the argument, using the policy already resolved
            # under the lock. Revocation must not reopen the credential store.
            with connection_scope(server, source="server-remove argument"):
                warning = revoke_credentials(server, entry, verify=verify)
            if warning:
                raise AuthenticationError(
                    "Could not revoke saved credentials; the server was not removed.\n"
                    f"{warning}\n"
                    "Resolve the reported problem before retrying, or use "
                    "--local-only to remove the record without revocation."
                )
        del config["servers"][server]
        if config["active_server"] == server:
            config["active_server"] = None
        storage.save_config(config)
    return server, bool(local_only and entry.get("refresh_token"))
