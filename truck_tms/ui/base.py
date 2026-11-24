"""Base class for the list + add/edit/delete pages."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..database import Database
from ..i18n import t
from .theme import icon, token
from .toast import show_toast
from .visuals import flash_row
from .widgets import (
    button,
    confirm,
    driver_combo,
    fill_driver_combo,
    fill_table,
    fill_truck_combo,
    make_table,
    search_box,
    selected_id,
    show_error,
    truck_combo,
)


class EmptyState(QWidget):
    """Shown instead of an empty table: an icon, a short explanation and an "Add" button."""

    def __init__(self, icon_name: str, on_add, parent: QWidget | None = None):
        super().__init__(parent)
        self.picture = QLabel()
        self.picture.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.picture.setPixmap(icon(icon_name, token("muted")).pixmap(56, 56))
        self.title = QLabel()
        self.title.setProperty("role", "emptytitle")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint = QLabel()
        self.hint.setProperty("role", "emptyhint")
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint.setWordWrap(True)
        self.add_btn = button(t("btn.add"), "primary", "plus")
        self.add_btn.clicked.connect(on_add)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.add_btn)
        row.addStretch(1)
        self.button_row = row
        layout = QVBoxLayout(self)
        layout.addStretch(1)
        layout.addWidget(self.picture)
        layout.addSpacing(6)
        layout.addWidget(self.title)
        layout.addWidget(self.hint)
        layout.addSpacing(10)
        layout.addLayout(row)
        layout.addStretch(2)

    def add_button(self, extra) -> None:
        """Another action next to "Add" (e.g. "Import from Excel")."""
        self.button_row.insertWidget(self.button_row.count() - 1, extra)
        self.extra_buttons = getattr(self, "extra_buttons", []) + [extra]

    def show_text(self, filtered: bool, key: str) -> None:
        buttons = [self.add_btn] + getattr(self, "extra_buttons", [])
        if filtered:
            self.title.setText(t("empty.filtered_title"))
            self.hint.setText(t("empty.filtered_hint"))
            for b in buttons:
                b.hide()
        else:
            self.title.setText(t(f"empty.{key}_title"))
            self.hint.setText(t(f"empty.{key}_hint"))
            for b in buttons:
                b.show()


class CrudTab(QWidget):
    """Toolbar (Add / Edit / Delete + filters) above a sortable table.

    Subclasses implement ``headers``, ``rows``, ``open_dialog`` and ``delete_record``
    and may add filter widgets with ``add_filter``. ``empty_key`` / ``empty_icon`` pick the
    text and picture shown while the list is empty.
    """

    empty_key = "generic"
    empty_icon = "inbox"

    def __init__(self, db: Database, parent: QWidget | None = None):
        super().__init__(parent)
        self.db = db
        self._truck_filters: list[QComboBox] = []
        self._driver_filters: list[QComboBox] = []
        self._tools = 0
        self.toolbar = QHBoxLayout()
        self.toolbar.setSpacing(8)
        self.add_btn = button(t("btn.add"), "primary", "plus")
        self.edit_btn = button(t("btn.edit"), None, "edit")
        self.delete_btn = button(t("btn.delete"), "danger", "trash")
        for btn in (self.add_btn, self.edit_btn, self.delete_btn):
            self.toolbar.addWidget(btn)
        self.toolbar.addStretch(1)

        self.table = make_table(self.headers())
        self.empty = EmptyState(self.empty_icon, lambda: self._open(None))
        self.body = QStackedWidget()
        self.body.addWidget(self.table)
        self.body.addWidget(self.empty)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.addLayout(self.toolbar)
        layout.addWidget(self.body, 1)

        self.add_btn.clicked.connect(lambda: self._open(None))
        self.edit_btn.clicked.connect(self._edit_selected)
        self.delete_btn.clicked.connect(self._delete_selected)
        self.table.doubleClicked.connect(self._edit_selected)
        # keyboard: Enter edits, Delete deletes the selected row while the table has the focus
        for key, slot in ((Qt.Key.Key_Return, self._edit_selected), (Qt.Key.Key_Enter, self._edit_selected),
                          (Qt.Key.Key_Delete, self._delete_selected)):
            shortcut = QShortcut(QKeySequence(key), self.table)
            shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
            shortcut.activated.connect(slot)

    # -- to override -------------------------------------------------------
    def headers(self) -> list[str]:
        raise NotImplementedError

    def rows(self) -> list[tuple[int, list]]:
        raise NotImplementedError

    def open_dialog(self, record_id: int | None) -> bool:
        """Show the add/edit dialog. Return True if something was saved."""
        raise NotImplementedError

    def delete_record(self, record_id: int) -> bool:
        """Ask for confirmation and delete. Return True if deleted."""
        if not confirm(self, t("confirm.delete")):
            return False
        self.delete(record_id)
        return True

    def delete(self, record_id: int) -> None:
        raise NotImplementedError

    # -- shared behavior ----------------------------------------------------
    def add_filter(self, widget: QWidget, label: str | None = None) -> None:
        if label:
            self.toolbar.addWidget(QLabel(label))
        self.toolbar.addWidget(widget)

    def add_truck_filter(self, label: bool = True) -> QComboBox:
        """An "All trucks / truck…" filter that reloads the list and keeps its truck list current."""
        combo = truck_combo(self.db, include_all=True)
        combo.currentIndexChanged.connect(self.refresh)
        self.add_filter(combo, t("truck") if label else None)
        self._truck_filters.append(combo)
        return combo

    def add_driver_filter(self) -> QComboBox:
        combo = driver_combo(self.db, include_all=True)
        combo.currentIndexChanged.connect(self.refresh)
        self.add_filter(combo, t("driver"))
        self._driver_filters.append(combo)
        return combo

    def add_search(self) -> QLineEdit:
        box = search_box()
        box.textChanged.connect(self.refresh)
        self.add_filter(box)
        return box

    def add_tool(self, text: str, icon_name: str, slot) -> QPushButton:
        """An extra toolbar button, placed after Add / Edit / Delete and earlier extras."""
        btn = button(text, None, icon_name)
        btn.clicked.connect(slot)
        self.toolbar.insertWidget(3 + self._tools, btn)
        self._tools += 1
        return btn

    def selected_or_warn(self) -> int | None:
        """Id of the selected row, or None after telling the user to pick a row."""
        record_id = selected_id(self.table)
        if record_id is None:
            show_error(self, "select_row")
        return record_id

    def focus_search(self) -> bool:
        """Ctrl+F: put the cursor in the page's search box (False when the page has none)."""
        for i in range(self.toolbar.count()):
            widget = self.toolbar.itemAt(i).widget()
            if isinstance(widget, QLineEdit):
                widget.setFocus()
                widget.selectAll()
                return True
        return False

    def has_filters(self) -> bool:
        """True when a search text or a non-"All" filter is active in the toolbar."""
        for i in range(self.toolbar.count()):
            widget = self.toolbar.itemAt(i).widget()
            if isinstance(widget, QLineEdit) and widget.text().strip():
                return True
            if isinstance(widget, QComboBox) and widget.currentIndex() > 0:
                return True
        return False

    def refresh_filters(self) -> None:
        for combo in self._truck_filters:  # another page may have added or renamed a truck
            fill_truck_combo(combo, self.db, include_all=True)
        for combo in self._driver_filters:
            fill_driver_combo(combo, self.db, include_all=True)

    def refresh(self) -> None:
        self.refresh_filters()
        rows = self.rows()
        fill_table(self.table, rows)
        if rows:
            self.body.setCurrentWidget(self.table)
        else:
            self.empty.show_text(self.has_filters(), self.empty_key)
            self.body.setCurrentWidget(self.empty)

    def _open(self, record_id: int | None) -> None:
        if self.open_dialog(record_id):
            self.refresh()
            show_toast(t("toast.saved"))

    def _edit_selected(self) -> None:
        record_id = self.selected_or_warn()
        if record_id is not None:
            self._open(record_id)

    def _delete_selected(self) -> None:
        record_id = self.selected_or_warn()
        if record_id is None:
            return
        row = self.table.currentRow()
        try:
            deleted = self.delete_record(record_id)
        except Exception as exc:  # pragma: no cover - surfaced to the user
            show_error(self, exc)
            return
        if deleted:
            def done() -> None:
                self.refresh()
                show_toast(t("toast.deleted"), "info")
            flash_row(self.table, row, "danger", done)
