"""Tests for the modular Excel storage layer and file locking."""

from __future__ import annotations

import threading

from app.storage.excel_store import ExcelPropertyStore
from app.storage.locking import FileLock


def _store(tmp_path) -> ExcelPropertyStore:
    return ExcelPropertyStore(tmp_path / "properties.xlsx")


def test_append_creates_file_and_row(tmp_path):
    store = _store(tmp_path)
    rec = store.append({"Property ID": "P-1", "Property Type": "Apartment"})
    assert rec.row_id == 2
    assert store.path.exists()
    all_rows = store.read_all()
    assert len(all_rows) == 1
    assert all_rows[0].get("Property ID") == "P-1"


def test_dynamic_columns_are_added(tmp_path):
    store = _store(tmp_path)
    store.append({"Property ID": "P-1", "Bedrooms": 2})
    # A brand new field must create its column without breaking anything.
    store.append({"Property ID": "P-2", "View": "Sea View", "Balcony": "Yes"})
    headers = store.headers()
    assert "View" in headers and "Balcony" in headers
    p2 = store.find_by("Property ID", "P-2")
    assert p2 is not None
    assert p2.get("View") == "Sea View"


def test_update_maps_by_header_not_index(tmp_path):
    store = _store(tmp_path)
    rec = store.append({"Property ID": "P-1", "Status": "Draft"})
    store.update(rec.row_id, {"Status": "Ready", "Listing URL": "https://x/1"})
    updated = store.get(rec.row_id)
    assert updated.get("Status") == "Ready"
    assert updated.get("Listing URL") == "https://x/1"


def test_upsert_is_idempotent_on_key(tmp_path):
    store = _store(tmp_path)
    store.upsert("Property ID", {"Property ID": "P-1", "Rent": 5000})
    store.upsert("Property ID", {"Property ID": "P-1", "Rent": 6000})
    rows = store.read_all()
    assert len(rows) == 1
    assert str(rows[0].get("Rent")) == "6000"


def test_search_matches_substring(tmp_path):
    store = _store(tmp_path)
    store.append({"Property ID": "P-1", "Community": "Lusail"})
    store.append({"Property ID": "P-2", "Community": "The Pearl"})
    results = store.search("pearl")
    assert len(results) == 1
    assert results[0].get("Property ID") == "P-2"


def test_list_values_are_serialised(tmp_path):
    store = _store(tmp_path)
    store.append({"Property ID": "P-1", "Amenities": ["Gym", "Pool"], "Bills Included": True})
    rec = store.find_by("Property ID", "P-1")
    assert rec.get("Amenities") == "Gym, Pool"
    assert rec.get("Bills Included") == "Yes"


def test_concurrent_appends_do_not_corrupt(tmp_path):
    store = _store(tmp_path)
    store.ensure_columns(["Property ID"])

    def worker(n: int) -> None:
        store.append({"Property ID": f"P-{n}"})

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    rows = store.read_all()
    refs = {r.get("Property ID") for r in rows}
    assert len(rows) == 12
    assert refs == {f"P-{i}" for i in range(12)}


def test_file_lock_is_reentrant(tmp_path):
    target = tmp_path / "x.xlsx"
    lock = FileLock(target)
    with lock, lock:  # reentrant acquire on the same thread must not deadlock
        assert lock._lock_path.exists()
    assert not lock._lock_path.exists()
