"""Reusable UI widgets: stat cards, status badges, bar chart, table helpers."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.ui.theme import STATUS_COLORS


class StatCard(QFrame):
    """Dashboard metric card."""

    def __init__(self, label: str, value: str = "0", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("StatCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        self._value = QLabel(value)
        self._value.setObjectName("StatValue")
        self._label = QLabel(label)
        self._label.setObjectName("StatLabel")
        layout.addWidget(self._value)
        layout.addWidget(self._label)

    def set_value(self, value: str) -> None:
        self._value.setText(value)


def status_item(status: str) -> QTableWidgetItem:
    """Table item colored by status."""
    item = QTableWidgetItem(status)
    color = STATUS_COLORS.get(status)
    if color:
        item.setForeground(QColor(color))
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return item


def readonly_item(text: str) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return item


def configure_table(table: QTableWidget, headers: list[str]) -> None:
    """Standard table appearance."""
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setAlternatingRowColors(True)
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setStretchLastSection(True)
    table.setSortingEnabled(True)


class BarChart(QWidget):
    """Minimal dependency-free bar chart for the statistics page."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._series: list[tuple[str, float, float]] = []  # (label, published, failed)
        self.setMinimumHeight(220)

    def set_series(self, series: list[tuple[str, float, float]]) -> None:
        self._series = series[-30:]
        self.update()

    def paintEvent(self, event) -> None:  # noqa: ANN001, N802 - Qt override
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(10, 10, -10, -24)
        if not self._series:
            painter.setPen(QPen(QColor("#5a6172")))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No data yet")
            return
        max_value = max((p + f) for _, p, f in self._series) or 1
        bar_span = rect.width() / len(self._series)
        bar_width = max(4, int(bar_span * 0.6))
        for i, (label, published, failed) in enumerate(self._series):
            x = int(rect.left() + i * bar_span + (bar_span - bar_width) / 2)
            ph = int(rect.height() * published / max_value)
            fh = int(rect.height() * failed / max_value)
            painter.fillRect(x, rect.bottom() - ph, bar_width, ph, QColor("#4ec98a"))
            painter.fillRect(x, rect.bottom() - ph - fh, bar_width, fh, QColor("#e06c75"))
            if len(self._series) <= 14 or i % 3 == 0:
                painter.setPen(QPen(QColor("#5a6172")))
                painter.drawText(
                    x - 14, rect.bottom() + 4, bar_width + 28, 16,
                    Qt.AlignmentFlag.AlignHCenter, label[-5:],
                )
