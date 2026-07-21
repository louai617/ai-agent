"""Tests for property validation."""

from __future__ import annotations

import pytest

from app.core.exceptions import ValidationError
from app.models.schemas import PropertyData
from app.utils.validators import validate_property


def _data(sample_row, tmp_path, **overrides):
    row = dict(sample_row)
    folder = tmp_path / "imgs"
    folder.mkdir(exist_ok=True)
    row["Images Folder"] = str(folder)
    row.update(overrides)
    return PropertyData.from_sheet_row(row)


def test_valid_property_passes(sample_row, tmp_path):
    validate_property(_data(sample_row, tmp_path))


def test_missing_folder_fails(sample_row, tmp_path):
    data = _data(sample_row, tmp_path)
    data.images_folder = str(tmp_path / "does-not-exist")
    with pytest.raises(ValidationError, match="Images folder"):
        validate_property(data)


def test_bad_phone_fails(sample_row, tmp_path):
    data = _data(sample_row, tmp_path, **{"Phone": "not-a-phone!!"})
    with pytest.raises(ValidationError, match="phone"):
        validate_property(data)


def test_bad_latitude_fails(sample_row, tmp_path):
    data = _data(sample_row, tmp_path, **{"Latitude": "123.0"})
    with pytest.raises(ValidationError, match="Latitude"):
        validate_property(data)


def test_no_price_fails(sample_row, tmp_path):
    data = _data(sample_row, tmp_path, **{"Rent": "", "Sale Price": ""})
    with pytest.raises(ValidationError, match="rent or sale_price"):
        validate_property(data)
