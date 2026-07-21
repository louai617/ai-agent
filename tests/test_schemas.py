"""Tests for PropertyData parsing, validation helpers and hashing."""

from __future__ import annotations

from app.models.schemas import PropertyData


def test_from_sheet_row_parses_types(sample_row):
    data = PropertyData.from_sheet_row(sample_row, sheet_row=2)
    assert data.property_ref == "PROP-100"
    assert data.platform == "propertyoryx"
    assert data.bedrooms == 2
    assert data.area_sqm == 110.0
    assert data.rent == 7500.0
    assert data.sale_price is None
    assert data.bills_included is True
    assert data.amenities == ["Pool", "Gym", "Parking"]
    assert data.sheet_row == 2
    assert data.listing_category() == "rent"


def test_platform_is_normalised(sample_row):
    sample_row["Platform"] = "Property Oryx"
    data = PropertyData.from_sheet_row(sample_row)
    assert data.platform == "propertyoryx"


def test_sale_listing_category(sample_row):
    sample_row["Rent"] = ""
    sample_row["Sale Price"] = "2500000"
    data = PropertyData.from_sheet_row(sample_row)
    assert data.listing_category() == "sale"


def test_missing_required_fields(sample_row):
    sample_row["Images Folder"] = ""
    sample_row["Rent"] = ""
    sample_row["Sale Price"] = ""
    data = PropertyData.from_sheet_row(sample_row)
    missing = data.missing_required_fields()
    assert "images_folder" in missing
    assert "rent or sale_price" in missing


def test_price_display_prefers_rent(sample_row):
    data = PropertyData.from_sheet_row(sample_row)
    assert data.price_display() == "QAR 7,500/month"


def test_content_hash_is_stable_and_discriminates(sample_row):
    a = PropertyData.from_sheet_row(sample_row)
    b = PropertyData.from_sheet_row(sample_row)
    assert a.content_hash() == b.content_hash()
    sample_row["Rent"] = "9999"
    c = PropertyData.from_sheet_row(sample_row)
    assert a.content_hash() != c.content_hash()


def test_numeric_garbage_becomes_none(sample_row):
    sample_row["Bedrooms"] = "two"
    data = PropertyData.from_sheet_row(sample_row)
    assert data.bedrooms is None
