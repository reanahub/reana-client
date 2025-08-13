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
"""Directory where REANA client configuration is stored."""

CONFIG_FILE_PATH = os.path.join(CONFIG_DIR, "config.json")
"""Path to the REANA client configuration file."""

CONFIG_SCHEMA = {
    "type": "object",
    "properties": {
        "servers": {
            "type": "object",
            "patternProperties": {
                "^.*$": {
                    "type": "object",
                    "properties": {
                        "access_token": {"type": "string"},
                    },
                    "required": ["access_token"]
                }
            }
        }
    },
    "required": ["servers"]
}
"""JSON schema for the configuration file."""

DEFAULT_CONFIG = {
    "servers": {}
}
"""Default configuration structure."""


def ensure_config_dir_exists() -> None:
    """Create the configuration directory if it doesn't exist."""
    if not os.path.exists(CONFIG_DIR):
        os.makedirs(CONFIG_DIR)


def load_config() -> dict:
    """Load configuration from file.

    Returns:
        dict: Configuration dictionary.
    """
    ensure_config_dir_exists()
    if not os.path.exists(CONFIG_FILE_PATH):
        return DEFAULT_CONFIG.copy()

    try:
        with open(CONFIG_FILE_PATH, 'r') as f:
            config = json.load(f)
            jsonschema.validate(instance=config, schema=CONFIG_SCHEMA)
            return config
    except (json.JSONDecodeError, jsonschema.exceptions.ValidationError):
        return DEFAULT_CONFIG.copy()


def save_config(config: dict) -> None:
    """Save configuration to file.

    Args:
        config (dict): Configuration to save.
    """
    ensure_config_dir_exists()
    jsonschema.validate(instance=config, schema=CONFIG_SCHEMA)
    with open(CONFIG_FILE_PATH, 'w') as f:
        json.dump(config, f, indent=2)


def get_server_config(server_url: str) -> Optional[Dict]:
    """Get configuration for a specific server.

    Args:
        server_url (str): URL of the REANA server.

    Returns:
        Optional[Dict]: Server configuration if exists, None otherwise.
    """
    config = load_config()
    return config["servers"].get(server_url)


def set_server_config(server_url: str, access_token: str) -> None:
    """Set or update configuration for a specific server.

    Args:
        server_url (str): URL of the REANA server.
        access_token (str): Access token for the server.
    """
    config = load_config()
    config["servers"][server_url] = {
        "access_token": access_token,
    }
    save_config(config)


def remove_server_config(server_url: str) -> None:
    """Remove configuration for a specific server.

    Args:
        server_url (str): URL of the REANA server.
    """
    config = load_config()
    if server_url in config["servers"]:
        del config["servers"][server_url]
        save_config(config)


def get_current_server_access_token(server_url: str) -> Optional[str]:
    """Get access token for a specific server.

    Args:
        server_url (str): URL of the REANA server.

    Returns:
        Optional[str]: Access token if exists, None otherwise.
    """
    server_config = get_server_config(server_url)
    return server_config["access_token"] if server_config else None
