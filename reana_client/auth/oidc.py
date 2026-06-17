# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2026 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
"""OIDC login (loopback PKCE and device flow) and token refresh helpers."""

import base64
import hashlib
import json
import secrets
import time
import webbrowser
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Callable, Dict, Optional, Tuple
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

import requests

from reana_client.auth.storage import (
    CREDENTIAL_EPOCH_FIELD,
    clear_token_material,
    clear_token_material_if_matches,
    credential_store_lock,
    get_active_server,
    get_server_entry,
    normalize_server_url,
    release_refresh_lock,
    try_acquire_refresh_lock,
    upsert_server_entry,
    wait_for_refresh_lock,
)
from reana_client.config import tls_verify

DEFAULT_SCOPES = "openid profile email offline_access"
EXPIRY_LEEWAY_SECONDS = 60
DISCOVERY_PATH = "/api/.well-known/openid-configuration"
PKCE_CODE_CHALLENGE_METHOD = "S256"
REFRESH_LOCK_WAIT_SECONDS = 35
"""How long to wait for another process's in-flight refresh before giving up
and refreshing unlocked ourselves; slightly longer than the 30s network
timeout on the refresh request itself, so a legitimate in-flight refresh
almost always finishes (or fails) before this deadline."""

LOOPBACK_HOST = "127.0.0.1"
LOOPBACK_CALLBACK_PATH = "/callback"
LOOPBACK_TIMEOUT_SECONDS = 300

_CALLBACK_SUCCESS_HTML = (
    b"<html><body><h1>REANA login complete.</h1>"
    b"<p>You can close this tab and return to the terminal.</p></body></html>"
)
_CALLBACK_ERROR_HTML = (
    b"<html><body><h1>REANA login failed.</h1>"
    b"<p>Return to the terminal for details.</p></body></html>"
)


class AuthenticationError(Exception):
    """Authentication failure visible to CLI users."""


_OIDC_HTTPS_URL_FIELDS = (
    "issuer",
    "authorization_endpoint",
    "token_endpoint",
    "device_authorization_endpoint",
    "revocation_endpoint",
)
"""OIDC metadata fields that may receive or authorize credentials."""


def _validate_oidc_https_urls(metadata: Dict, required=()) -> None:
    """Reject missing or non-HTTPS OIDC metadata URLs.

    REANA Server validates and rewrites issuer metadata before relaying it, but
    the CLI is a separate credential-handling boundary.  Validate again here so
    a compromised or older server cannot redirect authorization codes, device
    codes, access tokens, or refresh tokens to a cleartext endpoint.
    """
    for field in _OIDC_HTTPS_URL_FIELDS:
        value = metadata.get(field)
        if not value:
            if field in required:
                raise AuthenticationError(
                    f"Authentication metadata is missing required field: {field}"
                )
            continue
        parsed = urlparse(value)
        if parsed.scheme.lower() != "https" or not parsed.netloc:
            raise AuthenticationError(
                f"Authentication metadata field '{field}' must be an HTTPS URL."
            )


def utcnow() -> datetime:
    """Return timezone-aware current UTC time."""
    return datetime.now(timezone.utc)


def parse_timestamp(value: Optional[str]) -> Optional[datetime]:
    """Parse ISO timestamp stored in credential file."""
    if not value:
        return None
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def format_timestamp(value: datetime) -> str:
    """Format timestamp for credential file."""
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _decode_jwt_exp(token: Optional[str]) -> Optional[datetime]:
    """Decode JWT exp claim without validating the token."""
    if not token or token.count(".") < 2:
        return None
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    try:
        claims = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
        exp = claims.get("exp")
        return datetime.fromtimestamp(exp, timezone.utc) if exp else None
    except Exception:
        return None


def _token_expires_at(token_response: Dict) -> Optional[str]:
    """Return access token expiry timestamp from token response."""
    expires_in = token_response.get("expires_in")
    if expires_in is not None:
        return format_timestamp(utcnow() + timedelta(seconds=int(expires_in)))
    jwt_exp = _decode_jwt_exp(token_response.get("access_token"))
    return format_timestamp(jwt_exp) if jwt_exp else None


def _refresh_token_expires_at(token_response: Dict) -> Optional[str]:
    """Return refresh token expiry timestamp if issuer exposes it."""
    refresh_expires_in = token_response.get("refresh_expires_in")
    if refresh_expires_in is None:
        return None
    return format_timestamp(utcnow() + timedelta(seconds=int(refresh_expires_in)))


def _reject_redirect(response: requests.Response, description: str) -> None:
    """Raise if the server tried to redirect this request.

    Every call site here uses ``allow_redirects=False`` and must call this
    immediately afterwards. ``requests`` follows redirects by default,
    including 307/308, which -- unlike 301/302/303 -- preserve the original
    method and body: a compromised or misconfigured issuer could otherwise
    3xx-redirect an HTTPS token/device/refresh/revocation POST to an
    attacker-controlled HTTP endpoint and have the client resend the
    authorization code, refresh token, or client credentials to it verbatim.
    """
    if response.is_redirect:
        location = response.headers.get("location", "<no Location header>")
        raise AuthenticationError(
            f"{description} attempted to redirect to {location!r}. "
            "Refusing to follow a redirect on an authentication request."
        )


def _response_json(response: requests.Response) -> Dict:
    """Return JSON response or raise a readable authentication error."""
    try:
        return response.json()
    except ValueError as exc:
        raise AuthenticationError(
            f"Authentication server returned a non-JSON response: {response.text}"
        ) from exc


def _base64url_encode(value: bytes) -> str:
    """Return unpadded base64url-encoded value."""
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def generate_pkce_pair() -> Dict[str, str]:
    """Generate PKCE verifier and S256 challenge."""
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = _base64url_encode(
        hashlib.sha256(code_verifier.encode("ascii")).digest()
    )
    return {
        "code_verifier": code_verifier,
        "code_challenge": code_challenge,
        "code_challenge_method": PKCE_CODE_CHALLENGE_METHOD,
    }


def discover(server_url: str) -> Dict:
    """Discover OIDC endpoints relayed by REANA server."""
    normalized_url = normalize_server_url(server_url)
    try:
        response = requests.get(
            urljoin(normalized_url + "/", DISCOVERY_PATH.lstrip("/")),
            timeout=30,
            allow_redirects=False,
            verify=tls_verify(),
        )
    except requests.RequestException as exc:
        raise AuthenticationError(
            f"Could not connect to the REANA server at {normalized_url}."
        ) from exc
    _reject_redirect(response, "Authentication metadata discovery")
    if not response.ok:
        raise AuthenticationError(
            "Could not discover authentication metadata from "
            f"{normalized_url}: HTTP {response.status_code}"
        )
    metadata = _response_json(response)
    required_fields = [
        "issuer",
        "authorization_endpoint",
        "token_endpoint",
        "reana_cli_client_id",
    ]
    missing_fields = [field for field in required_fields if not metadata.get(field)]
    if missing_fields:
        raise AuthenticationError(
            "Authentication metadata is missing required field(s): "
            + ", ".join(missing_fields)
        )
    _validate_oidc_https_urls(metadata, required=required_fields)
    return metadata


def _store_token_response(
    server_url: str, metadata: Dict, token_response: Dict, make_active: bool = True
) -> Dict:
    """Persist token response for a server.

    ``make_active`` is forwarded to :func:`upsert_server_entry`. It must stay
    ``True`` (the default) for user-initiated logins, but a background
    refresh write-back passes ``False`` so it can never undo a concurrent
    explicit ``login`` to a different server (see ``refresh_credentials``).
    """
    _validate_oidc_https_urls(metadata, required=("issuer", "token_endpoint"))
    access_token = token_response.get("access_token")
    if not access_token:
        raise AuthenticationError(
            "Authentication server did not return an access token."
        )
    entry = {
        "issuer": metadata["issuer"],
        "client_id": metadata["reana_cli_client_id"],
        "token_endpoint": metadata["token_endpoint"],
        "authorization_endpoint": metadata.get("authorization_endpoint"),
        "device_authorization_endpoint": metadata.get("device_authorization_endpoint"),
        "revocation_endpoint": metadata.get("revocation_endpoint"),
        "access_token": access_token,
        "access_token_expires_at": _token_expires_at(token_response),
        "refresh_token": token_response.get("refresh_token"),
        "refresh_token_expires_at": _refresh_token_expires_at(token_response),
    }
    return upsert_server_entry(server_url, entry, make_active=make_active)


def _revoke_discarded_tokens(metadata: Dict, token_response: Dict) -> None:
    """Best-effort revoke tokens from a refresh whose write-back was discarded.

    Used when a refresh's credential epoch no longer matches what it started
    with (a concurrent logout or another refresh raced it) -- the tokens
    this refresh just obtained are about to be thrown away rather than
    written to disk, so revoke them at the issuer too instead of leaving a
    live, un-revoked, never-persisted token pair.
    """
    revocation_endpoint = metadata.get("revocation_endpoint")
    refresh_token = token_response.get("refresh_token")
    if not revocation_endpoint or not refresh_token:
        return
    try:
        _validate_oidc_https_urls({"revocation_endpoint": revocation_endpoint})
        response = requests.post(
            revocation_endpoint,
            data={
                "client_id": metadata["reana_cli_client_id"],
                "token": refresh_token,
                "token_type_hint": "refresh_token",
            },
            timeout=30,
            allow_redirects=False,
            verify=tls_verify(),
        )
        _reject_redirect(response, "Token revocation")
    except (AuthenticationError, requests.RequestException):
        pass


def _build_authorization_url(
    metadata: Dict, scopes: str, pkce: Dict, state: str, redirect_uri: str
) -> str:
    """Build the OIDC authorization endpoint URL for the loopback flow."""
    params = {
        "response_type": "code",
        "client_id": metadata["reana_cli_client_id"],
        "redirect_uri": redirect_uri,
        "scope": scopes,
        "state": state,
        "code_challenge": pkce["code_challenge"],
        "code_challenge_method": pkce["code_challenge_method"],
    }
    return metadata["authorization_endpoint"] + "?" + urlencode(params)


class _CallbackHandler(BaseHTTPRequestHandler):
    """Capture the single authorization-code redirect on the loopback server."""

    def do_GET(self):  # noqa: N802
        """Record callback query parameters and acknowledge the browser.

        Only a request carrying ``code`` or ``error`` is treated as the
        issuer's authorization response and stops the wait loop. Any other
        local process reaching this ephemeral port during the login window
        (its port number is visible in the printed authorization URL) could
        otherwise send a bare request first and pre-empt the real browser
        redirect, forcing a misleading failure instead of a clean wait for
        the actual callback.
        """
        parsed = urlparse(self.path)
        if parsed.path != LOOPBACK_CALLBACK_PATH:
            self.send_response(404)
            self.end_headers()
            return
        query = {key: values[0] for key, values in parse_qs(parsed.query).items()}
        if "code" not in query and "error" not in query:
            self.send_response(400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(_CALLBACK_ERROR_HTML)
            return
        self.server.callback_query = query
        body = _CALLBACK_SUCCESS_HTML if "code" in query else _CALLBACK_ERROR_HTML
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        """Silence the default stderr request logging."""


def _start_callback_server() -> Tuple[HTTPServer, str]:
    """Start a loopback HTTP server and return it with its redirect URI."""
    httpd = HTTPServer((LOOPBACK_HOST, 0), _CallbackHandler)
    httpd.callback_query = None
    port = httpd.server_address[1]
    redirect_uri = f"http://{LOOPBACK_HOST}:{port}{LOOPBACK_CALLBACK_PATH}"
    return httpd, redirect_uri


def _wait_for_callback(httpd: HTTPServer, timeout: int) -> Optional[Dict]:
    """Serve requests until the authorization callback arrives or times out."""
    deadline = time.monotonic() + timeout
    httpd.callback_query = None
    while httpd.callback_query is None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        httpd.timeout = remaining
        httpd.handle_request()
    return httpd.callback_query


def _exchange_authorization_code(
    metadata: Dict, code: str, pkce: Dict, redirect_uri: str
) -> Dict:
    """Exchange an authorization code for tokens using the PKCE verifier."""
    try:
        response = requests.post(
            metadata["token_endpoint"],
            data={
                "grant_type": "authorization_code",
                "client_id": metadata["reana_cli_client_id"],
                "code": code,
                "redirect_uri": redirect_uri,
                "code_verifier": pkce["code_verifier"],
            },
            timeout=30,
            allow_redirects=False,
            verify=tls_verify(),
        )
    except requests.RequestException as exc:
        raise AuthenticationError(
            "Could not exchange the authorization code. Please try again."
        ) from exc
    _reject_redirect(response, "Authorization code exchange")
    payload = _response_json(response)
    if not response.ok:
        raise AuthenticationError(
            "Browser login failed: "
            f"{payload.get('error_description') or payload.get('error') or response.text}"
        )
    return payload


def login_with_loopback(
    server_url: str,
    display_url: Callable[[str], None],
    open_browser: Callable[[str], bool] = webbrowser.open,
    timeout: int = LOOPBACK_TIMEOUT_SECONDS,
) -> Dict:
    """Perform the loopback authorization-code + PKCE flow and store credentials."""
    normalized_url = normalize_server_url(server_url)
    metadata = discover(normalized_url)
    pkce = generate_pkce_pair()
    state = secrets.token_urlsafe(32)

    httpd, redirect_uri = _start_callback_server()
    try:
        authorization_url = _build_authorization_url(
            metadata, DEFAULT_SCOPES, pkce, state, redirect_uri
        )
        display_url(authorization_url)
        try:
            open_browser(authorization_url)
        except Exception:
            pass
        query = _wait_for_callback(httpd, timeout)
    finally:
        httpd.server_close()

    if query is None:
        raise AuthenticationError("Browser login timed out. Please run login again.")
    if query.get("error"):
        raise AuthenticationError(
            "Browser login failed: "
            f"{query.get('error_description') or query.get('error')}"
        )
    returned_state = query.get("state")
    if not returned_state or not secrets.compare_digest(returned_state, state):
        raise AuthenticationError(
            "Browser login failed: state parameter mismatch (possible CSRF)."
        )
    code = query.get("code")
    if not code:
        raise AuthenticationError(
            "Browser login failed: no authorization code was returned."
        )

    token_response = _exchange_authorization_code(metadata, code, pkce, redirect_uri)
    return _store_token_response(normalized_url, metadata, token_response)


def _start_device_authorization(metadata: Dict, pkce: Dict) -> Dict:
    """Start OIDC device authorization flow."""
    try:
        response = requests.post(
            metadata["device_authorization_endpoint"],
            data={
                "client_id": metadata["reana_cli_client_id"],
                "scope": DEFAULT_SCOPES,
                "code_challenge": pkce["code_challenge"],
                "code_challenge_method": pkce["code_challenge_method"],
            },
            timeout=30,
            allow_redirects=False,
            verify=tls_verify(),
        )
    except requests.RequestException as exc:
        raise AuthenticationError(
            "Could not start device login. Please try again."
        ) from exc
    _reject_redirect(response, "Device authorization")
    payload = _response_json(response)
    if response.ok:
        return payload
    raise AuthenticationError(
        "Could not start device login: "
        f"{payload.get('error_description') or payload.get('error') or response.text}"
    )


def login_with_device_flow(
    server_url: str,
    display_callback: Callable[[Dict], None],
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> Dict:
    """Perform OIDC device flow (headless fallback) and store credentials."""
    normalized_url = normalize_server_url(server_url)
    metadata = discover(normalized_url)
    if not metadata.get("device_authorization_endpoint"):
        raise AuthenticationError(
            "This REANA server does not advertise a device authorization endpoint."
        )
    pkce = generate_pkce_pair()
    device_response = _start_device_authorization(metadata, pkce)
    display_callback(device_response)

    interval = int(device_response.get("interval", 5))
    device_code = device_response["device_code"]
    try:
        deadline = monotonic() + int(device_response["expires_in"])
    except (KeyError, TypeError, ValueError) as exc:
        raise AuthenticationError(
            "Device login response did not contain a valid expiry."
        ) from exc
    while True:
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise AuthenticationError("Device login expired. Please run login again.")
        sleep(min(interval, remaining))
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise AuthenticationError("Device login expired. Please run login again.")
        try:
            response = requests.post(
                metadata["token_endpoint"],
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    "device_code": device_code,
                    "client_id": metadata["reana_cli_client_id"],
                    "code_verifier": pkce["code_verifier"],
                },
                timeout=max(0.1, min(30, remaining)),
                allow_redirects=False,
                verify=tls_verify(),
            )
        except requests.RequestException as exc:
            raise AuthenticationError(
                "Could not complete device login. Please try again."
            ) from exc
        _reject_redirect(response, "Device token polling")
        payload = _response_json(response)
        if response.ok:
            return _store_token_response(normalized_url, metadata, payload)

        error = payload.get("error")
        if error == "authorization_pending":
            continue
        if error == "slow_down":
            interval += 5
            continue
        if error == "expired_token":
            raise AuthenticationError("Device login expired. Please run login again.")
        if error == "access_denied":
            raise AuthenticationError("Device login was denied.")
        raise AuthenticationError(
            "Device login failed: "
            f"{payload.get('error_description') or error or response.text}"
        )


def _access_token_valid(server_entry: Dict) -> bool:
    """Return whether stored access token can be used now."""
    access_token = server_entry.get("access_token")
    expires_at = parse_timestamp(server_entry.get("access_token_expires_at"))
    if not access_token:
        return False
    if not expires_at:
        return True
    return expires_at - timedelta(seconds=EXPIRY_LEEWAY_SECONDS) > utcnow()


def refresh_credentials(server_url: str, server_entry: Optional[Dict] = None) -> Dict:
    """Refresh credentials for a server.

    The credential-store lock protects only the on-disk read and the final
    write, not the token-endpoint request in between: holding a
    cross-process file lock for the duration of a blocking network call
    would serialise every other ``reana-client`` invocation on the machine
    behind a single slow or unresponsive issuer (the same bug class fixed
    server-side for OIDC discovery). ``upsert_server_entry`` re-reads the
    on-disk entry at write time under its own lock, so a concurrent
    refresh from another process is merged rather than silently lost.

    Three safeguards close the gaps that design otherwise leaves open:

    - A separate, refresh-scoped advisory lock, keyed to this specific
      server (distinct from the general credential-store lock, and from any
      other server's refresh lock) serialises the network call itself
      across processes, so concurrent refreshes of the *same* server don't
      all pay a redundant round-trip against the same refresh token -- a
      process that loses the race waits for the winner and reuses its
      result instead -- while a refresh of a *different* server is never
      blocked waiting on it.
    - The credential epoch captured before the network call is re-checked
      against the on-disk epoch before writing back: if a concurrent
      ``logout()`` (or another login/refresh) ran while this request was
      in flight, the epoch will have moved and the freshly obtained tokens
      are revoked and discarded instead of resurrecting a session the user
      already logged out of.
    - The write-back passes ``make_active=False``, so a background refresh
      completing after the user has already run ``login`` to switch to a
      different server can never flip ``active_server`` back to this one.
    """
    normalized_url = normalize_server_url(server_url)
    with credential_store_lock():
        # Always use the newest on-disk refresh token after acquiring the lock.
        # Another CLI process may have rotated it while this process waited.
        server_entry = get_server_entry(normalized_url) or server_entry or {}
        refresh_token = server_entry.get("refresh_token")
        if not refresh_token:
            raise AuthenticationError("Please run `reana-client login`.")
        _validate_oidc_https_urls(server_entry, required=("issuer", "token_endpoint"))
        started_epoch = int(server_entry.get(CREDENTIAL_EPOCH_FIELD, 0))

    refresh_lock_file = try_acquire_refresh_lock(normalized_url)
    if refresh_lock_file is None:
        # Another process is already refreshing this server's tokens. Wait
        # for it to finish and reuse its result instead of racing it with
        # our own network call. This lock is scoped to `normalized_url`, so
        # a concurrent refresh of a *different* server never waits here.
        if wait_for_refresh_lock(normalized_url, timeout=REFRESH_LOCK_WAIT_SECONDS):
            with credential_store_lock():
                waited_entry = get_server_entry(normalized_url)
            if _access_token_valid(waited_entry):
                return waited_entry
        # Either the wait timed out, or the other process's refresh didn't
        # leave a usable access token (e.g. it failed) -- fall back to an
        # unlocked refresh of our own, same as the pre-serialization
        # behavior; correctness still doesn't depend on this lock.

    try:
        try:
            response = requests.post(
                server_entry["token_endpoint"],
                data={
                    "grant_type": "refresh_token",
                    "client_id": server_entry["client_id"],
                    "refresh_token": refresh_token,
                },
                timeout=30,
                allow_redirects=False,
                verify=tls_verify(),
            )
        except requests.RequestException as exc:
            raise AuthenticationError(
                "Could not refresh authentication credentials. Please try again."
            ) from exc
        _reject_redirect(response, "Token refresh")
        payload = _response_json(response)
        if not response.ok:
            if payload.get("error") == "invalid_grant":
                # A concurrent process may have already rotated this exact
                # refresh token and stored a new, valid one while this request
                # was in flight -- only clear if the stored token is still the
                # one that was just rejected, so a losing process's failure
                # here can never destroy a winning process's fresh credentials.
                if clear_token_material_if_matches(normalized_url, refresh_token):
                    raise AuthenticationError("Please run `reana-client login`.")
                raise AuthenticationError(
                    "Credentials were changed by another process (login, "
                    "logout, or refresh). Please retry, or run "
                    "`reana-client login` if you're not signed in."
                )
            message = payload.get("error_description") or payload.get("error")
            raise AuthenticationError(
                "Could not refresh authentication credentials: "
                f"{message or f'HTTP {response.status_code}'}"
            )

        metadata = {
            "issuer": server_entry["issuer"],
            "reana_cli_client_id": server_entry["client_id"],
            "token_endpoint": server_entry["token_endpoint"],
            "authorization_endpoint": server_entry.get("authorization_endpoint"),
            "device_authorization_endpoint": server_entry.get(
                "device_authorization_endpoint"
            ),
            "revocation_endpoint": server_entry.get("revocation_endpoint"),
        }
        if "refresh_token" not in payload:
            payload["refresh_token"] = refresh_token

        with credential_store_lock():
            current_entry = get_server_entry(normalized_url)
            if int(current_entry.get(CREDENTIAL_EPOCH_FIELD, 0)) != started_epoch:
                _revoke_discarded_tokens(metadata, payload)
                raise AuthenticationError("Please run `reana-client login`.")
            # A background refresh write-back must never flip the active
            # server: an explicit `login` to a different server that
            # completed while this refresh's network call was in flight
            # must win, not be silently undone here.
            return _store_token_response(
                normalized_url, metadata, payload, make_active=False
            )
    finally:
        if refresh_lock_file is not None:
            release_refresh_lock(refresh_lock_file)


def get_access_token() -> str:
    """Return valid access token for the active server, refreshing as needed."""
    with credential_store_lock():
        server_url = get_active_server()
        if not server_url:
            raise AuthenticationError(
                "REANA client is not connected to any REANA cluster."
            )
        # Re-read after acquiring the lock: a waiting process can reuse the
        # access token produced by the refresh that just completed.
        server_entry = get_server_entry(server_url)
        if _access_token_valid(server_entry):
            return server_entry["access_token"]
    # Refresh outside the lock: refresh_credentials() does its own locking
    # around the on-disk read/write and must not hold it across the blocking
    # token-endpoint request, so it cannot be called from inside this lock
    # either -- doing so would keep the file lock held for the whole refresh
    # regardless, defeating the point.
    return refresh_credentials(server_url, server_entry)["access_token"]


def logout(server_url: Optional[str] = None) -> Optional[str]:
    """Logout from active server and return remote revocation warning if any.

    Holds the credential-store lock across the whole operation, including
    the revocation request: unlike a refresh (a hot path invoked on every
    near-expiry request, where holding the lock across the network call
    would serialise every concurrent CLI invocation on the machine), logout
    is a rare, one-shot, user-initiated action, so there's no throughput
    cost to keeping this atomic. Without it, a concurrent
    ``refresh_credentials()`` could rotate the refresh token between the
    read here and the final clear: this would revoke the now-superseded
    token (a no-op at the issuer) while wiping the newly-rotated one from
    local disk, leaving that new token live and un-revoked at the issuer
    even though the CLI reports a successful logout.
    """
    with credential_store_lock():
        server_url = server_url or get_active_server()
        if not server_url:
            raise AuthenticationError(
                "REANA client is not connected to any REANA cluster."
            )
        server_entry = get_server_entry(server_url)
        refresh_token = server_entry.get("refresh_token")
        revocation_endpoint = server_entry.get("revocation_endpoint")
        warning = None
        if refresh_token and revocation_endpoint:
            try:
                _validate_oidc_https_urls({"revocation_endpoint": revocation_endpoint})
                response = requests.post(
                    revocation_endpoint,
                    data={
                        "client_id": server_entry["client_id"],
                        "token": refresh_token,
                        "token_type_hint": "refresh_token",
                    },
                    timeout=30,
                    allow_redirects=False,
                    verify=tls_verify(),
                )
                _reject_redirect(response, "Token revocation")
                if not response.ok:
                    warning = (
                        "Remote token revocation failed with "
                        f"HTTP {response.status_code}."
                    )
            except (AuthenticationError, requests.RequestException) as exc:
                warning = f"Remote token revocation failed: {exc}"
        clear_token_material(server_url)
        return warning
