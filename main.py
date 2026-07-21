"""Elite Real Estate AI Publisher - application entry point.

Usage:
    python main.py            # start the desktop application
    python main.py --headless # run one publish cycle without the UI (Docker/CI)
"""

from __future__ import annotations

import argparse
import logging
import sys

from app.core.config import get_config
from app.core.logging import DatabaseLogHandler, get_logger, setup_logging
from app.database.engine import init_engine
from app.database.repository import LogRepository

logger = get_logger(__name__)


def bootstrap_engine():
    """Build the publishing engine with all dependencies (composition root)."""
    # Importing app.platforms registers the platform plugins.
    import app.platforms  # noqa: F401
    from app.services.publisher import PublishingEngine

    init_engine()
    logging.getLogger().addHandler(DatabaseLogHandler(LogRepository()))
    return PublishingEngine(get_config())


def run_headless() -> int:
    """One publish cycle without a UI - used by Docker and cron-style setups."""
    engine = bootstrap_engine()
    engine.sync_from_sheet()
    engine.start_worker()
    # Drain the queue, then exit.
    import time

    while True:
        job = engine.jobs.next_queued()
        running = engine.jobs.running_count()
        if job is None and running == 0:
            break
        time.sleep(3)
    engine.stop_worker()
    logger.info("Headless run complete")
    return 0


def run_gui() -> int:
    """Start the PySide6 desktop application."""
    from PySide6.QtWidgets import QApplication

    from app.scheduler.scheduler import PublishScheduler
    from app.ui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)

    engine = bootstrap_engine()
    scheduler = PublishScheduler(engine.run_once, get_config().scheduler)
    scheduler.apply()
    engine.start_worker()

    window = MainWindow(engine, scheduler)
    window.show()
    return app.exec()


def main() -> int:
    setup_logging()
    parser = argparse.ArgumentParser(description="Elite Real Estate AI Publisher")
    parser.add_argument("--headless", action="store_true", help="run one publish cycle without the UI")
    args = parser.parse_args()
    try:
        return run_headless() if args.headless else run_gui()
    except Exception:
        logger.exception("Fatal startup error")
        raise


if __name__ == "__main__":
    sys.exit(main())
