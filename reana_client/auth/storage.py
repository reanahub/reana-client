# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2026 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
"""File-backed credential storage for REANA client."""

import json
import os
import tempfile
from typing import Dict, Optional
from urllib.parse import urlparse, urlunparse


DEFAULT_CONFIG_PATH = os.path.expanduser("~/.config/reana/reana-client.json")
TOKEN_FIELDS = {
    "access_token",
    "access_token_expires_at",
    "refresh_token",
    "refresh_token_expires_at",
}


def normalize_server_url(server_url: str) -> str:
    """Normalize server URL used as credential store key."""
    if not server_url:
        raise ValueError("REANA server URL is not set")
    server_url = server_url.strip()
    if "://" not in server_url:
        server_url = f"http://{server_url}"
    parsed = urlparse(server_url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError("REANA server URL must include scheme and host")
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
    config_path = get_config_path()
    config_dir = os.path.dirname(config_path)
    os.makedirs(config_dir, mode=0o700, exist_ok=True)
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


def upsert_server_entry(server_url: str, entry: Dict) -> Dict:
    """Update credential store entry for a server and mark it active."""
    config = load_config()
    normalized_url = normalize_server_url(server_url)
    existing_entry = config.setdefault("servers", {}).get(normalized_url, {})
    existing_entry.update(entry)
    config["servers"][normalized_url] = existing_entry
    config["active_server"] = normalized_url
    save_config(config)
    return existing_entry


def clear_token_material(server_url: str) -> None:
    """Remove token material for a server while preserving issuer metadata."""
    config = load_config()
    normalized_url = normalize_server_url(server_url)
    server_entry = config.setdefault("servers", {}).get(normalized_url, {})
    for field in TOKEN_FIELDS:
        server_entry.pop(field, None)
    config["servers"][normalized_url] = server_entry
    save_config(config)
