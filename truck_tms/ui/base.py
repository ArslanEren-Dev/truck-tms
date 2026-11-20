"""Base class for the list + add/edit/delete pages."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QLineEdit, QStackedWidget, QVBoxLayout, QWidget

from ..database import Database
from ..i18n import t
from .theme import icon, token
from .toast import show_toast
from .widgets import button, confirm, fill_table, make_table, selected_id, show_error


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

    # -- shared behaviour ----------------------------------------------------
    def add_filter(self, widget: QWidget) -> None:
        self.toolbar.addWidget(widget)

    def has_filters(self) -> bool:
        """True when a search text or a non-"All" filter is active in the toolbar."""
        for i in range(self.toolbar.count()):
            widget = self.toolbar.itemAt(i).widget()
            if isinstance(widget, QLineEdit) and widget.text().strip():
                return True
            if isinstance(widget, QComboBox) and widget.currentIndex() > 0:
                return True
        return False

    def refresh(self) -> None:
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
        record_id = selected_id(self.table)
        if record_id is None:
            show_error(self, "select_row")
            return
        self._open(record_id)

    def _delete_selected(self) -> None:
        record_id = selected_id(self.table)
        if record_id is None:
            show_error(self, "select_row")
            return
        try:
            if self.delete_record(record_id):
                self.refresh()
                show_toast(t("toast.deleted"), "info")
        except Exception as exc:  # pragma: no cover - surfaced to the user
            show_error(self, exc)
