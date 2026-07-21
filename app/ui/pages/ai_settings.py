"""AI Settings page: Gemini model, temperature, tokens, language, prompts."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.core.config import save_config
from app.services.ai import ContentGenerator
from app.services.publisher import PublishingEngine

_MODELS = ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.5-flash-lite"]
_LANGUAGES = ["en", "ar", "fr"]


class AISettingsPage(QWidget):
    """Configure Gemini content generation."""

    def __init__(self, engine: PublishingEngine, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._engine = engine
        cfg = engine.config.ai

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        title = QLabel("AI Settings")
        title.setObjectName("PageTitle")
        layout.addWidget(title)
        layout.addWidget(QLabel(
            "The Gemini API key is read from the GEMINI_API_KEY environment variable "
            "(.env file) and is never stored in configuration or the database."
        ))

        group = QGroupBox("Content Generation")
        form = QFormLayout(group)
        self.enabled = QCheckBox("Enable AI generation (falls back to templates when off)")
        self.enabled.setChecked(cfg.enabled)
        self.model = QComboBox()
        self.model.setEditable(True)
        self.model.addItems(_MODELS)
        self.model.setCurrentText(cfg.model)
        self.temperature = QDoubleSpinBox()
        self.temperature.setRange(0.0, 2.0)
        self.temperature.setSingleStep(0.1)
        self.temperature.setValue(cfg.temperature)
        self.max_tokens = QSpinBox()
        self.max_tokens.setRange(50, 4000)
        self.max_tokens.setValue(cfg.max_tokens)
        self.language = QComboBox()
        self.language.setEditable(True)
        self.language.addItems(_LANGUAGES)
        self.language.setCurrentText(cfg.language)
        self.generate_arabic = QCheckBox(
            "Also generate Arabic title/description (titleAr/descriptionAr) for Property Oryx"
        )
        self.generate_arabic.setChecked(cfg.generate_arabic)
        form.addRow(self.enabled)
        form.addRow("Model", self.model)
        form.addRow("Temperature", self.temperature)
        form.addRow("Max tokens", self.max_tokens)
        form.addRow("Language", self.language)
        form.addRow(self.generate_arabic)
        layout.addWidget(group)

        prompt_group = QGroupBox("Prompts")
        prompt_layout = QVBoxLayout(prompt_group)
        prompt_layout.addWidget(QLabel("Title prompt ({max_chars} placeholder available):"))
        self.title_prompt = QTextEdit(cfg.title_prompt)
        self.title_prompt.setMaximumHeight(80)
        prompt_layout.addWidget(self.title_prompt)
        prompt_layout.addWidget(QLabel("Description prompt ({language} placeholder available):"))
        self.description_prompt = QTextEdit(cfg.description_prompt)
        self.description_prompt.setMaximumHeight(80)
        prompt_layout.addWidget(self.description_prompt)
        layout.addWidget(prompt_group)

        buttons = QHBoxLayout()
        save_btn = QPushButton("Save AI Settings")
        save_btn.setObjectName("SuccessButton")
        save_btn.clicked.connect(self._save)
        buttons.addWidget(save_btn)
        buttons.addStretch()
        layout.addLayout(buttons)
        layout.addStretch()

    def _save(self) -> None:
        cfg = self._engine.config.ai
        cfg.enabled = self.enabled.isChecked()
        cfg.model = self.model.currentText().strip()
        cfg.temperature = self.temperature.value()
        cfg.max_tokens = self.max_tokens.value()
        cfg.language = self.language.currentText().strip() or "en"
        cfg.generate_arabic = self.generate_arabic.isChecked()
        cfg.title_prompt = self.title_prompt.toPlainText().strip()
        cfg.description_prompt = self.description_prompt.toPlainText().strip()
        save_config(self._engine.config)
        # Rebuild the generator so new settings take effect immediately
        self._engine.content = ContentGenerator(cfg)
        QMessageBox.information(self, "AI Settings", "AI settings saved.")
