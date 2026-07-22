"""Tests for the professional description generator (template path, offline)."""

from __future__ import annotations

from app.core.config import AIConfig
from app.models.schemas import PropertyData
from app.services.ai import ContentGenerator
from app.services.description import DescriptionGenerator


def _describer() -> DescriptionGenerator:
    # AI disabled -> deterministic landmark template, no network.
    return DescriptionGenerator(ContentGenerator(AIConfig(enabled=False)))


def _apartment() -> PropertyData:
    return PropertyData(
        property_ref="P-1",
        platform="propertyoryx",
        property_type="Apartment",
        bedrooms=2,
        bathrooms=2,
        area_sqm=110,
        rent=8500,
        furnished="Fully Furnished",
        community="Lusail",
        amenities=["Central AC", "Gym", "Swimming Pool"],
        agent="Sara Ahmed",
    )


def test_description_includes_key_facts_and_landmarks():
    text = _describer().build_professional_description(_apartment())
    assert "2-bedroom" in text
    assert "Lusail" in text
    assert "8,500" in text
    # A Lusail landmark from the knowledge base should appear.
    assert "Lusail Marina" in text or "Place Vendome" in text or "Boulevard" in text
    assert "Sara Ahmed" in text


def test_description_mentions_amenities():
    text = _describer().build_professional_description(_apartment())
    assert "gym" in text.lower()


def test_title_is_seo_friendly_and_bounded():
    title = _describer().generate_title(_apartment())
    assert len(title) <= 80
    assert "Lusail" in title
    assert "2-Bedroom" in title or "2-bedroom" in title.lower() or "Bedroom" in title


def test_ensure_fills_only_empty_fields():
    describer = _describer()
    data = _apartment()
    data.title = "Existing Title"
    describer.ensure(data)
    assert data.title == "Existing Title"
    assert data.description  # was empty -> generated


def test_villa_description_uses_plot_and_rooms():
    villa = PropertyData(
        property_ref="P-2",
        platform="propertyoryx",
        property_type="Standalone Villa",
        bedrooms=4,
        bathrooms=5,
        plot_size=600,
        sale_price=3_200_000,
        community="West Bay Lagoon",
        maid_room="Yes",
        driver_room="Yes",
    )
    text = _describer().build_professional_description(villa)
    assert "600 sqm plot" in text
    assert "maid's room" in text
    assert "driver's room" in text
    assert "for sale" in text
