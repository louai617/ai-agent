"""Reference-data resolution for Property Oryx.

The spreadsheet holds human text ("Apartment", "The Pearl", "Swimming Pool")
but the API wants its own integer IDs and fixed enum strings. This service
fetches ``GET /api-reference-data`` (cached), and resolves sheet values to the
IDs the listing endpoints expect.
"""

from __future__ import annotations

import time
from typing import Any

from app.core.config import OryxConfig, get_config
from app.core.exceptions import ReferenceDataError
from app.core.logging import get_logger
from app.platforms.propertyoryx.client import PropertyOryxClient

logger = get_logger(__name__)

# API property-type enum values
PROPERTY_TYPES = [
    "Apartment",
    "Compound Villa",
    "Standalone Villa",
    "Townhouse",
    "Penthouse",
    "Compound Apartment",
]
FURNISHINGS = ["Unfurnished", "Partly Furnished", "Fully Furnished"]

# Spreadsheet synonyms -> API property-type enum
_TYPE_SYNONYMS = {
    "apartment": "Apartment",
    "flat": "Apartment",
    "studio": "Apartment",
    "compound apartment": "Compound Apartment",
    "villa": "Standalone Villa",
    "standalone villa": "Standalone Villa",
    "independent villa": "Standalone Villa",
    "compound villa": "Compound Villa",
    "townhouse": "Townhouse",
    "town house": "Townhouse",
    "penthouse": "Penthouse",
}
# Spreadsheet synonyms -> API furnishing enum
_FURNISHING_SYNONYMS = {
    "unfurnished": "Unfurnished",
    "not furnished": "Unfurnished",
    "no": "Unfurnished",
    "partly furnished": "Partly Furnished",
    "part furnished": "Partly Furnished",
    "semi furnished": "Partly Furnished",
    "semi-furnished": "Partly Furnished",
    "fully furnished": "Fully Furnished",
    "furnished": "Fully Furnished",
    "yes": "Fully Furnished",
}


class ReferenceDataService:
    """Caches reference data and resolves sheet text to API IDs."""

    def __init__(self, client: PropertyOryxClient, config: OryxConfig | None = None) -> None:
        self._client = client
        self._config = config or get_config().oryx
        self._data: dict[str, Any] | None = None
        self._fetched_at = 0.0

    # ------------------------------------------------------------- caching

    def data(self) -> dict[str, Any]:
        """Return cached reference data, refreshing when the TTL expires."""
        ttl = self._config.reference_cache_seconds
        age = time.monotonic() - self._fetched_at
        if self._data is None or (ttl and age > ttl):
            self._data = self._client.reference_data()
            self._fetched_at = time.monotonic()
            logger.info(
                "Loaded Property Oryx reference data: %d locations, %d amenities",
                len(self._data.get("locations", [])),
                len(self._data.get("amenities", [])),
            )
        return self._data

    def refresh(self) -> None:
        """Force a reference-data refresh on the next lookup."""
        self._data = None

    # ------------------------------------------------------------- enums

    def resolve_type(self, value: str) -> str:
        """Map a sheet property type to an API type enum."""
        v = (value or "").strip()
        if v in PROPERTY_TYPES:
            return v
        mapped = _TYPE_SYNONYMS.get(v.lower())
        if mapped:
            return mapped
        raise ReferenceDataError(
            f"Property type {value!r} is not a Property Oryx type. Allowed: {', '.join(PROPERTY_TYPES)}"
        )

    def resolve_furnishing(self, value: str) -> str:
        """Map a sheet furnishing value to an API furnishing enum (default Unfurnished)."""
        v = (value or "").strip()
        if v in FURNISHINGS:
            return v
        return _FURNISHING_SYNONYMS.get(v.lower(), "Unfurnished")

    # ------------------------------------------------------------- locations

    def resolve_location(self, *names: str) -> int:
        """Resolve the first matching location name to its ID (district or area)."""
        locations = self.data().get("locations", [])
        for name in names:
            key = (name or "").strip().lower()
            if not key:
                continue
            for loc in locations:
                if loc.get("nameEn", "").strip().lower() == key:
                    return int(loc["value"])
            for loc in locations:  # looser contains match
                if key in loc.get("nameEn", "").strip().lower():
                    return int(loc["value"])
        raise ReferenceDataError(
            f"Location {', '.join(n for n in names if n)!r} not found in Property Oryx locations"
        )

    # ------------------------------------------------------------- amenities

    def resolve_amenities(self, names: list[str]) -> list[int]:
        """Map amenity names to IDs; unknown names are skipped with a warning."""
        if not names:
            return []
        amenities = self.data().get("amenities", [])
        by_name = {a.get("nameEn", "").strip().lower(): int(a["value"]) for a in amenities}
        resolved: list[int] = []
        for name in names:
            key = name.strip().lower()
            if key in by_name:
                resolved.append(by_name[key])
            else:
                match = next((v for n, v in by_name.items() if key in n or n in key), None)
                if match is not None:
                    resolved.append(match)
                else:
                    logger.warning("Amenity %r not found in Property Oryx reference data - skipped", name)
        return sorted(set(resolved))

    # ------------------------------------------- listing options (rent/sale)

    def _options(self, category: str, key: str) -> list[dict[str, Any]]:
        return self.data().get("listingOptions", {}).get(category, {}).get(key, [])

    def default_option(self, category: str, key: str) -> int | None:
        """First available option ID for a listing option group, or None."""
        options = self._options(category, key)
        return int(options[0]["value"]) if options else None

    def resolve_availability(self, sheet_value: str, fallback: int | None) -> int:
        """Sales listings require an availability ID. Resolve by name, config, or first option."""
        options = self._options("sale", "availability")
        key = (sheet_value or "").strip().lower()
        if key:
            for opt in options:
                if opt.get("nameEn", "").strip().lower() == key:
                    return int(opt["value"])
        if fallback is not None:
            return fallback
        if options:
            return int(options[0]["value"])
        raise ReferenceDataError("Sales listing requires an availability option, but none are available")
