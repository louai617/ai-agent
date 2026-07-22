"""Modular storage layer.

The property database lives behind the :class:`~app.storage.base.PropertyStore`
interface so the concrete backend can change without touching callers. The
default backend is an Excel (``.xlsx``) workbook
(:class:`~app.storage.excel_store.ExcelPropertyStore`); a future SQL backend
only has to implement the same interface.
"""

from __future__ import annotations

from app.storage.base import PropertyStore, StoredRecord
from app.storage.excel_store import ExcelPropertyStore

__all__ = ["ExcelPropertyStore", "PropertyStore", "StoredRecord"]
