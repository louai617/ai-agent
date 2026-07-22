"""Professional, SEO-friendly listing description generation.

Produces publication-ready copy for portals such as Property Finder, Bayut and
Qatar Living. When a live Gemini client is available the prose is AI-written
(via :class:`~app.services.ai.ContentGenerator`); otherwise a strong,
landmark-aware template guarantees a natural, non-repetitive description with no
network dependency.

The description always draws on real facts only - property attributes plus the
curated Qatar landmarks for the community - so nothing is fabricated.
"""

from __future__ import annotations

from app.core.logging import get_logger
from app.domain.qatar import Area, area_or_default
from app.models.schemas import PropertyData
from app.services.ai import ContentGenerator

logger = get_logger(__name__)


def _bedroom_phrase(data: PropertyData) -> str:
    if data.bedrooms is None:
        return data.property_type or "property"
    label = "studio" if data.bedrooms == 0 else f"{data.bedrooms}-bedroom"
    return f"{label} {data.property_type.lower()}" if data.property_type else label


def _purpose_phrase(data: PropertyData) -> str:
    if data.sale_price is not None:
        return "for sale"
    if data.rent is not None:
        return "for rent"
    return "available"


class DescriptionGenerator:
    """Generates a title and a polished description for a property."""

    def __init__(self, content: ContentGenerator | None = None) -> None:
        self._content = content or ContentGenerator()

    # ------------------------------------------------------------------ public

    def generate_title(self, data: PropertyData) -> str:
        if self._content.ai_available:
            return self._content.generate_title(data)
        return self._template_title(data)

    def generate_description(self, data: PropertyData) -> str:
        """Return a professional description (AI when available, else template)."""
        if self._content.ai_available:
            try:
                return self._content.generate_description(data)
            except Exception:  # noqa: BLE001 - never block on the AI layer
                logger.exception("AI description failed; using landmark template")
        return self.build_professional_description(data)

    def ensure(self, data: PropertyData) -> PropertyData:
        """Fill empty title/description in place and return ``data``."""
        if not data.title:
            data.title = self.generate_title(data)
        if not data.description:
            data.description = self.generate_description(data)
        return data

    # --------------------------------------------------------------- templates

    def _template_title(self, data: PropertyData) -> str:
        parts: list[str] = []
        if data.furnished:
            parts.append(data.furnished)
        parts.append(_bedroom_phrase(data).title())
        parts.append(_purpose_phrase(data).title())
        where = data.community or data.district or data.location
        if where:
            parts.append(f"in {where}")
        title = " ".join(parts)
        price = data.price_display()
        if price:
            title = f"{title} — {price}"
        return title[:80]

    def build_professional_description(self, data: PropertyData, area: Area | None = None) -> str:
        """Deterministic, SEO-friendly, landmark-aware description."""
        area = area or area_or_default(data.community or data.district or data.location)
        where = data.community or data.district or data.location or area.city
        paragraphs: list[str] = []

        # 1. Headline.
        furnished = f"{data.furnished.lower()} " if data.furnished else ""
        headline = (
            f"Presenting this {furnished}{_bedroom_phrase(data)} {_purpose_phrase(data)} "
            f"in {where}, {area.city}."
        ).replace("  ", " ")
        paragraphs.append(headline)

        # 2. Key specifications (varied connectors to avoid repetition).
        specs: list[str] = []
        if data.area_sqm is not None:
            specs.append(f"a generous {data.area_sqm:g} sqm of living space")
        if data.plot_size is not None:
            specs.append(f"a {data.plot_size:g} sqm plot")
        if data.bathrooms is not None:
            specs.append(f"{data.bathrooms} bathroom{'s' if data.bathrooms != 1 else ''}")
        if data.floor:
            specs.append(f"positioned on the {data.floor.lower()} floor" if data.floor.isdigit()
                         else f"a {data.floor.lower()}-floor setting")
        if data.view:
            specs.append(f"stunning {data.view.lower()}")
        if data.parking:
            specs.append("dedicated covered parking")
        if data.maid_room.lower() == "yes":
            specs.append("a maid's room")
        if data.driver_room.lower() == "yes":
            specs.append("a driver's room")
        if specs:
            paragraphs.append("The home offers " + self._join(specs) + ".")

        # 3. Amenities.
        if data.amenities:
            top = data.amenities[:8]
            paragraphs.append("Residents enjoy " + self._join([a.lower() for a in top]) + ".")

        # 4. Landmarks / location selling points.
        if area.landmarks:
            paragraphs.append(
                "Ideally located, it is just moments from "
                + self._join(list(area.landmarks[:3])) + "."
            )

        # 5. Commercials.
        commercials: list[str] = []
        price = data.price_display()
        if price:
            commercials.append(f"Offered at {price}")
        if data.payment_terms:
            commercials.append(f"payable {data.payment_terms.lower()}")
        if data.bills_included:
            commercials.append("with bills included")
        elif data.utilities_included:
            commercials.append("with " + self._join([u.lower() for u in data.utilities_included]) + " included")
        if commercials:
            paragraphs.append(self._capitalise(", ".join(commercials)) + ".")

        # 6. Call to action.
        contact = data.agent or "our team"
        paragraphs.append(f"Contact {contact} today to arrange a viewing.")
        return "\n\n".join(paragraphs)

    # ----------------------------------------------------------------- helpers

    @staticmethod
    def _join(items: list[str]) -> str:
        items = [i for i in items if i]
        if not items:
            return ""
        if len(items) == 1:
            return items[0]
        return ", ".join(items[:-1]) + " and " + items[-1]

    @staticmethod
    def _capitalise(text: str) -> str:
        return text[:1].upper() + text[1:] if text else text
