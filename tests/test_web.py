"""Tests for the FastAPI web dashboard (engine mocked via a temp DB)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import AIConfig, AppConfig
from app.services.ai import ContentGenerator
from app.services.publisher import PublishingEngine
from app.web.server import create_app


def _engine() -> PublishingEngine:
    return PublishingEngine(
        config=AppConfig(),
        sheet=object(),  # not used by the endpoints under test
        content=ContentGenerator(AIConfig(enabled=False)),
    )


def test_overview_reports_no_key(temp_db, monkeypatch):
    monkeypatch.delenv("PROPERTYORYX_API_KEY", raising=False)
    with TestClient(create_app(_engine())) as client:
        res = client.get("/api/overview")
        assert res.status_code == 200
        body = res.json()
        assert body["has_api_key"] is False
        assert set(body["stats"]) >= {"published_today", "failed_today", "pending", "success_rate"}
        assert body["platforms"] and body["platforms"][0]["name"] == "Property Oryx"


def test_save_api_key_then_overview_reports_key(temp_db):
    with TestClient(create_app(_engine())) as client:
        res = client.post("/api/account", json={"api_key": "secret-key", "label": "Main"})
        assert res.status_code == 200 and res.json()["ok"] is True
        assert client.get("/api/overview").json()["has_api_key"] is True


def test_properties_empty_and_index_served(temp_db):
    with TestClient(create_app(_engine())) as client:
        assert client.get("/api/properties").json() == []
        page = client.get("/")
        assert page.status_code == 200
        assert "Elite Publisher" in page.text


def test_publish_missing_property_404(temp_db):
    with TestClient(create_app(_engine())) as client:
        assert client.post("/api/properties/999/publish").status_code == 404


def test_invalid_status_filter_rejected(temp_db):
    with TestClient(create_app(_engine())) as client:
        assert client.get("/api/properties", params={"status": "Nonsense"}).status_code == 400
