"""Tests for context-aware amenities generation."""

from __future__ import annotations

from app.models.schemas import PropertyData
from app.services.amenities_generator import AmenitiesGenerator


def _prop(**kw) -> PropertyData:
    base = {"property_ref": "P-1", "platform": "propertyoryx"}
    base.update(kw)
    return PropertyData(**base)


def test_luxury_apartment_gets_premium_amenities():
    gen = AmenitiesGenerator()
    amenities = gen.generate(_prop(property_type="Apartment", community="Lusail"))
    assert "Central AC" in amenities
    assert any("Swimming Pool" in a for a in amenities)
    assert "Near Metro" in amenities  # Lusail is metro-served


def test_villa_amenities_differ_from_apartment():
    gen = AmenitiesGenerator()
    villa = set(gen.generate(_prop(property_type="Standalone Villa", community="Al Waab")))
    apartment = set(gen.generate(_prop(property_type="Apartment", community="Al Sadd")))
    assert "Private Garden" in villa
    assert "Private Garden" not in apartment
    assert villa != apartment


def test_standard_area_is_leaner_than_luxury():
    gen = AmenitiesGenerator()
    luxury = gen.generate(_prop(property_type="Apartment", community="The Pearl"))
    standard = gen.generate(_prop(property_type="Apartment", community="Old Airport"))
    assert len(luxury) > len(standard)


def test_ensure_amenities_merges_without_duplicates():
    gen = AmenitiesGenerator()
    data = _prop(property_type="Apartment", community="Lusail", amenities=["Central AC", "Rooftop Terrace"])
    result = gen.ensure_amenities(data)
    assert "Rooftop Terrace" in result           # agent-supplied kept
    assert result.count("Central AC") == 1        # no duplicate
    assert len(result) > 2                         # generated ones added


def test_unknown_area_still_produces_base_amenities():
    gen = AmenitiesGenerator()
    amenities = gen.generate(_prop(property_type="Apartment", community="Nowheresville"))
    assert "Central AC" in amenities
    assert len(amenities) >= 6
