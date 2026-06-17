# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2026 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
"""File-backed credential storage for REANA client."""

import hashlib
import json
import logging
import os
import tempfile
import threading
import time
from contextlib import contextmanager
from typing import Dict, Optional
from urllib.parse import urlparse, urlunparse

try:  # POSIX advisory file locking; ``fcntl`` is unavailable on Windows.
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX platform (e.g. Windows).
    fcntl = None
    try:
        import msvcrt
    except ImportError:  # pragma: no cover - neither POSIX nor Windows.
        msvcrt = None
else:
    msvcrt = None

DEFAULT_CONFIG_PATH = os.path.expanduser("~/.config/reana/reana-client.json")
TOKEN_FIELDS = {
    "access_token",
    "access_token_expires_at",
    "refresh_token",
    "refresh_token_expires_at",
}
CREDENTIAL_EPOCH_FIELD = "credential_epoch"
"""Monotonic per-server counter bumped by every login, refresh, and logout.

A refresh that started before a concurrent logout can complete afterwards --
its network round-trip is unlocked by design (see ``refresh_credentials``'s
docstring in ``oidc.py``). Comparing the epoch captured before the refresh
started against the epoch on disk when it's ready to write lets the caller
detect that intervening logout (or login, or another refresh) and discard
the now-stale result instead of silently resurrecting cleared credentials.
"""
_lock_state = threading.local()

logger = logging.getLogger(__name__)

CREDENTIAL_LOCK_TIMEOUT_SECONDS = 30
"""How long :func:`_acquire_file_lock` polls for the credential-store lock
before giving up. A wedged lock holder must eventually produce a loud,
user-facing failure instead of hanging every credential operation forever."""

CREDENTIAL_LOCK_POLL_INTERVAL_SECONDS = 0.1


def _acquire_file_lock(
    lock_file, timeout: float = CREDENTIAL_LOCK_TIMEOUT_SECONDS
) -> None:
    """Take an exclusive advisory lock across processes, bounded by a timeout.

    Polls the same non-blocking primitive used by the refresh lock
    (:func:`_try_acquire_file_lock_nb`) on both POSIX and Windows instead of:

    - POSIX: blocking forever on ``fcntl.flock(LOCK_EX)``, which would wedge
      every credential-store operation behind a stuck holder with no
      user-facing message.
    - Windows: silently swallowing the ``OSError`` raised by a contended
      ``msvcrt.locking`` and proceeding as if the lock had been taken,
      giving Windows no real mutual exclusion at all when contended.

    Raises :class:`TimeoutError` if the lock is still held after ``timeout``
    seconds, on both platforms. When neither locking primitive is available
    on this platform, this is a no-op (as before): the in-process reentrancy
    guard in :func:`credential_store_lock` and atomic file replacement in
    :func:`save_config` are the only guarantees left.
    """
    if fcntl is None and msvcrt is None:  # pragma: no cover - exotic platform.
        return
    deadline = time.monotonic() + timeout
    warned = False
    while not _try_acquire_file_lock_nb(lock_file):
        if time.monotonic() >= deadline:
            raise TimeoutError(
                "Timed out after {:.0f}s waiting for the REANA client "
                "credential lock. Another reana-client process may be stuck "
                "holding it.".format(timeout)
            )
        if not warned:
            logger.warning("Waiting for credential lock...")
            warned = True
        time.sleep(CREDENTIAL_LOCK_POLL_INTERVAL_SECONDS)


def _release_file_lock(lock_file):
    """Release a lock taken by :func:`_acquire_file_lock`."""
    if fcntl is not None:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    elif msvcrt is not None:  # pragma: no cover - exercised only on Windows.
        lock_file.seek(0)
        try:
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass


def _try_acquire_file_lock_nb(lock_file) -> bool:
    """Attempt a non-blocking exclusive lock; return whether it was taken."""
    if fcntl is not None:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False
    elif msvcrt is not None:  # pragma: no cover - exercised only on Windows.
        lock_file.seek(0)
        try:
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False
    # Neither locking primitive is available: pessimistically report
    # "already held" so callers fall back to their own refresh rather than
    # risk two writers overlapping with no mutual exclusion at all.
    return False


def _refresh_lock_path(server_url: str) -> str:
    """Return the path of the advisory lock scoped to refresh attempts for a server.

    Includes a hash of the normalized server URL so that refreshing one
    server's tokens never serialises a concurrent command against a
    completely unrelated server, even though both servers' credentials live
    in the same underlying config file.
    """
    normalized_url = normalize_server_url(server_url)
    server_hash = hashlib.sha256(normalized_url.encode("utf-8")).hexdigest()[:16]
    return "{}.refresh.{}.lock".format(os.path.abspath(get_config_path()), server_hash)


def _open_refresh_lock_file(server_url: str):
    lock_path = _refresh_lock_path(server_url)
    config_dir = os.path.dirname(lock_path) or "."
    os.makedirs(config_dir, mode=0o700, exist_ok=True)
    lock_file = open(lock_path, "a+", encoding="utf-8")
    os.chmod(lock_path, 0o600)
    return lock_file


def try_acquire_refresh_lock(server_url: str):
    """Attempt to become the sole in-flight refresher for ``server_url``.

    This lock is scoped to refresh network attempts against one specific
    server only -- it is separate from :func:`credential_store_lock`, so
    unrelated login/logout/ping invocations (against this server or any
    other) are never blocked behind a slow issuer's refresh response, and a
    refresh of one server never blocks a concurrent refresh of a different
    server either.

    :returns: an open lock-file handle (pass to :func:`release_refresh_lock`
        when the refresh completes) if this process should perform the
        token-endpoint request itself, or ``None`` if another process
        already holds it.
    """
    lock_file = _open_refresh_lock_file(server_url)
    if _try_acquire_file_lock_nb(lock_file):
        return lock_file
    lock_file.close()
    return None


def release_refresh_lock(lock_file) -> None:
    """Release a lock obtained from :func:`try_acquire_refresh_lock`."""
    _release_file_lock(lock_file)
    lock_file.close()


def wait_for_refresh_lock(server_url: str, timeout: float) -> bool:
    """Block until another process's in-flight refresh of ``server_url`` releases the lock.

    :returns: ``True`` if the lock became acquirable within ``timeout`` (the
        other refresh finished -- callers should re-read on-disk credentials
        instead of performing their own network call), or ``False`` if it
        timed out (callers should fall back to refreshing themselves rather
        than waiting forever).
    """
    lock_file = _open_refresh_lock_file(server_url)
    try:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if _try_acquire_file_lock_nb(lock_file):
                _release_file_lock(lock_file)
                return True
            time.sleep(0.1)
        return False
    finally:
        lock_file.close()


@contextmanager
def credential_store_lock():
    """Serialise credential read-modify-write sequences across processes."""
    config_path = os.path.abspath(get_config_path())
    lock_path = "{}.lock".format(config_path)
    held_locks = getattr(_lock_state, "held_locks", None)
    if held_locks is None:
        held_locks = {}
        _lock_state.held_locks = held_locks

    held_lock = held_locks.get(lock_path)
    if held_lock:
        held_lock["depth"] += 1
        try:
            yield
        finally:
            held_lock["depth"] -= 1
        return

    config_dir = os.path.dirname(config_path) or "."
    os.makedirs(config_dir, mode=0o700, exist_ok=True)
    if config_path == os.path.abspath(DEFAULT_CONFIG_PATH):
        os.chmod(config_dir, 0o700)
    lock_file = open(lock_path, "a+", encoding="utf-8")
    os.chmod(lock_path, 0o600)
    try:
        _acquire_file_lock(lock_file)
    except BaseException:
        lock_file.close()
        raise
    held_locks[lock_path] = {"file": lock_file, "depth": 1}
    try:
        yield
    finally:
        held_locks.pop(lock_path, None)
        _release_file_lock(lock_file)
        lock_file.close()


def normalize_server_url(server_url: str) -> str:
    """Normalize server URL used as credential store key."""
    if not server_url:
        raise ValueError("REANA server URL is not set")
    server_url = server_url.strip()
    if "://" not in server_url:
        server_url = f"https://{server_url}"
    parsed = urlparse(server_url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError("REANA server URL must include scheme and host")
    if parsed.scheme.lower() != "https":
        raise ValueError("REANA server URL must use HTTPS")
    path = parsed.path.rstrip("/")
    return urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc,
            path,
            "",
            "",
            "",
        )
    )


def get_config_path() -> str:
    """Return credential store path."""
    return os.path.expanduser(os.getenv("REANA_CLIENT_CONFIG", DEFAULT_CONFIG_PATH))


def empty_config() -> Dict:
    """Return empty credential store structure."""
    return {"active_server": None, "servers": {}}


def load_config() -> Dict:
    """Load credential store from disk."""
    config_path = get_config_path()
    if not os.path.exists(config_path):
        return empty_config()
    with open(config_path, "r", encoding="utf-8") as config_file:
        try:
            config = json.load(config_file)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid REANA client credential file: {exc}") from exc
    config.setdefault("active_server", None)
    config.setdefault("servers", {})
    return config


def save_config(config: Dict) -> None:
    """Save credential store atomically with restrictive permissions."""
    with credential_store_lock():
        config_path = get_config_path()
        config_dir = os.path.dirname(config_path) or "."
        os.makedirs(config_dir, mode=0o700, exist_ok=True)
        if os.path.abspath(config_path) == os.path.abspath(DEFAULT_CONFIG_PATH):
            os.chmod(config_dir, 0o700)
        fd, tmp_path = tempfile.mkstemp(prefix=".reana-client-", dir=config_dir)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
                json.dump(config, tmp_file, indent=2, sort_keys=True)
                tmp_file.write("\n")
            os.chmod(tmp_path, 0o600)
            os.replace(tmp_path, config_path)
            os.chmod(config_path, 0o600)
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)


def get_active_server(config: Optional[Dict] = None) -> Optional[str]:
    """Return active server URL from environment or credential store."""
    env_server = os.getenv("REANA_SERVER_URL")
    if env_server:
        return normalize_server_url(env_server)
    config = config or load_config()
    active_server = config.get("active_server")
    return normalize_server_url(active_server) if active_server else None


def get_server_entry(server_url: str, config: Optional[Dict] = None) -> Dict:
    """Return credential store entry for a server."""
    config = config or load_config()
    normalized_url = normalize_server_url(server_url)
    return config.get("servers", {}).get(normalized_url, {})


def upsert_server_entry(server_url: str, entry: Dict, make_active: bool = True) -> Dict:
    """Update credential store entry for a server, optionally marking it active.

    ``make_active`` defaults to ``True`` for explicit user-initiated writes
    (login, device flow) that are supposed to switch the CLI's active
    server. A background token refresh must pass ``make_active=False``:
    otherwise a slow refresh of server A's tokens that writes back after the
    user has already run ``login`` to switch to server B would silently
    flip ``active_server`` back to A, undoing the user's explicit switch.
    """
    with credential_store_lock():
        config = load_config()
        normalized_url = normalize_server_url(server_url)
        existing_entry = config.setdefault("servers", {}).get(normalized_url, {})
        next_epoch = int(existing_entry.get(CREDENTIAL_EPOCH_FIELD, 0)) + 1
        existing_entry.update(entry)
        existing_entry[CREDENTIAL_EPOCH_FIELD] = next_epoch
        config["servers"][normalized_url] = existing_entry
        if make_active:
            config["active_server"] = normalized_url
        save_config(config)
        return existing_entry


def clear_token_material(server_url: str) -> None:
    """Remove token material for a server while preserving issuer metadata."""
    with credential_store_lock():
        config = load_config()
        normalized_url = normalize_server_url(server_url)
        server_entry = config.setdefault("servers", {}).get(normalized_url, {})
        server_entry[CREDENTIAL_EPOCH_FIELD] = (
            int(server_entry.get(CREDENTIAL_EPOCH_FIELD, 0)) + 1
        )
        for field in TOKEN_FIELDS:
            server_entry.pop(field, None)
        config["servers"][normalized_url] = server_entry
        save_config(config)


def clear_token_material_if_matches(
    server_url: str, rejected_refresh_token: str
) -> bool:
    """Clear token material only if it still matches a rejected refresh token.

    Two concurrent ``reana-client`` processes can both read the same
    refresh token before either has rotated it (refresh no longer holds
    the credential-store lock across the token-endpoint network call).
    The loser's request is rejected with ``invalid_grant`` after the
    winner has already stored a new, valid token. An unconditional clear
    at that point would destroy the winner's credentials too. Re-checking
    under the lock that the on-disk refresh token is still the exact one
    that was rejected -- not just any refresh token -- makes the clear
    safe: it only fires when this really was the last surviving copy.

    :returns: whether token material was actually cleared.
    """
    with credential_store_lock():
        config = load_config()
        normalized_url = normalize_server_url(server_url)
        server_entry = config.setdefault("servers", {}).get(normalized_url, {})
        if server_entry.get("refresh_token") != rejected_refresh_token:
            return False
        server_entry[CREDENTIAL_EPOCH_FIELD] = (
            int(server_entry.get(CREDENTIAL_EPOCH_FIELD, 0)) + 1
        )
        for field in TOKEN_FIELDS:
            server_entry.pop(field, None)
        config["servers"][normalized_url] = server_entry
        save_config(config)
        return True
