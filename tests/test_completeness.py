"""Tests for the property completeness scorer."""

from __future__ import annotations

from app.models.schemas import PropertyData
from app.services.completeness import CompletenessScorer


def _full_apartment(**overrides) -> PropertyData:
    data = PropertyData(
        property_ref="P-1",
        platform="propertyoryx",
        property_type="Apartment",
        purpose="Rent",
        bedrooms=2,
        bathrooms=2,
        area_sqm=110,
        rent=8500,
        payment_terms="4 cheques",
        bills_included=True,
        community="Lusail",
        amenities=["Central AC", "Gym", "Pool", "Security", "Balcony", "Near Metro"],
        images_folder="/tmp/imgs",
        description="A" * 80,
    )
    for k, v in overrides.items():
        setattr(data, k, v)
    return data


def test_full_property_scores_100():
    report = CompletenessScorer().score(_full_apartment())
    assert report.percent == 100
    assert report.missing_categories() == []


def test_missing_images_and_description_lowers_score():
    report = CompletenessScorer().score(_full_apartment(images_folder="", description=""))
    assert report.percent < 100
    assert "Images" in report.missing_categories()
    assert "Description" in report.missing_categories()


def test_threshold_gate():
    scorer = CompletenessScorer(threshold_percent=90)
    assert scorer.meets_threshold(_full_apartment())
    assert not scorer.meets_threshold(_full_apartment(images_folder="", description=""))


def test_report_text_format():
    text = CompletenessScorer().score(_full_apartment()).as_text()
    assert "Property Completeness" in text
    assert "Overall:" in text
    assert "%" in text


def test_empty_property_scores_low():
    report = CompletenessScorer().score(PropertyData(property_ref="P-1", platform="propertyoryx"))
    assert report.percent < 30
