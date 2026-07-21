"""Tests for the image processing pipeline."""

from __future__ import annotations

import pytest
from PIL import Image

from app.core.config import ImageConfig
from app.core.exceptions import ImageError
from app.services import images as images_module
from app.services.images import ImageProcessor


@pytest.fixture()
def processor(tmp_path, monkeypatch):
    monkeypatch.setattr(images_module, "PROCESSED_DIR", tmp_path / "processed")
    return ImageProcessor(ImageConfig(max_width=800, max_height=600, jpeg_quality=80))


def _make_image(path, size=(1600, 1200), color=(200, 60, 60)):
    Image.new("RGB", size, color).save(path)


def test_resize_rename_and_compress(tmp_path, processor):
    src = tmp_path / "photos"
    src.mkdir()
    _make_image(src / "IMG_9001.png")
    _make_image(src / "IMG_9002.jpg", color=(30, 120, 220))

    result = processor.process_folder(src, "PROP-1")
    assert len(result.ready) == 2
    for i, img in enumerate(result.ready, start=1):
        assert img.processed_path.endswith(f"PROP-1_{i:02d}.jpg")
        assert img.width <= 800 and img.height <= 600
        assert img.size_bytes > 0


def test_duplicates_are_skipped(tmp_path, processor):
    src = tmp_path / "photos"
    src.mkdir()
    _make_image(src / "a.jpg")
    _make_image(src / "b.jpg")  # identical pixels -> duplicate

    result = processor.process_folder(src, "PROP-2")
    assert len(result.ready) == 1
    assert len(result.duplicates) == 1


def test_corrupted_images_are_skipped(tmp_path, processor):
    src = tmp_path / "photos"
    src.mkdir()
    _make_image(src / "good.jpg")
    (src / "broken.jpg").write_bytes(b"this is not an image")

    result = processor.process_folder(src, "PROP-3")
    assert len(result.ready) == 1
    assert len(result.corrupted) == 1


def test_unsupported_extensions_ignored(tmp_path, processor):
    src = tmp_path / "photos"
    src.mkdir()
    _make_image(src / "good.webp")
    (src / "notes.txt").write_text("hello")

    result = processor.process_folder(src, "PROP-4")
    assert len(result.ready) == 1


def test_empty_folder_raises(tmp_path, processor):
    src = tmp_path / "empty"
    src.mkdir()
    with pytest.raises(ImageError):
        processor.process_folder(src, "PROP-5")


def test_missing_folder_raises(tmp_path, processor):
    with pytest.raises(ImageError):
        processor.process_folder(tmp_path / "nope", "PROP-6")
