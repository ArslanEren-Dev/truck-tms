"""Ctrl+K quick search: one box that finds pages, "new" actions and records, and opens the choice."""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtWidgets import QDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from ..database import Database
from ..i18n import t
from ..search import search_records
from .theme import icon, token

KIND_ICONS = {"load": "layers", "truck": "truck", "driver": "user", "invoice": "receipt"}
KIND_TABS = {"load": "tab.loads", "truck": "tab.trucks", "driver": "tab.drivers", "invoice": "tab.invoices"}


class QuickSearch(QDialog):
    """``pages`` = [(title, icon name, can_add)] in nav order; after ``exec`` ``choice`` is
    ("page", index), ("new", index) or ("open", kind, record_id)."""

    def __init__(self, db: Database, pages: list[tuple[str, str, bool]], parent: QWidget | None = None):
        super().__init__(parent)
        self.db = db
        self.pages = pages
        self.choice: tuple | None = None
        self.setWindowTitle(t("menu.quick_search").rstrip("…"))
        self.setMinimumSize(620, 440)
        self.box = QLineEdit()
        self.box.setPlaceholderText(t("quick.placeholder"))
        self.box.setClearButtonEnabled(True)
        self.box.addAction(icon("search", token("muted")), QLineEdit.ActionPosition.LeadingPosition)
        self.box.setMinimumHeight(40)
        self.list = QListWidget()
        self.list.setUniformItemSizes(True)
        self.hint = QLabel(t("quick.hint"))
        self.hint.setProperty("role", "hint")
        layout = QVBoxLayout(self)
        layout.addWidget(self.box)
        layout.addWidget(self.list, 1)
        layout.addWidget(self.hint)
        self.timer = QTimer(self)  # wait for a pause in typing before querying the database
        self.timer.setSingleShot(True)
        self.timer.setInterval(120)
        self.timer.timeout.connect(self.update_results)
        self.box.textChanged.connect(self.timer.start)
        self.box.returnPressed.connect(self.accept_current)
        self.list.itemActivated.connect(lambda _item: self.accept_current())
        self.box.installEventFilter(self)
        self.update_results()

    def eventFilter(self, obj, event):  # noqa: N802 (Qt API)
        """Up / Down in the text box move through the list."""
        if obj is self.box and event.type() == QEvent.Type.KeyPress and event.key() in (Qt.Key.Key_Up,
                                                                                       Qt.Key.Key_Down):
            step = -1 if event.key() == Qt.Key.Key_Up else 1
            rows = self.list.count()
            if rows:
                self.list.setCurrentRow((self.list.currentRow() + step) % rows)
            return True
        return super().eventFilter(obj, event)

    def _add(self, text: str, icon_name: str, data: tuple) -> None:
        item = QListWidgetItem(icon(icon_name, token("muted")), text)
        item.setData(Qt.ItemDataRole.UserRole, data)
        self.list.addItem(item)

    def update_results(self) -> None:
        self.timer.stop()
        text = self.box.text().strip()
        needle = text.lower()
        self.list.clear()
        for index, (title, icon_name, can_add) in enumerate(self.pages):
            if needle in title.lower():
                self._add(f"{title}    ·  {t('quick.page')}", icon_name, ("page", index))
            if can_add and needle and needle in title.lower():
                self._add(t("quick.new", what=title), "plus", ("new", index))
        for hit in search_records(self.db, text):
            detail = f"    ·  {hit.detail}" if hit.detail else ""
            self._add(f"{hit.title}{detail}    ·  {t(KIND_TABS[hit.kind])}", KIND_ICONS[hit.kind],
                      ("open", hit.kind, hit.record_id))
        if self.list.count():
            self.list.setCurrentRow(0)
        else:
            empty = QListWidgetItem(t("quick.no_results"))
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            self.list.addItem(empty)

    def accept_current(self) -> None:
        if self.timer.isActive():  # Enter pressed right after typing: search first
            self.update_results()
        item = self.list.currentItem()
        data = item.data(Qt.ItemDataRole.UserRole) if item else None
        if data:
            self.choice = tuple(data)
            self.accept()
