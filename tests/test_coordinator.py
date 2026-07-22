"""End-to-end tests for the listing intake coordinator (offline)."""

from __future__ import annotations

import pytest

from app.core.config import AIConfig, AppConfig
from app.services.ai import ContentGenerator
from app.services.coordinator import IntakeStatus, ListingCoordinator
from app.services.description import DescriptionGenerator
from app.storage.excel_store import ExcelPropertyStore


@pytest.fixture()
def coordinator(tmp_path) -> ListingCoordinator:
    store = ExcelPropertyStore(tmp_path / "properties.xlsx")
    describer = DescriptionGenerator(ContentGenerator(AIConfig(enabled=False)))
    return ListingCoordinator(store=store, config=AppConfig(), describer=describer)


def test_incomplete_intake_asks_for_missing_info(coordinator):
    result = coordinator.intake("2BHK in Lusail.")
    assert result.status is IntakeStatus.NEEDS_INFO
    assert "few more details" in result.message
    # A draft row is persisted so follow-ups can enrich it.
    assert result.row_id is not None
    assert len(coordinator.store.read_all()) == 1


def test_follow_up_completes_the_same_listing(coordinator):
    first = coordinator.intake("2BHK apartment in Lusail for 8500 monthly.")
    assert first.status is IntakeStatus.NEEDS_INFO
    second = coordinator.intake(
        "Fully furnished, 2 bathrooms, covered parking, bills included, "
        "available now, 4 cheques",
        property_ref=first.property_ref,
    )
    # Still one row (upserted, not duplicated).
    assert len(coordinator.store.read_all()) == 1
    assert second.property_ref == first.property_ref
    # All required info present now -> description written.
    assert second.data.description
    assert second.status in (IntakeStatus.READY, IntakeStatus.INCOMPLETE)


def test_ready_when_images_and_all_fields_present(coordinator, tmp_path):
    folder = tmp_path / "imgs"
    folder.mkdir()
    coordinator.intake(
        "Fully furnished 2 bedroom 2 bathroom apartment in Lusail for 8500 monthly, "
        "110 sqm, covered parking, bills included, available now, 4 cheques.",
        property_ref="PROP-READY",
    )
    # Attach images out of band and re-run to reach the Ready threshold.
    stored = coordinator.get("PROP-READY")
    stored.images_folder = str(folder)
    coordinator.store.update(stored.sheet_row, {"Images Folder": str(folder)})
    result = coordinator.intake("confirm", property_ref="PROP-READY")
    assert result.completeness.percent >= 90
    assert result.status is IntakeStatus.READY
    assert "ready to publish" in result.message


def test_amenities_are_generated_on_intake(coordinator):
    result = coordinator.intake("Luxury villa in The Pearl for sale at 5,000,000")
    assert result.data.amenities
    assert any("Garden" in a or "Pool" in a for a in result.data.amenities)


def test_search_finds_stored_listing(coordinator):
    coordinator.intake("2BHK apartment in Lusail for 8500 monthly", property_ref="PROP-S1")
    coordinator.intake("Villa in Al Waab for 15000", property_ref="PROP-S2")
    hits = coordinator.search("Lusail")
    assert len(hits) == 1
    assert hits[0].property_ref == "PROP-S1"
