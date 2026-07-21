"""Tests for repositories and the job queue."""

from __future__ import annotations

from app.database.models import JobStatus, PropertyStatus
from app.database.repository import (
    AccountRepository,
    JobRepository,
    PropertyRepository,
    StatsRepository,
)
from app.models.schemas import PropertyData


def _make_property(repo: PropertyRepository, sample_row, ref="PROP-100"):
    sample_row = dict(sample_row)
    sample_row["Property ID"] = ref
    data = PropertyData.from_sheet_row(sample_row, sheet_row=2)
    return repo.upsert_from_sheet(data.to_db_dict())


def test_upsert_is_idempotent(temp_db, sample_row):
    repo = PropertyRepository()
    first = _make_property(repo, sample_row)
    second = _make_property(repo, sample_row)
    assert first.id == second.id
    assert len(repo.list()) == 1


def test_upsert_does_not_regress_published_status(temp_db, sample_row):
    repo = PropertyRepository()
    prop = _make_property(repo, sample_row)
    repo.set_status(prop.id, PropertyStatus.PUBLISHED, listing_url="https://x/1")
    again = _make_property(repo, sample_row)
    assert again.status == PropertyStatus.PUBLISHED
    assert again.listing_url == "https://x/1"


def test_duplicate_detection(temp_db, sample_row):
    repo = PropertyRepository()
    a = _make_property(repo, sample_row, "PROP-A")
    b = _make_property(repo, sample_row, "PROP-B")  # same facts, different ref
    repo.set_status(a.id, PropertyStatus.PUBLISHED)
    duplicate = repo.find_duplicate(b.content_hash, exclude_id=b.id)
    assert duplicate is not None
    assert duplicate.property_ref == "PROP-A"


def test_job_queue_priority_order(temp_db, sample_row):
    props = PropertyRepository()
    jobs = JobRepository()
    low = _make_property(props, sample_row, "PROP-LOW")
    high = _make_property(props, sample_row, "PROP-HIGH")
    jobs.enqueue(low.id, "propertyoryx", priority=5)
    jobs.enqueue(high.id, "propertyoryx", priority=1)
    next_job = jobs.next_queued()
    assert next_job is not None
    assert next_job.property_id == high.id


def test_enqueue_deduplicates(temp_db, sample_row):
    props = PropertyRepository()
    jobs = JobRepository()
    prop = _make_property(props, sample_row)
    j1 = jobs.enqueue(prop.id, "propertyoryx")
    j2 = jobs.enqueue(prop.id, "propertyoryx")
    assert j1.id == j2.id


def test_pause_and_resume(temp_db, sample_row):
    props = PropertyRepository()
    jobs = JobRepository()
    prop = _make_property(props, sample_row)
    jobs.enqueue(prop.id, "propertyoryx")
    assert jobs.pause_queued() == 1
    assert jobs.next_queued() is None
    assert jobs.resume_paused() == 1
    assert jobs.next_queued() is not None


def test_job_duration_recorded(temp_db, sample_row):
    props = PropertyRepository()
    jobs = JobRepository()
    prop = _make_property(props, sample_row)
    job = jobs.enqueue(prop.id, "propertyoryx")
    jobs.set_status(job.id, JobStatus.RUNNING)
    jobs.set_status(job.id, JobStatus.COMPLETED)
    finished = jobs.list(status=JobStatus.COMPLETED)
    assert finished and finished[0].duration_seconds is not None


def test_accounts_roundtrip(temp_db):
    repo = AccountRepository()
    account = repo.add("propertyoryx", "agent@example.com", "encrypted-token")
    assert repo.active_for_platform("propertyoryx").id == account.id
    repo.mark_login(account.id, success=False)
    assert repo.active_for_platform("propertyoryx") is None


def test_stats_aggregation(temp_db):
    stats = StatsRepository()
    stats.record_publish("propertyoryx", True, 30.0)
    stats.record_publish("propertyoryx", True, 50.0)
    stats.record_publish("propertyoryx", False, 0.0)
    today = stats.today()
    assert today["published_today"] == 2
    assert today["failed_today"] == 1
    assert today["avg_publish_seconds"] == 40.0
    assert round(today["success_rate"]) == 67
