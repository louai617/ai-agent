# Installation Guide

## Requirements

- Windows 10/11, macOS, or Linux
- Python 3.13+
- A Property Oryx account with an API key
- A Google Gemini API key (optional — template fallback works without it)

The property database is a local Microsoft Excel (`.xlsx`) file — no Google
account or cloud credentials are required.

No browser/Playwright is needed — publishing uses the Property Oryx REST API.

## 1. Install Python dependencies

```powershell
cd "C:\path\to\posting agent"
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

On macOS/Linux use `source .venv/bin/activate` and the equivalent paths.

## 2. Configuration files

```powershell
copy config\config.example.json config\config.json
copy .env.example .env
```

Edit both — see [CONFIGURATION.md](CONFIGURATION.md) for every option.

## 3. Property Oryx API key

1. Sign in to your Property Oryx account.
2. Generate an API key (Account → API key). Copy it — it is shown only once.
3. In the app, open **Accounts → Add / Replace API Key**, paste it, and press
   **Test Connection** to verify (`GET /account`).
   Alternatively set `PROPERTYORYX_API_KEY` in `.env` (used for headless/Docker).

## 4. Property database (Microsoft Excel)

The property database is a local Excel (`.xlsx`) workbook — no Google account or
service credentials required.

1. Leave `sheet.source_type` as `"excel"`.
2. Optionally set `sheet.excel_path` to a workbook path (default
   `data/properties.xlsx`, created automatically on first write).
3. Add listings conversationally — e.g.
   `python main.py --intake "2BHK apartment in Lusail for 8,500 QAR"` — or drop
   an existing workbook at that path. Columns are matched by header name, so the
   schema can grow without breaking anything.

## 5. First run

```powershell
.venv\Scripts\python main.py
```

1. **Accounts** — add and test your Property Oryx API key.
2. **Settings** — confirm the sheet settings and (optionally) the Property Oryx
   API base URL and public listing URL template.
3. **Properties → Sync From Sheet**, then watch the Dashboard.

## 6. Scheduling

Open **Scheduler**, choose an interval, and press *Apply Schedule*. The app
keeps running in the system tray.

## 7. Docker (headless server mode)

The Docker image runs one publish cycle per container start (no GUI, no browser):

```bash
docker compose build
docker compose run --rm publisher
```

Provide `GEMINI_API_KEY`, `PROPERTYORYX_API_KEY` and `PUBLISHER_ENCRYPTION_KEY`
via `.env` / compose secrets, and mount your config, listing images and a data
volume as shown in `docker-compose.yml`.

## 8. Running the tests

```powershell
.venv\Scripts\python -m pytest
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `AUTHENTICATION_REQUIRED` / 401 | The API key is missing or wrong — re-add it on the Accounts page |
| `No Property Oryx API key configured` | Add an account or set `PROPERTYORYX_API_KEY` in `.env` |
| `Location ... not found` | The sheet's District/Location must match a real Property Oryx location name |
| `Property type ... is not a Property Oryx type` | Use one of the six API types (see README) |
| Sales listing rejected for availability | Set an `Availability` sheet column or `oryx.default_availability` |
| `Failed to decrypt credential` | The encryption key changed — restore `data/.secret.key` or re-enter the API key |
