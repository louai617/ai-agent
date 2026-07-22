"""Tests for missing-information detection."""

from __future__ import annotations

from app.services.missing_info import MissingInfoDetector
from app.services.property_parser import PropertyParser


def _fields(text: str) -> set[str]:
    parsed = PropertyParser().parse(text)
    return {q.field for q in MissingInfoDetector().detect(parsed.data, parsed.provided)}


def test_apartment_asks_price_furnishing_bath_parking_bills_availability():
    fields = _fields("2BHK in Lusail.")
    assert "price" in fields
    assert "furnished" in fields
    assert "bathrooms" in fields
    assert "parking" in fields
    assert "utilities" in fields
    assert "availability" in fields
    assert "bedrooms" not in fields  # 2BHK already stated


def test_villa_asks_beds_baths_plot_furnishing_parking_rooms():
    fields = _fields("Villa in Al Waab for 15,000.")
    assert "bedrooms" in fields
    assert "bathrooms" in fields
    assert "plot_size" in fields
    assert "furnished" in fields
    assert "parking" in fields
    assert "maid_room" in fields
    assert "driver_room" in fields
    assert "price" not in fields  # 15,000 already given


def test_only_missing_fields_are_asked():
    parsed = PropertyParser().parse(
        "Fully furnished 2 bedroom 2 bathroom apartment in Lusail for 8500 monthly, "
        "covered parking, bills included, available now, 4 cheques"
    )
    questions = MissingInfoDetector().detect(parsed.data, parsed.provided)
    assert questions == []


def test_is_ready_reflects_completeness():
    detector = MissingInfoDetector()
    incomplete = PropertyParser().parse("2BHK in Lusail.")
    assert not detector.is_ready(incomplete.data, incomplete.provided)


def test_format_prompt_lists_questions():
    parsed = PropertyParser().parse("2BHK in Lusail.")
    prompt = MissingInfoDetector().format_prompt(
        MissingInfoDetector().detect(parsed.data, parsed.provided)
    )
    assert "few more details" in prompt
    assert "•" in prompt
