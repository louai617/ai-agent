# Elite Real Estate AI Publisher — Property Oryx

A production desktop application that turns a real estate agent's plain-language
notes into validated, publication-ready listings stored in **Microsoft Excel**,
then publishes them to **Property Oryx** via its official **Agents API** — with
AI-generated amenities and descriptions, image processing, scheduling, retries,
and full audit logging.

> This build targets Property Oryx only, using the official REST API — no
> browser automation, no selectors, no CAPTCHAs. It is faster and far more
> reliable than screen-scraping.

## Conversational listing intake

Instead of a rigid form, describe the property the way you'd tell a colleague:

```
> 2BHK apartment in Lusail for 8,500 QAR.

The assistant understands the type, bedrooms, location and rent, generates
realistic Lusail amenities, then asks only for what's genuinely missing:

  I need a few more details before posting:
  • Number of bathrooms?
  • Furnished or unfurnished?
  • Parking included?
  • Bills included or excluded?
  • Availability date?
```

It infers reasonable defaults, generates **context-aware amenities** (a luxury
Pearl villa gets different amenities than a standard Old Airport flat), tracks
**included vs excluded utilities**, computes a **completeness score**, writes a
**professional SEO description** with nearby landmarks, and stores everything in
Excel — publishing only once the listing clears the completeness threshold.

Try it: `python main.py --intake "Furnished 1 bedroom in The Pearl"`.

## How it works

```
Natural-language message  ──►  ListingCoordinator (posting engine)
                                 │  parse → amenities → missing-info →
                                 │  completeness → description
                                 ▼
                         Excel workbook (.xlsx, dynamic schema)
        │  (scheduler or "Run Now")
        ▼
  Sheet sync ──► SQLite (properties + priority job queue)
        │
        ▼  per property
  Validate ─► AI title/description ─► Local image pipeline
        │                                   │
        │        Property Oryx API:  request-upload → PUT bytes → process-image
        │                                   │  (image hashes)
        └─► map reference data (type, furnishing, location, amenities, availability)
                                            │
              create residential rental/sales listing ─► resolve listing ID
                                            │
        Excel write-back (Posted + Listing URL) ◄──────┘
        Notifications (desktop / email / Telegram / WhatsApp)
```

- New rows with `Status = Pending` are picked up automatically.
- Rent vs sale is decided from the row (a `Rent` value → rental listing, a
  `Sale Price` → sales listing).
- Empty titles/descriptions are generated with Google Gemini (facts only, no
  emojis, ≥10-char titles, ≥50-char descriptions to satisfy the API). Optional
  Arabic title/description generation (`titleAr`/`descriptionAr`).
- Images are validated, deduplicated, auto-rotated, resized and compressed
  locally, then uploaded to Property Oryx (signed URL → process-image).
- Reference-data values (property type, furnishing, location, amenities,
  availability, agent) are resolved to the API's IDs automatically.
- Failures retry with exponential backoff on transient/5xx errors; validation
  and auth (4xx) errors fail fast. One failed property never stops the queue.

## Feature highlights

| Area | Details |
|---|---|
| Intake | Natural-language parsing, context-aware amenities, missing-info questions, completeness score, AI descriptions — the "listing coordinator" (`app/services`) |
| Storage | Microsoft Excel (`.xlsx`) with a dynamic, header-mapped schema behind a `PropertyStore` interface (SQL-swappable); concurrency-safe writes |
| API | Official Property Oryx Agents API (`X-API-Key`); typed client for listings, uploads, reference data, dashboard, account |
| UI | PySide6 dark-mode desktop app: Dashboard, Properties, Accounts, Logs, Scheduler, AI Settings, Statistics, Settings |
| Auth | API key encrypted at rest (Fernet); "Test Connection" verifies it via `GET /account` |
| Scheduler | 5 m / 10 m / 30 m / 1 h / daily / weekly / manual |
| Queue | Priority queue with pause/resume, bulk publish, duplicate detection |
| Reference data | Workbook text → API IDs (locations, amenities, types, availability), cached |
| Logging | Rotating files + database log viewer + CSV export |
| Notifications | Desktop tray, email (SMTP), Telegram, optional WhatsApp gateway |
| Docker | Headless publishing container (`docker compose up`) — no browser needed |

## Quick start

```powershell
# 1. Install dependencies (Python 3.13)
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt

# 2. Configure
copy config\config.example.json config\config.json
copy .env.example .env                                # add GEMINI_API_KEY

# 3. Run
.venv\Scripts\python main.py
```

Then open **Accounts**, paste your Property Oryx API key (Test Connection to
verify), point **Settings → Data Source** at your Excel workbook, and press
**Properties → Sync From Sheet**.

Full instructions: [docs/INSTALL.md](docs/INSTALL.md) ·
Configuration: [docs/CONFIGURATION.md](docs/CONFIGURATION.md) ·
Internal API: [docs/API.md](docs/API.md) ·
Developer guide: [docs/DEVELOPER.md](docs/DEVELOPER.md)

## Getting a Property Oryx API key

The API key authenticates every request via the `X-API-Key` header. Generate
it from your Property Oryx account (Account → API key). The key is shown only
once and replacing it invalidates the previous one. Store it on the Accounts
page (encrypted) or in `.env` as `PROPERTYORYX_API_KEY`.

## Excel workbook format

The property database is a local Microsoft Excel (`.xlsx`) workbook
(`data/properties.xlsx` by default), accessed through the modular `app.storage`
layer. **Columns are matched by header name, never by position**, so you can add
new fields as new columns without breaking anything — the store creates missing
columns automatically and serialises concurrent writes with a file lock. To move
to SQL later, implement the `PropertyStore` interface; nothing else changes.

A starter header row is in
[examples/example_sheet.csv](examples/example_sheet.csv). Key points:

- **Platform** — set to `propertyoryx` (this build coerces it anyway).
- **Property Type** — mapped to an API type (`Apartment`, `Compound Villa`,
  `Standalone Villa`, `Townhouse`, `Penthouse`, `Compound Apartment`). Common
  synonyms are handled (`Villa` → `Standalone Villa`, `Studio` → `Apartment`).
- **Rent** or **Sale Price** — determines rental vs sales listing.
- **Furnished** — mapped to `Unfurnished` / `Partly Furnished` / `Fully
  Furnished` (`Semi Furnished` → `Partly Furnished`).
- **District / Location** — resolved to a Property Oryx location ID (must
  match a real location name).
- **Amenities** — comma-separated names resolved to amenity IDs; unknown names
  are skipped with a warning.
- Optional extra columns: **Title AR**, **Description AR**, **Availability**
  (sales; defaults to the first available option if blank).

The app writes back `Status`, `Title`, `Description`, `Listing URL`, `Error`,
`Updated Date`. Set `Status` to `Retry` to re-queue a failed row.

The conversational intake also fills flexible fields when mentioned: `Purpose`,
`Community`, `Building`, `Floor`, `View`, `Balcony`, `Parking`, `Plot Size`,
`Maid Room`, `Driver Room`, `Payment Terms`, `Availability`, and
`Utilities Included` / `Utilities Excluded`.

## Tests

```powershell
.venv\Scripts\python -m pytest
```

## Security notes

- The API key is encrypted with Fernet; the key comes from
  `PUBLISHER_ENCRYPTION_KEY` or an auto-generated `data/.secret.key`.
  **Back up that key** — without it the stored API key cannot be decrypted.
- All secrets live in `.env` (git-ignored). No secrets in source or
  `config.json`.
