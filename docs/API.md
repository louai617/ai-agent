# Internal API Reference

The application is a desktop app, not a web service; this documents the public
Python API of each module for maintainers. For the Property Oryx REST API
itself, see its OpenAPI document (`GET /api-docs`) and reference data
(`GET /api-reference-data`).

## app.core.config
- `get_config() -> AppConfig` — cached, validated configuration singleton.
- `reload_config()` / `save_config(config)` — reload/persist `config.json`.
- `get_secret(name, required=False)` — environment-only secrets.
- Models: `AppConfig`, `RetryConfig`, `ImageConfig`, `AIConfig`, `SheetConfig`,
  `SchedulerConfig`, `NotificationConfig`, `OryxConfig`.

## app.core.security
- `CredentialVault.encrypt/decrypt` — Fernet; used for the API key.
- `CredentialVault.generate_key()` — provision `PUBLISHER_ENCRYPTION_KEY`.

## app.models.schemas
- `PropertyData` — canonical property row.
  - `from_sheet_row(row, sheet_row)`, `missing_required_fields()`,
    `price_display()`, `listing_category() -> "rent"|"sale"`,
    `content_hash()`, `to_db_dict()`.
  - Fields include `title_ar`, `description_ar`, `availability`.
- `PublishResult(success, listing_id, listing_url, error, duration_seconds, published_at)`.
- `SHEET_COLUMNS` — spreadsheet column → field mapping.

## app.platforms.propertyoryx.client — `PropertyOryxClient(api_key, config)`
- System: `status()`, `session()`, `account()`, `company()`,
  `reference_data()`, `list_agents()`.
- Uploads: `request_upload(hash, content_type) -> url`,
  `upload_bytes(url, data, content_type)`,
  `process_image(hash, image_type, watermark) -> hash`.
- Listings: `create_rental/create_sale(payload)`,
  `update_rental/update_sale(id, payload)`,
  `delete_rental/delete_sale(id)`, `get_rental/get_sale(id)`.
- Listings query: `dashboard_search(**params)`, `dashboard_counts()`,
  `stats_overview()`.
- Raises `OryxApiError` (with `.status_code`, `.codes`, `.is_retryable`) and
  `AuthError` on 401/403.

## app.platforms.propertyoryx.reference — `ReferenceDataService(client, config)`
- `data()` / `refresh()` — cached reference data.
- `resolve_type(str)`, `resolve_furnishing(str)`,
  `resolve_location(*names) -> int`, `resolve_amenities(names) -> [int]`,
  `resolve_availability(sheet_value, fallback) -> int`,
  `default_option(category, key)`.

## app.platforms.propertyoryx.images — `ImageUploader(client, watermark)`
- `upload(path) -> hash`, `upload_all(paths) -> [hash]`.

## app.platforms.propertyoryx.platform — `PropertyOryxPlatform(credential, config)`
- `login()` (verifies key), `is_authenticated()`, `logout()`.
- `publish(data, image_paths) -> PublishResult`,
  `update(external_id, data, image_paths) -> PublishResult`,
  `delete(external_id, category) -> bool`.

## app.services
- **ContentGenerator** (`ai.py`): `generate_title/description`,
  `ensure_content(data)` (fills empty fields, enforces min lengths, optional
  Arabic). Template fallback when AI is disabled/unavailable.
- **ImageProcessor** (`images.py`): `process_folder(folder, ref) -> ImageBatchResult`.
- **Sheet sources** (`sheets.py`): `create_sheet_source(config)` → Excel-backed
  `read_properties()`, `write_back(row, values)`, `mark_posted`, `mark_failed`.
- **Listing intake modules** (the conversational "coordinator"):
  - `PropertyParser` (`property_parser.py`): `parse(text, base=?, property_ref=?)
    -> ParseResult` — natural language → `PropertyData` + `provided` field set.
  - `AmenitiesGenerator` (`amenities_generator.py`): `generate(data, area)` /
    `ensure_amenities(data)` — context-aware amenities by type + area tier.
  - `MissingInfoDetector` (`missing_info.py`): `detect(data, provided)
    -> list[Question]`, `is_ready`, `format_prompt`.
  - `CompletenessScorer` (`completeness.py`): `score(data) -> CompletenessReport`,
    `meets_threshold(data)`.
  - `DescriptionGenerator` (`description.py`): `ensure(data)` /
    `build_professional_description(data)` — SEO + landmark-aware copy.
  - `ListingCoordinator` (`coordinator.py`): `intake(text, property_ref=?)
    -> IntakeResult`, `search(query)`, `get(ref)`; `create_coordinator(config)`.

## app.storage (modular property store)
`PropertyStore` interface (`base.py`) with `ExcelPropertyStore` (`excel_store.py`)
— header-name mapping, dynamic columns, `read_all/get/find_by/append/update/
search/upsert`. Concurrency-safe via `FileLock` (`locking.py`). Swap in a SQL
`PropertyStore` later without touching callers.
- **Notifier** (`notifications.py`): `notify`, `property_published`,
  `publish_failed`, `login_expired`.
- **PublishingEngine** (`publisher.py`):
  - `resolve_api_key() -> (key, account_id|None)`, `get_platform()`,
    `invalidate_platform()`.
  - `sync_from_sheet() -> int`, `start_worker()/stop_worker()`,
    `pause()/resume()/is_paused`, `run_once()`.
  - `on_job_done` callback hook `(job_id, PublishResult|None)`.

## app.database.repository
`PropertyRepository`, `AccountRepository` (the API key lives in
`password_encrypted`, the label in `email`), `JobRepository` (priority queue),
`LogRepository`, `SettingsRepository`, `PlatformRepository`, `ImageRepository`,
`StatsRepository`.

## Exceptions (app.core.exceptions)
`PublisherError` ← `ConfigurationError`, `ValidationError`, `CredentialError`,
`SheetError`, `AIError`, `ImageError`, `ReferenceDataError`, `UploadError`,
`PublishError`, `NotificationError`, and `OryxApiError` ← `AuthError` ←
`LoginError`. `OryxApiError.is_retryable` is true for network/5xx, false for 4xx.
