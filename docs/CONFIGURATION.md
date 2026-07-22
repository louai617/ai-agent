# Configuration Guide

Configuration lives in two places:

1. **`config/config.json`** — everything non-secret. Editable in the app
   (Settings / Scheduler / AI Settings pages) or by hand.
2. **`.env`** — secrets only. Never committed, never stored in the DB.

## .env (secrets)

| Variable | Purpose |
|---|---|
| `GEMINI_API_KEY` | AI title/description generation (https://aistudio.google.com/apikey) |
| `PROPERTYORYX_API_KEY` | Property Oryx API key fallback (prefer the Accounts page) |
| `PUBLISHER_ENCRYPTION_KEY` | Fernet key for credential encryption (optional; auto key file otherwise) |
| `SMTP_PASSWORD` | Password for the email notification sender |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token |
| `WHATSAPP_API_TOKEN` | Bearer token for your WhatsApp gateway |
| `PUBLISHER_DATA_DIR` | Override the data directory (Docker sets `/data`) |

## config.json sections

### oryx (Property Oryx API)
| Key | Default | Meaning |
|---|---|---|
| `api_base_url` | `https://mqdyqyic12.execute-api.ap-southeast-1.amazonaws.com` | API server |
| `request_timeout_s` | `45` | Per-request timeout |
| `watermark_images` | `false` | Ask the API to watermark uploaded photos |
| `public_listing_url_template` | `https://www.propertyoryx.com/property/{id}` | Used to build the Listing URL written back to the sheet |
| `reference_cache_seconds` | `3600` | How long to cache `/api-reference-data` |
| `default_commission` | `null` | Fallback commission option ID |
| `default_deposit` | `null` | Fallback deposit option ID (rentals) |
| `default_availability` | `null` | Fallback availability option ID (sales) |
| `default_agent_id` | `null` | Agent assigned when the sheet's Agent is blank/unknown |

Option IDs (commission/deposit/availability/flags/amenities/locations) come
from `GET /api-reference-data` — the app resolves most of them from sheet text
automatically; the defaults above cover fields the sheet does not provide.

### retry
`max_attempts` (3), `backoff_base_seconds` (5), `backoff_multiplier` (2),
`backoff_max_seconds` (300). Transient/5xx errors retry; validation and auth
(4xx) errors fail fast.

### images
`max_width`/`max_height` bounding box, `jpeg_quality`, `max_file_size_mb`
(quality steps down until under the limit), `max_images_per_listing`,
`allowed_extensions`. Images are processed locally, then uploaded to the API.

### ai
`enabled`, `model`, `temperature`, `max_tokens`, `language`,
`title_max_chars`, `title_min_chars` (10), `description_min_chars` (50),
`generate_arabic`, and the two prompt templates. `{max_chars}` and
`{language}` placeholders are substituted at runtime. When `generate_arabic`
is on, the title/description are translated to Arabic for `titleAr`/`descriptionAr`.

### sheet
The property database is a local Microsoft Excel (`.xlsx`) workbook accessed
through the modular `app.storage` layer (Google Sheets is no longer supported).
- `source_type` — `excel` (default); `sql` is reserved for a future
  `PropertyStore` backend.
- `excel_path` — workbook path; empty means `<data>/properties.xlsx`.
- `worksheet_name` — sheet/tab name (default `Properties`).

The store maps columns by **header name**, not position, so new fields become new
columns automatically and concurrent writes are serialised by a file lock.

### workflow
Conversational listing intake (`parser → validate → store`):
- `completeness_threshold` (default 90) — publish only above this score.
- `min_amenities` (default 6) — how many amenities to generate when none given.
- `auto_publish` (default false) — enqueue a "Ready" listing automatically.

### scheduler
`enabled`, `interval` (`5m`/`10m`/`30m`/`1h`/`daily`/`weekly`/`manual`),
`daily_time` (`HH:MM`), `weekly_day` (`mon`…`sun`).

### notifications
Per-channel enable flags plus SMTP host/port/from/to, Telegram chat id, and the
WhatsApp gateway URL + destination number.

## Sheet columns

Header must match `examples/example_sheet.csv`. Notes:

- **Platform** — `propertyoryx` (coerced regardless).
- **Status** — leave `Pending` for new rows. The app writes `Posted` /
  `Failed`. Write `Retry` to re-queue a failed row. `Posted`, `Archived`,
  `Deleted`, `Skip` rows are ignored.
- **Property Type** — one of the six API types; synonyms handled.
- **Rent** or **Sale Price** — determines rental vs sales listing (at least
  one required).
- **Furnished** — `Unfurnished` / `Partly Furnished` / `Fully Furnished`
  (`Semi Furnished` maps to `Partly Furnished`).
- **District / Location** — must match a real Property Oryx location name.
- **Amenities** — comma-separated names; resolved to amenity IDs.
- **Images Folder** — absolute path (inside the container for Docker).
- Optional: **Title AR**, **Description AR**, **Availability** (sales).

The app writes back only `Status`, `Title`, `Description`, `Listing URL`,
`Error`, `Updated Date`.
