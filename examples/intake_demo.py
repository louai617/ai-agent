"""Demonstrate the conversational listing intake end to end (offline).

Runs a few natural-language messages through the :class:`ListingCoordinator`
using the deterministic (non-AI) path, storing results in a temporary Excel
workbook. No API keys or network required.

    python examples/intake_demo.py
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from app.core.config import AIConfig, AppConfig
from app.services.ai import ContentGenerator
from app.services.coordinator import ListingCoordinator
from app.services.description import DescriptionGenerator
from app.storage.excel_store import ExcelPropertyStore

MESSAGES = [
    ("Hey, this is a 2BHK apartment in Lusail for 8,500 QAR.", None),
    ("Post a furnished 1 bedroom in The Pearl.", None),
    ("Villa in Al Waab for 15,000.", None),
]


def main() -> None:
    workbook = Path(tempfile.mkdtemp()) / "properties.xlsx"
    coordinator = ListingCoordinator(
        store=ExcelPropertyStore(workbook),
        config=AppConfig(),
        describer=DescriptionGenerator(ContentGenerator(AIConfig(enabled=False))),
    )

    for text, ref in MESSAGES:
        print("=" * 72)
        print(f"AGENT: {text}")
        result = coordinator.intake(text, property_ref=ref)
        print(f"\n[{result.status.value}] {result.property_ref}")
        print(result.message)
        print(f"\nAmenities: {', '.join(result.data.amenities)}")
        print(f"\n{result.completeness.as_text()}\n")

    print("=" * 72)
    print(f"Stored {len(coordinator.store.read_all())} listings in {workbook}")


if __name__ == "__main__":
    main()
