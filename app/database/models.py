"""SQLAlchemy ORM models.

Tables: properties, accounts, platforms, images, jobs, logs, settings,
statistics. All timestamps are stored in UTC.
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    """Timezone-aware UTC now (SQLite stores naive; we normalise on read)."""
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


class PropertyStatus(enum.StrEnum):
    """Lifecycle of a property listing."""

    PENDING = "Pending"
    PUBLISHING = "Publishing"
    PUBLISHED = "Published"
    FAILED = "Failed"
    NEEDS_REVIEW = "Needs Review"
    ARCHIVED = "Archived"
    DELETED = "Deleted"


class JobStatus(enum.StrEnum):
    """Lifecycle of a queued publish job."""

    QUEUED = "Queued"
    RUNNING = "Running"
    PAUSED = "Paused"
    COMPLETED = "Completed"
    FAILED = "Failed"
    CANCELLED = "Cancelled"


class Property(Base):
    """A property row mirrored from the spreadsheet."""

    __tablename__ = "properties"
    __table_args__ = (UniqueConstraint("property_ref", "platform", name="uq_property_platform"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    property_ref: Mapped[str] = mapped_column(String(64), index=True)  # "Property ID" column
    platform: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[PropertyStatus] = mapped_column(
        Enum(PropertyStatus, values_callable=lambda e: [m.value for m in e]),
        default=PropertyStatus.PENDING,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), default="")
    title_ar: Mapped[str] = mapped_column(String(255), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    description_ar: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(64), default="")
    availability: Mapped[str] = mapped_column(String(64), default="")
    property_type: Mapped[str] = mapped_column(String(64), default="")
    bedrooms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bathrooms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    area_sqm: Mapped[float | None] = mapped_column(Float, nullable=True)
    rent: Mapped[float | None] = mapped_column(Float, nullable=True)
    sale_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    bills_included: Mapped[bool] = mapped_column(default=False)
    furnished: Mapped[str] = mapped_column(String(32), default="")
    location: Mapped[str] = mapped_column(String(255), default="")
    district: Mapped[str] = mapped_column(String(128), default="")
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    amenities: Mapped[str] = mapped_column(Text, default="")  # comma separated
    images_folder: Mapped[str] = mapped_column(String(512), default="")
    video_url: Mapped[str] = mapped_column(String(512), default="")
    agent: Mapped[str] = mapped_column(String(128), default="")
    phone: Mapped[str] = mapped_column(String(64), default="")
    whatsapp: Mapped[str] = mapped_column(String(64), default="")
    email: Mapped[str] = mapped_column(String(255), default="")
    listing_url: Mapped[str] = mapped_column(String(1024), default="")
    external_id: Mapped[str] = mapped_column(String(64), default="", index=True)  # Property Oryx listing ID
    error: Mapped[str] = mapped_column(Text, default="")
    sheet_row: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), default="", index=True)  # duplicate detection
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    images: Mapped[list[ImageRecord]] = relationship(back_populates="property", cascade="all, delete-orphan")
    jobs: Mapped[list[Job]] = relationship(back_populates="property")


class Account(Base):
    """Platform login account. Password is Fernet-encrypted, never plain."""

    __tablename__ = "accounts"
    __table_args__ = (UniqueConstraint("platform", "email", name="uq_account_platform_email"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String(64), index=True)
    email: Mapped[str] = mapped_column(String(255))
    password_encrypted: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="Active")  # Active | Disabled | Login Failed
    last_login: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    session_dir: Mapped[str] = mapped_column(String(512), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PlatformRecord(Base):
    """Registered platform and its health status."""

    __tablename__ = "platforms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    display_name: Mapped[str] = mapped_column(String(128))
    enabled: Mapped[bool] = mapped_column(default=True)
    last_success: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_failure: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)


class ImageRecord(Base):
    """A processed image belonging to a property."""

    __tablename__ = "images"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    original_path: Mapped[str] = mapped_column(String(1024))
    processed_path: Mapped[str] = mapped_column(String(1024), default="")
    sha256: Mapped[str] = mapped_column(String(64), default="", index=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="Ready")  # Ready | Corrupted | Duplicate
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    property: Mapped[Property] = relationship(back_populates="images")


class Job(Base):
    """A queued/running publish job with priority support."""

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    property_id: Mapped[int] = mapped_column(ForeignKey("properties.id"), index=True)
    platform: Mapped[str] = mapped_column(String(64))
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, values_callable=lambda e: [m.value for m in e]),
        default=JobStatus.QUEUED,
        index=True,
    )
    priority: Mapped[int] = mapped_column(Integer, default=5)  # 1 = highest
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    property: Mapped[Property] = relationship(back_populates="jobs")


class LogEntry(Base):
    """Structured application log mirrored for the UI."""

    __tablename__ = "logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    level: Mapped[str] = mapped_column(String(16), index=True)
    source: Mapped[str] = mapped_column(String(128), default="")
    message: Mapped[str] = mapped_column(Text)
    property_ref: Mapped[str] = mapped_column(String(64), default="", index=True)
    platform: Mapped[str] = mapped_column(String(64), default="")
    screenshot_path: Mapped[str] = mapped_column(String(1024), default="")
    html_dump_path: Mapped[str] = mapped_column(String(1024), default="")
    trace_path: Mapped[str] = mapped_column(String(1024), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class Setting(Base):
    """Key/value runtime settings editable from the UI."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class StatRecord(Base):
    """Daily aggregated statistics per platform."""

    __tablename__ = "statistics"
    __table_args__ = (UniqueConstraint("day", "platform", name="uq_stat_day_platform"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    day: Mapped[str] = mapped_column(String(10), index=True)  # YYYY-MM-DD
    platform: Mapped[str] = mapped_column(String(64), default="all")
    published: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    total_publish_seconds: Mapped[float] = mapped_column(Float, default=0.0)
