# Installation Guide

## Requirements

- Windows 10/11, macOS, or Linux
- Python 3.13+
- A Property Oryx account with an API key
- A Google Cloud service account (for Google Sheets mode)
- A Google Gemini API key (optional — template fallback works without it)

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

## 4. Google Sheets access (google mode)

1. In Google Cloud Console create a project and enable the **Google Sheets API**.
2. Create a **service account**, download its JSON key, save it as
   `config/service_account.json`.
3. Share your spreadsheet with the service account's email (Editor).
4. Put the spreadsheet ID into `config.json → sheet.spreadsheet_id`.

For Excel mode instead set `sheet.source_type` to `"excel"` and
`sheet.excel_path` to the workbook path.

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
