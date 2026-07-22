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


def run_intake(text: str, property_ref: str | None = None) -> int:
    """Run one natural-language listing intake and print the coordinator reply.

    Example::

        python main.py --intake "2BHK apartment in Lusail for 8,500 QAR"
    """
    from app.database.engine import init_engine
    from app.services.coordinator import create_coordinator

    init_engine()
    coordinator = create_coordinator()
    result = coordinator.intake(text, property_ref=property_ref)
    print(f"Listing: {result.property_ref}  [{result.status.value}]")
    print()
    print(result.message)
    print()
    print(result.completeness.as_text())
    return 0


def run_web(host: str = "127.0.0.1", port: int = 8000) -> int:
    """Start the FastAPI web dashboard (browser interface to the agent)."""
    import uvicorn

    from app.web.server import app as web_app

    logger.info("Starting web dashboard on http://%s:%d", host, port)
    uvicorn.run(web_app, host=host, port=port, log_level="info")
    return 0


def main() -> int:
    setup_logging()
    parser = argparse.ArgumentParser(description="Elite Real Estate AI Publisher")
    parser.add_argument("--headless", action="store_true", help="run one publish cycle without the UI")
    parser.add_argument("--web", action="store_true", help="run the browser dashboard (FastAPI)")
    parser.add_argument("--host", default="127.0.0.1", help="web server host (with --web)")
    parser.add_argument("--port", type=int, default=8000, help="web server port (with --web)")
    parser.add_argument("--intake", metavar="TEXT", help="parse a natural-language listing and store it in Excel")
    parser.add_argument("--ref", help="continue an existing listing (with --intake)")
    args = parser.parse_args()
    try:
        if args.intake:
            return run_intake(args.intake, args.ref)
        if args.web:
            return run_web(args.host, args.port)
        return run_headless() if args.headless else run_gui()
    except Exception:
        logger.exception("Fatal startup error")
        raise


if __name__ == "__main__":
    sys.exit(main())
