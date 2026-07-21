"""Accounts page: manage the encrypted Property Oryx API key.

Property Oryx authenticates with an ``X-API-Key`` (generate it from your
Property Oryx account under API access). The key is encrypted with Fernet
before storage - it is never written in plain text.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from app.core.exceptions import OryxApiError
from app.platforms.propertyoryx.client import PropertyOryxClient
from app.services.publisher import PLATFORM_NAME, PublishingEngine
from app.ui.widgets import configure_table, readonly_item, status_item


class ApiKeyDialog(QDialog):
    """Add/replace the API key for a labelled account."""

    def __init__(self, parent: QWidget | None = None, label: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle("Property Oryx API Key")
        form = QFormLayout(self)
        self.label_edit = QLineEdit(label)
        self.label_edit.setPlaceholderText("A name for this account, e.g. 'Main office'")
        self.key_edit = QLineEdit()
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.setPlaceholderText("Paste the 64-character API key")
        form.addRow("Label", self.label_edit)
        form.addRow("API Key", self.key_edit)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)


class AccountsPage(QWidget):
    """Property Oryx API-key management."""

    def __init__(self, engine: PublishingEngine, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._engine = engine
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        title = QLabel("Accounts")
        title.setObjectName("PageTitle")
        layout.addWidget(title)
        layout.addWidget(QLabel(
            "Property Oryx uses an API key (X-API-Key). Keys are encrypted with Fernet (AES) "
            "before storage - they never touch the database in plain text. The newest active "
            "key is used for publishing."
        ))

        actions = QHBoxLayout()
        add_btn = QPushButton("Add / Replace API Key")
        add_btn.setObjectName("SuccessButton")
        add_btn.clicked.connect(self._add)
        test_btn = QPushButton("Test Connection")
        test_btn.clicked.connect(self._test)
        toggle_btn = QPushButton("Enable / Disable")
        toggle_btn.clicked.connect(self._toggle)
        delete_btn = QPushButton("Delete")
        delete_btn.setObjectName("DangerButton")
        delete_btn.clicked.connect(self._delete)
        for b in (add_btn, test_btn, toggle_btn, delete_btn):
            actions.addWidget(b)
        actions.addStretch()
        layout.addLayout(actions)

        self._table = QTableWidget()
        configure_table(self._table, ["ID", "Label", "Status", "Last Verified"])
        self._table.setColumnHidden(0, True)
        layout.addWidget(self._table, stretch=1)
        self.refresh()

    def _selected_id(self) -> int | None:
        rows = {i.row() for i in self._table.selectedIndexes()}
        if not rows:
            return None
        return int(self._table.item(min(rows), 0).text())

    def _add(self) -> None:
        dialog = ApiKeyDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        label = dialog.label_edit.text().strip() or "Property Oryx"
        key = dialog.key_edit.text().strip()
        if not key:
            QMessageBox.warning(self, "API Key", "The API key is required.")
            return
        encrypted = self._engine.vault.encrypt(key)
        self._engine.accounts.add(PLATFORM_NAME, label, encrypted)
        self._engine.invalidate_platform()
        self.refresh()

    def _test(self) -> None:
        account_id = self._selected_id()
        account = next((a for a in self._engine.accounts.list() if a.id == account_id), None)
        if account is None:
            QMessageBox.information(self, "Test Connection", "Select an account first.")
            return
        try:
            key = self._engine.vault.decrypt(account.password_encrypted)
            client = PropertyOryxClient(key, self._engine.config.oryx)
            data = client.account()
            self._engine.accounts.mark_login(account.id, success=True)
            QMessageBox.information(
                self, "Test Connection",
                f"Success. Authenticated as {data.get('name', '?')} ({data.get('email', '?')}).",
            )
        except OryxApiError as exc:
            self._engine.accounts.mark_login(account.id, success=False)
            QMessageBox.critical(self, "Test Connection", f"Failed: {exc}")
        self.refresh()

    def _toggle(self) -> None:
        account_id = self._selected_id()
        account = next((a for a in self._engine.accounts.list() if a.id == account_id), None)
        if account is None:
            return
        new_status = "Disabled" if account.status == "Active" else "Active"
        self._engine.accounts.update(account_id, status=new_status)
        self._engine.invalidate_platform()
        self.refresh()

    def _delete(self) -> None:
        account_id = self._selected_id()
        if account_id is None:
            return
        if QMessageBox.question(self, "Delete", "Delete the selected API key?") == QMessageBox.StandardButton.Yes:
            self._engine.accounts.delete(account_id)
            self._engine.invalidate_platform()
            self.refresh()

    def refresh(self) -> None:
        accounts = self._engine.accounts.list(platform=PLATFORM_NAME)
        self._table.setRowCount(len(accounts))
        for row, a in enumerate(accounts):
            self._table.setItem(row, 0, readonly_item(str(a.id)))
            self._table.setItem(row, 1, readonly_item(a.email))
            self._table.setItem(row, 2, status_item(a.status))
            self._table.setItem(
                row, 3,
                readonly_item(a.last_login.strftime("%Y-%m-%d %H:%M") if a.last_login else "Never"),
            )
