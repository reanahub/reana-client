# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2026 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
"""Safe connection diagnostics shared by discovery, login and refresh."""

import logging
import os
import socket
import ssl

import requests

from reana_client.config import CA_CERTS_ENV, same_https_origin, server_description


def connection_error(server_url, endpoint, error):
    """Explain a transport failure without exposing request bodies or URL queries."""
    pending, causes, seen = [error], [], set()
    while pending:
        cause = pending.pop()
        if not isinstance(cause, BaseException) or id(cause) in seen:
            continue
        seen.add(id(cause))
        causes.append(cause)
        pending.extend(
            [cause.__cause__, cause.__context__, getattr(cause, "reason", None)]
        )
        pending.extend(cause.args)
    # Request exception strings can include credentials, queries and bodies.
    # Retain the original exception through chaining, but log only safe details.
    verification = next(
        (item for item in causes if isinstance(item, ssl.SSLCertVerificationError)),
        None,
    )
    code = getattr(verification, "verify_code", None)
    logging.debug(
        "Connection failure types: %s; certificate verification code: %s",
        ", ".join(type(item).__name__ for item in causes),
        code,
    )
    reason = (
        "The network request failed. Check the server address and network connection."
    )
    if any(
        isinstance(item, (requests.exceptions.SSLError, ssl.SSLError))
        for item in causes
    ):
        if code == 10:
            reason = (
                "The TLS certificate has expired. Ask the administrator to renew it."
            )
        elif code == 9:
            reason = "The TLS certificate is not yet valid. Check the clock and contact the administrator."
        elif code in (62, 64):
            reason = "The TLS certificate does not match the hostname. Check the server URL and contact the administrator."
        elif code in (18, 19, 20, 21):
            detail = " (self-signed certificate)" if code in (18, 19) else ""
            reason = f"The TLS certificate is not trusted{detail}. "
            if os.getenv(CA_CERTS_ENV):
                reason += "The CA bundle in REANA_SERVER_CA_CERTS does not trust this certificate."
            else:
                reason += "Ask the administrator for a CA bundle and set REANA_SERVER_CA_CERTS."
                if same_https_origin(server_url, endpoint):
                    reason += f" For a trusted development server, run `reana-client login --server {server_url} --no-tls-verify` to disable verification."
                else:
                    reason += " The REANA server's TLS bypass does not apply to this identity provider."
        else:
            reason = "TLS negotiation or certificate verification failed. Check certificate trust, validity and hostname."
    elif any(
        isinstance(item, (requests.exceptions.Timeout, TimeoutError)) for item in causes
    ):
        reason = "The connection timed out. Check connectivity and try again."
    elif any(isinstance(item, socket.gaierror) for item in causes):
        reason = "The hostname could not be resolved. Check the server URL and DNS."
    elif any(isinstance(item, ConnectionRefusedError) for item in causes):
        reason = "The connection was refused. Check that the server is running and reachable."
    return f"Could not connect to {server_description(server_url)}: {reason}"
