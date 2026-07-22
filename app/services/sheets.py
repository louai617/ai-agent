"""Spreadsheet data source for the publishing pipeline.

Backed exclusively by a local Microsoft Excel (``.xlsx``) workbook through the
modular :mod:`app.storage` layer (Google Sheets support has been removed). The
storage layer maps by header *name*, handles concurrent writes and creates
missing columns automatically, so this module stays a thin adapter that turns
records into :class:`~app.models.schemas.PropertyData` and writes status back.

Swapping to SQL later means providing a different
:class:`~app.storage.base.PropertyStore` here - no change to the publisher.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime

from app.core.config import SheetConfig, get_config
from app.core.exceptions import SheetError
from app.core.logging import get_logger
from app.models.schemas import SHEET_COLUMNS, PropertyData
from app.storage.excel_store import ExcelPropertyStore

logger = get_logger(__name__)

# Columns the app is allowed to write back to the sheet.
WRITABLE_COLUMNS = ["Status", "Title", "Description", "Listing URL", "Error", "Updated Date"]


class SheetSource(ABC):
    """Abstract spreadsheet backend."""

    @abstractmethod
    def read_properties(self) -> list[PropertyData]:
        """Read all rows as validated PropertyData objects."""

    @abstractmethod
    def write_back(self, sheet_row: int, values: dict[str, str]) -> None:
        """Write selected columns back to one row (1-based sheet row number)."""

    def mark_posted(self, sheet_row: int, listing_url: str, title: str, description: str) -> None:
        """Convenience: mark a row Posted with its listing URL."""
        self.write_back(
            sheet_row,
            {
                "Status": "Posted",
                "Title": title,
                "Description": description,
                "Listing URL": listing_url,
                "Error": "",
                "Updated Date": datetime.now(UTC).strftime("%Y-%m-%d %H:%M"),
            },
        )

    def mark_failed(self, sheet_row: int, error: str) -> None:
        """Convenience: record a failure on the row."""
        self.write_back(
            sheet_row,
            {
                "Status": "Failed",
                "Error": error[:500],
                "Updated Date": datetime.now(UTC).strftime("%Y-%m-%d %H:%M"),
            },
        )


class ExcelSheetSource(SheetSource):
    """Local Excel (``.xlsx``) backend built on :class:`ExcelPropertyStore`."""

    def __init__(self, config: SheetConfig | None = None) -> None:
        self._config = config or get_config().sheet
        self._store = ExcelPropertyStore(
            self._config.resolved_excel_path(), self._config.worksheet_name
        )

    @property
    def store(self) -> ExcelPropertyStore:
        return self._store

    def read_properties(self) -> list[PropertyData]:
        try:
            records = self._store.read_all()
        except SheetError:
            raise
        properties: list[PropertyData] = []
        for rec in records:
            if not str(rec.get("Property ID", "")).strip():
                continue
            try:
                properties.append(PropertyData.from_sheet_row(rec.values, sheet_row=rec.row_id))
            except Exception as exc:  # noqa: BLE001 - one bad row must not stop the sync
                logger.error("Skipping invalid Excel row %d: %s", rec.row_id, exc)
        logger.info("Read %d properties from Excel", len(properties))
        return properties

    def write_back(self, sheet_row: int, values: dict[str, str]) -> None:
        allowed = {k: v for k, v in values.items() if k in WRITABLE_COLUMNS}
        if not allowed:
            return
        try:
            self._store.update(sheet_row, allowed)
        except SheetError as exc:
            raise SheetError(f"Failed to write back to Excel row {sheet_row}: {exc}") from exc


def create_sheet_source(config: SheetConfig | None = None) -> SheetSource:
    """Factory choosing the backend from configuration (Excel today)."""
    cfg = config or get_config().sheet
    # ``source_type == "sql"`` is reserved for a future PropertyStore backend.
    return ExcelSheetSource(cfg)


# Ordered header row for generating example sheets.
EXAMPLE_HEADER: list[str] = list(SHEET_COLUMNS.keys())
