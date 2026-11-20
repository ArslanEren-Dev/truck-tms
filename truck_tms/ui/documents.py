"""Files attached to a load (rate confirmation, BOL, POD…): drag & drop, open, remove."""

from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..database import DOCUMENT_KINDS, Database, ValidationError
from ..i18n import t
from .theme import icon, token
from .widgets import button, confirm, hint_label, set_combo_data, show_error

_KIND_PATTERNS = (
    ("rate_con", r"rate|\brc\b|confirm|carrier.?agreement"),
    ("bol", r"\bbol\b|bill.?of.?lading|\bbl\b"),
    ("pod", r"\bpod\b|proof|delivery.?receipt|signed"),
    ("invoice", r"invoice|fatura|\binv\b"),
    ("receipt", r"receipt|lumper|fi[sş]|scale|toll"),
)


def guess_kind(file_name: str) -> str:
    """Guess the document type from its file name; 'other' when unsure."""
    name = Path(file_name).stem.lower().replace("_", " ").replace("-", " ")
    for kind, pattern in _KIND_PATTERNS:
        if re.search(pattern, name):
            return kind
    return "other"


def human_size(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size} B"


class DocumentsPanel(QWidget):
    """Lists a load's documents. For a load that is not saved yet, files are kept aside and
    attached by ``commit(load_id)`` once the load exists."""

    changed = Signal()

    def __init__(self, db: Database, load_id: int | None, parent: QWidget | None = None):
        super().__init__(parent)
        self.db = db
        self.load_id = load_id
        self.pending: list[tuple[Path, str]] = []

        self.list = QListWidget()
        self.list.setIconSize(QSize(18, 18))
        self.list.setMinimumHeight(84)
        self.list.setMaximumHeight(140)
        # the list itself must not accept drops, so dropped files reach this panel's dropEvent
        self.list.setAcceptDrops(False)
        self.list.viewport().setAcceptDrops(False)
        self.list.itemDoubleClicked.connect(lambda _: self.open_selected())
        self.list.currentRowChanged.connect(self._selection_changed)
        self.setAcceptDrops(True)

        self.kind = QComboBox()
        for kind in DOCUMENT_KINDS:
            self.kind.addItem(t("doc.kind." + kind), kind)
        self.kind.setEnabled(False)
        self.kind.currentIndexChanged.connect(self._kind_changed)

        add = button(t("doc.add"), None, "plus")
        add.clicked.connect(self.choose_files)
        self.open_btn = button(t("doc.open"), None, "file")
        self.open_btn.clicked.connect(self.open_selected)
        self.remove_btn = button(t("doc.remove"), "danger", "trash")
        self.remove_btn.clicked.connect(self.remove_selected)

        bar = QHBoxLayout()
        bar.addWidget(add)
        bar.addWidget(self.open_btn)
        bar.addWidget(self.remove_btn)
        bar.addStretch(1)
        bar.addWidget(QLabel(t("doc.kind")))
        bar.addWidget(self.kind)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(bar)
        layout.addWidget(self.list)
        layout.addWidget(hint_label(t("doc.drop_hint")))
        self.reload()

    # -------------------------------------------------------------- display
    def reload(self) -> None:
        self.list.clear()
        if self.load_id is not None:
            for doc in self.db.list_documents(self.load_id):
                path = self.db.document_path(doc)
                self._add_item(doc.file_name, doc.kind, path.stat().st_size if path.exists() else doc.size,
                               ("saved", doc.id))
        for i, (path, kind) in enumerate(self.pending):
            self._add_item(path.name, kind, path.stat().st_size if path.exists() else 0, ("pending", i))
        self._selection_changed(self.list.currentRow())

    def _add_item(self, name: str, kind: str, size: int, ref: tuple) -> None:
        item = QListWidgetItem(icon("file", token("accent")), f"{name}   ·   {t('doc.kind.' + kind)}   ·   "
                                                              f"{human_size(size)}")
        item.setData(Qt.ItemDataRole.UserRole, ref)
        item.setData(Qt.ItemDataRole.UserRole + 1, kind)
        self.list.addItem(item)

    def count(self) -> int:
        return self.list.count()

    def _selected_ref(self):
        item = self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _selection_changed(self, row: int) -> None:
        has = row >= 0 and self.list.item(row) is not None
        self.open_btn.setEnabled(has)
        self.remove_btn.setEnabled(has)
        self.kind.setEnabled(has)
        if has:
            self.kind.blockSignals(True)
            set_combo_data(self.kind, self.list.item(row).data(Qt.ItemDataRole.UserRole + 1))
            self.kind.blockSignals(False)

    # -------------------------------------------------------------- actions
    def add_files(self, paths: list[str | Path]) -> None:
        for raw in paths:
            path = Path(raw)
            if not path.is_file():
                continue
            kind = guess_kind(path.name)
            if self.load_id is None:
                self.pending.append((path, kind))
            else:
                try:
                    self.db.add_document(self.load_id, path, kind)
                except ValidationError as exc:
                    show_error(self, exc)
        self.reload()
        self.changed.emit()

    def choose_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, t("doc.add"), "", t("doc.filter"))
        if paths:
            self.add_files(paths)

    def open_selected(self) -> None:
        ref = self._selected_ref()
        if ref is None:
            return
        kind, key = ref
        if kind == "saved":
            doc = next((d for d in self.db.list_documents(self.load_id) if d.id == key), None)
            path = self.db.document_path(doc) if doc else None
        else:
            path = self.pending[key][0]
        if path and path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def remove_selected(self, ask: bool = True) -> None:
        ref = self._selected_ref()
        if ref is None:
            return
        if ask and not confirm(self, t("doc.confirm_remove")):
            return
        kind, key = ref
        if kind == "saved":
            self.db.delete_document(key)
        else:
            del self.pending[key]
        self.reload()
        self.changed.emit()

    def _kind_changed(self) -> None:
        ref = self._selected_ref()
        new_kind = self.kind.currentData()
        if ref is None or new_kind is None:
            return
        kind, key = ref
        if kind == "saved":
            self.db.update_document_kind(key, new_kind)
        else:
            self.pending[key] = (self.pending[key][0], new_kind)
        row = self.list.currentRow()
        self.reload()
        self.list.setCurrentRow(row)

    def commit(self, load_id: int) -> None:
        """Attach the files that were added before the load was saved."""
        self.load_id = load_id
        for path, kind in self.pending:
            self.db.add_document(load_id, path, kind)
        self.pending.clear()
        self.reload()

    # ------------------------------------------------------- drag and drop
    def dragEnterEvent(self, event) -> None:  # noqa: N802 (Qt API)
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    dragMoveEvent = dragEnterEvent

    def dropEvent(self, event) -> None:  # noqa: N802 (Qt API)
        files = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if files:
            self.add_files(files)
            event.acceptProposedAction()
