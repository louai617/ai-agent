"""FastAPI web dashboard for the Property Oryx publishing agent.

This is a thin front layer: every route delegates to the same
``PublishingEngine`` and repositories the desktop app uses, so behaviour is
identical across the two interfaces. The engine's background worker thread is
started on app startup and stopped on shutdown.

Run it with::

    python main.py --web --port 8000
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.core.exceptions import AuthError, CredentialError, OryxApiError, PublisherError
from app.core.logging import get_logger
from app.database.models import PropertyStatus
from app.services.publisher import PLATFORM_NAME, PublishingEngine

logger = get_logger(__name__)
STATIC_DIR = Path(__file__).resolve().parent / "static"


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------


class AccountBody(BaseModel):
    api_key: str
    label: str = "Property Oryx"


class IntakeBody(BaseModel):
    """A natural-language listing message (optionally continuing a listing)."""

    text: str
    property_ref: str | None = None


# ---------------------------------------------------------------------------
# Serialisers (ORM -> JSON-friendly dicts)
# ---------------------------------------------------------------------------


def _price(prop: Any) -> str:
    if prop.rent is not None:
        return f"{prop.rent:,.0f}/mo"
    if prop.sale_price is not None:
        return f"{prop.sale_price:,.0f}"
    return "-"


def _property_json(prop: Any) -> dict[str, Any]:
    return {
        "id": prop.id,
        "ref": prop.property_ref,
        "platform": prop.platform,
        "status": prop.status.value,
        "title": prop.title,
        "type": prop.property_type,
        "bedrooms": prop.bedrooms,
        "price": _price(prop),
        "location": prop.location or prop.district,
        "listing_url": prop.listing_url,
        "error": prop.error,
    }


def _log_json(log: Any) -> dict[str, Any]:
    return {
        "time": log.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        "level": log.level,
        "source": log.source,
        "message": log.message,
    }


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app(engine: PublishingEngine | None = None) -> FastAPI:
    """Build the FastAPI app. Bootstraps and owns a PublishingEngine."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Bootstrap here so importing this module never has side effects.
        if engine is not None:
            app.state.engine = engine
        else:
            from main import bootstrap_engine

            app.state.engine = bootstrap_engine()
        app.state.engine.start_worker()
        logger.info("Web dashboard started; publishing worker running")
        yield
        app.state.engine.stop_worker()

    app = FastAPI(title="Elite Real Estate AI Publisher", lifespan=lifespan)

    def get_engine() -> PublishingEngine:
        return app.state.engine

    def get_coordinator():
        """Lazily build the listing intake coordinator (shares the Excel workbook)."""
        coordinator = getattr(app.state, "coordinator", None)
        if coordinator is None:
            from app.services.coordinator import create_coordinator

            coordinator = create_coordinator(get_engine().config)
            app.state.coordinator = coordinator
        return coordinator

    # ---------------------------------------------------------- pages

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    # ---------------------------------------------------------- read APIs

    @app.get("/api/overview")
    def overview() -> dict[str, Any]:
        eng = get_engine()
        stats = eng.stats.today()
        platforms = [
            {
                "name": p.display_name,
                "enabled": p.enabled,
                "last_success": p.last_success.strftime("%Y-%m-%d %H:%M") if p.last_success else "-",
                "last_failure": p.last_failure.strftime("%Y-%m-%d %H:%M") if p.last_failure else "-",
                "consecutive_failures": p.consecutive_failures,
            }
            for p in eng.platforms.list()
        ]
        has_key = True
        try:
            eng.resolve_api_key()
        except CredentialError:
            has_key = False
        return {
            "stats": stats,
            "platforms": platforms,
            "running_jobs": eng.jobs.running_count(),
            "is_paused": eng.is_paused,
            "has_api_key": has_key,
        }

    @app.get("/api/properties")
    def properties(status: str | None = None, search: str | None = None) -> list[dict[str, Any]]:
        eng = get_engine()
        status_enum = None
        if status:
            try:
                status_enum = PropertyStatus(status)
            except ValueError as exc:
                raise HTTPException(400, f"Invalid status: {status}") from exc
        rows = eng.properties.list(status=status_enum, search=search or None, limit=500)
        return [_property_json(p) for p in rows]

    @app.get("/api/logs")
    def logs(limit: int = 40) -> list[dict[str, Any]]:
        return [_log_json(entry) for entry in get_engine().logs.recent(limit=min(limit, 200))]

    # ---------------------------------------------------------- actions

    @app.post("/api/sync")
    def sync() -> dict[str, Any]:
        eng = get_engine()
        try:
            enqueued = eng.sync_from_sheet()
        except PublisherError as exc:
            raise HTTPException(400, str(exc)) from exc
        eng.start_worker()
        return {"enqueued": enqueued}

    @app.post("/api/publish-all")
    def publish_all() -> dict[str, Any]:
        eng = get_engine()
        pending = eng.properties.pending()
        for prop in pending:
            eng.jobs.enqueue(prop.id, prop.platform)
        eng.start_worker()
        return {"queued": len(pending)}

    @app.post("/api/properties/{property_id}/publish")
    def publish_one(property_id: int) -> dict[str, Any]:
        eng = get_engine()
        prop = eng.properties.get(property_id)
        if prop is None:
            raise HTTPException(404, "Property not found")
        eng.properties.set_status(property_id, PropertyStatus.PENDING)
        eng.jobs.enqueue(property_id, prop.platform, priority=1)
        eng.start_worker()
        return {"ok": True}

    @app.post("/api/worker/pause")
    def pause() -> dict[str, Any]:
        eng = get_engine()
        eng.pause()
        return {"is_paused": eng.is_paused}

    @app.post("/api/worker/resume")
    def resume() -> dict[str, Any]:
        eng = get_engine()
        eng.resume()
        eng.start_worker()
        return {"is_paused": eng.is_paused}

    # ---------------------------------------------------------- listing intake

    @app.post("/api/intake")
    def intake(body: IntakeBody) -> dict[str, Any]:
        """Conversational listing intake: parse -> validate -> store in Excel."""
        text = body.text.strip()
        if not text:
            raise HTTPException(400, "Message text is required")
        try:
            result = get_coordinator().intake(text, property_ref=body.property_ref)
        except PublisherError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {
            "status": result.status.value,
            "property_ref": result.property_ref,
            "message": result.message,
            "questions": [{"field": q.field, "text": q.text} for q in result.questions],
            "completeness": {
                "percent": result.completeness.percent,
                "categories": [
                    {"name": c.name, "complete": c.complete, "mark": c.mark}
                    for c in result.completeness.categories
                ],
            },
            "listing": {
                "type": result.data.property_type,
                "bedrooms": result.data.bedrooms,
                "location": result.data.community or result.data.location,
                "price": result.data.price_display(),
                "amenities": result.data.amenities,
                "title": result.data.title,
                "description": result.data.description,
            },
        }

    @app.get("/api/listings/search")
    def search_listings(q: str = "") -> list[dict[str, Any]]:
        results = get_coordinator().search(q)
        return [
            {
                "ref": p.property_ref,
                "status": p.status,
                "type": p.property_type,
                "bedrooms": p.bedrooms,
                "location": p.community or p.location,
                "price": p.price_display(),
            }
            for p in results
        ]

    # ---------------------------------------------------------- account

    @app.post("/api/account")
    def save_account(body: AccountBody) -> dict[str, Any]:
        eng = get_engine()
        key = body.api_key.strip()
        if not key:
            raise HTTPException(400, "API key is required")
        encrypted = eng.vault.encrypt(key)
        eng.accounts.add(PLATFORM_NAME, body.label.strip() or "Property Oryx", encrypted)
        eng.invalidate_platform()
        return {"ok": True}

    @app.post("/api/account/test")
    def test_account() -> dict[str, Any]:
        eng = get_engine()
        from app.platforms.propertyoryx.client import PropertyOryxClient

        try:
            api_key, _ = eng.resolve_api_key()
            data = PropertyOryxClient(api_key, eng.config.oryx).account()
        except CredentialError as exc:
            raise HTTPException(400, str(exc)) from exc
        except AuthError as exc:
            code = exc.status_code or 401
            raise HTTPException(
                400,
                f"Property Oryx rejected the API key ({code}). It is invalid, expired, "
                "or lacks permission — generate a fresh key and save it again.",
            ) from exc
        except OryxApiError as exc:
            raise HTTPException(400, f"Property Oryx API error: {exc}") from exc
        return {"ok": True, "name": data.get("name", ""), "email": data.get("email", "")}

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    return app


#: Module-level ASGI app for ``uvicorn app.web.server:app``.
app = create_app()
