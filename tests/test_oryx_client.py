"""Tests for the Property Oryx API client (HTTP mocked)."""

from __future__ import annotations

import pytest

from app.core.config import OryxConfig
from app.core.exceptions import AuthError, OryxApiError, UploadError
from app.platforms.propertyoryx.client import PropertyOryxClient


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, content=b"{}", text=""):
        self.status_code = status_code
        self._json = json_data
        self.content = content
        self.text = text

    @property
    def ok(self) -> bool:
        return self.status_code < 400

    def json(self):
        if self._json is None:
            raise ValueError("no json")
        return self._json

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError("http error")


@pytest.fixture()
def client():
    return PropertyOryxClient("test-key", OryxConfig())


def test_account_success(client, monkeypatch):
    captured = {}

    def fake_request(method, url, **kwargs):
        captured["method"] = method
        captured["url"] = url
        captured["headers"] = client._session.headers
        return FakeResponse(200, {"email": "a@b.com", "name": "Agent"})

    monkeypatch.setattr(client._session, "request", fake_request)
    data = client.account()
    assert data["email"] == "a@b.com"
    assert captured["url"].endswith("/account")
    assert client._session.headers["X-API-Key"] == "test-key"


def test_auth_error_raised_on_401(client, monkeypatch):
    monkeypatch.setattr(
        client._session, "request",
        lambda *a, **k: FakeResponse(401, [{"code": "AUTHENTICATION_REQUIRED"}], content=b"[]"),
    )
    with pytest.raises(AuthError) as exc:
        client.account()
    assert "AUTHENTICATION_REQUIRED" in exc.value.codes


def test_validation_error_carries_codes(client, monkeypatch):
    monkeypatch.setattr(
        client._session, "request",
        lambda *a, **k: FakeResponse(400, [{"code": "VALUE_TOO_SHORT"}], content=b"[]"),
    )
    with pytest.raises(OryxApiError) as exc:
        client.create_rental({})
    assert exc.value.status_code == 400
    assert exc.value.is_retryable is False
    assert "VALUE_TOO_SHORT" in exc.value.codes


def test_request_upload_returns_url(client, monkeypatch):
    monkeypatch.setattr(
        client._session, "request",
        lambda *a, **k: FakeResponse(200, {"url": "https://signed.example/put"}),
    )
    url = client.request_upload("abc", "image/jpeg")
    assert url == "https://signed.example/put"


def test_request_upload_missing_url_raises(client, monkeypatch):
    monkeypatch.setattr(client._session, "request", lambda *a, **k: FakeResponse(200, {}))
    with pytest.raises(UploadError):
        client.request_upload("abc", "image/jpeg")


def test_process_image_returns_hash(client, monkeypatch):
    monkeypatch.setattr(
        client._session, "request", lambda *a, **k: FakeResponse(200, {"hash": "processed-123"})
    )
    assert client.process_image("raw", "PropertyImage", False) == "processed-123"


def test_dashboard_search_drops_none_params(client, monkeypatch):
    captured = {}

    def fake_request(method, url, **kwargs):
        captured["params"] = kwargs.get("params")
        return FakeResponse(200, {"listings": [], "matchingCount": 0})

    monkeypatch.setattr(client._session, "request", fake_request)
    client.dashboard_search(category="rent", reference="R-1", agentid=None)
    assert "agentid" not in captured["params"]
    assert captured["params"]["reference"] == "R-1"
    assert captured["params"]["page"] == 1
