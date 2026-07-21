"""Shared test fixtures: isolated temp database and image folders."""

from __future__ import annotations

import pytest

from app.database import engine as db_engine


@pytest.fixture()
def temp_db(tmp_path):
    """Fresh SQLite database per test."""
    db_engine.dispose_engine()
    db_engine.init_engine(str(tmp_path / "test.db"))
    yield
    db_engine.dispose_engine()


@pytest.fixture()
def sample_row() -> dict:
    """A valid raw sheet row."""
    return {
        "Property ID": "PROP-100",
        "Platform": "propertyoryx",
        "Status": "Pending",
        "Title": "",
        "Description": "",
        "Category": "Residential",
        "Property Type": "Apartment",
        "Bedrooms": "2",
        "Bathrooms": "2",
        "Area": "110",
        "Rent": "7500",
        "Sale Price": "",
        "Bills Included": "Yes",
        "Furnished": "Fully Furnished",
        "Location": "Doha",
        "District": "The Pearl",
        "Latitude": "25.3691",
        "Longitude": "51.5511",
        "Amenities": "Pool, Gym, Parking",
        "Images Folder": "",
        "Video": "",
        "Agent": "Sara Ahmed",
        "Phone": "+97455512345",
        "WhatsApp": "+97455512345",
        "Email": "sara@eliterealty.qa",
        "Listing URL": "",
        "Error": "",
        "Created Date": "2026-07-15",
        "Updated Date": "",
    }
