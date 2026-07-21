"""Scheduler page: automatic run interval configuration."""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.core.config import save_config
from app.scheduler.scheduler import PublishScheduler
from app.services.publisher import PublishingEngine

_INTERVAL_LABELS = {
    "5m": "Every 5 minutes",
    "10m": "Every 10 minutes",
    "30m": "Every 30 minutes",
    "1h": "Every hour",
    "daily": "Daily",
    "weekly": "Weekly",
    "manual": "Manual only",
}


class SchedulerPage(QWidget):
    """Configure the automatic publish cycle."""

    def __init__(
        self,
        engine: PublishingEngine,
        scheduler: PublishScheduler,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._engine = engine
        self._scheduler = scheduler
        cfg = engine.config.scheduler

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        title = QLabel("Scheduler")
        title.setObjectName("PageTitle")
        layout.addWidget(title)

        group = QGroupBox("Automatic Publishing")
        form = QFormLayout(group)
        self.enabled = QCheckBox("Enable automatic runs")
        self.enabled.setChecked(cfg.enabled)
        self.interval = QComboBox()
        for key, label in _INTERVAL_LABELS.items():
            self.interval.addItem(label, key)
        index = self.interval.findData(cfg.interval)
        if index >= 0:
            self.interval.setCurrentIndex(index)
        self.daily_time = QLineEdit(cfg.daily_time)
        self.daily_time.setPlaceholderText("HH:MM (for daily/weekly)")
        self.weekly_day = QComboBox()
        self.weekly_day.addItems(["mon", "tue", "wed", "thu", "fri", "sat", "sun"])
        self.weekly_day.setCurrentText(cfg.weekly_day)
        form.addRow(self.enabled)
        form.addRow("Interval", self.interval)
        form.addRow("Run time", self.daily_time)
        form.addRow("Weekly day", self.weekly_day)
        layout.addWidget(group)

        self._next_run = QLabel()
        layout.addWidget(self._next_run)

        buttons = QHBoxLayout()
        apply_btn = QPushButton("Apply Schedule")
        apply_btn.setObjectName("SuccessButton")
        apply_btn.clicked.connect(self._apply)
        run_btn = QPushButton("Run Now")
        run_btn.clicked.connect(self._run_now)
        buttons.addWidget(apply_btn)
        buttons.addWidget(run_btn)
        buttons.addStretch()
        layout.addLayout(buttons)
        layout.addStretch()

        timer = QTimer(self)
        timer.timeout.connect(self._refresh_next_run)
        timer.start(5_000)
        self._refresh_next_run()

    def _apply(self) -> None:
        cfg = self._engine.config.scheduler
        cfg.enabled = self.enabled.isChecked()
        cfg.interval = self.interval.currentData()
        cfg.daily_time = self.daily_time.text().strip() or "09:00"
        cfg.weekly_day = self.weekly_day.currentText()
        save_config(self._engine.config)
        self._scheduler.apply(cfg)
        self._refresh_next_run()
        QMessageBox.information(self, "Scheduler", "Schedule applied.")

    def _run_now(self) -> None:
        self._scheduler.trigger_now()
        QMessageBox.information(self, "Scheduler", "Publish cycle started.")

    def _refresh_next_run(self) -> None:
        self._next_run.setText(f"Next scheduled run: {self._scheduler.next_run_time()}")
