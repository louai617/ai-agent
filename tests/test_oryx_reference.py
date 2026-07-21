"""Tests for Property Oryx reference-data resolution and payload building."""

from __future__ import annotations

import pytest

from app.core.config import AppConfig, OryxConfig
from app.core.exceptions import ReferenceDataError
from app.models.schemas import PropertyData
from app.platforms.propertyoryx.platform import PropertyOryxPlatform
from app.platforms.propertyoryx.reference import ReferenceDataService

_REFERENCE_DATA = {
    "propertyTypes": ["Apartment", "Standalone Villa"],
    "furnishings": ["Unfurnished", "Partly Furnished", "Fully Furnished"],
    "amenities": [
        {"value": 1, "nameEn": "Swimming Pool", "nameAr": None},
        {"value": 2, "nameEn": "Gym", "nameAr": None},
        {"value": 3, "nameEn": "Covered Parking", "nameAr": None},
    ],
    "locations": [
        {"value": 10, "nameEn": "The Pearl", "nameAr": None, "kind": "district", "parentIds": [1]},
        {"value": 20, "nameEn": "Al Sadd", "nameAr": None, "kind": "district", "parentIds": [1]},
    ],
    "listingOptions": {
        "rent": {"commission": [{"value": 100, "nameEn": "1 Month"}], "deposit": [], "flags": []},
        "sale": {"availability": [{"value": 5, "nameEn": "Ready"}], "commission": [], "flags": []},
    },
}


class FakeClient:
    """Stands in for PropertyOryxClient - returns canned reference data."""

    def __init__(self):
        self.created: list[dict] = []

    def reference_data(self):
        return _REFERENCE_DATA

    def list_agents(self):
        return {"agents": [{"id": 7, "name": "Sara Ahmed"}]}

    def account(self):
        return {"email": "a@b.com", "name": "Agent"}

    def create_rental(self, payload):
        self.created.append(payload)

    def create_sale(self, payload):
        self.created.append(payload)

    def dashboard_search(self, **params):
        return {"listings": [{"id": 999, "reference": params.get("reference"), "created": 1}]}


@pytest.fixture()
def reference():
    return ReferenceDataService(FakeClient(), OryxConfig())


def test_resolve_type_synonyms(reference):
    assert reference.resolve_type("Apartment") == "Apartment"
    assert reference.resolve_type("Villa") == "Standalone Villa"
    assert reference.resolve_type("studio") == "Apartment"


def test_resolve_type_rejects_unknown(reference):
    with pytest.raises(ReferenceDataError):
        reference.resolve_type("Castle")


def test_resolve_furnishing_maps_semi(reference):
    assert reference.resolve_furnishing("Semi Furnished") == "Partly Furnished"
    assert reference.resolve_furnishing("Fully Furnished") == "Fully Furnished"
    assert reference.resolve_furnishing("") == "Unfurnished"


def test_resolve_location_by_name(reference):
    assert reference.resolve_location("The Pearl") == 10
    assert reference.resolve_location("", "Al Sadd") == 20


def test_resolve_location_unknown_raises(reference):
    with pytest.raises(ReferenceDataError):
        reference.resolve_location("Atlantis")


def test_resolve_amenities_skips_unknown(reference):
    assert reference.resolve_amenities(["Gym", "Swimming Pool", "Helipad"]) == [1, 2]


def test_resolve_availability_by_name_and_fallback(reference):
    assert reference.resolve_availability("Ready", None) == 5
    assert reference.resolve_availability("", None) == 5  # first option fallback


def _property(**overrides) -> PropertyData:
    base = dict(
        property_ref="PROP-1",
        platform="propertyoryx",
        title="Lovely two bedroom apartment in The Pearl",
        description="A" * 60,
        property_type="Apartment",
        bedrooms=2,
        bathrooms=2,
        area_sqm=110.0,
        rent=7500.0,
        furnished="Fully Furnished",
        location="Doha",
        district="The Pearl",
        amenities=["Gym", "Swimming Pool"],
        agent="Sara Ahmed",
    )
    base.update(overrides)
    return PropertyData(**base)


def _platform() -> tuple[PropertyOryxPlatform, FakeClient]:
    client = FakeClient()
    reference = ReferenceDataService(client, OryxConfig())
    platform = PropertyOryxPlatform("key", AppConfig(), client=client, reference=reference)
    return platform, client


def test_build_rental_payload_maps_everything():
    platform, _ = _platform()
    payload = platform._build_payload(_property(), ["img-hash-1"], "rent")
    assert payload["type"] == "Apartment"
    assert payload["furnishing"] == "Fully Furnished"
    assert payload["location"] == 10
    assert payload["amenities"] == [1, 2]
    assert payload["price"] == 7500
    assert payload["images"] == ["img-hash-1"]
    assert payload["agentId"] == 7
    assert "deposit" in payload  # rent-specific field present
    assert "availability" not in payload


def test_build_sale_payload_has_availability():
    platform, _ = _platform()
    prop = _property(rent=None, sale_price=3200000.0, availability="Ready")
    payload = platform._build_payload(prop, ["h"], "sale")
    assert payload["price"] == 3200000
    assert payload["availability"] == 5
    assert "deposit" not in payload


def test_publish_creates_and_resolves_id(monkeypatch):
    platform, client = _platform()
    # Avoid real uploads: return the hashes directly.
    monkeypatch.setattr(platform._uploader, "upload_all", lambda paths: ["h1", "h2"])
    result = platform.publish(_property(), ["a.jpg", "b.jpg"])
    assert result.success is True
    assert result.listing_id == "999"
    assert result.listing_url.endswith("/999")
    assert client.created and client.created[0]["reference"] == "PROP-1"
