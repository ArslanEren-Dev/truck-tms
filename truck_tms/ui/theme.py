"""Look and feel: light (white) / dark (black) themes, icons, button and tab animations."""

from __future__ import annotations

import sys
from functools import cache
from pathlib import Path

from PySide6.QtCore import (
    QByteArray,
    QEasingCurve,
    QEvent,
    QLibraryInfo,
    QLocale,
    QObject,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QSize,
    Qt,
    QTranslator,
    QVariantAnimation,
)
from PySide6.QtGui import QColor, QIcon, QPainter, QPalette, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QPushButton,
    QWidget,
)

THEMES = ("light", "dark")

TOKENS = {
    "light": {
        "bg": "#FFFFFF", "surface": "#F5F7FA", "surface2": "#EDF1F6", "border": "#D9E0E8",
        "text": "#1B2430", "muted": "#6B7685",
        "accent": "#1E63C6", "accent_hover": "#2A72DA", "accent_pressed": "#164F9F", "accent_text": "#FFFFFF",
        "danger": "#D63A3A", "danger_soft": "#FDECEC",
        "alt": "#F7F9FC", "select": "#DCE8FA", "select_text": "#0E2A52", "header": "#F3F6FA",
        "input": "#FFFFFF", "btn": "#FFFFFF", "btn_hover": "#F1F5FB", "btn_pressed": "#E2E9F4",
        "warning": "#C62828", "sidebar": "#F7F9FC", "card": "#FFFFFF", "toast": "#1B2430", "toast_text": "#FFFFFF",
        "success_bg": "#E6F4EA", "success_fg": "#1E7B34", "warning_bg": "#FFF3DF", "warning_fg": "#9A5A00",
        "danger_bg": "#FDECEC", "danger_fg": "#C62828", "info_bg": "#E3EEFC", "info_fg": "#1E63C6",
        "neutral_bg": "#EEF1F5", "neutral_fg": "#5F6B7A",
        "accent2": "#5B9BF0", "hero_end": "#4338CA", "series": "#1E63C6,#F5A623,#E8743B,#D63A3A,#8E1E1E,#7C5CC4",
    },
    "dark": {
        "bg": "#121417", "surface": "#181C21", "surface2": "#20252C", "border": "#2E353E",
        "text": "#E6E9ED", "muted": "#8D97A3",
        "accent": "#3B82F6", "accent_hover": "#5A96F8", "accent_pressed": "#2E6AD0", "accent_text": "#FFFFFF",
        "danger": "#EF5350", "danger_soft": "#3A1F22",
        "alt": "#16191E", "select": "#1E3A66", "select_text": "#FFFFFF", "header": "#1B2026",
        "input": "#1A1E23", "btn": "#20252C", "btn_hover": "#29313B", "btn_pressed": "#1A1F25",
        "warning": "#FF6E6E", "sidebar": "#15181D", "card": "#181C21", "toast": "#2B323C", "toast_text": "#FFFFFF",
        "success_bg": "#163322", "success_fg": "#6BD08A", "warning_bg": "#3A2B12", "warning_fg": "#F2B45A",
        "danger_bg": "#3A1F22", "danger_fg": "#FF8A80", "info_bg": "#172B4D", "info_fg": "#7DB0FF",
        "neutral_bg": "#262C34", "neutral_fg": "#A3ADB9",
        "accent2": "#7DB0FF", "hero_end": "#312E81", "series": "#3B82F6,#F2B45A,#F08A55,#EF5350,#C2414B,#A78BFA",
    },
}

_current_theme = "light"


def asset_path(name: str) -> Path:
    """Path of a file in truck_tms/assets, also inside the PyInstaller .exe."""
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "truck_tms" / "assets" / name
    return Path(__file__).resolve().parent.parent / "assets" / name


def token(name: str) -> str:
    return TOKENS[_current_theme][name]


def warning_color(theme: str | None = None) -> QColor:
    return QColor(TOKENS[theme or _current_theme]["warning"])


def _palette(theme: str) -> QPalette:
    c = {k: QColor(v) for k, v in TOKENS[theme].items()}
    p = QPalette()
    R = QPalette.ColorRole
    p.setColor(R.Window, c["bg"])
    p.setColor(R.WindowText, c["text"])
    p.setColor(R.Base, c["input"])
    p.setColor(R.AlternateBase, c["alt"])
    p.setColor(R.ToolTipBase, c["surface2"])
    p.setColor(R.ToolTipText, c["text"])
    p.setColor(R.PlaceholderText, c["muted"])
    p.setColor(R.Text, c["text"])
    p.setColor(R.Button, c["btn"])
    p.setColor(R.ButtonText, c["text"])
    p.setColor(R.BrightText, c["danger"])
    p.setColor(R.Link, c["accent"])
    p.setColor(R.Highlight, c["accent"])
    p.setColor(R.HighlightedText, QColor("#FFFFFF"))
    p.setColor(R.Light, c["surface"])
    p.setColor(R.Midlight, c["surface2"])
    p.setColor(R.Mid, c["border"])
    p.setColor(R.Dark, c["border"])
    p.setColor(R.Shadow, QColor(0, 0, 0, 80))
    for role in (R.Text, R.ButtonText, R.WindowText):
        p.setColor(QPalette.ColorGroup.Disabled, role, c["muted"])
    return p


def stylesheet(theme: str) -> str:
    t = dict(TOKENS[theme])
    t["chevron"] = asset_path(f"chevron_{theme}.svg").as_posix()
    t["chevron_up"] = asset_path(f"chevron_up_{theme}.svg").as_posix()
    qss = """
QMainWindow, QDialog { background: @bg; }
QWidget { font-family: "Segoe UI Variable Text", "Segoe UI", "Inter", "Helvetica Neue", Arial, sans-serif;
          font-size: 10pt; }
QTabWidget::pane { border: 1px solid @border; border-radius: 10px; background: @bg; top: -1px; }
QTabBar::tab { background: transparent; color: @muted; padding: 9px 16px; margin-right: 2px;
               border: none; border-bottom: 2px solid transparent; font-weight: 600; }
QTabBar::tab:hover { color: @text; background: @surface2; border-top-left-radius: 8px; border-top-right-radius: 8px; }
QTabBar::tab:selected { color: @accent; border-bottom: 2px solid @accent; }
QPushButton { background: @btn; color: @text; border: 1px solid @border; border-radius: 8px;
              padding: 6px 14px; font-weight: 600; min-height: 20px; }
QPushButton:hover { background: @btn_hover; border-color: @accent; }
QPushButton:pressed { background: @btn_pressed; }
QPushButton:disabled { color: @muted; background: @surface; border-color: @border; }
QPushButton:default { border-color: @accent; }
QPushButton[variant="primary"] { background: @accent; color: @accent_text; border: 1px solid @accent; }
QPushButton[variant="primary"]:hover { background: @accent_hover; border-color: @accent_hover; }
QPushButton[variant="primary"]:pressed { background: @accent_pressed; }
QPushButton[variant="primary"]:disabled { background: @surface2; color: @muted; border-color: @border; }
QPushButton[variant="danger"] { color: @danger; }
QPushButton[variant="danger"]:hover { background: @danger_soft; border-color: @danger; }
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QDateEdit, QSpinBox {
    background: @input; color: @text; border: 1px solid @border; border-radius: 6px; padding: 5px 8px;
    selection-background-color: @accent; selection-color: #FFFFFF; }
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus, QDateEdit:focus { border: 1px solid @accent; }
QLineEdit:hover, QComboBox:hover, QDateEdit:hover { border-color: @muted; }
QLineEdit:disabled, QComboBox:disabled, QDateEdit:disabled { color: @muted; background: @surface; }
QComboBox::drop-down, QDateEdit::drop-down { border: none; width: 24px;
    subcontrol-origin: padding; subcontrol-position: center right; }
QComboBox::down-arrow, QDateEdit::down-arrow { image: url("@chevron"); width: 12px; height: 12px; }
QSpinBox { padding-right: 24px; }
QSpinBox:focus { border: 1px solid @accent; }
QSpinBox:hover { border-color: @muted; }
QSpinBox::up-button, QSpinBox::down-button { subcontrol-origin: border; width: 22px; border: none;
    background: transparent; margin: 2px 2px 2px 0; border-radius: 4px; }
QSpinBox::up-button { subcontrol-position: top right; }
QSpinBox::down-button { subcontrol-position: bottom right; }
QSpinBox::up-button:hover, QSpinBox::down-button:hover { background: @surface2; }
QSpinBox::up-arrow { image: url("@chevron_up"); width: 10px; height: 10px; }
QSpinBox::down-arrow { image: url("@chevron"); width: 10px; height: 10px; }
QComboBox QAbstractItemView { background: @input; color: @text; border: 1px solid @border;
    selection-background-color: @select; selection-color: @select_text; outline: 0; padding: 4px; }
QTableView { background: @bg; alternate-background-color: @alt; gridline-color: @border;
    border: 1px solid @border; border-radius: 8px; selection-background-color: @select; selection-color: @select_text; }
QTableView::item { padding: 2px 6px; }
QHeaderView::section { background: @header; color: @muted; padding: 7px 8px; border: none;
    border-bottom: 1px solid @border; border-right: 1px solid @border; font-weight: 600; }
QTableCornerButton::section { background: @header; border: none; }
QGroupBox { border: 1px solid @border; border-radius: 10px; margin-top: 14px; padding-top: 10px; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; color: @muted; }
QScrollBar:vertical { background: transparent; width: 11px; margin: 2px; }
QScrollBar::handle:vertical { background: @border; border-radius: 4px; min-height: 30px; }
QScrollBar:horizontal { background: transparent; height: 11px; margin: 2px; }
QScrollBar::handle:horizontal { background: @border; border-radius: 4px; min-width: 30px; }
QScrollBar::handle:hover { background: @muted; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: none; }
QStatusBar { background: @surface; color: @muted; border-top: 1px solid @border; }
QStatusBar QLabel { color: @muted; padding: 2px 8px; }
QStatusBar::item { border: none; }
QMenuBar { background: @bg; color: @text; padding: 2px; }
QMenuBar::item { padding: 6px 10px; background: transparent; border-radius: 6px; }
QMenuBar::item:selected { background: @surface2; }
QMenu { background: @input; color: @text; border: 1px solid @border; padding: 4px; border-radius: 8px; }
QMenu::item { padding: 6px 24px 6px 12px; border-radius: 6px; }
QMenu::item:selected { background: @select; color: @select_text; }
QMenu::separator { height: 1px; background: @border; margin: 4px 8px; }
QToolTip { background: @surface2; color: @text; border: 1px solid @border; padding: 4px 6px; }
QLabel[role="hint"] { color: @muted; }
QLabel[role="title"] { font-size: 13pt; font-weight: 700; }
QCheckBox { spacing: 6px; }
QCalendarWidget QWidget#qt_calendar_navigationbar { background: @surface; }
QCalendarWidget QToolButton { color: @text; background: transparent; border-radius: 6px; padding: 4px 8px; }
QCalendarWidget QToolButton:hover { background: @surface2; }
QCalendarWidget QAbstractItemView { background: @input; color: @text;
    selection-background-color: @accent; selection-color: #FFFFFF; }

/* --- sidebar navigation --- */
QFrame#Sidebar { background: @sidebar; border: none; border-right: 1px solid @border; }
QLabel#Brand { font-size: 14pt; font-weight: 800; color: @text; }
QLabel#SidebarSection { color: @muted; font-size: 8pt; font-weight: 700; letter-spacing: 1px; padding: 0 14px; }
QPushButton#NavButton { background: transparent; border: none; border-radius: 8px; text-align: left;
    padding: 9px 14px; color: @muted; font-weight: 600; min-height: 18px; }
QPushButton#NavButton:hover { color: @text; background: @surface2; }
QPushButton#NavButton:checked { color: @accent; background: transparent; }
QPushButton#NavButton:checked:hover { background: transparent; }
QFrame#NavIndicator { background: @select; border-radius: 8px; border-left: 3px solid @accent; }
QLabel#Version { color: @muted; font-size: 8pt; padding: 0 14px; }
QLabel[role="pagetitle"] { font-size: 18pt; font-weight: 800; color: @text; }
QLabel[role="pagesub"] { color: @muted; font-size: 10pt; }
QWidget#PageHeader { background: @bg; }

/* --- cards, dashboard --- */
QFrame#Card { background: @card; border: 1px solid @border; border-radius: 12px; }
QFrame#Card:hover { border-color: @accent; }
QLabel[role="cardtitle"] { color: @muted; font-size: 8.5pt; font-weight: 700; letter-spacing: 0.5px; }
QLabel[role="kpi"] { font-size: 19pt; font-weight: 800; color: @text; }
QLabel[role="kpisub"] { color: @muted; font-size: 9pt; }
QLabel[role="section"] { font-size: 11.5pt; font-weight: 700; color: @text; }
QLabel[role="chip"] { background: @select; border-radius: 10px; }
QLabel[role="chip"][tone="danger"] { background: @danger_bg; }
QLabel[role="chip"][tone="success"] { background: @success_bg; }

/* --- dialogs: header band and section cards --- */
QWidget#DialogHeader { background: @surface; border-bottom: 1px solid @border; }
QScrollArea#DialogScroll, QWidget#DialogBody { background: @bg; }
QWidget#DialogFooter { background: @bg; border-top: 1px solid @border; }
QFrame#PayoutCard { background: @select; border-radius: 12px; }
QLabel[role="payouttitle"] { color: @accent; font-size: 9pt; font-weight: 800; letter-spacing: 0.6px; }
QLabel[role="payoutvalue"] { color: @text; font-size: 22pt; font-weight: 800; }
QLabel[role="payoutsub"] { color: @muted; font-size: 9.5pt; }
QLabel#DialogChip { background: @select; border-radius: 12px; }
QLabel[role="dialogtitle"] { font-size: 14pt; font-weight: 800; color: @text; }
QLabel[role="dialogsub"] { color: @muted; font-size: 9.5pt; }
QFrame#Section { background: @card; border: 1px solid @border; border-radius: 12px; }
QLabel[role="sectiontitle"] { color: @muted; font-size: 8.5pt; font-weight: 800; letter-spacing: 0.6px; }
QLabel[role="metric"] { background: @surface; border: 1px solid @border; border-radius: 8px; padding: 6px 10px; }

/* --- empty state --- */
QLabel[role="emptytitle"] { font-size: 13pt; font-weight: 700; color: @text; }
QLabel[role="emptyhint"] { color: @muted; font-size: 10pt; }

/* --- overview hero band (glass buttons on a gradient) --- */
QFrame#Hero QLabel { color: #FFFFFF; background: transparent; }
QLabel[role="herotitle"] { font-size: 20pt; font-weight: 800; }
QLabel[role="herosub"] { font-size: 10pt; color: rgba(255, 255, 255, 0.82); }
QFrame#Hero QPushButton { background: rgba(255, 255, 255, 0.14); color: #FFFFFF;
    border: 1px solid rgba(255, 255, 255, 0.30); }
QFrame#Hero QPushButton:hover { background: rgba(255, 255, 255, 0.24); border-color: rgba(255, 255, 255, 0.55); }
QFrame#Hero QPushButton:pressed { background: rgba(255, 255, 255, 0.10); }
QFrame#Hero QPushButton[variant="primary"] { background: #FFFFFF; color: @accent; border: 1px solid #FFFFFF; }
QFrame#Hero QPushButton[variant="primary"]:hover { background: #EEF3FF; }
QLabel[role="delta"] { border-radius: 8px; padding: 1px 7px; font-size: 8.5pt; font-weight: 700; }
QLabel[role="delta"][tone="success"] { background: @success_bg; color: @success_fg; }
QLabel[role="delta"][tone="danger"] { background: @danger_bg; color: @danger_fg; }
QLabel[role="delta"][tone="neutral"] { background: @neutral_bg; color: @neutral_fg; }
QLabel[role="step"] { background: @surface2; color: @muted; border-radius: 13px; font-weight: 800; }
QLabel[role="step"][done="true"] { background: @success_bg; color: @success_fg; }

/* --- load board and detail panel --- */
QFrame#BoardColumn { background: @surface; border: 1px solid @border; border-radius: 12px; }
QLabel[role="colcount"] { background: @surface2; color: @muted; border-radius: 9px; padding: 0 7px; font-weight: 700; }
QListWidget#CardList { background: transparent; border: none; outline: 0; }
QFrame#DetailPanel { background: @card; border: 1px solid @border; border-radius: 14px; }
QLabel[role="detailtitle"] { font-size: 15pt; font-weight: 800; color: @text; }
QPushButton[segment="true"] { border-radius: 0; padding: 6px 12px; }
QPushButton[segment="true"]:checked { background: @select; color: @accent; border-color: @accent; }
QPushButton[segment="first"] { border-top-right-radius: 0; border-bottom-right-radius: 0; }
QPushButton[segment="last"] { border-top-left-radius: 0; border-bottom-left-radius: 0; margin-left: -1px; }
QPushButton[segment="first"]:checked, QPushButton[segment="last"]:checked { background: @select; color: @accent;
    border-color: @accent; }

/* --- toast notifications --- */
QFrame#Toast { background: @toast; border-radius: 10px; }
QFrame#Toast QLabel { color: @toast_text; font-weight: 600; }
QFrame#Toast QPushButton { background: transparent; color: #7DB0FF; border: none; font-weight: 700; padding: 2px 6px; }
QFrame#Toast QPushButton:hover { text-decoration: underline; }
"""
    for key in sorted(t, key=len, reverse=True):  # longest first: @accent_hover before @accent
        qss = qss.replace("@" + key, t[key])
    return qss


def apply_theme(theme: str) -> None:
    global _current_theme
    _current_theme = theme if theme in TOKENS else "light"
    app = QApplication.instance()
    if app is None:
        return
    app.setStyle("Fusion")
    app.setPalette(_palette(_current_theme))
    app.setStyleSheet(stylesheet(_current_theme))
    icon.cache_clear()
    if not any(isinstance(f, ButtonAnimator) for f in app.children()):
        app.installEventFilter(ButtonAnimator(app))


# ----------------------------------------------------------------------- language
_qt_translator: QTranslator | None = None


def apply_qt_language(code: str) -> None:
    """Translate Qt's own texts (context menus, calendar, standard buttons) and set the locale."""
    global _qt_translator
    QLocale.setDefault(QLocale("tr_TR" if code == "tr" else "en_US"))
    app = QApplication.instance()
    if app is None:
        return
    if _qt_translator is not None:
        app.removeTranslator(_qt_translator)
        _qt_translator = None
    if code != "en":
        translator = QTranslator(app)
        folders = [QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)]
        if hasattr(sys, "_MEIPASS"):
            folders.append(str(Path(sys._MEIPASS) / "PySide6" / "translations"))
        for folder in folders:
            if translator.load(f"qtbase_{code}", folder):
                app.installTranslator(translator)
                _qt_translator = translator
                break


# -------------------------------------------------------------------------- icons
ICON_PATHS = {
    "shield": "M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6zM9 12l2 2 4-4",
    "receipt": "M6 3h12v18l-3-2-3 2-3-2-3 2zM9 8h6M9 12h6M9 16h4",
    "map": "M3 6l6-3 6 3 6-3v15l-6 3-6-3-6 3zM9 3v15M15 6v15",
    "bell": "M6 16v-5a6 6 0 0 1 12 0v5l2 2H4zM10 21h4",
    "plus": "M12 5v14M5 12h14",
    "edit": "M4 20h4L19 9l-4-4L4 16v4zM13.5 6.5l4 4",
    "trash": "M4 7h16M10 11v6M14 11v6M9 7V4h6v3M6 7l1 13h10l1-13",
    "history": "M3 12a9 9 0 1 0 3-6.7L3 8M3 3v5h5M12 7v5l3 2",
    "export": "M12 3v12M7 10l5 5 5-5M5 21h14",
    "print": "M7 9V3h10v6M7 18H4v-8h16v8h-3M7 14h10v7H7z",
    "chart": "M5 20V10M12 20V4M19 20v-7",
    "save": "M5 3h11l3 3v15H5zM8 3v5h7V3M8 14h8v7H8z",
    "folder": "M3 6h6l2 2h10v11H3z",
    "close": "M6 6l12 12M18 6L6 18",
    "file": "M6 3h8l4 4v14H6zM14 3v4h4",
    "grid": "M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z",
    "truck": "M2 6h12v10H2zM14 9h4l3 3v4h-7M6 19a2 2 0 1 0 0-.01M17 19a2 2 0 1 0 0-.01",
    "user": "M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 21c0-4 4-6 8-6s8 2 8 6",
    "layers": "M3 7l9-4 9 4-9 4-9-4zM3 12l9 4 9-4M3 17l9 4 9-4",
    "wrench": "M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 0 0 5.4-5.4l-2.5 2.5-2.4-.6-.6-2.4z",
    "wallet": "M3 7h18v12H3zM3 7l3-3h12l3 3M16 13h2",
    "sliders": "M4 7h9M17 7h3M4 17h3M11 17h9M15 5v4M9 15v4",
    "moon": "M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z",
    "sun": "M12 7a5 5 0 1 0 0 10 5 5 0 0 0 0-10zM12 1v2M12 21v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4"
           "M1 12h2M21 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4",
    "search": "M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14zM20 20l-4-4",
    "check": "M5 12.5l4.5 4.5L19 7",
    "alert": "M12 3l9.5 17h-19zM12 10v4M12 17v.5",
    "dollar": "M12 2v20M17 6H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6",
    "route": "M5 19a2 2 0 1 0 0-.01M19 5a2 2 0 1 0 0-.01M7 19h7a3 3 0 0 0 0-6h-4a3 3 0 0 1 0-6h7",
    "clock": "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 7v5l3 2",
    "inbox": "M3 13l3-8h12l3 8v6H3zM3 13h5l1 3h6l1-3h5",
    "upload": "M12 15V3M7 8l5-5 5 5M5 21h14",
    "paperclip": "M21 11l-8.5 8.5a5 5 0 0 1-7-7L14 4a3.5 3.5 0 0 1 5 5l-8.5 8.5a2 2 0 0 1-3-3L15 7",
}


def nav_icon(name: str) -> QIcon:
    """Icon for checkable navigation buttons: muted when off, accent color when selected."""
    result = QIcon()
    for color, state in ((token("muted"), QIcon.State.Off), (token("accent"), QIcon.State.On)):
        for pix_icon in (icon(name, color),):
            result.addPixmap(pix_icon.pixmap(20, 20), QIcon.Mode.Normal, state)
            result.addPixmap(pix_icon.pixmap(40, 40), QIcon.Mode.Normal, state)
    return result


@cache
def icon(name: str, color: str | None = None) -> QIcon:
    """Line icon drawn from an inline SVG path, colored for the current theme."""
    color = color or token("text")
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="{ICON_PATHS[name]}" '
           f'fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>')
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    result = QIcon()
    for size in (16, 20, 32):
        pix = QPixmap(size, size)
        pix.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        renderer.render(painter)
        painter.end()
        result.addPixmap(pix)
    return result


def style_button(button: QPushButton, variant: str | None = None, icon_name: str | None = None) -> QPushButton:
    """Give a button a variant ('primary' / 'danger') and an icon."""
    if variant:
        button.setProperty("variant", variant)
    if icon_name:
        color = {"primary": token("accent_text"), "danger": token("danger")}.get(variant or "")
        button.setIcon(icon(icon_name, color))
        button.setIconSize(QSize(16, 16))
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


# --------------------------------------------------------------------- animations
class ButtonAnimator(QObject):
    """App-wide event filter for the small animations:

    - buttons (and cards marked ``lift``) rise with a soft shadow on hover and sink when pressed;
    - dialogs fade in when they open.
    """

    def eventFilter(self, obj, event):  # noqa: N802 (Qt API)
        kind = event.type()
        if kind == QEvent.Type.Show and isinstance(obj, QDialog) and obj.isWindow():
            self._fade_window(obj)
            return False
        liftable = (isinstance(obj, QPushButton) and not obj.property("noLift")) or (
            isinstance(obj, QWidget) and obj.property("lift"))
        if liftable and obj.isEnabled():
            if kind == QEvent.Type.Enter:
                self._animate(obj, 16.0, 3.0)
            elif kind == QEvent.Type.Leave:
                self._animate(obj, 0.0, 0.0)
            elif kind == QEvent.Type.MouseButtonPress and isinstance(obj, QPushButton):
                self._animate(obj, 5.0, 1.0, duration=70)
            elif kind == QEvent.Type.MouseButtonRelease and isinstance(obj, QPushButton):
                self._animate(obj, 16.0 if obj.underMouse() else 0.0, 3.0 if obj.underMouse() else 0.0, duration=120)
        return False

    @staticmethod
    def _fade_window(window: QWidget, duration: int = 170) -> None:
        window.setWindowOpacity(0.0)
        anim = QVariantAnimation(window)
        anim.setDuration(duration)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.valueChanged.connect(window.setWindowOpacity)
        window._show_anim = anim
        anim.start()

    @staticmethod
    def _animate(button: QWidget, blur: float, offset: float, duration: int = 160) -> None:
        # Qt cannot draw nested graphics effects reliably: skip while a parent is fading in.
        parent = button.parentWidget()
        while parent is not None:
            if parent.graphicsEffect() is not None:
                return
            parent = parent.parentWidget()
        effect = button.graphicsEffect()
        if not isinstance(effect, QGraphicsDropShadowEffect):
            if effect is not None:
                return  # someone else uses this button's effect
            effect = QGraphicsDropShadowEffect(button)
            effect.setBlurRadius(0)
            effect.setOffset(0, 0)
            primary = button.property("variant") == "primary"
            color = QColor(token("accent")) if primary else QColor(0, 0, 0)
            color.setAlpha(120 if primary else 55)
            effect.setColor(color)
            button.setGraphicsEffect(effect)
        old = getattr(button, "_lift_anim", None)
        if old is not None:
            old.stop()
        start_blur, start_offset = effect.blurRadius(), effect.offset().y()
        anim = QVariantAnimation(button)
        anim.setDuration(duration)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        def step(v: float) -> None:
            effect.setBlurRadius(start_blur + (blur - start_blur) * v)
            effect.setOffset(QPointF(0, start_offset + (offset - start_offset) * v))

        anim.valueChanged.connect(step)
        if blur == 0:
            # back at rest: remove the shadow completely so nothing is left behind
            anim.finished.connect(lambda: button.graphicsEffect() is effect and button.setGraphicsEffect(None))
        button._lift_anim = anim
        anim.start()


def fade_in(widget: QWidget, duration: int = 180) -> None:
    """Fade a widget in (used when switching tabs)."""
    if widget.graphicsEffect() is not None:
        return
    if any(child.graphicsEffect() is not None for child in widget.findChildren(QWidget)):
        return  # a button is still animating; nested effects would draw incorrectly
    for child in widget.findChildren(QWidget):  # make sure no hover shadow starts mid-fade
        anim = getattr(child, "_lift_anim", None)
        if anim is not None:
            anim.stop()
    effect = QGraphicsOpacityEffect(widget)
    effect.setOpacity(0.0)
    widget.setGraphicsEffect(effect)
    anim = QVariantAnimation(widget)
    anim.setDuration(duration)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    anim.valueChanged.connect(effect.setOpacity)
    anim.finished.connect(lambda: widget.setGraphicsEffect(None))
    widget._fade_anim = anim
    anim.start()


def slide_in(widget: QWidget, distance: int = 28, duration: int = 240) -> None:
    """Slide a page in from the right while it fades in (page changes)."""
    end = widget.pos()
    start = QPoint(end.x() + distance, end.y())
    old = getattr(widget, "_slide_anim", None)
    if old is not None:
        old.stop()
    anim = QPropertyAnimation(widget, b"pos", widget)
    anim.setDuration(duration)
    anim.setStartValue(start)
    anim.setEndValue(end)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    widget._slide_anim = anim
    widget.move(start)
    anim.start()
    fade_in(widget, duration)


def count_up(label, value: float, fmt, duration: int = 900) -> QVariantAnimation:
    """Animate a number label to ``value``: from 0 the first time, later gliding from the number it shows.

    ``fmt(number) -> str`` formats each frame."""
    old = getattr(label, "_count_anim", None)
    if old is not None:
        old.stop()
    start = float(getattr(label, "_count_value", 0.0))
    anim = QVariantAnimation(label)
    anim.setDuration(duration if start == 0 else max(350, duration // 2))
    anim.setStartValue(start)
    anim.setEndValue(float(value))
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    anim.valueChanged.connect(lambda v: label.setText(fmt(v)))
    anim.finished.connect(lambda: label.setText(fmt(value)))
    label._count_anim = anim
    label._count_value = float(value)
    label.setText(fmt(start))
    anim.start()
    return anim
