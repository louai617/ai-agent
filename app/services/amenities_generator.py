"""Context-aware amenities generation.

When an agent mentions only a property type and a location, this module infers a
realistic amenity list from the Qatar knowledge base - premium coastal towers
get pools, gyms and concierge; standard villas get gardens and maid rooms; a
metro-served area adds "Near Metro". The result varies by *type* and *area* tier
rather than being a fixed list.

Generation is deterministic and offline. It never overwrites amenities the agent
supplied; it only fills the gap.
"""

from __future__ import annotations

from app.core.logging import get_logger
from app.domain import amenities as catalog
from app.domain.qatar import Area, area_or_default
from app.models.schemas import PropertyData

logger = get_logger(__name__)


class AmenitiesGenerator:
    """Suggests amenities appropriate to the property type and community."""

    def __init__(self, min_amenities: int = 6) -> None:
        self._min = min_amenities

    def generate(self, data: PropertyData, area: Area | None = None) -> list[str]:
        """Return a realistic amenity list for ``data`` (does not mutate it)."""
        area = area or area_or_default(data.community or data.district or data.location)
        kind = catalog.kind_for_type(data.property_type)

        suggested: list[str] = []
        self._extend(suggested, catalog.base_amenities(kind))
        self._extend(suggested, catalog.tier_amenities(kind, area.tier))
        if area.near_metro:
            self._extend(suggested, [catalog.METRO_AMENITY])

        # Reflect explicitly-stated features so they appear in the amenity list too.
        if data.balcony.strip().lower() == "yes":
            self._extend(suggested, ["Balcony"])
        if data.parking:
            self._extend(suggested, ["Covered Parking"])
        if data.maid_room.strip().lower() == "yes":
            self._extend(suggested, ["Maid Room"])
        if data.driver_room.strip().lower() == "yes":
            self._extend(suggested, ["Driver Room"])
        if data.furnished.lower().startswith("fully"):
            self._extend(suggested, ["Fully Furnished"])
        if data.view:
            self._extend(suggested, [data.view])

        logger.info(
            "Generated %d amenities for %s (%s, %s tier)",
            len(suggested), data.property_ref, kind, area.tier,
        )
        return suggested

    def ensure_amenities(self, data: PropertyData, area: Area | None = None) -> list[str]:
        """Fill ``data.amenities`` when empty and return the final list.

        Existing (agent-provided) amenities are kept and merged with generated
        ones so nothing is lost.
        """
        generated = self.generate(data, area)
        if not data.amenities:
            data.amenities = generated
        else:
            merged = list(data.amenities)
            self._extend(merged, generated)
            data.amenities = merged
        return data.amenities

    @staticmethod
    def _extend(target: list[str], items: list[str]) -> None:
        """Append items, skipping case-insensitive duplicates."""
        seen = {t.lower() for t in target}
        for item in items:
            if item.lower() not in seen:
                target.append(item)
                seen.add(item.lower())
