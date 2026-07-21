"""Field validation helpers for property rows."""

from __future__ import annotations

import re
from pathlib import Path

from app.core.exceptions import ValidationError
from app.models.schemas import PropertyData

_PHONE_RE = re.compile(r"^\+?[\d\s\-()]{7,20}$")
_EMAIL_RE = re.compile(r"^[\w.+-]+@[\w-]+\.[\w.-]+$")


def validate_property(data: PropertyData) -> None:
    """Raise ``ValidationError`` listing every problem found, or return None."""
    problems: list[str] = []
    missing = data.missing_required_fields()
    if missing:
        problems.append(f"Missing required fields: {', '.join(missing)}")

    if data.phone and not _PHONE_RE.match(data.phone):
        problems.append(f"Invalid phone number: {data.phone!r}")
    if data.email and not _EMAIL_RE.match(data.email):
        problems.append(f"Invalid email: {data.email!r}")
    if data.latitude is not None and not (-90 <= data.latitude <= 90):
        problems.append("Latitude out of range")
    if data.longitude is not None and not (-180 <= data.longitude <= 180):
        problems.append("Longitude out of range")
    if data.bedrooms is not None and data.bedrooms < 0:
        problems.append("Bedrooms cannot be negative")
    if data.area_sqm is not None and data.area_sqm <= 0:
        problems.append("Area must be positive")

    if data.images_folder:
        folder = Path(data.images_folder)
        if not folder.is_dir():
            problems.append(f"Images folder does not exist: {data.images_folder}")

    if problems:
        raise ValidationError("; ".join(problems), missing_fields=missing)
