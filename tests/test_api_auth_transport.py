# -*- coding: utf-8 -*-
#
# This file is part of REANA.
# Copyright (C) 2026 CERN.
#
# REANA is free software; you can redistribute it and/or modify it
# under the terms of the MIT License; see LICENSE file for more details.
"""REANA client API authentication transport tests."""

from types import SimpleNamespace

from reana_client.api import client


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

    def fake_post(url, data, params, headers, verify):
        post_call.update(
            {
                "url": url,
                "data": data,
                "params": params,
                "headers": headers,
                "verify": verify,
            }
        )
        return MockResponse()

    monkeypatch.setattr(
        client,
        "current_rs_api_client",
        SimpleNamespace(api=SimpleNamespace(upload_file=MockPathOperation())),
    )
    monkeypatch.setattr(client.requests, "post", fake_post)
    monkeypatch.setattr("reana_client.utils.get_api_url", lambda: "https://reana")

    assert client.upload_file("workflow.1", b"payload", "file.txt", "access-token") == {
        "message": "uploaded"
    }
    assert post_call["params"] == {"file_name": "file.txt"}
    assert post_call["headers"] == {
        "Authorization": "Bearer access-token",
        "Content-Type": "application/octet-stream",
    }
