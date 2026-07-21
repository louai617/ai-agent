"""Logs page: filterable log table with artifact access and export."""

from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from app.services.publisher import PublishingEngine
from app.ui.widgets import configure_table, readonly_item, status_item


def _open_path(path: str) -> None:
    """Open a file with the OS default application."""
    if not path or not Path(path).exists():
        return
    if sys.platform == "win32":
        subprocess.Popen(["cmd", "/c", "start", "", path], shell=False)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


class LogsPage(QWidget):
    """Structured log viewer."""

    def __init__(self, engine: PublishingEngine, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._engine = engine
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        title = QLabel("Logs")
        title.setObjectName("PageTitle")
        layout.addWidget(title)

        filters = QHBoxLayout()
        self._level = QComboBox()
        self._level.addItems(["All Levels", "INFO", "WARNING", "ERROR"])
        self._level.currentIndexChanged.connect(self.refresh)
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search log messages...")
        self._search.textChanged.connect(self.refresh)
        screenshot_btn = QPushButton("Open Screenshot")
        screenshot_btn.clicked.connect(lambda: self._open_artifact("screenshot"))
        html_btn = QPushButton("Open HTML Dump")
        html_btn.clicked.connect(lambda: self._open_artifact("html"))
        export_btn = QPushButton("Export CSV")
        export_btn.clicked.connect(self._export)
        filters.addWidget(self._level)
        filters.addWidget(self._search, stretch=1)
        filters.addWidget(screenshot_btn)
        filters.addWidget(html_btn)
        filters.addWidget(export_btn)
        layout.addLayout(filters)

        self._table = QTableWidget()
        configure_table(
            self._table,
            ["Time (UTC)", "Level", "Source", "Platform", "Property", "Message", "Screenshot", "HTML"],
        )
        layout.addWidget(self._table, stretch=1)

        timer = QTimer(self)
        timer.timeout.connect(self.refresh)
        timer.start(10_000)
        self.refresh()

    def _current_logs(self):
        level = self._level.currentText()
        return self._engine.logs.list(
            level=None if level == "All Levels" else level,
            search=self._search.text().strip() or None,
        )

    def _open_artifact(self, kind: str) -> None:
        rows = {i.row() for i in self._table.selectedIndexes()}
        if not rows:
            return
        column = 6 if kind == "screenshot" else 7
        path = self._table.item(min(rows), column).text()
        if path:
            _open_path(path)
        else:
            QMessageBox.information(self, "Artifact", f"No {kind} recorded for this entry.")

    def _export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export Logs", "logs.csv", "CSV (*.csv)")
        if not path:
            return
        logs = self._current_logs()
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["Time", "Level", "Source", "Platform", "Property", "Message",
                             "Screenshot", "HTML", "Trace"])
            for log in logs:
                writer.writerow([log.created_at.isoformat(), log.level, log.source, log.platform,
                                 log.property_ref, log.message, log.screenshot_path,
                                 log.html_dump_path, log.trace_path])
        QMessageBox.information(self, "Export", f"Exported {len(logs)} log entries.")

    def refresh(self) -> None:
        logs = self._current_logs()
        self._table.setSortingEnabled(False)
        self._table.setRowCount(len(logs))
        for row, log in enumerate(logs):
            self._table.setItem(row, 0, readonly_item(log.created_at.strftime("%Y-%m-%d %H:%M:%S")))
            self._table.setItem(row, 1, status_item(
                {"ERROR": "Failed", "WARNING": "Pending", "INFO": "Published"}.get(log.level, log.level)))
            self._table.item(row, 1).setText(log.level)
            self._table.setItem(row, 2, readonly_item(log.source))
            self._table.setItem(row, 3, readonly_item(log.platform))
            self._table.setItem(row, 4, readonly_item(log.property_ref))
            self._table.setItem(row, 5, readonly_item(log.message[:200]))
            self._table.setItem(row, 6, readonly_item(log.screenshot_path))
            self._table.setItem(row, 7, readonly_item(log.html_dump_path))
        self._table.setSortingEnabled(True)
