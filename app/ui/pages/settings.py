"""Settings page: sheet source, browser, retries, images, notifications.

Saves back to config/config.json (secrets remain in .env only).
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.core.config import reload_config, save_config
from app.services.publisher import PublishingEngine


class SettingsPage(QWidget):
    """General configuration editor."""

    def __init__(self, engine: PublishingEngine, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._engine = engine
        cfg = engine.config

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        title = QLabel("Settings")
        title.setObjectName("PageTitle")
        outer.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setSpacing(14)

        # --- Sheet source
        sheet_group = QGroupBox("Data Source (Google Sheet / Excel)")
        sheet_form = QFormLayout(sheet_group)
        self.source_type = QComboBox()
        self.source_type.addItems(["google", "excel"])
        self.source_type.setCurrentText(cfg.sheet.source_type)
        self.spreadsheet_id = QLineEdit(cfg.sheet.spreadsheet_id)
        self.worksheet_name = QLineEdit(cfg.sheet.worksheet_name)
        self.excel_path = QLineEdit(cfg.sheet.excel_path)
        self.service_account = QLineEdit(cfg.sheet.service_account_file)
        sheet_form.addRow("Source type", self.source_type)
        sheet_form.addRow("Spreadsheet ID", self.spreadsheet_id)
        sheet_form.addRow("Worksheet name", self.worksheet_name)
        sheet_form.addRow("Excel path (excel mode)", self.excel_path)
        sheet_form.addRow("Service account JSON", self.service_account)
        layout.addWidget(sheet_group)

        # --- Property Oryx API
        oryx_group = QGroupBox("Property Oryx API")
        oryx_form = QFormLayout(oryx_group)
        self.api_base_url = QLineEdit(cfg.oryx.api_base_url)
        self.public_url_template = QLineEdit(cfg.oryx.public_listing_url_template)
        self.watermark = QCheckBox("Watermark uploaded images")
        self.watermark.setChecked(cfg.oryx.watermark_images)
        self.api_timeout = QSpinBox()
        self.api_timeout.setRange(5, 300)
        self.api_timeout.setSuffix(" s")
        self.api_timeout.setValue(cfg.oryx.request_timeout_s)
        oryx_form.addRow("API base URL", self.api_base_url)
        oryx_form.addRow("Public listing URL template", self.public_url_template)
        oryx_form.addRow(self.watermark)
        oryx_form.addRow("Request timeout", self.api_timeout)
        layout.addWidget(oryx_group)

        # --- Retry
        retry_group = QGroupBox("Error Recovery")
        retry_form = QFormLayout(retry_group)
        self.max_attempts = QSpinBox()
        self.max_attempts.setRange(1, 10)
        self.max_attempts.setValue(cfg.retry.max_attempts)
        self.backoff_base = QDoubleSpinBox()
        self.backoff_base.setRange(1, 120)
        self.backoff_base.setSuffix(" s")
        self.backoff_base.setValue(cfg.retry.backoff_base_seconds)
        retry_form.addRow("Max attempts", self.max_attempts)
        retry_form.addRow("Backoff base", self.backoff_base)
        layout.addWidget(retry_group)

        # --- Images
        image_group = QGroupBox("Image Processing")
        image_form = QFormLayout(image_group)
        self.max_width = QSpinBox()
        self.max_width.setRange(640, 4096)
        self.max_width.setValue(cfg.images.max_width)
        self.jpeg_quality = QSpinBox()
        self.jpeg_quality.setRange(30, 100)
        self.jpeg_quality.setValue(cfg.images.jpeg_quality)
        self.max_images = QSpinBox()
        self.max_images.setRange(1, 50)
        self.max_images.setValue(cfg.images.max_images_per_listing)
        image_form.addRow("Max width (px)", self.max_width)
        image_form.addRow("JPEG quality", self.jpeg_quality)
        image_form.addRow("Max images per listing", self.max_images)
        layout.addWidget(image_group)

        # --- Notifications
        notif_group = QGroupBox("Notifications (tokens/passwords go in .env)")
        notif_form = QFormLayout(notif_group)
        self.desktop_notif = QCheckBox("Desktop notifications")
        self.desktop_notif.setChecked(cfg.notifications.desktop_enabled)
        self.email_notif = QCheckBox("Email notifications")
        self.email_notif.setChecked(cfg.notifications.email_enabled)
        self.smtp_host = QLineEdit(cfg.notifications.email_smtp_host)
        self.email_from = QLineEdit(cfg.notifications.email_from)
        self.email_to = QLineEdit(", ".join(cfg.notifications.email_to))
        self.telegram_notif = QCheckBox("Telegram notifications")
        self.telegram_notif.setChecked(cfg.notifications.telegram_enabled)
        self.telegram_chat = QLineEdit(cfg.notifications.telegram_chat_id)
        notif_form.addRow(self.desktop_notif)
        notif_form.addRow(self.email_notif)
        notif_form.addRow("SMTP host", self.smtp_host)
        notif_form.addRow("From address", self.email_from)
        notif_form.addRow("To (comma separated)", self.email_to)
        notif_form.addRow(self.telegram_notif)
        notif_form.addRow("Telegram chat ID", self.telegram_chat)
        layout.addWidget(notif_group)

        layout.addStretch()
        scroll.setWidget(body)
        outer.addWidget(scroll, stretch=1)

        buttons = QHBoxLayout()
        save_btn = QPushButton("Save Settings")
        save_btn.setObjectName("SuccessButton")
        save_btn.clicked.connect(self._save)
        buttons.addWidget(save_btn)
        buttons.addStretch()
        outer.addLayout(buttons)

    def _save(self) -> None:
        cfg = self._engine.config
        cfg.sheet.source_type = self.source_type.currentText()
        cfg.sheet.spreadsheet_id = self.spreadsheet_id.text().strip()
        cfg.sheet.worksheet_name = self.worksheet_name.text().strip() or "Properties"
        cfg.sheet.excel_path = self.excel_path.text().strip()
        cfg.sheet.service_account_file = self.service_account.text().strip()
        cfg.oryx.api_base_url = self.api_base_url.text().strip() or cfg.oryx.api_base_url
        cfg.oryx.public_listing_url_template = self.public_url_template.text().strip()
        cfg.oryx.watermark_images = self.watermark.isChecked()
        cfg.oryx.request_timeout_s = self.api_timeout.value()
        cfg.retry.max_attempts = self.max_attempts.value()
        cfg.retry.backoff_base_seconds = self.backoff_base.value()
        cfg.images.max_width = self.max_width.value()
        cfg.images.jpeg_quality = self.jpeg_quality.value()
        cfg.images.max_images_per_listing = self.max_images.value()
        cfg.notifications.desktop_enabled = self.desktop_notif.isChecked()
        cfg.notifications.email_enabled = self.email_notif.isChecked()
        cfg.notifications.email_smtp_host = self.smtp_host.text().strip()
        cfg.notifications.email_from = self.email_from.text().strip()
        cfg.notifications.email_to = [
            e.strip() for e in self.email_to.text().split(",") if e.strip()
        ]
        cfg.notifications.telegram_enabled = self.telegram_notif.isChecked()
        cfg.notifications.telegram_chat_id = self.telegram_chat.text().strip()

        save_config(cfg)
        reload_config()
        # Force the engine to rebuild the sheet source and API client with new settings
        self._engine._sheet = None
        self._engine.invalidate_platform()
        QMessageBox.information(self, "Settings", "Settings saved to config/config.json.")
