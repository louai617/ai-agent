"""Missing-information detection.

Before a listing can be published it must carry the details buyers/renters
expect. This module inspects a parsed :class:`~app.models.schemas.PropertyData`
and returns **only** the genuinely missing required fields, phrased as questions
a real estate coordinator would ask - never the full form.

The required set adapts to context:

* apartments vs villas (villas need plot size, maid/driver rooms),
* rent vs sale (rentals ask about bills, payment terms).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.domain import amenities as catalog
from app.models.schemas import PropertyData


@dataclass(frozen=True, slots=True)
class Question:
    """One missing-field prompt."""

    field: str
    text: str


@dataclass(frozen=True, slots=True)
class _Requirement:
    field: str
    question: str
    is_missing: Callable[[PropertyData, set[str] | None], bool]


def _blank(field: str) -> Callable[[PropertyData, set[str] | None], bool]:
    def check(data: PropertyData, _provided: set[str] | None) -> bool:
        value = getattr(data, field, "")
        return value in (None, "", [])
    return check


def _price_missing(data: PropertyData, _provided: set[str] | None) -> bool:
    return data.rent is None and data.sale_price is None


def _utilities_missing(data: PropertyData, provided: set[str] | None) -> bool:
    if data.utilities_included or data.utilities_excluded:
        return False
    if provided is not None:
        return "bills_included" not in provided
    return not data.bills_included  # no positive signal -> ask


# --------------------------------------------------------------------------- sets

def _price_question(data: PropertyData) -> str:
    if data.purpose.lower() == "sale":
        return "What is the selling price?"
    if data.purpose.lower() == "rent":
        return "What is the monthly rent?"
    return "Monthly rent or selling price?"


_COMMON: list[_Requirement] = [
    _Requirement("price", "", _price_missing),
    _Requirement("bathrooms", "Number of bathrooms?", lambda d, p: d.bathrooms is None),
    _Requirement("furnished", "Furnished or unfurnished?", _blank("furnished")),
    _Requirement("parking", "Parking included?", _blank("parking")),
]

_APARTMENT_EXTRA: list[_Requirement] = [
    _Requirement("bedrooms", "Number of bedrooms?", lambda d, p: d.bedrooms is None),
    _Requirement("utilities", "Bills included or excluded?", _utilities_missing),
    _Requirement("availability", "Availability date?", _blank("availability")),
]

_VILLA_EXTRA: list[_Requirement] = [
    _Requirement("bedrooms", "Number of bedrooms?", lambda d, p: d.bedrooms is None),
    _Requirement("plot_size", "Plot size?", lambda d, p: d.plot_size is None),
    _Requirement("maid_room", "Maid room?", _blank("maid_room")),
    _Requirement("driver_room", "Driver room?", _blank("driver_room")),
]

_RENT_EXTRA: list[_Requirement] = [
    _Requirement("payment_terms", "Payment terms (e.g. number of cheques)?", _blank("payment_terms")),
]


class MissingInfoDetector:
    """Determines which required fields are still missing."""

    def detect(self, data: PropertyData, provided: set[str] | None = None) -> list[Question]:
        """Return the missing required fields as questions (empty when complete)."""
        questions: list[Question] = []
        for req in self._requirements(data):
            if req.is_missing(data, provided):
                text = _price_question(data) if req.field == "price" else req.question
                questions.append(Question(field=req.field, text=text))
        return questions

    def is_ready(self, data: PropertyData, provided: set[str] | None = None) -> bool:
        """True when no required field is missing."""
        return not self.detect(data, provided)

    def format_prompt(self, questions: list[Question]) -> str:
        """Render questions the way a coordinator would ask them."""
        if not questions:
            return ""
        lines = ["I need a few more details before posting:", ""]
        lines += [f"• {q.text}" for q in questions]
        return "\n".join(lines)

    # ----------------------------------------------------------------- internals

    @staticmethod
    def _requirements(data: PropertyData) -> list[_Requirement]:
        kind = catalog.kind_for_type(data.property_type)
        reqs = list(_COMMON)
        reqs += _VILLA_EXTRA if kind == catalog.VILLA else _APARTMENT_EXTRA
        if data.sale_price is None and (data.rent is not None or data.purpose.lower() != "sale"):
            reqs += _RENT_EXTRA
        return reqs
