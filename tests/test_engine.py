"""End-to-end engine test with the Property Oryx API mocked out."""

from __future__ import annotations

from PIL import Image

from app.core.config import AIConfig, AppConfig
from app.models.schemas import PropertyData, PublishResult
from app.services import images as images_module
from app.services.ai import ContentGenerator
from app.services.images import ImageProcessor
from app.services.publisher import PublishingEngine


class FakeSheet:
    """Minimal sheet source recording write-backs."""

    def __init__(self, row: dict):
        self._row = row
        self.posted: tuple | None = None
        self.failed: tuple | None = None

    def read_properties(self):
        return [PropertyData.from_sheet_row(self._row, sheet_row=2)]

    def mark_posted(self, sheet_row, listing_url, title, description):
        self.posted = (sheet_row, listing_url, title, description)

    def mark_failed(self, sheet_row, error):
        self.failed = (sheet_row, error)


class FakePlatform:
    """Stands in for PropertyOryxPlatform inside the engine."""

    published: list[tuple] = []

    def __init__(self, credential, config=None, **kwargs):
        self.credential = credential

    def login(self):
        return None

    def publish(self, data, image_paths):
        FakePlatform.published.append((data.property_ref, list(image_paths)))
        return PublishResult(success=True, listing_id="42", listing_url="https://oryx/property/42")

    def update(self, external_id, data, image_paths):
        return PublishResult(success=True, listing_id=external_id, listing_url=f"https://oryx/property/{external_id}")


def _make_engine(sample_row, tmp_path, monkeypatch) -> tuple[PublishingEngine, FakeSheet]:
    folder = tmp_path / "imgs"
    folder.mkdir()
    Image.new("RGB", (800, 600), (10, 20, 30)).save(folder / "a.jpg")
    row = dict(sample_row)
    row["Images Folder"] = str(folder)

    monkeypatch.setattr(images_module, "PROCESSED_DIR", tmp_path / "processed")
    monkeypatch.setattr("app.services.publisher.PropertyOryxPlatform", FakePlatform)
    FakePlatform.published.clear()

    sheet = FakeSheet(row)
    engine = PublishingEngine(
        config=AppConfig(),
        sheet=sheet,
        content=ContentGenerator(AIConfig(enabled=False)),
        images=ImageProcessor(),
    )
    engine.accounts.add("propertyoryx", "Main", engine.vault.encrypt("test-api-key"))
    return engine, sheet


def test_full_publish_cycle(temp_db, sample_row, tmp_path, monkeypatch):
    engine, sheet = _make_engine(sample_row, tmp_path, monkeypatch)

    enqueued = engine.sync_from_sheet()
    assert enqueued == 1

    job = engine.jobs.next_queued()
    assert job is not None
    engine._run_job(job.id, job.property_id, job.platform)

    prop = engine.properties.list()[0]
    assert prop.status.value == "Published"
    assert prop.external_id == "42"
    assert prop.listing_url == "https://oryx/property/42"
    # Title/description were generated (template fallback) since the sheet left them blank.
    assert prop.title and prop.description
    # Sheet write-back happened.
    assert sheet.posted is not None
    assert sheet.posted[1] == "https://oryx/property/42"
    # Images were uploaded through the platform.
    assert FakePlatform.published and FakePlatform.published[0][0] == "PROP-100"


def test_missing_api_key_fails_permanently(temp_db, sample_row, tmp_path, monkeypatch):
    engine, sheet = _make_engine(sample_row, tmp_path, monkeypatch)
    # Remove the account so no API key is available (and no env fallback in tests).
    monkeypatch.delenv("PROPERTYORYX_API_KEY", raising=False)
    for account in engine.accounts.list():
        engine.accounts.delete(account.id)

    engine.sync_from_sheet()
    job = engine.jobs.next_queued()
    engine._run_job(job.id, job.property_id, job.platform)

    prop = engine.properties.list()[0]
    assert prop.status.value == "Failed"
    assert "API key" in prop.error or "PROPERTYORYX_API_KEY" in prop.error
