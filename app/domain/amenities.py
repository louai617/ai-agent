"""Amenity catalogs keyed by property kind and location tier.

The :class:`~app.services.amenities_generator.AmenitiesGenerator` composes a
realistic amenity list from these building blocks:

    base(kind) + tier_extras(kind, tier) + contextual (metro, furnished, ...)

Amenity names follow common Qatar portal wording (Property Finder / Bayut /
Qatar Living) so they resolve cleanly downstream.
"""

from __future__ import annotations

# Property kinds we generate for. Specific API types collapse to one of these.
APARTMENT = "apartment"
VILLA = "villa"

# Map detailed property types -> a generation "kind".
KIND_BY_TYPE: dict[str, str] = {
    "apartment": APARTMENT,
    "flat": APARTMENT,
    "studio": APARTMENT,
    "penthouse": APARTMENT,
    "compound apartment": APARTMENT,
    "duplex": APARTMENT,
    "villa": VILLA,
    "standalone villa": VILLA,
    "compound villa": VILLA,
    "townhouse": VILLA,
    "town house": VILLA,
}

# Amenities every property of a kind reasonably has.
_BASE: dict[str, list[str]] = {
    APARTMENT: [
        "Central AC",
        "Covered Parking",
        "Security",
        "24/7 Maintenance",
        "Built-in Wardrobes",
        "High-speed Elevators",
    ],
    VILLA: [
        "Central AC",
        "Covered Parking",
        "Security",
        "Private Garden",
        "Built-in Wardrobes",
        "Maid Room",
    ],
}

# Extra amenities layered on by location tier (cumulative: standard < premium < luxury).
_TIER_EXTRAS: dict[str, dict[str, list[str]]] = {
    APARTMENT: {
        "standard": ["Balcony", "Children's Play Area"],
        "premium": [
            "Balcony",
            "Gym",
            "Swimming Pool",
            "Reception",
            "Children's Play Area",
        ],
        "luxury": [
            "Balcony",
            "Fully Equipped Gym",
            "Temperature-controlled Swimming Pool",
            "Concierge Service",
            "Reception",
            "Children's Play Area",
            "Sauna & Steam Room",
            "Landscaped Podium",
            "Retail & Dining",
        ],
    },
    VILLA: {
        "standard": ["Balcony", "Storage Room"],
        "premium": [
            "Private Garden",
            "Shared Swimming Pool",
            "Gym",
            "Children's Play Area",
            "Driver Room",
        ],
        "luxury": [
            "Private Swimming Pool",
            "Landscaped Garden",
            "Driver Room",
            "Smart Home System",
            "Private Elevator",
            "Home Cinema",
            "Guest Majlis",
        ],
    },
}

#: Added when the community is served by Doha Metro.
METRO_AMENITY = "Near Metro"


def base_amenities(kind: str) -> list[str]:
    return list(_BASE.get(kind, _BASE[APARTMENT]))


def tier_amenities(kind: str, tier: str) -> list[str]:
    by_tier = _TIER_EXTRAS.get(kind, _TIER_EXTRAS[APARTMENT])
    return list(by_tier.get(tier, by_tier["standard"]))


def kind_for_type(property_type: str) -> str:
    """Collapse a specific property type to a generation kind (default apartment)."""
    return KIND_BY_TYPE.get((property_type or "").strip().lower(), APARTMENT)
