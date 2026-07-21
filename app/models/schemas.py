"""Pydantic schemas used between the sheet layer, services and platforms.

``PropertyData`` is the canonical, validated in-memory representation of one
spreadsheet row. Platform modules receive this object plus the processed
image paths and must not read the spreadsheet themselves.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

# Spreadsheet column -> schema field mapping (order matches the sheet)
SHEET_COLUMNS: dict[str, str] = {
    "Property ID": "property_ref",
    "Platform": "platform",
    "Status": "status",
    "Title": "title",
    "Description": "description",
    "Category": "category",
    "Property Type": "property_type",
    "Bedrooms": "bedrooms",
    "Bathrooms": "bathrooms",
    "Area": "area_sqm",
    "Rent": "rent",
    "Sale Price": "sale_price",
    "Bills Included": "bills_included",
    "Furnished": "furnished",
    "Location": "location",
    "District": "district",
    "Latitude": "latitude",
    "Longitude": "longitude",
    "Amenities": "amenities",
    "Images Folder": "images_folder",
    "Video": "video_url",
    "Agent": "agent",
    "Phone": "phone",
    "WhatsApp": "whatsapp",
    "Email": "email",
    "Listing URL": "listing_url",
    "Error": "error",
    "Created Date": "created_date",
    "Updated Date": "updated_date",
}

REQUIRED_FIELDS = ["property_ref", "platform", "category", "property_type", "location", "images_folder"]


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except ValueError:
        return None


def _to_int(value: Any) -> int | None:
    f = _to_float(value)
    return int(f) if f is not None else None


def _to_bool(value: Any) -> bool:
    return str(value).strip().lower() in {"yes", "true", "1", "y", "included"}


class PropertyData(BaseModel):
    """Validated property row."""

    property_ref: str
    platform: str
    status: str = "Pending"
    title: str = ""
    title_ar: str = ""
    description: str = ""
    description_ar: str = ""
    category: str = ""
    availability: str = ""
    property_type: str = ""
    bedrooms: int | None = None
    bathrooms: int | None = None
    area_sqm: float | None = None
    rent: float | None = None
    sale_price: float | None = None
    bills_included: bool = False
    furnished: str = ""
    location: str = ""
    district: str = ""
    latitude: float | None = None
    longitude: float | None = None
    amenities: list[str] = Field(default_factory=list)
    images_folder: str = ""
    video_url: str = ""
    agent: str = ""
    phone: str = ""
    whatsapp: str = ""
    email: str = ""
    listing_url: str = ""
    error: str = ""
    sheet_row: int | None = None
    created_date: str = ""
    updated_date: str = ""

    @field_validator("platform")
    @classmethod
    def _normalise_platform(cls, v: str) -> str:
        return v.strip().lower().replace(" ", "")

    @classmethod
    def from_sheet_row(cls, row: dict[str, Any], sheet_row: int | None = None) -> PropertyData:
        """Build from a raw sheet row keyed by spreadsheet column names."""
        data: dict[str, Any] = {}
        for column, field in SHEET_COLUMNS.items():
            data[field] = row.get(column, "")
        amenities_raw = str(data.get("amenities") or "")
        return cls(
            property_ref=str(data["property_ref"]).strip(),
            platform=str(data["platform"]).strip(),
            status=str(data["status"]).strip() or "Pending",
            title=str(data["title"]).strip(),
            title_ar=str(row.get("Title AR", "") or "").strip(),
            description=str(data["description"]).strip(),
            description_ar=str(row.get("Description AR", "") or "").strip(),
            category=str(data["category"]).strip(),
            availability=str(row.get("Availability", "") or "").strip(),
            property_type=str(data["property_type"]).strip(),
            bedrooms=_to_int(data["bedrooms"]),
            bathrooms=_to_int(data["bathrooms"]),
            area_sqm=_to_float(data["area_sqm"]),
            rent=_to_float(data["rent"]),
            sale_price=_to_float(data["sale_price"]),
            bills_included=_to_bool(data["bills_included"]),
            furnished=str(data["furnished"]).strip(),
            location=str(data["location"]).strip(),
            district=str(data["district"]).strip(),
            latitude=_to_float(data["latitude"]),
            longitude=_to_float(data["longitude"]),
            amenities=[a.strip() for a in amenities_raw.split(",") if a.strip()],
            images_folder=str(data["images_folder"]).strip(),
            video_url=str(data["video_url"]).strip(),
            agent=str(data["agent"]).strip(),
            phone=str(data["phone"]).strip(),
            whatsapp=str(data["whatsapp"]).strip(),
            email=str(data["email"]).strip(),
            listing_url=str(data["listing_url"]).strip(),
            error=str(data["error"]).strip(),
            sheet_row=sheet_row,
            created_date=str(data["created_date"]).strip(),
            updated_date=str(data["updated_date"]).strip(),
        )

    def missing_required_fields(self) -> list[str]:
        """Names of required fields that are empty."""
        missing = [f for f in REQUIRED_FIELDS if not getattr(self, f)]
        if self.rent is None and self.sale_price is None:
            missing.append("rent or sale_price")
        return missing

    def price_display(self) -> str:
        """Human-readable price string for AI prompts and titles."""
        if self.rent is not None:
            return f"QAR {self.rent:,.0f}/month"
        if self.sale_price is not None:
            return f"QAR {self.sale_price:,.0f}"
        return ""

    def listing_category(self) -> str:
        """Property Oryx listing category: 'rent' when a rent is set, else 'sale'."""
        return "rent" if self.rent is not None else "sale"

    def content_hash(self) -> str:
        """Stable hash for duplicate detection (platform + key facts)."""
        basis = "|".join(
            [
                self.platform,
                self.property_type,
                str(self.bedrooms),
                str(self.area_sqm),
                self.location.lower(),
                self.district.lower(),
                str(self.rent),
                str(self.sale_price),
            ]
        )
        return hashlib.sha256(basis.encode("utf-8")).hexdigest()

    def to_db_dict(self) -> dict[str, Any]:
        """Map to the Property ORM column names."""
        return {
            "property_ref": self.property_ref,
            "platform": self.platform,
            "title": self.title,
            "title_ar": self.title_ar,
            "description": self.description,
            "description_ar": self.description_ar,
            "category": self.category,
            "availability": self.availability,
            "property_type": self.property_type,
            "bedrooms": self.bedrooms,
            "bathrooms": self.bathrooms,
            "area_sqm": self.area_sqm,
            "rent": self.rent,
            "sale_price": self.sale_price,
            "bills_included": self.bills_included,
            "furnished": self.furnished,
            "location": self.location,
            "district": self.district,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "amenities": ", ".join(self.amenities),
            "images_folder": self.images_folder,
            "video_url": self.video_url,
            "agent": self.agent,
            "phone": self.phone,
            "whatsapp": self.whatsapp,
            "email": self.email,
            "sheet_row": self.sheet_row,
            "content_hash": self.content_hash(),
        }


class PublishResult(BaseModel):
    """Result returned by a platform's publish()."""

    success: bool
    listing_id: str = ""
    listing_url: str = ""
    error: str = ""
    duration_seconds: float = 0.0
    published_at: datetime | None = None
