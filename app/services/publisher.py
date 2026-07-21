"""Publishing engine - the orchestrator.

Workflow per property (see README for the full diagram):

sheet sync -> validate -> AI content -> image pipeline -> browser login ->
fill form -> upload images -> publish -> write listing URL back to sheet ->
mark Posted -> stats + notifications.

Design notes
------------
- Dependencies are injected through the constructor (testable without
  network, browser or a real sheet).
- Retries use exponential backoff; CAPTCHA pauses the whole engine and
  notifies the user instead of retrying.
- One property failing never stops the rest of the queue.
"""

from __future__ import annotations

import threading
from collections.abc import Callable

from app.core.config import AppConfig, get_config, get_secret
from app.core.exceptions import (
    AuthError,
    CredentialError,
    ImageError,
    OryxApiError,
    PublisherError,
    ReferenceDataError,
    ValidationError,
)
from app.core.logging import get_logger
from app.core.security import CredentialVault
from app.database.models import JobStatus, PropertyStatus
from app.database.repository import (
    AccountRepository,
    ImageRepository,
    JobRepository,
    LogRepository,
    PlatformRepository,
    PropertyRepository,
    StatsRepository,
)
from app.models.schemas import PropertyData, PublishResult
from app.platforms.propertyoryx.platform import PropertyOryxPlatform
from app.platforms.registry import available_platforms
from app.services.ai import ContentGenerator
from app.services.images import ImageProcessor
from app.services.notifications import Notifier
from app.services.sheets import SheetSource, create_sheet_source
from app.utils.retry import compute_backoff
from app.utils.validators import validate_property

logger = get_logger(__name__)

#: This build targets a single platform: Property Oryx (official Agents API).
PLATFORM_NAME = "propertyoryx"


class PublishingEngine:
    """Coordinates the end-to-end publishing pipeline."""

    def __init__(
        self,
        config: AppConfig | None = None,
        sheet: SheetSource | None = None,
        content: ContentGenerator | None = None,
        images: ImageProcessor | None = None,
        notifier: Notifier | None = None,
        vault: CredentialVault | None = None,
    ) -> None:
        self.config = config or get_config()
        self._sheet = sheet
        self.content = content or ContentGenerator(self.config.ai)
        self.images = images or ImageProcessor(self.config.images)
        self.notifier = notifier or Notifier(self.config.notifications)
        self.vault = vault or CredentialVault()

        self.properties = PropertyRepository()
        self.accounts = AccountRepository()
        self.jobs = JobRepository()
        self.logs = LogRepository()
        self.platforms = PlatformRepository()
        self.image_records = ImageRepository()
        self.stats = StatsRepository()

        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._worker: threading.Thread | None = None
        #: UI hook fired after each job: Callable[[int, PublishResult | None], None]
        self.on_job_done: Callable[[int, PublishResult | None], None] | None = None

        # Cached platform client (keyed by credential so reference data is reused).
        self._platform: PropertyOryxPlatform | None = None
        self._platform_credential = ""

        for name, cls in available_platforms().items():
            self.platforms.ensure(name, cls.display_name)

    # ------------------------------------------------------------- credentials

    def resolve_api_key(self) -> tuple[str, int | None]:
        """Return the Property Oryx API key and the account id it came from.

        Prefers an active account (encrypted in the DB); falls back to the
        ``PROPERTYORYX_API_KEY`` environment variable.
        """
        account = self.accounts.active_for_platform(PLATFORM_NAME)
        if account is not None:
            try:
                return self.vault.decrypt(account.password_encrypted), account.id
            except CredentialError as exc:
                logger.error("Stored API key for account %d could not be decrypted: %s", account.id, exc)
        env_key = get_secret("PROPERTYORYX_API_KEY")
        if env_key:
            return env_key, None
        raise CredentialError(
            "No Property Oryx API key configured. Add an account on the Accounts page "
            "or set PROPERTYORYX_API_KEY in your .env file."
        )

    def get_platform(self) -> PropertyOryxPlatform:
        """Lazily build and cache the Property Oryx platform client."""
        api_key, _ = self.resolve_api_key()
        if self._platform is None or api_key != self._platform_credential:
            self._platform = PropertyOryxPlatform(api_key, self.config)
            self._platform_credential = api_key
        return self._platform

    def invalidate_platform(self) -> None:
        """Drop the cached platform client (call after the API key changes)."""
        self._platform = None
        self._platform_credential = ""

    # ---------------------------------------------------------------- sheet IO

    @property
    def sheet(self) -> SheetSource:
        """Lazily-created sheet source (so the UI can start unconfigured)."""
        if self._sheet is None:
            self._sheet = create_sheet_source(self.config.sheet)
        return self._sheet

    def sync_from_sheet(self) -> int:
        """Pull the sheet into the local DB and enqueue new pending rows.

        Returns the number of properties enqueued.
        """
        rows = self.sheet.read_properties()
        enqueued = 0
        for data in rows:
            status = data.status.strip().lower()
            if status in {"posted", "published", "archived", "deleted", "skip"}:
                continue
            # This build publishes only to Property Oryx - coerce the platform.
            data.platform = PLATFORM_NAME
            record = self.properties.upsert_from_sheet(data.to_db_dict())
            if record.status in (PropertyStatus.PENDING, PropertyStatus.FAILED):
                if record.status == PropertyStatus.FAILED and status != "retry":
                    continue  # failed rows need an explicit Retry status in the sheet
                self.properties.set_status(record.id, PropertyStatus.PENDING)
                self.jobs.enqueue(record.id, record.platform)
                enqueued += 1
        logger.info("Sheet sync complete: %d rows, %d enqueued", len(rows), enqueued)
        return enqueued

    # ------------------------------------------------------------ queue control

    def start_worker(self) -> None:
        """Start the background queue worker (idempotent)."""
        if self._worker is not None and self._worker.is_alive():
            return
        self._stop_event.clear()
        self._pause_event.clear()
        self._worker = threading.Thread(target=self._worker_loop, name="publish-worker", daemon=True)
        self._worker.start()
        logger.info("Publishing worker started")

    def stop_worker(self) -> None:
        self._stop_event.set()

    def pause(self) -> None:
        self._pause_event.set()
        self.jobs.pause_queued()
        logger.info("Publishing paused")

    def resume(self) -> None:
        self._pause_event.clear()
        self.jobs.resume_paused()
        logger.info("Publishing resumed")

    @property
    def is_paused(self) -> bool:
        return self._pause_event.is_set()

    def run_once(self) -> None:
        """Scheduler entry point: sync the sheet and make sure the worker runs."""
        try:
            self.sync_from_sheet()
        except PublisherError as exc:
            logger.error("Scheduled sheet sync failed: %s", exc)
            self.notifier.notify("Sheet Sync Failed", str(exc), "error")
            return
        self.start_worker()

    def _worker_loop(self) -> None:
        """Consume the priority queue until stopped."""
        while not self._stop_event.is_set():
            if self._pause_event.is_set():
                self._stop_event.wait(2.0)
                continue
            job = self.jobs.next_queued()
            if job is None:
                self._stop_event.wait(3.0)
                continue
            self._run_job(job.id, job.property_id, job.platform)
        logger.info("Publishing worker stopped")

    # ------------------------------------------------------------------- jobs

    def _run_job(self, job_id: int, property_id: int, platform_name: str) -> None:
        """Execute one publish job with retry/backoff on transient API errors."""
        self.jobs.set_status(job_id, JobStatus.RUNNING)
        self.properties.set_status(property_id, PropertyStatus.PUBLISHING)
        retry_cfg = self.config.retry
        result: PublishResult | None = None
        last_error = ""

        for attempt in range(1, retry_cfg.max_attempts + 1):
            if self._stop_event.is_set():
                self.jobs.set_status(job_id, JobStatus.CANCELLED)
                return
            try:
                result = self._publish_property(property_id)
                break
            except (ValidationError, ReferenceDataError, ImageError, AuthError, CredentialError) as exc:
                # Data/auth problems will not fix themselves - do not retry.
                last_error = str(exc)
                logger.error("Job %d permanent failure: %s", job_id, exc)
                break
            except OryxApiError as exc:
                last_error = str(exc)
                if not exc.is_retryable or attempt == retry_cfg.max_attempts:
                    logger.error("Job %d API failure (final): %s", job_id, exc)
                    break
                logger.warning("Job %d attempt %d/%d failed: %s", job_id, attempt, retry_cfg.max_attempts, exc)
                self._backoff_wait(attempt)
            except PublisherError as exc:
                last_error = str(exc)
                logger.warning("Job %d attempt %d/%d failed: %s", job_id, attempt, retry_cfg.max_attempts, exc)
                if attempt < retry_cfg.max_attempts:
                    self._backoff_wait(attempt)
            except Exception as exc:  # noqa: BLE001 - engine must never die on one job
                last_error = f"Unexpected error: {exc}"
                logger.exception("Job %d unexpected failure", job_id)
                break

        prop = self.properties.get(property_id)
        if result is not None and result.success:
            self.jobs.set_status(job_id, JobStatus.COMPLETED)
            self.properties.set_status(
                property_id, PropertyStatus.PUBLISHED, listing_url=result.listing_url
            )
            self.properties.update_fields(property_id, external_id=result.listing_id)
            self.platforms.record_result(platform_name, success=True)
            self.stats.record_publish(platform_name, True, result.duration_seconds)
            if prop is not None:
                self._write_back_success(prop.sheet_row, result, property_id)
                self.notifier.property_published(prop.property_ref, platform_name, result.listing_url)
                self.logs.add_log(
                    "INFO", "publisher",
                    f"Published {prop.property_ref} -> {result.listing_url or result.listing_id}",
                    property_ref=prop.property_ref, platform=platform_name,
                )
        else:
            self.jobs.set_status(job_id, JobStatus.FAILED, error=last_error)
            self.properties.set_status(property_id, PropertyStatus.FAILED, error=last_error)
            self.platforms.record_result(platform_name, success=False)
            self.stats.record_publish(platform_name, False, 0.0)
            if prop is not None:
                self._write_back_failure(prop.sheet_row, last_error)
                self.notifier.publish_failed(prop.property_ref, platform_name, last_error)
                self.logs.add_log(
                    "ERROR", "publisher",
                    f"Publish failed for {prop.property_ref}: {last_error}",
                    property_ref=prop.property_ref, platform=platform_name,
                )

        if self.on_job_done is not None:
            try:
                self.on_job_done(job_id, result)
            except Exception:  # noqa: BLE001 - UI callback must not kill the worker
                logger.exception("on_job_done callback failed")

    def _backoff_wait(self, attempt: int) -> None:
        """Interruptible exponential backoff between attempts."""
        retry_cfg = self.config.retry
        delay = compute_backoff(
            attempt,
            retry_cfg.backoff_base_seconds,
            retry_cfg.backoff_multiplier,
            retry_cfg.backoff_max_seconds,
        )
        self._stop_event.wait(delay)

    # ------------------------------------------------------------ single publish

    def _publish_property(self, property_id: int) -> PublishResult:
        """The full pipeline for one property against the Property Oryx API."""
        record = self.properties.get(property_id)
        if record is None:
            raise PublisherError(f"Property id {property_id} vanished from the database")
        data = self._record_to_data(record)

        # 1. Validate required fields and image folder.
        validate_property(data)

        # 2. Duplicate check against already-published listings.
        duplicate = self.properties.find_duplicate(data.content_hash(), exclude_id=property_id)
        if duplicate is not None:
            raise ValidationError(
                f"Duplicate of already-published property {duplicate.property_ref} "
                f"({duplicate.listing_url}) - marked for review"
            )

        # 3. AI content (title/description, and Arabic if enabled).
        data = self.content.ensure_content(data)
        self.properties.update_fields(
            property_id,
            title=data.title,
            description=data.description,
            title_ar=data.title_ar,
            description_ar=data.description_ar,
        )

        # 4. Local image processing (resize/compress/dedupe) before upload.
        batch = self.images.process_folder(data.images_folder, data.property_ref)
        self.image_records.replace_for_property(
            property_id,
            [
                {
                    "original_path": img.original_path,
                    "processed_path": img.processed_path,
                    "sha256": img.sha256,
                    "width": img.width,
                    "height": img.height,
                    "size_bytes": img.size_bytes,
                }
                for img in batch.ready
            ],
        )

        # 5. Publish through the Property Oryx API.
        platform = self.get_platform()
        _, account_id = self.resolve_api_key()
        try:
            platform.login()  # verifies the API key
            if account_id is not None:
                self.accounts.mark_login(account_id, success=True)
        except AuthError:
            if account_id is not None:
                self.accounts.mark_login(account_id, success=False)
            self.notifier.login_expired(PLATFORM_NAME, "API key")
            raise

        existing_id = (record.external_id or "").strip()
        if existing_id.isdigit():
            return platform.update(existing_id, data, batch.paths)
        return platform.publish(data, batch.paths)

    # ---------------------------------------------------------------- helpers

    @staticmethod
    def _record_to_data(record) -> PropertyData:  # noqa: ANN001 - ORM model
        """Convert a DB Property row back to the pydantic schema."""
        return PropertyData(
            property_ref=record.property_ref,
            platform=record.platform,
            status=record.status.value,
            title=record.title,
            title_ar=record.title_ar,
            description=record.description,
            description_ar=record.description_ar,
            category=record.category,
            availability=record.availability,
            property_type=record.property_type,
            bedrooms=record.bedrooms,
            bathrooms=record.bathrooms,
            area_sqm=record.area_sqm,
            rent=record.rent,
            sale_price=record.sale_price,
            bills_included=record.bills_included,
            furnished=record.furnished,
            location=record.location,
            district=record.district,
            latitude=record.latitude,
            longitude=record.longitude,
            amenities=[a.strip() for a in (record.amenities or "").split(",") if a.strip()],
            images_folder=record.images_folder,
            video_url=record.video_url,
            agent=record.agent,
            phone=record.phone,
            whatsapp=record.whatsapp,
            email=record.email,
            listing_url=record.listing_url,
            sheet_row=record.sheet_row,
        )

    def _write_back_success(self, sheet_row: int | None, result: PublishResult, property_id: int) -> None:
        if sheet_row is None:
            return
        record = self.properties.get(property_id)
        try:
            self.sheet.mark_posted(
                sheet_row,
                result.listing_url,
                record.title if record else "",
                record.description if record else "",
            )
        except PublisherError as exc:
            logger.error("Sheet write-back failed (row %s): %s", sheet_row, exc)

    def _write_back_failure(self, sheet_row: int | None, error: str) -> None:
        if sheet_row is None:
            return
        try:
            self.sheet.mark_failed(sheet_row, error)
        except PublisherError as exc:
            logger.error("Sheet write-back failed (row %s): %s", sheet_row, exc)
