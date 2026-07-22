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

# Spreadsheet column -> schema field mapping (order matches the sheet).
#
# Columns are matched by *name*, so new fields can be added here (or appear in a
# workbook) without breaking anything: the storage layer maps by header, not by
# position.
SHEET_COLUMNS: dict[str, str] = {
    "Property ID": "property_ref",
    "Platform": "platform",
    "Status": "status",
    "Title": "title",
    "Description": "description",
    "Category": "category",
    "Purpose": "purpose",
    "Property Type": "property_type",
    "Bedrooms": "bedrooms",
    "Bathrooms": "bathrooms",
    "Area": "area_sqm",
    "Plot Size": "plot_size",
    "Rent": "rent",
    "Sale Price": "sale_price",
    "Payment Terms": "payment_terms",
    "Bills Included": "bills_included",
    "Utilities Included": "utilities_included",
    "Utilities Excluded": "utilities_excluded",
    "Furnished": "furnished",
    "Location": "location",
    "Community": "community",
    "Building": "building",
    "District": "district",
    "Floor": "floor",
    "View": "view",
    "Balcony": "balcony",
    "Parking": "parking",
    "Maid Room": "maid_room",
    "Driver Room": "driver_room",
    "Availability": "availability",
    "Latitude": "latitude",
    "Longitude": "longitude",
    "Amenities": "amenities",
    "Images Folder": "images_folder",
    "Video": "video_url",
    "Agent": "agent",
    "Phone": "phone",
    "WhatsApp": "whatsapp",
    "Email": "email",
    "Title AR": "title_ar",
    "Description AR": "description_ar",
    "Listing URL": "listing_url",
    "Error": "error",
    "Created Date": "created_date",
    "Updated Date": "updated_date",
}

REQUIRED_FIELDS = ["property_ref", "platform", "category", "property_type", "location", "images_folder"]

#: Fields stored as comma-separated lists in a single spreadsheet cell.
LIST_FIELDS = {"amenities", "utilities_included", "utilities_excluded"}

#: Schema fields parsed as integers / floats / booleans from raw cells.
_INT_FIELDS = {"bedrooms", "bathrooms"}
_FLOAT_FIELDS = {"area_sqm", "plot_size", "rent", "sale_price", "latitude", "longitude"}
_BOOL_FIELDS = {"bills_included"}
#: Optional numeric fields that legitimately hold ``None``.
_NULLABLE_FIELDS = _INT_FIELDS | _FLOAT_FIELDS


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


def _to_list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [str(v).strip() for v in value if str(v).strip()]
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


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
    purpose: str = ""  # "Rent" | "Sale" - explicit intent (derived if blank)
    availability: str = ""
    property_type: str = ""
    bedrooms: int | None = None
    bathrooms: int | None = None
    area_sqm: float | None = None
    plot_size: float | None = None  # villa/land plot area in sqm
    rent: float | None = None
    sale_price: float | None = None
    payment_terms: str = ""  # e.g. "Yearly", "Monthly", "4 cheques"
    bills_included: bool = False
    utilities_included: list[str] = Field(default_factory=list)
    utilities_excluded: list[str] = Field(default_factory=list)
    furnished: str = ""
    location: str = ""
    community: str = ""
    building: str = ""
    district: str = ""
    floor: str = ""
    view: str = ""
    balcony: str = ""  # "Yes" | "No" | "" (unknown)
    parking: str = ""  # "Yes", "2 spaces", "Covered", ...
    maid_room: str = ""
    driver_room: str = ""
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
        """Build from a raw sheet row keyed by spreadsheet column names.

        The mapping is driven entirely by :data:`SHEET_COLUMNS`, so the row may
        contain extra columns (ignored) or omit columns (defaulted). This keeps
        the parser tolerant of a flexible, growing workbook schema.
        """
        values: dict[str, Any] = {}
        for column, field in SHEET_COLUMNS.items():
            if column not in row:
                continue
            raw = row.get(column, "")
            if field in _INT_FIELDS:
                values[field] = _to_int(raw)
            elif field in _FLOAT_FIELDS:
                values[field] = _to_float(raw)
            elif field in _BOOL_FIELDS:
                values[field] = _to_bool(raw)
            elif field in LIST_FIELDS:
                values[field] = _to_list(raw)
            else:
                values[field] = str(raw or "").strip()
        values["status"] = values.get("status") or "Pending"
        values["sheet_row"] = sheet_row
        # Keep None only for genuinely optional numeric fields; drop it elsewhere
        # so the model defaults apply cleanly.
        return cls(**{k: v for k, v in values.items() if v is not None or k in _NULLABLE_FIELDS})

    def to_sheet_dict(self) -> dict[str, Any]:
        """Serialise to a header-keyed dict for the Excel/storage layer.

        Lists are joined with ", " and booleans rendered as Yes/No so the values
        drop straight into spreadsheet cells.
        """
        out: dict[str, Any] = {}
        for column, field in SHEET_COLUMNS.items():
            value = getattr(self, field, "")
            if field in LIST_FIELDS:
                value = ", ".join(value)
            elif field in _BOOL_FIELDS:
                value = "Yes" if value else "No"
            elif value is None:
                value = ""
            out[column] = value
        return out

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
