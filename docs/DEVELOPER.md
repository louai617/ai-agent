# Developer Documentation

## Architecture

```
main.py                     composition root (DI wiring, GUI/headless entry)
app/
  core/       config (pydantic), logging, security (Fernet), exceptions
  database/   SQLAlchemy models, engine (+ additive migrations), repositories
  models/     pydantic schemas (PropertyData, PublishResult) + sheet mapping
  domain/     Qatar knowledge base (communities/tiers/landmarks, amenity catalogs)
  storage/    PropertyStore interface + ExcelPropertyStore + file locking
  services/   ai (Gemini), images (local pipeline), sheets, notifications,
              publisher (orchestrator); intake modules: property_parser,
              amenities_generator, missing_info, completeness, description,
              coordinator (conversational posting engine)
  platforms/  base contract + registry + propertyoryx/ (API client, reference
              mapping, image upload, platform)
  scheduler/  APScheduler wrapper
  ui/         PySide6 main window, theme, widgets, pages/
tests/        pytest suite (no network — the API is mocked)
```

Principles applied: SOLID/OCP (new platforms register without touching engine
code), dependency injection (`PublishingEngine` and `ListingCoordinator` take
their collaborators), single source of SQL (`repository.py`), storage behind an
interface (`PropertyStore`), and fail-safe orchestration (one job's failure
never kills the worker).

## Conversational listing intake

`ListingCoordinator` (`services/coordinator.py`) is the "posting engine" for
natural-language intake. Each message flows through small, single-purpose,
independently testable modules:

1. `PropertyParser` — regex + Qatar knowledge base → `PropertyData` plus the set
   of fields the agent explicitly stated (never fabricates).
2. `AmenitiesGenerator` — composes amenities from `base(kind) + tier(area) +
   context`, so a luxury Pearl tower differs from a standard flat.
3. `MissingInfoDetector` — returns *only* the genuinely missing required fields
   as questions, adapting to apartment/villa and rent/sale.
4. `CompletenessScorer` — weighted score across Basic/Pricing/Amenities/
   Utilities/Images/Description; gates publishing on a configurable threshold.
5. `DescriptionGenerator` — SEO- and landmark-aware copy (Gemini when available,
   deterministic template otherwise).

The coordinator persists progress to Excel via the modular storage layer, so
follow-up messages enrich the same record (`intake(text, property_ref=...)`).
Adding a new channel (WhatsApp, Telegram, CRM) only needs to call `intake`;
swapping Excel for SQL only needs a new `PropertyStore`.

## Storage abstraction

`app/storage/` decouples the workflow from where data lives. `PropertyStore`
(`base.py`) defines header-keyed CRUD + search; `ExcelPropertyStore`
(`excel_store.py`) implements it against `.xlsx` with **dynamic columns**
(matched by header name, auto-created on write) and **concurrency safety**
(`FileLock` in `locking.py` — reentrant, cross-thread and cross-process, no
extra dependency).

## Property Oryx integration

Four cooperating pieces under `app/platforms/propertyoryx/`:

- **`client.py`** — `PropertyOryxClient`: typed `requests` wrapper. Sends
  `X-API-Key`, raises `OryxApiError`/`AuthError` carrying the API's error
  codes. Covers account/session/status, reference data, uploads, listing
  CRUD, dashboard search, stats.
- **`reference.py`** — `ReferenceDataService`: caches `GET /api-reference-data`
  and resolves sheet text → API IDs (locations, amenities, availability) and
  enum strings (type, furnishing).
- **`images.py`** — `ImageUploader`: sha256 → `request-upload` → PUT bytes →
  `process-image`, returning the image hash used in the listing.
- **`platform.py`** — `PropertyOryxPlatform`: implements the platform contract
  (`login`/`publish`/`update`/`delete`/`logout`/`is_authenticated`), builds the
  `Create*ListingForm` payload, creates the listing, and resolves its numeric
  ID via `dashboard-search?reference=<Property ID>` (create returns no body).

### Image upload flow
```
local processed .jpg ─► sha256(bytes) = hash
  POST /request-upload {hash, contentType}        → signed URL
  PUT  <signed URL> (bytes)                        → stored
  POST /process-image {hash, imageType, watermark} → processed hash
listing.images = [processed hashes...]
```

### Rent vs sale
`PropertyData.listing_category()` returns `rent` when a rent is set, else
`sale`. Rentals use `deposit`; sales require `availability` (resolved from the
sheet, config default, or the first reference option).

## Publish job (`PublishingEngine._publish_property`)
1. `validate_property` — hard fail (no retry) on data errors.
2. Duplicate check via `content_hash`.
3. `ContentGenerator.ensure_content` — AI/template title+description, min-length
   enforcement, optional Arabic.
4. `ImageProcessor.process_folder` — verify → dedupe → rotate → resize →
   compress locally.
5. `get_platform()` (cached) → `login()` (verify key) → `publish()` or, if the
   row already has an `external_id`, `update()`.
6. On success: DB (`status`, `listing_url`, `external_id`) + sheet write-back +
   stats + notification. On failure: retry with backoff for transient/5xx,
   then sheet `Failed` + notification.

## Threading model
- Qt runs on the main thread.
- One `publish-worker` daemon thread consumes the priority queue (HTTP calls
  are synchronous `requests`, off the Qt thread).
- APScheduler triggers `PublishingEngine.run_once` (sheet sync + ensure worker).
- Pause/resume use `threading.Event`s. There is no CAPTCHA path — the API has
  no interactive challenge.

## Database migrations
`engine._apply_additive_migrations` adds any ORM columns missing from an older
database (SQLite `ALTER TABLE ADD COLUMN`) so upgrades need no manual step.
Non-additive changes still require a real migration.

## Adding another platform (future)
Create `app/platforms/<name>/platform.py` with a `@register_platform` class
inheriting `BasePlatform` and implementing the lifecycle; import it in
`app/platforms/__init__.py`. The base contract is transport-agnostic — a new
platform may use an API or any other mechanism. (This build ships Property Oryx
only; re-enable multi-platform selection in the engine's `PLATFORM_NAME`
handling if you add more.)

## Conventions
- Python 3.13, full type hints, Google-style docstrings.
- `ruff check app tests main.py` clean; `mypy` for types.
- All timestamps UTC in the DB.
- Log through `app.core.logging.get_logger(__name__)`; WARNING+ mirrors to the
  DB for the Logs page.
- Tests must run without network or API keys (the API client is mocked).
