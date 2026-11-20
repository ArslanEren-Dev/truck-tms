"""Settings tab: language, theme, company info, currency, distance unit, statement week, fees."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..database import Database, ValidationError
from ..i18n import LANGUAGES, t
from .theme import THEMES, apply_theme
from .toast import show_toast
from .widgets import NumberEdit, button, format_number, set_combo_data, show_error


class SettingsTab(QWidget):
    #: emitted after saving when the language or theme changed (the window is rebuilt)
    appearance_changed = Signal()

    def __init__(self, db: Database, parent: QWidget | None = None):
        super().__init__(parent)
        self.db = db
        self.language = QComboBox()
        for code, name in LANGUAGES.items():
            self.language.addItem(name, code)
        self.theme = QComboBox()
        for name in THEMES:
            self.theme.addItem(t("theme." + name), name)
        self.company_name = QLineEdit()
        self.company_address = QPlainTextEdit()
        self.company_address.setFixedHeight(70)
        self.currency = QLineEdit()
        self.currency.setMaxLength(5)
        self.distance_unit = QComboBox()
        self.distance_unit.addItem(t("settings.unit_mi"), "mi")
        self.distance_unit.addItem(t("settings.unit_km"), "km")
        self.week_start = QComboBox()
        for i in range(7):
            self.week_start.addItem(t(f"weekday.{i}"), str(i))
        self.dispatch_fee = NumberEdit()
        db_path = QLabel(db.path)
        db_path.setProperty("role", "hint")
        db_path.setWordWrap(True)
        db_path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        form = QFormLayout()
        form.setVerticalSpacing(10)
        form.addRow(t("settings.language"), self.language)
        form.addRow(t("settings.theme"), self.theme)
        form.addRow(t("settings.company_name"), self.company_name)
        form.addRow(t("settings.company_address"), self.company_address)
        form.addRow(t("settings.currency"), self.currency)
        form.addRow(t("settings.distance_unit"), self.distance_unit)
        form.addRow(t("settings.week_start"), self.week_start)
        form.addRow(t("settings.dispatch_fee"), self.dispatch_fee)
        form.addRow(t("settings.database"), db_path)

        save = button(t("btn.save"), "primary", "save")
        save.clicked.connect(self.save)
        buttons = QHBoxLayout()
        buttons.addWidget(save)
        buttons.addStretch(1)

        box = QWidget()
        box.setMaximumWidth(720)
        inner = QVBoxLayout(box)
        inner.addLayout(form)
        inner.addSpacing(8)
        inner.addLayout(buttons)
        layout = QVBoxLayout(self)
        layout.addWidget(box)
        layout.addStretch(1)
        # live preview of the theme; saving makes it permanent
        self.theme.currentIndexChanged.connect(lambda: apply_theme(self.theme.currentData()))
        self.refresh()

    def refresh(self) -> None:
        s = self.db.get_settings()
        set_combo_data(self.language, s["language"])
        self.theme.blockSignals(True)
        set_combo_data(self.theme, s["theme"])
        self.theme.blockSignals(False)
        self.company_name.setText(s["company_name"])
        self.company_address.setPlainText(s["company_address"])
        self.currency.setText(s["currency"])
        set_combo_data(self.distance_unit, s["distance_unit"])
        set_combo_data(self.week_start, s["week_start"])
        try:
            self.dispatch_fee.setValue(float(s["dispatch_fee_percent"] or 0))
        except ValueError:
            self.dispatch_fee.setValue(0)

    def save(self) -> None:
        try:
            fee = self.dispatch_fee.value() or 0
        except ValidationError as exc:
            show_error(self, exc)
            return
        if not 0 <= fee <= 100:
            show_error(self, "error.invalid_percent")
            return
        old = self.db.get_settings()
        new_language, new_theme = self.language.currentData(), self.theme.currentData()
        self.db.set_setting("language", new_language)
        self.db.set_setting("theme", new_theme)
        self.db.set_setting("company_name", self.company_name.text().strip())
        self.db.set_setting("company_address", self.company_address.toPlainText().strip())
        self.db.set_setting("currency", self.currency.text().strip() or "$")
        self.db.set_setting("distance_unit", self.distance_unit.currentData())
        self.db.set_setting("week_start", self.week_start.currentData())
        self.db.set_setting("dispatch_fee_percent", format_number(fee))
        if new_language != old["language"] or new_theme != old["theme"]:
            self.appearance_changed.emit()
        else:
            show_toast(t("saved"))
