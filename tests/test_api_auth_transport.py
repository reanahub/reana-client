# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2026 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
"""REANA client API authentication transport tests."""

import io
from types import SimpleNamespace
from unittest import mock

from reana_client import config
from reana_client.api import client


def _force_default_tls_verification(monkeypatch):
    """Clear TLS override env vars so ``tls_verify()`` returns ``True``."""
    monkeypatch.delenv(config.CA_CERTS_ENV, raising=False)
    monkeypatch.delenv(config.INSECURE_ENV, raising=False)


class MockOperation:
    """Bravado operation double."""

    def __init__(self, response):
        """Initialize operation double."""
        self.response = response
        self.kwargs = None

    def __call__(self, **kwargs):
        """Capture operation kwargs."""
        self.kwargs = kwargs
        return self

    def result(self):
        """Return operation result."""
        return self.response


def test_bravado_calls_use_bearer_request_options(monkeypatch):
    """Test bravado calls use bearer headers and not token query params."""
    http_response = SimpleNamespace(status_code=200)
    operation = MockOperation(({"quota": {}}, http_response))
    monkeypatch.setattr(
        client,
        "current_rs_api_client",
        SimpleNamespace(api=SimpleNamespace(get_you=operation)),
    )

    client.get_user_quota("access-token")

    assert operation.kwargs == {
        "_request_options": {"headers": {"Authorization": "Bearer access-token"}}
    }


def test_api_client_uses_active_oidc_server(monkeypatch):
    """Stored OIDC server selection configures generated API operations."""
    _force_default_tls_verification(monkeypatch)
    api_client = object()
    factory = mock.Mock(return_value=api_client)
    monkeypatch.setattr(client, "get_current_api_client", factory)
    monkeypatch.setattr(
        "reana_client.auth.storage.get_active_server",
        lambda: "https://stored.example.org",
    )

    assert client._get_current_reana_server_api_client() is api_client
    factory.assert_called_once_with(
        component="reana-server",
        ssl_verify=True,
        server_url="https://stored.example.org",
    )


def test_api_client_and_auth_agree_on_normalised_server(monkeypatch):
    """Generated calls must address the same origin as authentication."""
    _force_default_tls_verification(monkeypatch)
    monkeypatch.setenv("REANA_SERVER_URL", "localhost")
    monkeypatch.setattr(
        "reana_client.auth.storage.load_config",
        lambda: {"active_server": None, "servers": {}},
    )
    from reana_client.auth.storage import get_active_server

    api_client = client._get_current_reana_server_api_client()

    assert get_active_server() == "https://localhost"
    assert api_client.swagger_spec.api_url == "https://localhost"


def test_upload_file_uses_bearer_header_without_token_query(monkeypatch):
    """Test raw upload request uses bearer header and no access token query param."""
    post_call = {}

    class MockPathOperation:
        operation = SimpleNamespace(
            path_name="/api/workflows/{workflow_id_or_name}/workspace"
        )

    class MockResponse:
        ok = True

        def json(self):
            return {"message": "uploaded"}

    def fake_post(url, data, params, headers, timeout, verify):
        post_call.update(
            {
                "url": url,
                "data": data,
                "params": params,
                "headers": headers,
                "timeout": timeout,
                "verify": verify,
            }
        )
        return MockResponse()

    _force_default_tls_verification(monkeypatch)
    monkeypatch.setattr(
        client,
        "current_rs_api_client",
        SimpleNamespace(api=SimpleNamespace(upload_file=MockPathOperation())),
    )
    monkeypatch.setattr(client.requests, "post", fake_post)
    monkeypatch.setattr("reana_client.utils.get_api_url", lambda: "https://reana")

    file_source = io.BytesIO(b"payload")
    assert client.upload_file(
        "workflow.1", file_source, "file.txt", "access-token"
    ) == {"message": "uploaded"}
    assert post_call["params"] == {"file_name": "file.txt"}
    assert post_call["headers"] == {
        "Authorization": "Bearer access-token",
        "Content-Type": "application/octet-stream",
        "Content-Length": "7",
    }
    assert post_call["verify"] is True
    assert post_call["timeout"] == client.FILE_TRANSFER_TIMEOUT


def test_download_file_uses_bearer_request_options(monkeypatch):
    """Test downloads go through the generated Bravado operation with a bearer header."""
    http_response = SimpleNamespace(
        status_code=200,
        headers={"Content-Type": "text/plain"},
        raw_bytes=b"contents",
    )
    operation = MockOperation((None, http_response))
    monkeypatch.setattr(
        client,
        "current_rs_api_client",
        SimpleNamespace(api=SimpleNamespace(download_file=operation)),
    )

    assert client.download_file("workflow.1", "result.txt", "access-token") == (
        b"contents",
        "result.txt",
        False,
    )
    assert operation.kwargs["_request_options"]["headers"] == {
        "Authorization": "Bearer access-token"
    }


def test_interactive_session_secret_uses_bearer_header(monkeypatch):
    """Test notebook secrets use the generated authenticated transport."""
    http_response = SimpleNamespace(status_code=200)
    operation = MockOperation(
        (
            {"session_secret": "notebook secret", "path": "/session"},
            http_response,
        )
    )
    monkeypatch.setattr(
        client,
        "current_rs_api_client",
        SimpleNamespace(api=SimpleNamespace(get_interactive_session_secret=operation)),
    )

    result = client.get_interactive_session_secret("workflow.1", "access-token")

    assert result["session_secret"] == "notebook secret"
    assert operation.kwargs == {
        "_request_options": {"headers": {"Authorization": "Bearer access-token"}},
        "workflow_id_or_name": "workflow.1",
    }


def test_force_stop_does_not_send_removed_request_parameter(monkeypatch):
    """Force-stop uses the server's status transition without a JSON body."""
    http_response = SimpleNamespace(status_code=200)
    operation = MockOperation(({"status": "stopped"}, http_response))
    monkeypatch.setattr(
        client,
        "current_rs_api_client",
        SimpleNamespace(api=SimpleNamespace(set_workflow_status=operation)),
    )

    result = client.stop_workflow("workflow.1", True, "access-token")

    assert result == {"status": "stopped"}
    assert operation.kwargs == {
        "_request_options": {"headers": {"Authorization": "Bearer access-token"}},
        "workflow_id_or_name": "workflow.1",
        "status": "stop",
    }
