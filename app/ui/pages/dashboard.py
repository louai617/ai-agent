"""Dashboard page: KPI cards, platform status, recent activity, run controls."""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from app.services.publisher import PublishingEngine
from app.ui.widgets import StatCard, configure_table, readonly_item, status_item


class DashboardPage(QWidget):
    """Live operational overview, refreshed every 5 seconds."""

    def __init__(self, engine: PublishingEngine, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._engine = engine
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        title = QLabel("Dashboard")
        title.setObjectName("PageTitle")
        layout.addWidget(title)

        # KPI cards
        cards = QGridLayout()
        cards.setSpacing(12)
        self._card_published = StatCard("Published Today")
        self._card_failed = StatCard("Failed Today")
        self._card_pending = StatCard("Pending")
        self._card_rate = StatCard("Success Rate")
        self._card_avg = StatCard("Avg Publish Time")
        self._card_running = StatCard("Running Jobs")
        for i, card in enumerate(
            (self._card_published, self._card_failed, self._card_pending,
             self._card_rate, self._card_avg, self._card_running)
        ):
            cards.addWidget(card, i // 3, i % 3)
        layout.addLayout(cards)

        # Controls
        controls = QHBoxLayout()
        self._run_btn = QPushButton("Run Now (Sync + Publish)")
        self._run_btn.setObjectName("SuccessButton")
        self._run_btn.clicked.connect(self._run_now)
        self._pause_btn = QPushButton("Pause")
        self._pause_btn.clicked.connect(self._toggle_pause)
        controls.addWidget(self._run_btn)
        controls.addWidget(self._pause_btn)
        controls.addStretch()
        layout.addLayout(controls)

        # Platform status
        layout.addWidget(QLabel("Platform Status"))
        self._platform_table = QTableWidget()
        configure_table(
            self._platform_table,
            ["Platform", "Enabled", "Last Success", "Last Failure", "Consecutive Failures"],
        )
        self._platform_table.setMaximumHeight(140)
        layout.addWidget(self._platform_table)

        # Recent activity
        layout.addWidget(QLabel("Recent Activity"))
        self._activity_table = QTableWidget()
        configure_table(self._activity_table, ["Time", "Level", "Source", "Message"])
        layout.addWidget(self._activity_table, stretch=1)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(5_000)
        self.refresh()

    # ------------------------------------------------------------------ slots

    def _run_now(self) -> None:
        self._engine.run_once()
        self.refresh()

    def _toggle_pause(self) -> None:
        if self._engine.is_paused:
            self._engine.resume()
        else:
            self._engine.pause()
        self.refresh()

    def refresh(self) -> None:
        stats = self._engine.stats.today()
        self._card_published.set_value(str(stats["published_today"]))
        self._card_failed.set_value(str(stats["failed_today"]))
        self._card_pending.set_value(str(stats["pending"]))
        self._card_rate.set_value(f"{stats['success_rate']:.0f}%")
        self._card_avg.set_value(f"{stats['avg_publish_seconds']:.0f}s")
        self._card_running.set_value(str(self._engine.jobs.running_count()))
        self._pause_btn.setText("Resume" if self._engine.is_paused else "Pause")

        platforms = self._engine.platforms.list()
        self._platform_table.setRowCount(len(platforms))
        for row, p in enumerate(platforms):
            self._platform_table.setItem(row, 0, readonly_item(p.display_name))
            self._platform_table.setItem(row, 1, status_item("Active" if p.enabled else "Disabled"))
            self._platform_table.setItem(
                row, 2, readonly_item(p.last_success.strftime("%Y-%m-%d %H:%M") if p.last_success else "-")
            )
            self._platform_table.setItem(
                row, 3, readonly_item(p.last_failure.strftime("%Y-%m-%d %H:%M") if p.last_failure else "-")
            )
            self._platform_table.setItem(row, 4, readonly_item(str(p.consecutive_failures)))

        logs = self._engine.logs.recent(limit=30)
        self._activity_table.setRowCount(len(logs))
        for row, log in enumerate(logs):
            self._activity_table.setItem(row, 0, readonly_item(log.created_at.strftime("%H:%M:%S")))
            self._activity_table.setItem(row, 1, status_item(
                {"ERROR": "Failed", "WARNING": "Needs Review", "INFO": "Published"}.get(log.level, log.level)
            ))
            self._activity_table.item(row, 1).setText(log.level)
            self._activity_table.setItem(row, 2, readonly_item(log.source))
            self._activity_table.setItem(row, 3, readonly_item(log.message[:160]))
