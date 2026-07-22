"""Listing intake coordinator - the conversational "posting engine".

This is the orchestrator that makes the assistant behave like an experienced
listing coordinator rather than a form filler. For each incoming message it:

1. **parses** natural language into structured fields,
2. **generates** context-appropriate amenities,
3. **detects** genuinely missing required information (and asks only for that),
4. **scores** completeness,
5. **writes** a professional description once ready, and
6. **stores** everything in Excel via the modular storage layer.

It is intentionally decoupled from the Property Oryx :class:`PublishingEngine`:
the coordinator owns *intake and storage*; publishing remains a separate step
that reads the same workbook. This keeps the door open for future channels
(WhatsApp, Telegram, CRM, Property Finder API) that only need to call
:meth:`ListingCoordinator.intake`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from app.core.config import AppConfig, get_config
from app.core.logging import get_logger
from app.models.schemas import PropertyData
from app.services.amenities_generator import AmenitiesGenerator
from app.services.completeness import CompletenessReport, CompletenessScorer
from app.services.description import DescriptionGenerator
from app.services.missing_info import MissingInfoDetector, Question
from app.services.property_parser import PropertyParser
from app.storage.base import PropertyStore
from app.storage.excel_store import ExcelPropertyStore

logger = get_logger(__name__)

#: Business key column in the workbook.
_KEY_COLUMN = "Property ID"


class IntakeStatus(StrEnum):
    NEEDS_INFO = "needs_info"      # required fields missing - questions returned
    INCOMPLETE = "incomplete"     # required present but below completeness threshold
    READY = "ready"               # complete and stored, ready to publish


@dataclass(slots=True)
class IntakeResult:
    """What happened to one intake message."""

    status: IntakeStatus
    data: PropertyData
    completeness: CompletenessReport
    property_ref: str
    row_id: int | None = None
    questions: list[Question] = field(default_factory=list)
    message: str = ""

    @property
    def is_ready(self) -> bool:
        return self.status is IntakeStatus.READY


class ListingCoordinator:
    """Drives the natural-language -> validated -> stored listing workflow."""

    def __init__(
        self,
        store: PropertyStore | None = None,
        *,
        config: AppConfig | None = None,
        parser: PropertyParser | None = None,
        amenities: AmenitiesGenerator | None = None,
        detector: MissingInfoDetector | None = None,
        scorer: CompletenessScorer | None = None,
        describer: DescriptionGenerator | None = None,
    ) -> None:
        self.config = config or get_config()
        self.store = store or ExcelPropertyStore(
            self.config.sheet.resolved_excel_path(), self.config.sheet.worksheet_name
        )
        self.parser = parser or PropertyParser()
        self.amenities = amenities or AmenitiesGenerator(self.config.workflow.min_amenities)
        self.detector = detector or MissingInfoDetector()
        self.scorer = scorer or CompletenessScorer(self.config.workflow.completeness_threshold)
        self.describer = describer or DescriptionGenerator()

    # ------------------------------------------------------------------ intake

    def intake(self, text: str, property_ref: str | None = None) -> IntakeResult:
        """Process one message, persist progress, and report what is still needed.

        Passing ``property_ref`` (from a previous :class:`IntakeResult`) continues
        an in-progress listing so follow-up messages enrich the same record.
        """
        base, row_id = self._load_base(property_ref)
        parsed = self.parser.parse(text, base=base, property_ref=property_ref)
        data = parsed.data

        # Amenities are generated from type + area whenever none are present.
        self.amenities.ensure_amenities(data, parsed.area)

        questions = self.detector.detect(data, parsed.provided if base is None else None)
        if not questions:
            # Everything required is present - write the professional copy.
            self.describer.ensure(data)

        report = self.scorer.score(data)
        status = self._classify(questions, report)
        data.status = {
            IntakeStatus.NEEDS_INFO: "Draft",
            IntakeStatus.INCOMPLETE: "Needs Review",
            IntakeStatus.READY: "Ready",
        }[status]
        data.updated_date = datetime.now(UTC).strftime("%Y-%m-%d %H:%M")

        row_id = self._persist(data, row_id)
        message = self._compose_message(status, data, questions, report)
        logger.info("Intake %s -> %s (%d%%)", data.property_ref, status.value, report.percent)
        return IntakeResult(
            status=status,
            data=data,
            completeness=report,
            property_ref=data.property_ref,
            row_id=row_id,
            questions=questions,
            message=message,
        )

    # ------------------------------------------------------------------ search

    def search(self, query: str) -> list[PropertyData]:
        """Search stored listings by free text (ref, title, location, type...)."""
        return [
            PropertyData.from_sheet_row(rec.values, sheet_row=rec.row_id)
            for rec in self.store.search(query)
        ]

    def get(self, property_ref: str) -> PropertyData | None:
        rec = self.store.find_by(_KEY_COLUMN, property_ref)
        if rec is None:
            return None
        return PropertyData.from_sheet_row(rec.values, sheet_row=rec.row_id)

    # ----------------------------------------------------------------- helpers

    def _load_base(self, property_ref: str | None) -> tuple[PropertyData | None, int | None]:
        if not property_ref:
            return None, None
        rec = self.store.find_by(_KEY_COLUMN, property_ref)
        if rec is None:
            return None, None
        return PropertyData.from_sheet_row(rec.values, sheet_row=rec.row_id), rec.row_id

    def _persist(self, data: PropertyData, row_id: int | None) -> int:
        values = data.to_sheet_dict()
        if row_id is not None:
            return self.store.update(row_id, values).row_id
        return self.store.upsert(_KEY_COLUMN, values).row_id

    def _classify(self, questions: list[Question], report: CompletenessReport) -> IntakeStatus:
        if questions:
            return IntakeStatus.NEEDS_INFO
        if report.percent < self.scorer.threshold:
            return IntakeStatus.INCOMPLETE
        return IntakeStatus.READY

    def _compose_message(
        self,
        status: IntakeStatus,
        data: PropertyData,
        questions: list[Question],
        report: CompletenessReport,
    ) -> str:
        if status is IntakeStatus.NEEDS_INFO:
            return self.detector.format_prompt(questions)
        if status is IntakeStatus.INCOMPLETE:
            missing = ", ".join(report.missing_categories())
            return (
                f"Listing saved as a draft ({report.percent}% complete). "
                f"To publish, please add: {missing}."
            )
        return (
            f"All set — '{data.title}' is {report.percent}% complete and ready to publish."
        )


def create_coordinator(config: AppConfig | None = None) -> ListingCoordinator:
    """Build a coordinator from application configuration."""
    return ListingCoordinator(config=config or get_config())
