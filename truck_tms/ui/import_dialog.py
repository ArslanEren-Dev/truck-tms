"""Import loads from Excel / CSV: pick a file, check the column matching, import."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QStandardPaths
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QWidget,
)

from ..database import Database, ValidationError
from ..i18n import t
from ..importer import FIELDS, ImportResult, auto_map, import_loads, read_table, write_template
from .dialog_kit import Section, with_header
from .theme import style_button
from .toast import show_toast
from .widgets import button, fill_table, hint_label, make_table, show_error

FILE_FILTER_KEY = "import.filter"


class ImportDialog(QDialog):
    def __init__(self, db: Database, parent: QWidget | None = None):
        super().__init__(parent)
        self.db = db
        self.headers: list[str] = []
        self.rows: list[list] = []
        self.result: ImportResult | None = None
        self.resize(1000, 800)

        choose = button(t("import.choose"), "primary", "folder")
        choose.clicked.connect(self.choose_file)
        template = button(t("import.template"), None, "file")
        template.clicked.connect(self.save_template)
        self.file_label = hint_label(t("import.no_file"))
        top = QHBoxLayout()
        top.addWidget(choose)
        top.addWidget(self.file_label, 1)
        top.addWidget(template)

        self.preview = make_table([""])
        self.preview.setSortingEnabled(False)
        self.preview.setMinimumHeight(170)
        preview_box = Section(t("import.preview"), "layers")
        preview_box.body.addWidget(self.preview)

        self.combos: dict[str, QComboBox] = {}
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(6)
        for i, name in enumerate(FIELDS):
            combo = QComboBox()
            combo.setMinimumWidth(180)
            self.combos[name] = combo
            row, col = i % 9, (i // 9) * 2
            grid.addWidget(QLabel(t("import.field." + name)), row, col)
            grid.addWidget(combo, row, col + 1)
        mapping_box = Section(t("import.mapping"), "sliders")
        mapping_box.body.addWidget(hint_label(t("import.mapping_hint")))
        mapping_box.body.addLayout(grid)

        self.create_missing = QCheckBox(t("import.create_missing"))
        self.create_missing.setChecked(True)
        self.skip_duplicates = QCheckBox(t("import.skip_duplicates"))
        self.skip_duplicates.setChecked(True)
        mapping_box.body.addWidget(self.create_missing)
        mapping_box.body.addWidget(self.skip_duplicates)

        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.import_btn = box.button(QDialogButtonBox.StandardButton.Ok)
        style_button(self.import_btn, "primary", "check").setText(t("import.run"))
        style_button(box.button(QDialogButtonBox.StandardButton.Cancel)).setText(t("btn.cancel"))
        self.import_btn.setEnabled(False)
        box.accepted.connect(self.run_import)
        box.rejected.connect(self.reject)

        layout = with_header(self, "upload", t("import.title"), t("import.subtitle"))
        layout.addLayout(top)
        layout.addWidget(preview_box, 1)
        layout.addWidget(mapping_box)
        layout.addWidget(box)
        self._fill_combos()

    # ------------------------------------------------------------- file
    def choose_file(self) -> None:
        start = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
        path, _ = QFileDialog.getOpenFileName(self, t("import.choose"), start, t(FILE_FILTER_KEY))
        if path:
            self.load_file(path)

    def load_file(self, path: str | Path) -> bool:
        try:
            self.headers, self.rows = read_table(path)
        except (ValidationError, OSError) as exc:
            show_error(self, exc if isinstance(exc, ValidationError) else "import.unsupported")
            return False
        self.file_label.setText(t("import.file_info", name=Path(path).name, rows=len(self.rows)))
        self._fill_preview()
        self._fill_combos(auto_map(self.headers))
        self.import_btn.setEnabled(bool(self.rows))
        return True

    def save_template(self) -> None:
        start = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
        path, _ = QFileDialog.getSaveFileName(self, t("import.template"), str(Path(start) / "truck_tms_loads.csv"),
                                              "CSV (*.csv)")
        if path:
            write_template(path)
            show_toast(t("import.template_saved", name=Path(path).name))

    # ---------------------------------------------------------- mapping
    def _fill_preview(self) -> None:
        self.preview.setColumnCount(len(self.headers))
        self.preview.setHorizontalHeaderLabels(self.headers)
        fill_table(self.preview, [(i, [str(c) for c in row]) for i, row in enumerate(self.rows[:8])])

    def _fill_combos(self, mapping: dict[str, int] | None = None) -> None:
        mapping = mapping or {}
        for name, combo in self.combos.items():
            combo.clear()
            combo.addItem(t("import.skip_column"), None)
            for i, header in enumerate(self.headers):
                combo.addItem(header, i)
            index = combo.findData(mapping.get(name)) if name in mapping else 0
            combo.setCurrentIndex(max(index, 0))

    def mapping(self) -> dict[str, int]:
        return {name: combo.currentData() for name, combo in self.combos.items() if combo.currentData() is not None}

    # ----------------------------------------------------------- import
    def run_import(self) -> None:
        if not self.mapping():
            show_error(self, "import.nothing_mapped")
            return
        self.result = import_loads(self.db, self.rows, self.mapping(), self.create_missing.isChecked(),
                                   self.skip_duplicates.isChecked())
        self.show_summary(self.result)
        self.accept()

    def summary_text(self, r: ImportResult) -> str:
        lines = [t("import.done", n=r.imported)]
        if r.duplicates:
            lines.append(t("import.duplicates", n=r.duplicates))
        if r.created_trucks:
            lines.append(t("import.created_trucks", names=", ".join(r.created_trucks)))
        if r.created_drivers:
            lines.append(t("import.created_drivers", names=", ".join(r.created_drivers)))
        if r.errors:
            lines.append(t("import.errors", n=len(r.errors)))
        return "\n".join(lines)

    def show_summary(self, r: ImportResult) -> None:
        if not r.errors and not r.created_trucks and not r.created_drivers:
            show_toast(self.summary_text(r))
            return
        box = QMessageBox(QMessageBox.Icon.Information, t("import.title"), self.summary_text(r), parent=self)
        if r.errors:
            box.setDetailedText("\n".join(t("import.error_line", row=row, error=t(key)) for row, key in r.errors))
        style_button(box.addButton(t("btn.ok"), QMessageBox.ButtonRole.AcceptRole), "primary")
        if not getattr(self, "quiet", False):
            box.exec()
