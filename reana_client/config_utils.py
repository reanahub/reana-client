# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2025 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
"""REANA client configuration utilities."""

import json
import os
from typing import Dict, Optional

import jsonschema

CONFIG_DIR = os.path.expanduser("~/.reana")
CONFIG_FILE_PATH = os.path.join(CONFIG_DIR, "config.json")

CONFIG_SCHEMA = {
    "type": "object",
    "properties": {
        "servers": {
            "type": "object",
            "patternProperties": {
                "^.*$": {
                    "type": "object",
                    "properties": {
                        "jwt_access_token": {"type": "string"},
                    },
                    "required": ["jwt_access_token"],
                }
            },
        }
    },
    "required": ["servers"],
}

DEFAULT_CONFIG = {"servers": {}}


def ensure_config_dir_exists() -> None:
    """Create the configuration directory if it doesn't exist."""
    if not os.path.exists(CONFIG_DIR):
        os.makedirs(CONFIG_DIR)


def load_config() -> dict:
    """Load configuration from file."""
    ensure_config_dir_exists()
    if not os.path.exists(CONFIG_FILE_PATH):
        return DEFAULT_CONFIG.copy()

    try:
        with open(CONFIG_FILE_PATH, "r") as f:
            config = json.load(f)
            jsonschema.validate(instance=config, schema=CONFIG_SCHEMA)
            return config
    except (json.JSONDecodeError, jsonschema.exceptions.ValidationError):
        return DEFAULT_CONFIG.copy()


def save_config(config: dict) -> None:
    """Save configuration to file."""
    ensure_config_dir_exists()
    jsonschema.validate(instance=config, schema=CONFIG_SCHEMA)
    with open(CONFIG_FILE_PATH, "w") as f:
        json.dump(config, f, indent=2)


def get_current_server_url() -> Optional[str]:
    """Get the current REANA server URL from environment variables."""
    return os.environ.get("REANA_SERVER_URL")


def get_server_config() -> Optional[Dict]:
    """Get configuration for the current server."""
    server_url = get_current_server_url()
    if not server_url:
        return None
    config = load_config()
    return config["servers"].get(server_url)


def set_server_config(jwt_access_token: str) -> None:
    """Set or update configuration for the current server."""
    server_url = get_current_server_url()
    if not server_url:
        raise ValueError("REANA_SERVER_URL environment variable is not set.")
    config = load_config()
    config["servers"][server_url] = {"jwt_access_token": jwt_access_token}
    save_config(config)


def remove_server_config() -> None:
    """Remove configuration for the current server."""
    server_url = get_current_server_url()
    if not server_url:
        raise ValueError("REANA_SERVER_URL environment variable is not set.")
    config = load_config()
    if server_url in config["servers"]:
        del config["servers"][server_url]
        save_config(config)


def get_current_server_access_token() -> Optional[str]:
    """Get access token for the current server."""
    server_config = get_server_config()
    return server_config["jwt_access_token"] if server_config else None
