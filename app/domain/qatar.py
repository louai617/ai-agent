"""Knowledge base of Qatar communities used to enrich listings.

Each area maps to:

* ``tier``      - ``"luxury"`` | ``"premium"`` | ``"standard"``; drives which
  amenities are generated and the tone of the description.
* ``city``      - the parent city/municipality.
* ``kind``      - a hint of the typical property there (``"apartment"`` /
  ``"villa"`` / ``None``); used only when the user did not state a type.
* ``near_metro``- whether Doha Metro is within easy reach.
* ``landmarks`` - nearby points of interest for SEO-friendly descriptions.

The list is intentionally curated (not exhaustive). Unknown areas fall back to
``DEFAULT_AREA`` so the system degrades gracefully.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Area:
    """One known community/area."""

    name: str
    tier: str = "standard"
    city: str = "Doha"
    kind: str | None = None
    near_metro: bool = False
    landmarks: tuple[str, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Curated Qatar communities
# ---------------------------------------------------------------------------

_AREAS: tuple[Area, ...] = (
    # ---- Luxury waterfront / marquee districts -----------------------------
    Area("The Pearl", "luxury", "Doha", "apartment", False,
         ("Porto Arabia", "Medina Centrale", "Qanat Quartier", "the Marina")),
    Area("Gewan Island", "luxury", "Doha", "villa", False, ("The Pearl", "Crystal Walkway")),
    Area("Lusail", "luxury", "Lusail", "apartment", True,
         ("Lusail Marina", "Place Vendome", "Lusail Boulevard", "Lusail Stadium")),
    Area("Lusail Marina", "luxury", "Lusail", "apartment", True, ("Lusail Boulevard", "the Marina Promenade")),
    Area("Fox Hills", "premium", "Lusail", "apartment", True, ("Lusail Boulevard", "Place Vendome")),
    Area("Qetaifan Island", "luxury", "Lusail", "villa", False, ("Meryal Waterpark", "the beachfront")),
    Area("West Bay", "luxury", "Doha", "apartment", True,
         ("City Center Mall", "the Corniche", "Doha Exhibition Centre")),
    Area("West Bay Lagoon", "luxury", "Doha", "villa", False, ("the Corniche", "Katara")),
    Area("Katara", "luxury", "Doha", "apartment", False, ("Katara Cultural Village", "Katara Beach")),
    Area("Msheireb", "luxury", "Doha", "apartment", True,
         ("Msheireb Downtown Doha", "Souq Waqif", "the National Museum of Qatar")),
    Area("Msheireb Downtown", "luxury", "Doha", "apartment", True, ("Souq Waqif", "Msheireb Metro Station")),
    # ---- Premium residential ----------------------------------------------
    Area("Al Sadd", "premium", "Doha", "apartment", True, ("Al Sadd Metro Station", "Royal Plaza Mall")),
    Area("Bin Mahmoud", "premium", "Doha", "apartment", True, ("Fereej Bin Mahmoud", "Al Sadd")),
    Area("Fereej Bin Mahmoud", "premium", "Doha", "apartment", True, ("Al Sadd", "D-Ring Road")),
    Area("Al Dafna", "premium", "Doha", "apartment", True, ("the Corniche", "City Center Mall")),
    Area("Marina District", "premium", "Lusail", "apartment", True, ("Lusail Marina",)),
    Area("Al Erkyah", "premium", "Lusail", "apartment", True, ("Lusail City",)),
    # ---- Villa & compound suburbs -----------------------------------------
    Area("Ain Khaled", "standard", "Doha", "villa", False, ("Ezdan Mall", "B-Ring Road")),
    Area("Al Waab", "premium", "Doha", "villa", False, ("Villaggio Mall", "Aspire Park", "Aspire Zone")),
    Area("Aspire Zone", "premium", "Doha", "villa", False, ("Aspire Park", "Villaggio Mall", "Khalifa Stadium")),
    Area("Abu Hamour", "standard", "Doha", "villa", False, ("Dar Al Salam Mall", "B-Ring Road")),
    Area("Al Thumama", "standard", "Doha", "villa", False, ("Hamad International Airport", "Al Thumama Stadium")),
    Area("Muaither", "standard", "Doha", "villa", False, ("Al Rayyan",)),
    Area("Al Gharrafa", "standard", "Doha", "villa", False, ("Landmark Mall", "Qatar Foundation")),
    Area("Al Kheesa", "standard", "Doha", "villa", False, ("Al Kheesa",)),
    Area("Umm Salal", "standard", "Umm Salal", "villa", False, ("Umm Salal Mohammed",)),
    Area("Al Wakrah", "standard", "Al Wakrah", "villa", False, ("Al Wakrah Souq", "Al Janoub Stadium")),
    Area("Al Wukair", "standard", "Al Wakrah", "villa", False, ("Al Wakrah",)),
    Area("Al Duhail", "premium", "Doha", "villa", True, ("Al Duhail Metro Station",)),
    Area("Old Airport", "standard", "Doha", "apartment", True, ("Old Airport Metro Station", "Al Matar Mall")),
    Area("Al Mansoura", "standard", "Doha", "apartment", True, ("Al Mansoura Metro Station",)),
    Area("Najma", "standard", "Doha", "apartment", True, ("Najma Metro Station",)),
    Area("Nuaija", "standard", "Doha", "villa", False, ("Al Hilal", "D-Ring Road")),
    Area("Al Aziziyah", "standard", "Doha", "villa", False, ("Villaggio Mall", "Aspire Zone")),
    Area("Muraikh", "standard", "Doha", "villa", False, ("Al Shamal Road",)),
    Area("Bani Hajer", "standard", "Doha", "villa", False, ("Al Rayyan",)),
)

DEFAULT_AREA = Area("Qatar", "standard", "Doha", None, False, ())

# Fast lookup by lowercased name.
_BY_NAME: dict[str, Area] = {a.name.lower(): a for a in _AREAS}

# Longest names first so "West Bay Lagoon" matches before "West Bay".
_MATCH_ORDER: tuple[Area, ...] = tuple(sorted(_AREAS, key=lambda a: len(a.name), reverse=True))


def all_area_names() -> list[str]:
    """Every known community name (for parser matching and UI hints)."""
    return [a.name for a in _AREAS]


def lookup_area(name: str) -> Area | None:
    """Exact (case-insensitive) area lookup."""
    return _BY_NAME.get((name or "").strip().lower())


def find_area_in_text(text: str) -> Area | None:
    """Return the first known community mentioned anywhere in ``text``.

    Matching is longest-name-first and word-boundary aware so "Al Waab" is not
    matched inside an unrelated word.
    """
    import re

    haystack = f" {text.lower()} "
    for area in _MATCH_ORDER:
        pattern = r"\b" + re.escape(area.name.lower()) + r"\b"
        if re.search(pattern, haystack):
            return area
    return None


def area_or_default(name: str) -> Area:
    """Known area for ``name`` or a neutral default (never ``None``)."""
    return lookup_area(name) or DEFAULT_AREA
