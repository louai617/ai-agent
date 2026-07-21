"""Main application window: sidebar navigation, pages, system tray notifications."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QPushButton,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from app import __app_name__, __version__
from app.scheduler.scheduler import PublishScheduler
from app.services.publisher import PublishingEngine
from app.ui.pages.accounts import AccountsPage
from app.ui.pages.ai_settings import AISettingsPage
from app.ui.pages.dashboard import DashboardPage
from app.ui.pages.logs import LogsPage
from app.ui.pages.properties import PropertiesPage
from app.ui.pages.scheduler import SchedulerPage
from app.ui.pages.settings import SettingsPage
from app.ui.pages.statistics import StatisticsPage
from app.ui.theme import DARK_QSS


def _app_icon() -> QIcon:
    """Programmatic icon so the app has no binary asset dependencies."""
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor("#223051"))
    painter.setPen(QColor("#7aa2ff"))
    painter.drawRoundedRect(4, 4, 56, 56, 12, 12)
    painter.setPen(QColor("#7aa2ff"))
    font = painter.font()
    font.setPointSize(24)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "E")
    painter.end()
    return QIcon(pixmap)


class MainWindow(QMainWindow):
    """Top-level window wiring the engine, scheduler and all pages together."""

    NAV_ITEMS = [
        "Dashboard", "Properties", "Accounts", "Logs",
        "Scheduler", "AI Settings", "Statistics", "Settings",
    ]

    def __init__(self, engine: PublishingEngine, scheduler: PublishScheduler) -> None:
        super().__init__()
        self._engine = engine
        self._scheduler = scheduler
        self.setWindowTitle(f"{__app_name__} v{__version__}")
        self.setWindowIcon(_app_icon())
        self.resize(1280, 800)
        self.setStyleSheet(DARK_QSS)

        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Sidebar
        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(210)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(8, 0, 8, 12)
        app_title = QLabel("Elite Publisher")
        app_title.setObjectName("AppTitle")
        side_layout.addWidget(app_title)

        self._pages = QStackedWidget()
        self._pages.addWidget(DashboardPage(engine))
        self._pages.addWidget(PropertiesPage(engine))
        self._pages.addWidget(AccountsPage(engine))
        self._pages.addWidget(LogsPage(engine))
        self._pages.addWidget(SchedulerPage(engine, scheduler))
        self._pages.addWidget(AISettingsPage(engine))
        self._pages.addWidget(StatisticsPage(engine))
        self._pages.addWidget(SettingsPage(engine))

        group = QButtonGroup(self)
        group.setExclusive(True)
        for i, name in enumerate(self.NAV_ITEMS):
            button = QPushButton(name)
            button.setCheckable(True)
            button.setChecked(i == 0)
            button.clicked.connect(lambda _=False, index=i: self._pages.setCurrentIndex(index))
            group.addButton(button)
            side_layout.addWidget(button)
        side_layout.addStretch()
        version = QLabel(f"v{__version__}")
        version.setObjectName("StatLabel")
        version.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        side_layout.addWidget(version)

        root_layout.addWidget(sidebar)
        root_layout.addWidget(self._pages, stretch=1)
        self.setCentralWidget(root)
        self.statusBar().showMessage("Ready")

        self._setup_tray()
        # Wire desktop notifications from the engine to the tray icon
        engine.notifier.desktop_callback = self._show_tray_message

    # ------------------------------------------------------------------- tray

    def _setup_tray(self) -> None:
        self._tray = QSystemTrayIcon(_app_icon(), self)
        self._tray.setToolTip(__app_name__)
        menu = QMenu()
        show_action = QAction("Show", self)
        show_action.triggered.connect(self.showNormal)
        run_action = QAction("Run Publish Cycle", self)
        run_action.triggered.connect(self._engine.run_once)
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(QApplication.instance().quit)
        menu.addAction(show_action)
        menu.addAction(run_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self._tray.setContextMenu(menu)
        self._tray.show()

    def _show_tray_message(self, title: str, message: str) -> None:
        self._tray.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 8_000)

    # -------------------------------------------------------------- lifecycle

    def closeEvent(self, event) -> None:  # noqa: ANN001, N802 - Qt override
        """Stop background machinery cleanly on exit."""
        self._engine.stop_worker()
        self._scheduler.shutdown()
        self._tray.hide()
        super().closeEvent(event)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt override
        return QSize(1280, 800)
