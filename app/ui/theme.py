"""Application theming - professional dark mode via Qt style sheets."""

DARK_QSS = """
* { font-family: 'Segoe UI', 'Inter', sans-serif; font-size: 13px; }

QMainWindow, QWidget { background-color: #12151c; color: #e6e9ef; }

#Sidebar { background-color: #0c0f14; border-right: 1px solid #232838; }
#Sidebar QPushButton {
    background: transparent; border: none; border-radius: 8px;
    color: #9aa3b5; text-align: left; padding: 10px 16px; font-size: 14px;
}
#Sidebar QPushButton:hover { background-color: #1a1f2b; color: #e6e9ef; }
#Sidebar QPushButton:checked { background-color: #223051; color: #7aa2ff; font-weight: 600; }
#AppTitle { font-size: 16px; font-weight: 700; color: #7aa2ff; padding: 18px 16px 10px 16px; }

#PageTitle { font-size: 20px; font-weight: 700; color: #ffffff; }
#StatCard {
    background-color: #1a1f2b; border: 1px solid #232838; border-radius: 12px;
}
#StatValue { font-size: 26px; font-weight: 700; color: #7aa2ff; }
#StatLabel { font-size: 12px; color: #9aa3b5; }

QTableWidget, QTableView {
    background-color: #161a24; alternate-background-color: #1a1f2b;
    border: 1px solid #232838; border-radius: 8px; gridline-color: #232838;
    selection-background-color: #223051; selection-color: #ffffff;
}
QHeaderView::section {
    background-color: #1a1f2b; color: #9aa3b5; border: none;
    border-bottom: 1px solid #232838; padding: 8px; font-weight: 600;
}

QPushButton {
    background-color: #223051; color: #dfe7ff; border: 1px solid #2c3c66;
    border-radius: 8px; padding: 8px 16px; font-weight: 600;
}
QPushButton:hover { background-color: #2c3c66; }
QPushButton:disabled { background-color: #1a1f2b; color: #5a6172; border-color: #232838; }
QPushButton#DangerButton { background-color: #4a1f26; border-color: #6e2e38; color: #ffb4bd; }
QPushButton#DangerButton:hover { background-color: #6e2e38; }
QPushButton#SuccessButton { background-color: #1d3b2a; border-color: #2c5940; color: #9ae6b4; }
QPushButton#SuccessButton:hover { background-color: #2c5940; }

QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTimeEdit {
    background-color: #161a24; border: 1px solid #2a3040; border-radius: 8px;
    padding: 7px 10px; color: #e6e9ef; selection-background-color: #223051;
}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus { border-color: #7aa2ff; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox QAbstractItemView {
    background-color: #1a1f2b; border: 1px solid #2a3040; selection-background-color: #223051;
}

QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 16px; height: 16px; border-radius: 4px;
    border: 1px solid #2a3040; background: #161a24; }
QCheckBox::indicator:checked { background-color: #7aa2ff; border-color: #7aa2ff; }

QScrollBar:vertical { background: #12151c; width: 10px; border-radius: 5px; }
QScrollBar::handle:vertical { background: #2a3040; border-radius: 5px; min-height: 30px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }

QGroupBox {
    border: 1px solid #232838; border-radius: 10px; margin-top: 12px;
    padding-top: 16px; font-weight: 600; color: #9aa3b5;
}
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; }

QTabWidget::pane { border: 1px solid #232838; border-radius: 8px; }
QTabBar::tab {
    background: transparent; color: #9aa3b5; padding: 8px 18px;
    border-bottom: 2px solid transparent;
}
QTabBar::tab:selected { color: #7aa2ff; border-bottom-color: #7aa2ff; }

QToolTip { background-color: #1a1f2b; color: #e6e9ef; border: 1px solid #2a3040; }
QStatusBar { background: #0c0f14; color: #9aa3b5; border-top: 1px solid #232838; }
"""

# Status badge colors used by table renderers
STATUS_COLORS = {
    "Pending": "#d6a642",
    "Publishing": "#7aa2ff",
    "Published": "#4ec98a",
    "Posted": "#4ec98a",
    "Failed": "#e06c75",
    "Needs Review": "#e5905f",
    "Archived": "#9aa3b5",
    "Deleted": "#5a6172",
    "Queued": "#d6a642",
    "Running": "#7aa2ff",
    "Completed": "#4ec98a",
    "Cancelled": "#9aa3b5",
    "Paused": "#e5905f",
    "Active": "#4ec98a",
    "Login Failed": "#e06c75",
    "Disabled": "#9aa3b5",
}
