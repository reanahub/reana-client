# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2025 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.

"""REANA client login tests."""

from unittest.mock import Mock, patch

from click.testing import CliRunner

from reana_client.cli import cli


def test_login_config_not_available():
    """Test login when OpenID configuration is not available."""
    env = {"REANA_SERVER_URL": "localhost"}
    runner = CliRunner(env=env)

    mock_get_config = Mock(side_effect=Exception("Configuration not available"))

    with patch("reana_client.cli.login.get_openid_configuration", mock_get_config):
        result = runner.invoke(cli, ["login"])

        assert result.exit_code == 1
        assert "Configuration not available" in result.output


def test_login_device_authorization_failed():
    """Test login when device authorization request fails."""
    env = {"REANA_SERVER_URL": "localhost"}
    runner = CliRunner(env=env)

    mock_config = {
        "device_authorization_endpoint": "https://auth.example.com/device",
        "reana_client_id": "client-id",
    }

    mock_response = Mock()
    mock_response.raise_for_status.side_effect = Exception("Authorization failed")

    with patch(
        "reana_client.cli.login.get_openid_configuration", return_value=mock_config
    ), patch("reana_client.cli.login.requests.post", return_value=mock_response):
        result = runner.invoke(cli, ["login"])

        assert result.exit_code == 1
        assert "Authorization failed" in result.output


def test_login_token_request_expired():
    """Test login when token request returns expired token error."""
    env = {"REANA_SERVER_URL": "localhost"}
    runner = CliRunner(env=env)

    mock_config = {
        "device_authorization_endpoint": "https://auth.example.com/device",
        "token_endpoint": "https://auth.example.com/token",
        "reana_client_id": "client-id",
    }

    device_response = Mock()
    device_response.raise_for_status = Mock()
    device_response.json = Mock(
        return_value={
            "device_code": "device_code_123",
            "user_code": "USER123",
            "verification_uri": "https://auth.example.com/verify",
            "interval": 1,
        }
    )

    token_response = Mock()
    token_response.status_code = 400
    token_response.json = Mock(return_value={"error": "expired_token"})

    with patch(
        "reana_client.cli.login.get_openid_configuration", return_value=mock_config
    ), patch("reana_client.cli.login.requests.post") as mock_post:
        mock_post.side_effect = [device_response, token_response]
        result = runner.invoke(cli, ["login"])

        assert result.exit_code == 1
        assert "Authentication timed out" in result.output


def test_login_token_request_other_error():
    """Test login when token request returns other error."""
    env = {"REANA_SERVER_URL": "localhost"}
    runner = CliRunner(env=env)

    mock_config = {
        "device_authorization_endpoint": "https://auth.example.com/device",
        "token_endpoint": "https://auth.example.com/token",
        "reana_client_id": "client-id",
    }

    device_response = Mock()
    device_response.raise_for_status = Mock()
    device_response.json = Mock(
        return_value={
            "device_code": "device_code_123",
            "user_code": "USER123",
            "verification_uri": "https://auth.example.com/verify",
            "interval": 1,
        }
    )

    token_response = Mock()
    token_response.status_code = 400
    token_response.json = Mock(return_value={"error": "invalid_grant"})

    with patch(
        "reana_client.cli.login.get_openid_configuration", return_value=mock_config
    ), patch("reana_client.cli.login.requests.post") as mock_post:
        mock_post.side_effect = [device_response, token_response]
        result = runner.invoke(cli, ["login"])

        assert result.exit_code == 1
        assert "Authentication failed: invalid_grant" in result.output


def test_login_successful():
    """Test successful login flow."""
    env = {"REANA_SERVER_URL": "localhost"}
    runner = CliRunner(env=env)

    mock_config = {
        "device_authorization_endpoint": "https://auth.example.com/device",
        "token_endpoint": "https://auth.example.com/token",
        "reana_client_id": "client-id",
    }

    device_response = Mock()
    device_response.raise_for_status = Mock()
    device_response.json = Mock(
        return_value={
            "device_code": "device_code_123",
            "user_code": "USER123",
            "verification_uri": "https://auth.example.com/verify",
            "verification_uri_complete": "https://auth.example.com/verify?code=USER123",
            "interval": 1,
        }
    )

    token_response = Mock()
    token_response.status_code = 200
    token_response.json = Mock(return_value={"access_token": "access_token_123"})

    with patch(
        "reana_client.cli.login.get_openid_configuration", return_value=mock_config
    ), patch("reana_client.cli.login.requests.post") as mock_post, patch(
        "reana_client.cli.login.set_server_config"
    ) as mock_set_config:
        mock_post.side_effect = [device_response, token_response]
        result = runner.invoke(cli, ["login"])

        mock_set_config.assert_called_once_with("access_token_123")
        assert result.exit_code == 0
        assert "Successfully authenticated" in result.output
        assert "localhost" in result.output
