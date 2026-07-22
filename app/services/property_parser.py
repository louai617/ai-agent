"""Natural-language property parser.

Turns a free-form message from an agent into a structured
:class:`~app.models.schemas.PropertyData`, e.g.::

    "Hey, this is a 2BHK apartment in Lusail for 8,500 QAR."
    "Post a furnished 1 bedroom in The Pearl."
    "Villa in Ain Khaled."

The parser is deliberately **rule-based and deterministic** (regex + the Qatar
knowledge base) so it runs offline, is fully testable, and never fabricates
facts. It records which fields were *explicitly* stated (``provided``) versus
left blank, which the missing-information detector and completeness scorer rely
on. Amenities are intentionally *not* invented here - that is the amenities
generator's job.
"""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.core.logging import get_logger
from app.domain.qatar import Area, find_area_in_text
from app.models.schemas import PropertyData

logger = get_logger(__name__)


@dataclass(slots=True)
class ParseResult:
    """Outcome of parsing one message."""

    data: PropertyData
    #: Schema field names the user explicitly stated (not inferred/defaulted).
    provided: set[str] = field(default_factory=set)
    #: The community the text referred to, if recognised.
    area: Area | None = None

    def was_provided(self, *fields: str) -> bool:
        return all(f in self.provided for f in fields)


# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

# Specific type keyword -> canonical property type. Order matters (longest first).
_TYPE_KEYWORDS: list[tuple[str, str]] = [
    ("compound villa", "Compound Villa"),
    ("standalone villa", "Standalone Villa"),
    ("compound apartment", "Compound Apartment"),
    ("town house", "Townhouse"),
    ("townhouse", "Townhouse"),
    ("penthouse", "Penthouse"),
    ("duplex", "Apartment"),
    ("studio", "Apartment"),
    ("apartment", "Apartment"),
    ("flat", "Apartment"),
    ("villa", "Standalone Villa"),
]

_SALE_HINTS = ("for sale", "selling", "sell ", "freehold", "buy ", " sale")
_RENT_HINTS = ("for rent", "rent", "monthly", "per month", "/month", "/mo", "lease", "renting")

#: Above this figure an ambiguous price is treated as a sale, below it as rent.
_SALE_PRICE_THRESHOLD = 100_000


class PropertyParser:
    """Extracts structured property fields from natural language."""

    def parse(
        self,
        text: str,
        *,
        base: PropertyData | None = None,
        property_ref: str | None = None,
    ) -> ParseResult:
        """Parse ``text`` into a :class:`ParseResult`.

        ``base`` lets a follow-up message enrich an in-progress listing: fields
        already set on ``base`` are preserved unless the new text overrides them.
        """
        text = (text or "").strip()
        data = base.model_copy(deep=True) if base is not None else PropertyData(
            property_ref=property_ref or self._new_ref(),
            platform="propertyoryx",
        )
        if property_ref:
            data.property_ref = property_ref
        provided: set[str] = set()
        low = text.lower()

        area = find_area_in_text(text)
        self._apply_area(data, area, provided)
        self._parse_type(low, data, provided)
        self._parse_bedrooms(low, data, provided)
        self._parse_bathrooms(low, data, provided)
        self._parse_area_and_plot(low, data, provided)
        self._parse_furnished(low, data, provided)
        self._parse_purpose_and_price(low, data, provided)
        self._parse_rooms(low, data, provided)
        self._parse_features(text, low, data, provided)
        self._parse_utilities(low, data, provided)
        self._parse_availability(low, data, provided)
        self._parse_payment_terms(low, data, provided)

        if not data.created_date:
            data.created_date = datetime.now(UTC).strftime("%Y-%m-%d")
        logger.info(
            "Parsed listing %s: type=%s beds=%s area=%s provided=%d fields",
            data.property_ref, data.property_type or "?", data.bedrooms,
            area.name if area else "?", len(provided),
        )
        return ParseResult(data=data, provided=provided, area=area)

    # ----------------------------------------------------------------- helpers

    @staticmethod
    def _new_ref() -> str:
        # Timestamp + short random suffix so refs stay unique even when several
        # listings are created within the same second.
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        return f"PROP-{stamp}-{secrets.token_hex(2)}"

    def _apply_area(self, data: PropertyData, area: Area | None, provided: set[str]) -> None:
        if area is None:
            return
        data.community = area.name
        data.location = area.city
        provided.update({"community", "location"})
        if not data.district:
            data.district = area.name
        # Only use the area's typical property kind as a *hint* later, never here.

    def _parse_type(self, low: str, data: PropertyData, provided: set[str]) -> None:
        for keyword, canonical in _TYPE_KEYWORDS:
            if re.search(r"\b" + re.escape(keyword) + r"\b", low):
                data.property_type = canonical
                provided.add("property_type")
                if keyword == "studio":
                    data.bedrooms = 0
                    provided.add("bedrooms")
                return

    def _parse_bedrooms(self, low: str, data: PropertyData, provided: set[str]) -> None:
        if "bedrooms" in provided:  # e.g. studio already handled
            return
        m = re.search(r"(\d+)\s*(?:bhk|bedrooms?|beds?|br|b/r)\b", low)
        if m:
            data.bedrooms = int(m.group(1))
            provided.add("bedrooms")

    def _parse_bathrooms(self, low: str, data: PropertyData, provided: set[str]) -> None:
        m = re.search(r"(\d+)\s*(?:bathrooms?|baths?|wc)\b", low)
        if m:
            data.bathrooms = int(m.group(1))
            provided.add("bathrooms")

    def _parse_area_and_plot(self, low: str, data: PropertyData, provided: set[str]) -> None:
        unit = r"(?:sq\.?\s*m(?:et(?:er|re)s?)?|sqm|square\s*met(?:er|re)s?|m2|m²)"
        plot = re.search(r"plot(?:\s*(?:of|size|area))?\s*(?:of\s*)?([\d,]+)\s*" + unit, low) \
            or re.search(r"([\d,]+)\s*" + unit + r"\s*plot", low)
        area_text = low
        if plot:
            data.plot_size = float(plot.group(1).replace(",", ""))
            provided.add("plot_size")
            # Remove the plot phrase so it is not also counted as living area.
            area_text = low.replace(plot.group(0), " ")
        m = re.search(r"([\d,]+)\s*" + unit, area_text)
        if m:
            data.area_sqm = float(m.group(1).replace(",", ""))
            provided.add("area_sqm")

    def _parse_furnished(self, low: str, data: PropertyData, provided: set[str]) -> None:
        if re.search(r"\b(?:un\s?furnished|not furnished)\b", low):
            data.furnished = "Unfurnished"
        elif re.search(r"\b(?:semi|partly|part)\s*[- ]?\s*furnished\b", low):
            data.furnished = "Partly Furnished"
        elif re.search(r"\bfully furnished\b", low) or re.search(r"\bfurnished\b", low):
            data.furnished = "Fully Furnished"
        else:
            return
        provided.add("furnished")

    def _parse_purpose_and_price(self, low: str, data: PropertyData, provided: set[str]) -> None:
        purpose = ""
        if any(h in low for h in _SALE_HINTS):
            purpose = "Sale"
        elif any(h in low for h in _RENT_HINTS):
            purpose = "Rent"

        price = self._extract_price(low)
        if price is not None:
            if purpose == "Sale" or (purpose == "" and price >= _SALE_PRICE_THRESHOLD):
                data.sale_price = price
                purpose = purpose or "Sale"
                provided.add("sale_price")
            else:
                data.rent = price
                purpose = purpose or "Rent"
                provided.add("rent")
        if purpose:
            data.purpose = purpose
            provided.add("purpose")

    @staticmethod
    def _extract_price(low: str) -> float | None:
        patterns = [
            r"(?:qar|qr)\s*([\d,]+(?:\.\d+)?)",
            # number followed by a currency or a rent cadence (monthly/yearly/...)
            r"([\d,]+(?:\.\d+)?)\s*(?:qar|qr|riyals?|/?\s*month(?:ly)?|per\s*month|a\s*month|/?\s*year(?:ly)?|per\s*year)",
            # number introduced by a price keyword
            r"(?:for|price|asking|at|rent(?:al)?|selling(?:\s*price)?)\s+(?:qar\s*)?([\d,]+(?:\.\d+)?)",
            r"\b(\d{1,3}(?:,\d{3})+(?:\.\d+)?)\b",  # grouped thousands, e.g. 8,500
        ]
        for pattern in patterns:
            m = re.search(pattern, low)
            if m:
                try:
                    return float(m.group(1).replace(",", ""))
                except ValueError:
                    continue
        return None

    def _parse_rooms(self, low: str, data: PropertyData, provided: set[str]) -> None:
        if re.search(r"\bmaid'?s?\s*room\b", low):
            data.maid_room = "Yes"
            provided.add("maid_room")
        if re.search(r"\bdriver'?s?\s*room\b", low):
            data.driver_room = "Yes"
            provided.add("driver_room")

    def _parse_features(self, text: str, low: str, data: PropertyData, provided: set[str]) -> None:
        if "balcony" in low or "terrace" in low:
            data.balcony = "Yes"
            provided.add("balcony")
        if "parking" in low or "garage" in low:
            data.parking = "Covered Parking" if "covered" in low else "Yes"
            provided.add("parking")
        view = re.search(r"\b(sea|marina|city|pool|golf|park|lagoon|skyline)\s+view\b", low)
        if view:
            data.view = view.group(1).title() + " View"
            provided.add("view")
        floor = re.search(r"\b(?:on\s+the\s+)?(\d+)(?:st|nd|rd|th)?\s+floor\b", low) \
            or re.search(r"\bfloor\s+(\d+)\b", low)
        if floor:
            data.floor = floor.group(1)
            provided.add("floor")
        elif "ground floor" in low:
            data.floor = "Ground"
            provided.add("floor")
        elif "high floor" in low:
            data.floor = "High"
            provided.add("floor")

    def _parse_utilities(self, low: str, data: PropertyData, provided: set[str]) -> None:
        if re.search(r"\b(?:bills?|utilities)\s+(?:are\s+)?included\b", low) or "including bills" in low:
            data.bills_included = True
            provided.add("bills_included")
        elif re.search(r"\b(?:bills?|utilities)\s+(?:are\s+)?(?:not included|excluded)\b", low):
            data.bills_included = False
            provided.add("bills_included")
        util_map = {
            "water": "Water",
            "electricity": "Electricity",
            "internet": "Internet",
            "wifi": "Internet",
            "cooling": "Cooling",
            "kahramaa": "Electricity",
            "maintenance": "Maintenance",
            "cleaning": "Cleaning",
        }
        for keyword, label in util_map.items():
            incl = re.search(r"\b" + keyword + r"\b[^.,;]{0,20}\bincluded\b", low)
            excl = re.search(r"\b" + keyword + r"\b[^.,;]{0,20}\b(?:not included|excluded)\b", low)
            if incl and label not in data.utilities_included:
                data.utilities_included.append(label)
                provided.add("utilities_included")
            elif excl and label not in data.utilities_excluded:
                data.utilities_excluded.append(label)
                provided.add("utilities_excluded")

    def _parse_availability(self, low: str, data: PropertyData, provided: set[str]) -> None:
        if re.search(r"\b(?:available now|vacant|ready to move|move[- ]in ready|immediately)\b", low):
            data.availability = "Available Now"
            provided.add("availability")
            return
        m = re.search(r"available\s+(?:from\s+)?([\w\s]+?\d{4}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})", low)
        if m:
            data.availability = m.group(1).strip().title()
            provided.add("availability")

    def _parse_payment_terms(self, low: str, data: PropertyData, provided: set[str]) -> None:
        cheques = re.search(r"(\d+)\s*(?:cheques?|payments?)\b", low)
        if cheques:
            data.payment_terms = f"{cheques.group(1)} cheques"
            provided.add("payment_terms")
        elif "yearly" in low or "annually" in low or "per year" in low:
            data.payment_terms = "Yearly"
            provided.add("payment_terms")
        elif "quarterly" in low:
            data.payment_terms = "Quarterly"
            provided.add("payment_terms")
