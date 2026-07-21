"""Repository layer.

All database access goes through these repositories so services and UI code
never build queries directly (single responsibility + easy testing).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select

from app.database.engine import session_scope
from app.database.models import (
    Account,
    ImageRecord,
    Job,
    JobStatus,
    LogEntry,
    PlatformRecord,
    Property,
    PropertyStatus,
    Setting,
    StatRecord,
)


class PropertyRepository:
    """CRUD and queries for properties."""

    def upsert_from_sheet(self, data: dict[str, Any]) -> Property:
        """Insert or update a property keyed by (property_ref, platform)."""
        with session_scope() as s:
            stmt = select(Property).where(
                Property.property_ref == data["property_ref"],
                Property.platform == data["platform"],
            )
            prop = s.scalars(stmt).first()
            if prop is None:
                prop = Property(**data)
                s.add(prop)
            else:
                # Never regress a published listing back to pending on re-sync
                protected = {"id", "status", "listing_url", "error", "created_at"}
                for key, value in data.items():
                    if key not in protected:
                        setattr(prop, key, value)
            s.flush()
            s.refresh(prop)
            return prop

    def get(self, property_id: int) -> Property | None:
        with session_scope() as s:
            return s.get(Property, property_id)

    def list(
        self,
        status: PropertyStatus | None = None,
        platform: str | None = None,
        search: str | None = None,
        limit: int = 500,
    ) -> list[Property]:
        """Filtered listing for the Properties page."""
        with session_scope() as s:
            stmt = select(Property).order_by(Property.updated_at.desc()).limit(limit)
            if status is not None:
                stmt = stmt.where(Property.status == status)
            if platform:
                stmt = stmt.where(Property.platform == platform)
            if search:
                like = f"%{search}%"
                stmt = stmt.where(
                    Property.title.ilike(like)
                    | Property.property_ref.ilike(like)
                    | Property.location.ilike(like)
                    | Property.district.ilike(like)
                )
            return list(s.scalars(stmt).all())

    def pending(self, platform: str | None = None) -> list[Property]:
        """Properties awaiting publication."""
        with session_scope() as s:
            stmt = select(Property).where(Property.status == PropertyStatus.PENDING)
            if platform:
                stmt = stmt.where(Property.platform == platform)
            return list(s.scalars(stmt).all())

    def set_status(
        self,
        property_id: int,
        status: PropertyStatus,
        error: str = "",
        listing_url: str | None = None,
    ) -> None:
        with session_scope() as s:
            prop = s.get(Property, property_id)
            if prop is None:
                return
            prop.status = status
            prop.error = error
            if listing_url is not None:
                prop.listing_url = listing_url

    def find_duplicate(self, content_hash: str, exclude_id: int) -> Property | None:
        """Duplicate detection by content hash across already-published rows."""
        with session_scope() as s:
            stmt = select(Property).where(
                Property.content_hash == content_hash,
                Property.id != exclude_id,
                Property.status == PropertyStatus.PUBLISHED,
            )
            return s.scalars(stmt).first()

    def update_fields(self, property_id: int, **fields: Any) -> None:
        with session_scope() as s:
            prop = s.get(Property, property_id)
            if prop is None:
                return
            for key, value in fields.items():
                setattr(prop, key, value)


class AccountRepository:
    """CRUD for platform accounts (passwords already encrypted by caller)."""

    def add(self, platform: str, email: str, password_encrypted: str, session_dir: str = "") -> Account:
        with session_scope() as s:
            account = Account(
                platform=platform,
                email=email,
                password_encrypted=password_encrypted,
                session_dir=session_dir,
            )
            s.add(account)
            s.flush()
            s.refresh(account)
            return account

    def list(self, platform: str | None = None) -> list[Account]:
        with session_scope() as s:
            stmt = select(Account).order_by(Account.platform, Account.email)
            if platform:
                stmt = stmt.where(Account.platform == platform)
            return list(s.scalars(stmt).all())

    def active_for_platform(self, platform: str) -> Account | None:
        with session_scope() as s:
            stmt = select(Account).where(Account.platform == platform, Account.status == "Active")
            return s.scalars(stmt).first()

    def update(self, account_id: int, **fields: Any) -> None:
        with session_scope() as s:
            account = s.get(Account, account_id)
            if account is None:
                return
            for key, value in fields.items():
                setattr(account, key, value)

    def mark_login(self, account_id: int, success: bool) -> None:
        with session_scope() as s:
            account = s.get(Account, account_id)
            if account is None:
                return
            if success:
                account.last_login = datetime.now(UTC)
                account.status = "Active"
            else:
                account.status = "Login Failed"

    def delete(self, account_id: int) -> None:
        with session_scope() as s:
            account = s.get(Account, account_id)
            if account is not None:
                s.delete(account)


class JobRepository:
    """Priority job queue backed by the jobs table."""

    def enqueue(self, property_id: int, platform: str, priority: int = 5) -> Job:
        with session_scope() as s:
            existing = s.scalars(
                select(Job).where(
                    Job.property_id == property_id,
                    Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
                )
            ).first()
            if existing is not None:
                return existing
            job = Job(property_id=property_id, platform=platform, priority=priority)
            s.add(job)
            s.flush()
            s.refresh(job)
            return job

    def next_queued(self) -> Job | None:
        """Highest priority (lowest number), oldest first."""
        with session_scope() as s:
            stmt = (
                select(Job)
                .where(Job.status == JobStatus.QUEUED)
                .order_by(Job.priority.asc(), Job.created_at.asc())
                .limit(1)
            )
            return s.scalars(stmt).first()

    def set_status(self, job_id: int, status: JobStatus, error: str = "") -> None:
        with session_scope() as s:
            job = s.get(Job, job_id)
            if job is None:
                return
            job.status = status
            job.error = error
            now = datetime.now(UTC)
            if status == JobStatus.RUNNING:
                job.started_at = now
                job.attempts += 1
            elif status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
                job.finished_at = now
                if job.started_at is not None:
                    started = job.started_at
                    if started.tzinfo is None:
                        started = started.replace(tzinfo=UTC)
                    job.duration_seconds = (now - started).total_seconds()

    def list(self, status: JobStatus | None = None, limit: int = 200) -> list[Job]:
        with session_scope() as s:
            stmt = select(Job).order_by(Job.created_at.desc()).limit(limit)
            if status is not None:
                stmt = stmt.where(Job.status == status)
            return list(s.scalars(stmt).all())

    def running_count(self) -> int:
        with session_scope() as s:
            return s.scalar(select(func.count(Job.id)).where(Job.status == JobStatus.RUNNING)) or 0

    def pause_queued(self) -> int:
        """Pause all queued jobs; returns how many were paused."""
        with session_scope() as s:
            jobs = s.scalars(select(Job).where(Job.status == JobStatus.QUEUED)).all()
            for job in jobs:
                job.status = JobStatus.PAUSED
            return len(jobs)

    def resume_paused(self) -> int:
        with session_scope() as s:
            jobs = s.scalars(select(Job).where(Job.status == JobStatus.PAUSED)).all()
            for job in jobs:
                job.status = JobStatus.QUEUED
            return len(jobs)


class LogRepository:
    """Structured logs for the UI and export."""

    def add_log(
        self,
        level: str,
        source: str,
        message: str,
        property_ref: str = "",
        platform: str = "",
        screenshot_path: str = "",
        html_dump_path: str = "",
        trace_path: str = "",
        created_at: datetime | None = None,
    ) -> None:
        with session_scope() as s:
            s.add(
                LogEntry(
                    level=level,
                    source=source,
                    message=message,
                    property_ref=property_ref,
                    platform=platform,
                    screenshot_path=screenshot_path,
                    html_dump_path=html_dump_path,
                    trace_path=trace_path,
                    created_at=created_at or datetime.now(UTC),
                )
            )

    def list(self, level: str | None = None, search: str | None = None, limit: int = 500) -> list[LogEntry]:
        with session_scope() as s:
            stmt = select(LogEntry).order_by(LogEntry.created_at.desc()).limit(limit)
            if level:
                stmt = stmt.where(LogEntry.level == level)
            if search:
                stmt = stmt.where(LogEntry.message.ilike(f"%{search}%"))
            return list(s.scalars(stmt).all())

    def recent(self, limit: int = 20) -> list[LogEntry]:
        return self.list(limit=limit)


class SettingsRepository:
    """JSON key/value settings."""

    def get(self, key: str, default: Any = None) -> Any:
        with session_scope() as s:
            setting = s.get(Setting, key)
            return setting.value if setting is not None else default

    def set(self, key: str, value: Any) -> None:
        with session_scope() as s:
            setting = s.get(Setting, key)
            if setting is None:
                s.add(Setting(key=key, value=value))
            else:
                setting.value = value


class PlatformRepository:
    """Platform registry health tracking."""

    def ensure(self, name: str, display_name: str) -> None:
        with session_scope() as s:
            record = s.scalars(select(PlatformRecord).where(PlatformRecord.name == name)).first()
            if record is None:
                s.add(PlatformRecord(name=name, display_name=display_name))

    def list(self) -> list[PlatformRecord]:
        with session_scope() as s:
            return list(s.scalars(select(PlatformRecord).order_by(PlatformRecord.name)).all())

    def record_result(self, name: str, success: bool) -> None:
        with session_scope() as s:
            record = s.scalars(select(PlatformRecord).where(PlatformRecord.name == name)).first()
            if record is None:
                return
            now = datetime.now(UTC)
            if success:
                record.last_success = now
                record.consecutive_failures = 0
            else:
                record.last_failure = now
                record.consecutive_failures += 1


class ImageRepository:
    """Processed image records per property."""

    def replace_for_property(self, property_id: int, records: list[dict[str, Any]]) -> None:
        with session_scope() as s:
            for old in s.scalars(select(ImageRecord).where(ImageRecord.property_id == property_id)):
                s.delete(old)
            for rec in records:
                s.add(ImageRecord(property_id=property_id, **rec))

    def for_property(self, property_id: int) -> list[ImageRecord]:
        with session_scope() as s:
            stmt = select(ImageRecord).where(ImageRecord.property_id == property_id)
            return list(s.scalars(stmt).all())


class StatsRepository:
    """Aggregated statistics for the dashboard."""

    def record_publish(self, platform: str, success: bool, duration_seconds: float) -> None:
        day = datetime.now(UTC).strftime("%Y-%m-%d")
        with session_scope() as s:
            for key in (platform, "all"):
                stmt = select(StatRecord).where(StatRecord.day == day, StatRecord.platform == key)
                stat = s.scalars(stmt).first()
                if stat is None:
                    stat = StatRecord(day=day, platform=key, published=0, failed=0, total_publish_seconds=0.0)
                    s.add(stat)
                if success:
                    stat.published += 1
                    stat.total_publish_seconds += duration_seconds
                else:
                    stat.failed += 1

    def today(self) -> dict[str, Any]:
        """Dashboard summary for today."""
        day = datetime.now(UTC).strftime("%Y-%m-%d")
        with session_scope() as s:
            stat = s.scalars(
                select(StatRecord).where(StatRecord.day == day, StatRecord.platform == "all")
            ).first()
            published = stat.published if stat else 0
            failed = stat.failed if stat else 0
            total_seconds = stat.total_publish_seconds if stat else 0.0
            pending = (
                s.scalar(
                    select(func.count(Property.id)).where(Property.status == PropertyStatus.PENDING)
                )
                or 0
            )
        total = published + failed
        return {
            "published_today": published,
            "failed_today": failed,
            "pending": pending,
            "success_rate": (published / total * 100.0) if total else 0.0,
            "avg_publish_seconds": (total_seconds / published) if published else 0.0,
        }

    def history(self, days: int = 30) -> list[StatRecord]:
        cutoff = (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%d")
        with session_scope() as s:
            stmt = (
                select(StatRecord)
                .where(StatRecord.day >= cutoff)
                .order_by(StatRecord.day.asc())
            )
            return list(s.scalars(stmt).all())
