"""Configuration management.

Configuration is layered:

1. ``config/config.json``      - main JSON configuration (checked in as example).
2. ``.env`` / environment      - secrets (API keys, encryption key) NEVER live in JSON.
3. Database ``settings`` table - user-editable runtime settings from the UI.

All configuration is validated through Pydantic models so invalid config
fails fast at startup with a readable error.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator

from app.core.exceptions import ConfigurationError

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

APP_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = APP_DIR / "config"
DATA_DIR = Path(os.environ.get("PUBLISHER_DATA_DIR", APP_DIR / "data"))
LOGS_DIR = APP_DIR / "logs"
ARTIFACTS_DIR = LOGS_DIR / "artifacts"  # failure payloads / API error dumps

for _d in (DATA_DIR, LOGS_DIR, ARTIFACTS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

load_dotenv(APP_DIR / ".env")


# ---------------------------------------------------------------------------
# Pydantic configuration models
# ---------------------------------------------------------------------------


class RetryConfig(BaseModel):
    """Retry behaviour for publish attempts and API calls."""

    max_attempts: int = Field(3, ge=1, le=10)
    backoff_base_seconds: float = Field(5.0, gt=0)
    backoff_multiplier: float = Field(2.0, ge=1.0)
    backoff_max_seconds: float = Field(300.0, gt=0)


class ImageConfig(BaseModel):
    """Local image pipeline settings (run before uploading to Property Oryx)."""

    max_width: int = 1920
    max_height: int = 1080
    jpeg_quality: int = Field(85, ge=30, le=100)
    max_file_size_mb: float = 5.0
    max_images_per_listing: int = 30
    allowed_extensions: list[str] = [".jpg", ".jpeg", ".png", ".webp"]


class AIConfig(BaseModel):
    """Gemini content-generation settings (non-secret part)."""

    enabled: bool = True
    model: str = "gemini-2.5-flash"
    temperature: float = Field(0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(600, ge=50, le=4000)
    language: str = "en"
    title_max_chars: int = 80
    #: Property Oryx requires English title >= 10 chars and description >= 50 chars.
    title_min_chars: int = 10
    description_min_chars: int = 50
    #: Generate Arabic title/description too (some companies require them).
    generate_arabic: bool = False
    title_prompt: str = (
        "You are an expert real estate copywriter. Write an SEO-optimized listing title. "
        "Maximum {max_chars} characters. No emojis. Professional tone. "
        "Use only the facts provided; never invent details."
    )
    description_prompt: str = (
        "You are an expert real estate copywriter. Write a professional listing description "
        "in {language}. Highlight bedrooms, bathrooms, area, amenities, location and price. "
        "No emojis. Use only the facts provided; never invent details. 120-220 words."
    )


class SheetConfig(BaseModel):
    """Google Sheet / Excel data-source settings."""

    source_type: str = "google"  # "google" | "excel"
    spreadsheet_id: str = ""
    worksheet_name: str = "Properties"
    excel_path: str = ""
    service_account_file: str = "config/service_account.json"

    @field_validator("source_type")
    @classmethod
    def _valid_source(cls, v: str) -> str:
        if v not in {"google", "excel"}:
            raise ValueError("source_type must be 'google' or 'excel'")
        return v


class SchedulerConfig(BaseModel):
    """Automatic run scheduling."""

    enabled: bool = False
    interval: str = "30m"  # 5m | 10m | 30m | 1h | daily | weekly | manual
    daily_time: str = "09:00"
    weekly_day: str = "mon"

    @field_validator("interval")
    @classmethod
    def _valid_interval(cls, v: str) -> str:
        if v not in {"5m", "10m", "30m", "1h", "daily", "weekly", "manual"}:
            raise ValueError("invalid scheduler interval")
        return v


class NotificationConfig(BaseModel):
    """Notification channel settings (secrets come from env)."""

    desktop_enabled: bool = True
    email_enabled: bool = False
    email_smtp_host: str = ""
    email_smtp_port: int = 587
    email_from: str = ""
    email_to: list[str] = []
    telegram_enabled: bool = False
    telegram_chat_id: str = ""
    whatsapp_enabled: bool = False
    whatsapp_api_url: str = ""
    whatsapp_to: str = ""


class OryxConfig(BaseModel):
    """Property Oryx Agents API settings.

    The API key itself is a secret and is NOT stored here - it lives encrypted
    in the accounts table (or the ``PROPERTYORYX_API_KEY`` environment variable).
    """

    api_base_url: str = "https://mqdyqyic12.execute-api.ap-southeast-1.amazonaws.com"
    request_timeout_s: int = Field(45, ge=5, le=300)
    watermark_images: bool = False
    #: Template used to build a human-friendly listing URL for the sheet write-back.
    public_listing_url_template: str = "https://www.propertyoryx.com/property/{id}"
    reference_cache_seconds: int = Field(3600, ge=0)
    #: Fallbacks for API fields the spreadsheet does not provide.
    default_commission: int | None = None
    default_deposit: int | None = None
    default_availability: int | None = None
    default_agent_id: int | None = None


class AppConfig(BaseModel):
    """Root application configuration."""

    retry: RetryConfig = RetryConfig()
    images: ImageConfig = ImageConfig()
    ai: AIConfig = AIConfig()
    sheet: SheetConfig = SheetConfig()
    scheduler: SchedulerConfig = SchedulerConfig()
    notifications: NotificationConfig = NotificationConfig()
    oryx: OryxConfig = OryxConfig()
    database_path: str = str(DATA_DIR / "publisher.db")


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def load_config(path: Path | None = None) -> AppConfig:
    """Load and validate the JSON configuration file.

    Falls back to ``config/config.json`` then ``config/config.example.json``
    then built-in defaults.
    """
    cfg_path = path or CONFIG_DIR / "config.json"
    if not cfg_path.exists():
        example = CONFIG_DIR / "config.example.json"
        if example.exists():
            cfg_path = example
        else:
            return AppConfig()
    try:
        raw: dict[str, Any] = json.loads(cfg_path.read_text(encoding="utf-8"))
        return AppConfig.model_validate(raw)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise ConfigurationError(f"Failed to load config {cfg_path}: {exc}") from exc


def save_config(config: AppConfig, path: Path | None = None) -> None:
    """Persist configuration back to JSON (never contains secrets)."""
    cfg_path = path or CONFIG_DIR / "config.json"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(config.model_dump_json(indent=2), encoding="utf-8")


@lru_cache(maxsize=1)
def get_config() -> AppConfig:
    """Cached singleton accessor used across the app."""
    return load_config()


def reload_config() -> AppConfig:
    """Clear the cache and reload from disk (used after Settings UI saves)."""
    get_config.cache_clear()
    return get_config()


# ---------------------------------------------------------------------------
# Secrets (environment only - never stored in JSON or source)
# ---------------------------------------------------------------------------


def get_secret(name: str, required: bool = False) -> str:
    """Read a secret from the environment. Raise if required and absent."""
    value = os.environ.get(name, "")
    if required and not value:
        raise ConfigurationError(
            f"Required secret '{name}' is not set. Add it to your .env file or environment."
        )
    return value
