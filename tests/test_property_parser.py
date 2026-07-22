"""Tests for the natural-language property parser."""

from __future__ import annotations

from app.services.property_parser import PropertyParser


def _parse(text: str):
    return PropertyParser().parse(text)


def test_parses_2bhk_apartment_in_lusail_with_rent():
    r = _parse("Hey, this is a 2BHK apartment in Lusail for 8,500 QAR.")
    assert r.data.property_type == "Apartment"
    assert r.data.bedrooms == 2
    assert r.data.community == "Lusail"
    assert r.data.location == "Lusail"
    assert r.data.rent == 8500.0
    assert r.data.sale_price is None
    assert r.was_provided("bedrooms", "property_type", "community", "rent")


def test_parses_furnished_one_bedroom_in_the_pearl():
    r = _parse("Post a furnished 1 bedroom in The Pearl.")
    assert r.data.bedrooms == 1
    assert r.data.furnished == "Fully Furnished"
    assert r.data.community == "The Pearl"


def test_villa_only_infers_type_and_area():
    r = _parse("Villa in Ain Khaled.")
    assert r.data.property_type == "Standalone Villa"
    assert r.data.community == "Ain Khaled"
    assert r.data.bedrooms is None  # not stated - must not be invented


def test_studio_sets_zero_bedrooms():
    r = _parse("Studio in West Bay for 4500 monthly")
    assert r.data.bedrooms == 0
    assert r.data.rent == 4500.0


def test_large_price_treated_as_sale():
    r = _parse("Standalone villa in West Bay Lagoon for sale at 3,200,000")
    assert r.data.sale_price == 3_200_000.0
    assert r.data.rent is None
    assert r.data.purpose == "Sale"


def test_plot_and_area_are_distinct():
    r = _parse("Villa with 400 sqm built-up on a 600 sqm plot in Al Waab")
    assert r.data.plot_size == 600.0
    assert r.data.area_sqm == 400.0


def test_rooms_and_features_detected():
    r = _parse(
        "3 bedroom 2 bathroom apartment with balcony, covered parking, sea view "
        "on the 12th floor, maid's room, available now"
    )
    assert r.data.bathrooms == 2
    assert r.data.balcony == "Yes"
    assert r.data.parking == "Covered Parking"
    assert r.data.view == "Sea View"
    assert r.data.floor == "12"
    assert r.data.maid_room == "Yes"
    assert r.data.availability == "Available Now"


def test_utilities_included_and_excluded():
    r = _parse("2 bed in Al Sadd, water and internet included, electricity excluded")
    assert "Water" in r.data.utilities_included
    assert "Internet" in r.data.utilities_included
    assert "Electricity" in r.data.utilities_excluded


def test_payment_terms_cheques():
    r = _parse("2 bedroom in Najma for 6000, 4 cheques")
    assert r.data.payment_terms == "4 cheques"


def test_follow_up_enriches_base():
    parser = PropertyParser()
    first = parser.parse("2BHK apartment in Lusail", property_ref="PROP-X")
    second = parser.parse("8500 monthly, fully furnished, 2 bathrooms", base=first.data, property_ref="PROP-X")
    assert second.data.bedrooms == 2          # preserved from first message
    assert second.data.community == "Lusail"  # preserved
    assert second.data.rent == 8500.0         # added
    assert second.data.bathrooms == 2         # added
