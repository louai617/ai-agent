"""Centralised logging.

- Rotating file logs under ``logs/``.
- Console output for development.
- A database handler mirrors WARNING+ records into the ``logs`` table so the
  Logs page in the UI can display them (attached lazily to avoid circular
  imports at startup).
"""

from __future__ import annotations

import contextlib
import logging
import logging.handlers
from datetime import UTC, datetime

from app.core.config import LOGS_DIR

_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_configured = False


def setup_logging(level: int = logging.INFO) -> None:
    """Configure root logging once; safe to call repeatedly."""
    global _configured
    if _configured:
        return
    root = logging.getLogger()
    root.setLevel(level)

    file_handler = logging.handlers.RotatingFileHandler(
        LOGS_DIR / "publisher.log", maxBytes=5_000_000, backupCount=10, encoding="utf-8"
    )
    file_handler.setFormatter(logging.Formatter(_FORMAT))
    root.addHandler(file_handler)

    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter(_FORMAT))
    root.addHandler(console)

    # Quieten noisy third-party loggers
    for noisy in ("urllib3", "google", "google_genai", "httpx", "PIL"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Project-standard logger accessor."""
    setup_logging()
    return logging.getLogger(name)


class DatabaseLogHandler(logging.Handler):
    """Mirrors log records into the SQLite ``logs`` table.

    Attached from the application bootstrap after the database is ready.
    """

    def __init__(self, repository) -> None:  # noqa: ANN001 - avoid circular import
        super().__init__(level=logging.INFO)
        self._repo = repository

    def emit(self, record: logging.LogRecord) -> None:
        # Logging must never crash the app, so any DB failure is swallowed.
        with contextlib.suppress(Exception):
            self._repo.add_log(
                level=record.levelname,
                source=record.name,
                message=self.format(record) if record.exc_info else record.getMessage(),
                created_at=datetime.now(UTC),
            )
