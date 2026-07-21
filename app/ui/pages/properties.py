"""Properties page: searchable/filterable table, details with image preview,
publish / retry / archive actions, bulk publishing, CSV export."""

from __future__ import annotations

import csv
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.database.models import PropertyStatus
from app.platforms.registry import available_platforms
from app.services.publisher import PublishingEngine
from app.ui.widgets import configure_table, readonly_item, status_item


class PropertyDetailsDialog(QDialog):
    """Read-only property details with first-image preview."""

    def __init__(self, engine: PublishingEngine, property_id: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        prop = engine.properties.get(property_id)
        self.setWindowTitle(f"Property {prop.property_ref if prop else property_id}")
        self.resize(680, 560)
        layout = QVBoxLayout(self)
        if prop is None:
            layout.addWidget(QLabel("Property not found."))
            return

        preview = QLabel("No processed image yet")
        preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview.setMinimumHeight(220)
        images = engine.image_records.for_property(property_id)
        if images and Path(images[0].processed_path).exists():
            pixmap = QPixmap(images[0].processed_path)
            preview.setPixmap(pixmap.scaledToHeight(220, Qt.TransformationMode.SmoothTransformation))
        layout.addWidget(preview)

        details = QTextEdit()
        details.setReadOnly(True)
        price = f"Rent {prop.rent:,.0f}" if prop.rent else (f"Sale {prop.sale_price:,.0f}" if prop.sale_price else "-")
        details.setPlainText(
            f"Title: {prop.title}\n"
            f"Platform: {prop.platform}    Status: {prop.status.value}\n"
            f"Type: {prop.property_type} ({prop.category})\n"
            f"Bedrooms: {prop.bedrooms}   Bathrooms: {prop.bathrooms}   Area: {prop.area_sqm} sqm\n"
            f"Price: {price} QAR   Furnished: {prop.furnished}\n"
            f"Location: {prop.location}, {prop.district}\n"
            f"Amenities: {prop.amenities}\n"
            f"Agent: {prop.agent}  {prop.phone}\n"
            f"Listing URL: {prop.listing_url or '-'}\n"
            f"Error: {prop.error or '-'}\n\n"
            f"Description:\n{prop.description}"
        )
        layout.addWidget(details)


class PropertiesPage(QWidget):
    """Property management table."""

    def __init__(self, engine: PublishingEngine, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._engine = engine
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        title = QLabel("Properties")
        title.setObjectName("PageTitle")
        layout.addWidget(title)

        # Filters
        filters = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search title, ID, location...")
        self._search.textChanged.connect(self.refresh)
        self._status_filter = QComboBox()
        self._status_filter.addItem("All Statuses", None)
        for status in PropertyStatus:
            self._status_filter.addItem(status.value, status)
        self._status_filter.currentIndexChanged.connect(self.refresh)
        self._platform_filter = QComboBox()
        self._platform_filter.addItem("All Platforms", None)
        for name, cls in sorted(available_platforms().items()):
            self._platform_filter.addItem(cls.display_name, name)
        self._platform_filter.currentIndexChanged.connect(self.refresh)
        filters.addWidget(self._search, stretch=1)
        filters.addWidget(self._status_filter)
        filters.addWidget(self._platform_filter)
        layout.addLayout(filters)

        # Actions
        actions = QHBoxLayout()
        sync_btn = QPushButton("Sync From Sheet")
        sync_btn.clicked.connect(self._sync)
        publish_btn = QPushButton("Publish Selected (High Priority)")
        publish_btn.setObjectName("SuccessButton")
        publish_btn.clicked.connect(self._publish_selected)
        bulk_btn = QPushButton("Publish All Pending")
        bulk_btn.clicked.connect(self._publish_all_pending)
        details_btn = QPushButton("Details / Preview")
        details_btn.clicked.connect(self._show_details)
        archive_btn = QPushButton("Archive")
        archive_btn.clicked.connect(self._archive_selected)
        export_btn = QPushButton("Export CSV")
        export_btn.clicked.connect(self._export_csv)
        for b in (sync_btn, publish_btn, bulk_btn, details_btn, archive_btn, export_btn):
            actions.addWidget(b)
        actions.addStretch()
        layout.addLayout(actions)

        self._table = QTableWidget()
        configure_table(
            self._table,
            ["ID", "Ref", "Platform", "Status", "Title", "Type", "Beds", "Price", "Location", "Listing URL", "Error"],
        )
        self._table.setColumnHidden(0, True)
        layout.addWidget(self._table, stretch=1)

        timer = QTimer(self)
        timer.timeout.connect(self.refresh)
        timer.start(10_000)
        self.refresh()

    # ---------------------------------------------------------------- actions

    def _selected_ids(self) -> list[int]:
        rows = {i.row() for i in self._table.selectedIndexes()}
        return [int(self._table.item(r, 0).text()) for r in sorted(rows)]

    def _sync(self) -> None:
        try:
            count = self._engine.sync_from_sheet()
            self._engine.start_worker()
            QMessageBox.information(self, "Sheet Sync", f"Sync complete. {count} properties enqueued.")
        except Exception as exc:  # noqa: BLE001 - show any config/network problem
            QMessageBox.critical(self, "Sheet Sync Failed", str(exc))
        self.refresh()

    def _publish_selected(self) -> None:
        for property_id in self._selected_ids():
            prop = self._engine.properties.get(property_id)
            if prop is None:
                continue
            self._engine.properties.set_status(property_id, PropertyStatus.PENDING)
            self._engine.jobs.enqueue(property_id, prop.platform, priority=1)
        self._engine.start_worker()
        self.refresh()

    def _publish_all_pending(self) -> None:
        pending = self._engine.properties.pending()
        for prop in pending:
            self._engine.jobs.enqueue(prop.id, prop.platform)
        self._engine.start_worker()
        QMessageBox.information(self, "Bulk Publish", f"{len(pending)} properties queued.")
        self.refresh()

    def _archive_selected(self) -> None:
        for property_id in self._selected_ids():
            self._engine.properties.set_status(property_id, PropertyStatus.ARCHIVED)
        self.refresh()

    def _show_details(self) -> None:
        ids = self._selected_ids()
        if ids:
            PropertyDetailsDialog(self._engine, ids[0], self).exec()

    def _export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export Properties", "properties.csv", "CSV (*.csv)")
        if not path:
            return
        rows = self._engine.properties.list(limit=10_000)
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["Ref", "Platform", "Status", "Title", "Type", "Bedrooms",
                             "Rent", "Sale Price", "Location", "District", "Listing URL", "Error"])
            for p in rows:
                writer.writerow([p.property_ref, p.platform, p.status.value, p.title, p.property_type,
                                 p.bedrooms, p.rent, p.sale_price, p.location, p.district,
                                 p.listing_url, p.error])
        QMessageBox.information(self, "Export", f"Exported {len(rows)} properties to {path}")

    # ---------------------------------------------------------------- refresh

    def refresh(self) -> None:
        rows = self._engine.properties.list(
            status=self._status_filter.currentData(),
            platform=self._platform_filter.currentData(),
            search=self._search.text().strip() or None,
        )
        self._table.setSortingEnabled(False)
        self._table.setRowCount(len(rows))
        for row, p in enumerate(rows):
            price = f"{p.rent:,.0f}/mo" if p.rent else (f"{p.sale_price:,.0f}" if p.sale_price else "-")
            values = [str(p.id), p.property_ref, p.platform, None, p.title, p.property_type,
                      str(p.bedrooms if p.bedrooms is not None else "-"), price,
                      p.location, p.listing_url, p.error[:80]]
            for col, value in enumerate(values):
                if col == 3:
                    self._table.setItem(row, col, status_item(p.status.value))
                else:
                    self._table.setItem(row, col, readonly_item(value))
        self._table.setSortingEnabled(True)
