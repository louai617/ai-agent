"""Tests for AI content generation (template fallback path + emoji stripping)."""

from __future__ import annotations

from app.core.config import AIConfig
from app.models.schemas import PropertyData
from app.services.ai import ContentGenerator, _strip_emojis


def _generator() -> ContentGenerator:
    """AI disabled -> deterministic template path, no network."""
    return ContentGenerator(AIConfig(enabled=False))


def test_template_title_facts_and_length(sample_row):
    data = PropertyData.from_sheet_row(sample_row)
    title = _generator().generate_title(data)
    assert len(title) <= 80
    assert "2 BR" in title
    assert "Rent" in title
    assert "The Pearl" in title


def test_template_description_highlights(sample_row):
    data = PropertyData.from_sheet_row(sample_row)
    description = _generator().generate_description(data)
    for expected in ("Bedrooms", "Bathrooms", "110", "Pool", "7,500"):
        assert expected in description


def test_ensure_content_fills_only_empty(sample_row):
    data = PropertyData.from_sheet_row(sample_row)
    data.title = "Existing Title"
    data = _generator().ensure_content(data)
    assert data.title == "Existing Title"
    assert data.description  # was empty -> generated


def test_no_emojis_in_output():
    cleaned = _strip_emojis("Nice \U0001F600 place \U0001F3E0\U0001F525")
    assert "\U0001F600" not in cleaned
    assert "\U0001F3E0" not in cleaned
    assert "Nice" in cleaned and "place" in cleaned


def test_sale_property_uses_sale_wording(sample_row):
    sample_row["Rent"] = ""
    sample_row["Sale Price"] = "2500000"
    data = PropertyData.from_sheet_row(sample_row)
    title = _generator().generate_title(data)
    assert "Sale" in title
