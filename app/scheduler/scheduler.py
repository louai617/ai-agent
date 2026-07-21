"""Automatic run scheduler built on APScheduler.

Intervals: 5m / 10m / 30m / 1h / daily / weekly / manual.
The scheduled job simply calls ``PublishingEngine.run_once`` which syncs the
sheet and lets the queue worker pick up new properties.
"""

from __future__ import annotations

from collections.abc import Callable

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.core.config import SchedulerConfig, get_config
from app.core.logging import get_logger

logger = get_logger(__name__)

_INTERVAL_MINUTES = {"5m": 5, "10m": 10, "30m": 30, "1h": 60}
_WEEKDAYS = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}


class PublishScheduler:
    """Wraps APScheduler with the app's fixed set of intervals."""

    JOB_ID = "publish-cycle"

    def __init__(self, run_callback: Callable[[], None], config: SchedulerConfig | None = None) -> None:
        self._run = run_callback
        self._config = config or get_config().scheduler
        self._scheduler = BackgroundScheduler(daemon=True)
        self._scheduler.start(paused=True)

    def apply(self, config: SchedulerConfig | None = None) -> None:
        """(Re)apply the configured interval; call after settings change."""
        if config is not None:
            self._config = config
        if self._scheduler.get_job(self.JOB_ID):
            self._scheduler.remove_job(self.JOB_ID)

        interval = self._config.interval
        if not self._config.enabled or interval == "manual":
            self._scheduler.pause()
            logger.info("Scheduler disabled (manual mode)")
            return

        if interval in _INTERVAL_MINUTES:
            trigger = IntervalTrigger(minutes=_INTERVAL_MINUTES[interval])
        elif interval == "daily":
            hour, minute = self._parse_time(self._config.daily_time)
            trigger = CronTrigger(hour=hour, minute=minute)
        else:  # weekly
            hour, minute = self._parse_time(self._config.daily_time)
            day = self._config.weekly_day.lower()[:3]
            if day not in _WEEKDAYS:
                day = "mon"
            trigger = CronTrigger(day_of_week=day, hour=hour, minute=minute)

        self._scheduler.add_job(self._safe_run, trigger, id=self.JOB_ID, replace_existing=True)
        self._scheduler.resume()
        logger.info("Scheduler active: %s", interval)

    @staticmethod
    def _parse_time(value: str) -> tuple[int, int]:
        try:
            hour_s, minute_s = value.split(":")
            hour, minute = int(hour_s), int(minute_s)
            if 0 <= hour < 24 and 0 <= minute < 60:
                return hour, minute
        except ValueError:
            pass
        return 9, 0

    def _safe_run(self) -> None:
        """Never let one failed cycle kill the scheduler."""
        try:
            logger.info("Scheduled publish cycle starting")
            self._run()
        except Exception:  # noqa: BLE001
            logger.exception("Scheduled publish cycle crashed")

    def trigger_now(self) -> None:
        """Manual 'Run Now' button."""
        self._safe_run()

    def next_run_time(self) -> str:
        job = self._scheduler.get_job(self.JOB_ID)
        if job is None or job.next_run_time is None:
            return "Not scheduled"
        return job.next_run_time.strftime("%Y-%m-%d %H:%M")

    def shutdown(self) -> None:
        self._scheduler.shutdown(wait=False)
