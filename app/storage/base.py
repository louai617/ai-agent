"""Storage abstraction for the property database.

``PropertyStore`` is the seam that keeps the workflow independent of *where*
properties are stored. The default implementation is Excel; a SQL backend
(Postgres, SQLite, ...) only needs to implement the same handful of methods.

Records are plain dicts keyed by **column/header name** (never by position),
which is what makes the schema flexible: new fields become new columns without
any code change. A :class:`StoredRecord` pairs those values with a stable
``row_id`` used to address the record on update.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class StoredRecord:
    """One stored property row.

    ``row_id`` is backend-defined but stable for the lifetime of the record
    (for Excel it is the 1-based worksheet row; for SQL it would be the primary
    key). ``values`` maps header name -> cell value.
    """

    row_id: int
    values: dict[str, Any] = field(default_factory=dict)

    def get(self, column: str, default: Any = None) -> Any:
        return self.values.get(column, default)


class PropertyStore(ABC):
    """Backend-agnostic CRUD + search over property records.

    All methods operate on header-keyed dicts so callers never depend on column
    order. Implementations must make ``append``/``update`` safe under concurrent
    writers.
    """

    @abstractmethod
    def headers(self) -> list[str]:
        """Return the current column names, in order."""

    @abstractmethod
    def ensure_columns(self, names: list[str]) -> None:
        """Create any of ``names`` that do not exist yet (idempotent)."""

    @abstractmethod
    def read_all(self) -> list[StoredRecord]:
        """Return every record."""

    @abstractmethod
    def get(self, row_id: int) -> StoredRecord | None:
        """Return one record by its ``row_id`` (or ``None``)."""

    @abstractmethod
    def find_by(self, column: str, value: Any) -> StoredRecord | None:
        """Return the first record whose ``column`` equals ``value`` (or ``None``)."""

    @abstractmethod
    def append(self, values: dict[str, Any]) -> StoredRecord:
        """Append a new record, creating unknown columns as needed."""

    @abstractmethod
    def update(self, row_id: int, values: dict[str, Any]) -> StoredRecord:
        """Update selected fields on an existing record (creates unknown columns)."""

    @abstractmethod
    def search(self, query: str, columns: list[str] | None = None) -> list[StoredRecord]:
        """Case-insensitive substring search across ``columns`` (all if ``None``)."""

    def upsert(self, key_column: str, values: dict[str, Any]) -> StoredRecord:
        """Insert, or update the existing record matching ``values[key_column]``.

        A convenience built on ``find_by``/``append``/``update`` so every backend
        gets idempotent writes for free.
        """
        key_value = values.get(key_column)
        existing = self.find_by(key_column, key_value) if key_value not in (None, "") else None
        if existing is None:
            return self.append(values)
        return self.update(existing.row_id, values)
