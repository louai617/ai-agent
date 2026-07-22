"""Property completeness scoring.

Produces a weighted score across the dimensions that make a listing
publication-ready::

    Property Completeness
    • Basic Info    ✓
    • Pricing       ✓
    • Amenities     ✓
    • Utilities     ✓
    • Images        ✗
    • Description   ✗
    Overall: 86% Complete

Each category is scored as a fraction of its sub-checks, then weighted, so the
overall number reflects partial progress. The coordinator publishes only when
the score clears a configurable threshold.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.schemas import PropertyData


@dataclass(frozen=True, slots=True)
class CategoryScore:
    name: str
    fraction: float  # 0.0 - 1.0
    weight: float

    @property
    def complete(self) -> bool:
        return self.fraction >= 0.999

    @property
    def mark(self) -> str:
        if self.complete:
            return "✓"
        if self.fraction > 0:
            return "~"
        return "✗"


@dataclass(frozen=True, slots=True)
class CompletenessReport:
    categories: list[CategoryScore]
    percent: int

    def as_text(self) -> str:
        lines = ["Property Completeness", ""]
        width = max(len(c.name) for c in self.categories)
        for cat in self.categories:
            lines.append(f"• {cat.name.ljust(width)}  {cat.mark}")
        lines += ["", f"Overall: {self.percent}% Complete"]
        return "\n".join(lines)

    def missing_categories(self) -> list[str]:
        return [c.name for c in self.categories if not c.complete]


def _fraction(checks: list[bool]) -> float:
    return sum(1 for c in checks if c) / len(checks) if checks else 0.0


class CompletenessScorer:
    """Scores a property's readiness for publication."""

    def __init__(self, threshold_percent: int = 90) -> None:
        self._threshold = threshold_percent

    def score(self, data: PropertyData) -> CompletenessReport:
        has_price = data.rent is not None or data.sale_price is not None
        is_villa = "villa" in data.property_type.lower() or "townhouse" in data.property_type.lower()

        basic = _fraction([
            bool(data.property_type),
            data.bedrooms is not None,
            data.bathrooms is not None,
            bool(data.location or data.community or data.district),
            (data.plot_size is not None) if is_villa else (data.area_sqm is not None),
        ])
        pricing = _fraction([
            has_price,
            bool(data.purpose),
            bool(data.payment_terms) or data.sale_price is not None,
        ])
        amenities = _fraction([len(data.amenities) >= 3, len(data.amenities) >= 6])
        utilities = _fraction([
            bool(data.utilities_included or data.utilities_excluded) or data.bills_included,
        ])
        images = _fraction([bool(data.images_folder)])
        description = _fraction([bool(data.description), len(data.description) >= 50])

        categories = [
            CategoryScore("Basic Info", basic, 25),
            CategoryScore("Pricing", pricing, 20),
            CategoryScore("Amenities", amenities, 15),
            CategoryScore("Utilities", utilities, 10),
            CategoryScore("Images", images, 15),
            CategoryScore("Description", description, 15),
        ]
        total_weight = sum(c.weight for c in categories)
        earned = sum(c.weight * c.fraction for c in categories)
        percent = round(earned / total_weight * 100) if total_weight else 0
        return CompletenessReport(categories=categories, percent=percent)

    def meets_threshold(self, data: PropertyData) -> bool:
        return self.score(data).percent >= self._threshold

    @property
    def threshold(self) -> int:
        return self._threshold
