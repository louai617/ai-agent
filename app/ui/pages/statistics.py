"""Statistics page: 30-day publish history chart and per-day table."""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QLabel, QTableWidget, QVBoxLayout, QWidget

from app.services.publisher import PublishingEngine
from app.ui.widgets import BarChart, configure_table, readonly_item


class StatisticsPage(QWidget):
    """Aggregated publishing statistics."""

    def __init__(self, engine: PublishingEngine, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._engine = engine
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        title = QLabel("Statistics")
        title.setObjectName("PageTitle")
        layout.addWidget(title)

        layout.addWidget(QLabel("Last 30 days (green = published, red = failed)"))
        self._chart = BarChart()
        layout.addWidget(self._chart)

        self._table = QTableWidget()
        configure_table(
            self._table, ["Day", "Platform", "Published", "Failed", "Success Rate", "Avg Time (s)"]
        )
        layout.addWidget(self._table, stretch=1)

        timer = QTimer(self)
        timer.timeout.connect(self.refresh)
        timer.start(30_000)
        self.refresh()

    def refresh(self) -> None:
        records = self._engine.stats.history(days=30)
        all_records = [r for r in records if r.platform == "all"]
        self._chart.set_series([(r.day, float(r.published), float(r.failed)) for r in all_records])

        self._table.setSortingEnabled(False)
        self._table.setRowCount(len(records))
        for row, r in enumerate(records):
            total = r.published + r.failed
            rate = f"{r.published / total * 100:.0f}%" if total else "-"
            avg = f"{r.total_publish_seconds / r.published:.0f}" if r.published else "-"
            self._table.setItem(row, 0, readonly_item(r.day))
            self._table.setItem(row, 1, readonly_item(r.platform))
            self._table.setItem(row, 2, readonly_item(str(r.published)))
            self._table.setItem(row, 3, readonly_item(str(r.failed)))
            self._table.setItem(row, 4, readonly_item(rate))
            self._table.setItem(row, 5, readonly_item(avg))
        self._table.setSortingEnabled(True)
