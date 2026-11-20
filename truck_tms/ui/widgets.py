"""Reusable Qt widgets and helpers."""

from __future__ import annotations

from PySide6.QtCore import QDate, QEvent, QObject, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from ..database import Database, ValidationError
from ..i18n import t
from ..numbers import format_number, parse_number  # GUI-free; re-exported for the dialogs and tests
from .theme import icon, style_button, token


def _message(parent: QWidget, kind: QMessageBox.Icon, title: str, text: str) -> None:
    box = QMessageBox(kind, title, text, QMessageBox.StandardButton.Ok, parent)
    style_button(box.button(QMessageBox.StandardButton.Ok), "primary").setText(t("btn.ok"))
    box.exec()


def show_error(parent: QWidget, error: Exception | str) -> None:
    key = error.key if isinstance(error, ValidationError) else str(error)
    _message(parent, QMessageBox.Icon.Warning, t("error.title"), t(key))


def show_warning(parent: QWidget, text: str) -> None:
    _message(parent, QMessageBox.Icon.Warning, t("error.title"), text)


def show_info(parent: QWidget, text: str) -> None:
    _message(parent, QMessageBox.Icon.Information, t("info.title"), text)


def confirm(parent: QWidget, text: str) -> bool:
    """Yes / No question with translated buttons; 'No' is the default."""
    box = QMessageBox(QMessageBox.Icon.Question, t("confirm.title"), text,
                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, parent)
    style_button(box.button(QMessageBox.StandardButton.Yes), "danger").setText(t("btn.yes"))
    style_button(box.button(QMessageBox.StandardButton.No)).setText(t("btn.no"))
    box.setDefaultButton(QMessageBox.StandardButton.No)
    return box.exec() == QMessageBox.StandardButton.Yes


def confirm_action(parent: QWidget, text: str, yes_text: str) -> bool:
    """A friendly question (not a warning): the main button says what will happen."""
    box = QMessageBox(QMessageBox.Icon.Question, t("info.title"), text,
                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, parent)
    style_button(box.button(QMessageBox.StandardButton.Yes), "primary").setText(yes_text)
    style_button(box.button(QMessageBox.StandardButton.No)).setText(t("btn.cancel"))
    box.setDefaultButton(QMessageBox.StandardButton.Yes)
    return box.exec() == QMessageBox.StandardButton.Yes


def button(text: str, variant: str | None = None, icon_name: str | None = None) -> QPushButton:
    return style_button(QPushButton(text), variant, icon_name)



def buttons_box(dialog, on_save) -> QDialogButtonBox:
    """Translated Save / Cancel buttons for a dialog."""
    box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
    save = box.button(QDialogButtonBox.StandardButton.Save)
    style_button(save, "primary", "save").setText(t("btn.save"))
    style_button(box.button(QDialogButtonBox.StandardButton.Cancel)).setText(t("btn.cancel"))
    box.accepted.connect(on_save)
    box.rejected.connect(dialog.reject)
    return box


def hint_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setProperty("role", "hint")
    label.setWordWrap(True)
    return label


class NumberEdit(QLineEdit):
    """Optional numeric input: empty means 'not set'."""

    def value(self) -> float | None:
        return parse_number(self.text())

    def setValue(self, value: float | None) -> None:
        self.setText(format_number(value))

    def int_value(self) -> int | None:
        value = self.value()
        return None if value is None else int(round(value))


class OptionalDateEdit(QWidget):
    """A date picker with a checkbox; unchecked means 'no date'."""

    changed = Signal()

    def __init__(self, parent: QWidget | None = None, checked: bool = False):
        super().__init__(parent)
        self.check = QCheckBox()
        self.date = QDateEdit(QDate.currentDate())
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("yyyy-MM-dd")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.check)
        layout.addWidget(self.date, 1)
        self.check.toggled.connect(self.date.setEnabled)
        self.check.setChecked(checked)
        self.date.setEnabled(checked)
        self.check.toggled.connect(self.changed)
        self.date.dateChanged.connect(self.changed)

    def value(self) -> str | None:
        return self.date.date().toString("yyyy-MM-dd") if self.check.isChecked() else None

    def setValue(self, value: str | None) -> None:
        if value:
            self.date.setDate(QDate.fromString(value, "yyyy-MM-dd"))
            self.check.setChecked(True)
        else:
            self.check.setChecked(False)


def date_edit(value: QDate | None = None) -> QDateEdit:
    edit = QDateEdit(value or QDate.currentDate())
    edit.setCalendarPopup(True)
    edit.setDisplayFormat("yyyy-MM-dd")
    return edit


def choice_combo(values, prefix: str, include_all: bool = False) -> QComboBox:
    """Combo whose items show translated labels (``prefix + value``) and store the raw value."""
    combo = QComboBox()
    if include_all:
        combo.addItem(t("all"), None)
    for v in values:
        combo.addItem(t(prefix + v), v)
    return combo


def truck_combo(db: Database, include_all: bool = False, include_unassigned: bool = False) -> QComboBox:
    combo = QComboBox()
    fill_truck_combo(combo, db, include_all, include_unassigned)
    return combo


def fill_truck_combo(
    combo: QComboBox, db: Database, include_all: bool = False, include_unassigned: bool = False
) -> None:
    current = combo.currentData()
    combo.blockSignals(True)
    combo.clear()
    if include_all:
        combo.addItem(t("all"), None)
    if include_unassigned:
        combo.addItem(t("unassigned"), None)
    for truck in db.list_trucks():
        combo.addItem(truck.label, truck.id)
    set_combo_data(combo, current)
    combo.blockSignals(False)


def driver_combo(db: Database, include_all: bool = False, include_none: bool = False) -> QComboBox:
    combo = QComboBox()
    fill_driver_combo(combo, db, include_all, include_none)
    return combo


def fill_driver_combo(
    combo: QComboBox, db: Database, include_all: bool = False, include_none: bool = False
) -> None:
    current = combo.currentData()
    combo.blockSignals(True)
    combo.clear()
    if include_all:
        combo.addItem(t("all"), None)
    if include_none:
        combo.addItem(t("unassigned"), None)
    for driver in db.list_drivers():
        suffix = "" if driver.status == "active" else f"  ({t('status.inactive')})"
        combo.addItem(driver.name + suffix, driver.id)
    set_combo_data(combo, current)
    combo.blockSignals(False)


def set_combo_data(combo: QComboBox, data) -> None:
    index = combo.findData(data)
    if index >= 0:
        combo.setCurrentIndex(index)


class SortItem(QTableWidgetItem):
    """Table item that sorts by a hidden key (numbers sort numerically)."""

    def __init__(self, text: str, sort_key=None):
        super().__init__(text)
        self.sort_key = sort_key if sort_key is not None else text

    def __lt__(self, other):
        if isinstance(other, SortItem):
            try:
                return self.sort_key < other.sort_key
            except TypeError:
                return str(self.sort_key) < str(other.sort_key)
        return super().__lt__(other)


# ------------------------------------------------------------------ status badges
BADGE_ROLE = Qt.ItemDataRole.UserRole + 1

STATUS_TONES = {
    "active": "success", "maintenance": "warning", "inactive": "neutral",
    "planned": "neutral", "dispatched": "info", "in_transit": "info", "delivered": "success",
    "invoiced": "warning", "paid": "success", "cancelled": "danger",
    "draft": "neutral", "final": "info", "tonu": "warning", "due": "danger",
    "open": "info", "partial": "warning", "overdue": "danger",
    "expired": "danger", "soon": "warning", "ok": "success",
}


class Badge:
    """A table cell drawn as a coloured pill (see ``BadgeDelegate``)."""

    __slots__ = ("text", "tone")

    def __init__(self, text: str, tone: str = "neutral"):
        self.text, self.tone = text, tone


def status_badge(prefix: str, value: str) -> Badge:
    """``status_badge("status.", "active")`` → a green "Active" pill."""
    return Badge(t(prefix + value), STATUS_TONES.get(value, "neutral"))


class RowHover(QObject):
    """Remembers which table row is under the mouse so the delegate can tint the whole row."""

    def __init__(self, table: QTableWidget):
        super().__init__(table)
        self.table = table
        self.row = -1
        table.viewport().setMouseTracking(True)
        table.viewport().installEventFilter(self)

    def eventFilter(self, obj, event):  # noqa: N802 (Qt API)
        kind = event.type()
        if kind == QEvent.Type.MouseMove:
            self._set(self.table.rowAt(int(event.position().y())))
        elif kind in (QEvent.Type.Leave, QEvent.Type.Hide):
            self._set(-1)
        return False

    def _set(self, row: int) -> None:
        if row != self.row:
            self.row = row
            self.table.viewport().update()


class BadgeDelegate(QStyledItemDelegate):
    def __init__(self, table: QTableWidget):
        super().__init__(table)
        self.hover = RowHover(table)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        if index.row() == self.hover.row and not option.state & QStyle.StateFlag.State_Selected:
            tint = QColor(token("accent"))
            tint.setAlpha(20)
            painter.fillRect(option.rect, tint)
        tone = index.data(BADGE_ROLE)
        if not tone:
            super().paint(painter, option, index)
            return
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        text = opt.text
        opt.text = ""  # draw the row background / selection only
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)
        font = QFont(opt.font)
        font.setWeight(QFont.Weight.DemiBold)
        font.setPointSizeF(max(7.5, font.pointSizeF() - 0.5))
        metrics = QFontMetrics(font)
        height = metrics.height() + 6
        width = min(metrics.horizontalAdvance(text) + 20, opt.rect.width() - 10)
        pill = QRectF(opt.rect.x() + 6, opt.rect.center().y() - height / 2 + 1, width, height)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(token(f"{tone}_bg")))
        painter.drawRoundedRect(pill, height / 2, height / 2)
        painter.setPen(QColor(token(f"{tone}_fg")))
        painter.setFont(font)
        painter.drawText(pill, Qt.AlignmentFlag.AlignCenter, metrics.elidedText(text, Qt.TextElideMode.ElideRight,
                                                                                 int(width) - 12))
        painter.restore()

    def sizeHint(self, option, index):  # noqa: N802 (Qt API)
        size = super().sizeHint(option, index)
        if index.data(BADGE_ROLE):
            size.setWidth(size.width() + 24)
        return size


def search_box() -> QLineEdit:
    box = QLineEdit()
    box.setPlaceholderText(t("search"))
    box.setClearButtonEnabled(True)
    box.setMinimumWidth(200)
    box.addAction(icon("search", token("muted")), QLineEdit.ActionPosition.LeadingPosition)
    return box


def make_table(headers: list[str]) -> QTableWidget:
    table = QTableWidget(0, len(headers))
    table.setItemDelegate(BadgeDelegate(table))
    table.setShowGrid(False)
    table.verticalHeader().setDefaultSectionSize(36)
    table.setHorizontalHeaderLabels(headers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setAlternatingRowColors(True)
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    table.horizontalHeader().setStretchLastSection(True)
    # size columns from the first rows only: measuring thousands of rows made big lists slow
    table.horizontalHeader().setResizeContentsPrecision(150)
    table.setSortingEnabled(True)
    # keep the database order until the user clicks a column header
    table.horizontalHeader().setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
    return table


_NUMBER_ALIGN = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter  # built once, not per cell


def fill_table(table: QTableWidget, rows: list[tuple[int, list]]) -> None:
    """``rows`` = [(record_id, [cell, ...]), ...]; a cell is text, (text, sort_key),
    (text, sort_key, QColor) for coloured text, or a ``Badge``."""
    table.setUpdatesEnabled(False)  # one repaint at the end instead of one per cell
    table.setSortingEnabled(False)
    table.setRowCount(len(rows))
    for r, (record_id, cells) in enumerate(rows):
        for c, cell in enumerate(cells):
            color = None
            tone = None
            if isinstance(cell, Badge):
                text, key, tone = cell.text, cell.text, cell.tone
            elif isinstance(cell, tuple):
                text, key = cell[0], cell[1]
                color = cell[2] if len(cell) > 2 else None
            else:
                text, key = cell, None
            item = SortItem("" if text is None else str(text), key)
            if color is not None:
                item.setForeground(color)
            if tone:
                item.setData(BADGE_ROLE, tone)
            if c == 0:
                item.setData(Qt.ItemDataRole.UserRole, record_id)
            if isinstance(key, (int, float)):
                item.setTextAlignment(_NUMBER_ALIGN)
            table.setItem(r, c, item)
    table.setSortingEnabled(True)
    table.resizeColumnsToContents()
    table.setUpdatesEnabled(True)


def selected_id(table: QTableWidget) -> int | None:
    row = table.currentRow()
    if row < 0 or not table.selectionModel().hasSelection():
        return None
    item = table.item(row, 0)
    return item.data(Qt.ItemDataRole.UserRole) if item else None
