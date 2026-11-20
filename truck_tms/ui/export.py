"""Export dialog: choose what to export, the format, the folder and the file name."""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QStandardPaths, QUrl
from PySide6.QtGui import QDesktopServices, QPageLayout, QPageSize, QPdfWriter, QTextDocument
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QWidget,
)

from ..database import Database
from ..i18n import t
from ..report import TruckReport, report_to_csv, report_to_html
from ..statement import StatementSummary, driver_statement_to_html, statement_to_csv, statement_to_html
from .dialog_kit import DialogPage
from .theme import style_button
from .toast import show_toast
from .widgets import button, show_error, show_warning

STATEMENT_FORMATS = ("owner_pdf", "driver_pdf", "csv", "all")
REPORT_FORMATS = ("pdf", "csv", "pdf_csv")


# ------------------------------------------------------------------ file writers
def html_to_pdf(html: str, path: str | Path, landscape: bool = False) -> None:
    writer = QPdfWriter(str(path))
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setPageOrientation(
        QPageLayout.Orientation.Landscape if landscape else QPageLayout.Orientation.Portrait
    )
    writer.setResolution(300)
    doc = QTextDocument()
    doc.setHtml(html)
    doc.print_(writer)


def safe_name(name: str) -> str:
    """Make a string safe to use as a file name on Windows, macOS and Linux."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip().strip(".")
    return re.sub(r"\s+", "_", name) or "export"


def statement_file_stem(summary: StatementSummary) -> str:
    truck = summary.truck.unit_number or summary.truck.plate or str(summary.truck.id)
    return safe_name(f"statement_{truck}_{summary.week_start}")


def copy_load_documents(db: Database, summary: StatementSummary, folder: Path) -> list[Path]:
    """Copy the documents attached to the statement's loads into ``folder`` (``#123 - POD - file.pdf``)."""
    copied: list[Path] = []
    for load in summary.loads:
        for doc in db.list_documents(load.id):
            source = db.document_path(doc)
            if not source.is_file():
                continue
            folder.mkdir(parents=True, exist_ok=True)
            label = safe_name(f"{load.load_number or 'load'} - {t('doc.kind.' + doc.kind)} - {doc.file_name}")
            target = folder / label
            shutil.copy2(source, target)
            copied.append(target)
    return copied


def write_statement_files(summaries: list[StatementSummary], fmt: str, folder: Path, stem: str | None,
                          settings: dict[str, str], db: Database | None = None,
                          include_documents: bool = False) -> list[Path]:
    """Write one or more statements. ``stem`` is used when there is a single statement.
    With ``include_documents`` the loads' attached files go into ``<name>_documents``."""
    folder.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for summary in summaries:
        base = safe_name(stem) if stem and len(summaries) == 1 else statement_file_stem(summary)
        if include_documents and db is not None:
            written += copy_load_documents(db, summary, folder / f"{base}_documents")
        if fmt in ("owner_pdf", "all"):
            path = folder / f"{base}.pdf" if fmt == "owner_pdf" else folder / f"{base}_owner.pdf"
            html_to_pdf(statement_to_html(summary, settings), path, landscape=True)
            written.append(path)
        if fmt in ("driver_pdf", "all"):
            path = folder / (f"{base}.pdf" if fmt == "driver_pdf" else f"{base}_driver.pdf")
            html_to_pdf(driver_statement_to_html(summary, settings), path, landscape=True)
            written.append(path)
        if fmt in ("csv", "all"):
            path = folder / f"{base}.csv"
            statement_to_csv(summary, path, settings)
            written.append(path)
    return written


def write_report_files(report: TruckReport, fmt: str, folder: Path, stem: str,
                       settings: dict[str, str]) -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    stem = safe_name(stem)
    written: list[Path] = []
    if fmt in ("pdf", "pdf_csv"):
        path = folder / f"{stem}.pdf"
        html_to_pdf(report_to_html(report, settings), path)
        written.append(path)
    if fmt in ("csv", "pdf_csv"):
        path = folder / f"{stem}.csv"
        report_to_csv(report, path, settings)
        written.append(path)
    return written


def default_export_folder(db: Database) -> Path:
    saved = db.get_settings().get("export_dir")
    if saved:
        return Path(saved)
    docs = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
    return Path(docs or Path.home()) / "Truck TMS"


# ------------------------------------------------------------------------ dialog
@dataclass
class ExportChoice:
    fmt: str
    scope: str | None
    folder: Path
    stem: str
    open_after: bool
    include_documents: bool = False


class ExportDialog(QDialog):
    def __init__(self, db: Database, parent: QWidget | None, title: str, formats: tuple[str, ...],
                 stem: str, scopes: list[tuple[str, str]] | None = None, documents_option: bool = False):
        super().__init__(parent)
        self.db = db
        self.setMinimumWidth(620)

        self.format = QComboBox()
        for key in formats:
            self.format.addItem(t("export." + key), key)
        self.scope = QComboBox()
        for key, label in scopes or []:
            self.scope.addItem(label, key)
        self.folder = QLineEdit(str(default_export_folder(db)))
        browse = button(t("export.browse"), None, "folder")
        browse.clicked.connect(self._browse)
        folder_row = QHBoxLayout()
        folder_row.addWidget(self.folder, 1)
        folder_row.addWidget(browse)
        self.stem = QLineEdit(stem)
        self.extension = QLabel()
        self.extension.setProperty("role", "hint")
        name_row = QHBoxLayout()
        name_row.addWidget(self.stem, 1)
        name_row.addWidget(self.extension)
        self.open_after = QCheckBox(t("export.open_after"))
        self.open_after.setChecked(db.get_settings().get("open_after_export", "1") == "1")
        self.include_documents = QCheckBox(t("export.include_documents"))
        self.include_documents.setVisible(documents_option)

        page = self.page = DialogPage(self, "export", title, t("export.subtitle"))
        form = page.section(t("export.section_what"), "file")
        if scopes:
            form.addRow(t("export.scope"), self.scope)
        form.addRow(t("export.format"), self.format)
        if documents_option:
            form.addRow("", self.include_documents)
        form = page.section(t("export.section_where"), "folder")
        form.addRow(t("export.folder"), folder_row)
        form.addRow(t("export.filename"), name_row)
        form.addRow("", self.open_after)

        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        style_button(box.button(QDialogButtonBox.StandardButton.Ok), "primary", "export").setText(t("btn.export"))
        style_button(box.button(QDialogButtonBox.StandardButton.Cancel)).setText(t("btn.cancel"))
        box.accepted.connect(self._accept)
        box.rejected.connect(self.reject)
        page.finish(box)
        self.format.currentIndexChanged.connect(self._update)
        self.scope.currentIndexChanged.connect(self._update)
        self._update()

    def _update(self) -> None:
        fmt = self.format.currentData()
        many = self.scope.count() > 0 and self.scope.currentData() != "one"
        exts = {"owner_pdf": ".pdf", "driver_pdf": ".pdf", "pdf": ".pdf", "csv": ".csv",
                "all": "_owner.pdf · _driver.pdf · .csv", "pdf_csv": ".pdf · .csv"}
        self.extension.setText(exts.get(fmt, ""))
        self.stem.setEnabled(not many)
        if many:
            self.extension.setText(t("export.auto_names"))

    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, t("export.folder"), self.folder.text())
        if folder:
            self.folder.setText(folder)

    def _accept(self) -> None:
        if not self.folder.text().strip():
            show_error(self, "export.no_folder")
            return
        if self.stem.isEnabled() and not self.stem.text().strip():
            show_error(self, "export.no_name")
            return
        self.db.set_setting("export_dir", self.folder.text().strip())
        self.db.set_setting("open_after_export", "1" if self.open_after.isChecked() else "0")
        self.accept()

    def choice(self) -> ExportChoice:
        return ExportChoice(
            fmt=self.format.currentData(),
            scope=self.scope.currentData() if self.scope.count() else None,
            folder=Path(self.folder.text().strip()),
            stem=self.stem.text().strip(),
            open_after=self.open_after.isChecked(),
            include_documents=self.include_documents.isChecked(),
        )


def report_written(parent: QWidget, files: list[Path], open_after: bool) -> None:
    """Tell the user where the files went; optionally open the first file."""
    if not files:
        return
    if open_after:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(files[0])))
    folder = files[0].parent
    text = t("export.done", count=len(files), folder=str(folder))
    open_folder = (t("export.open_folder"), lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder))))
    if show_toast(text, "success", open_folder, 6000) is None:  # no main window (e.g. used on its own)
        box = QMessageBox(QMessageBox.Icon.Information, t("info.title"), text, parent=parent)
        style_button(box.addButton(t("btn.ok"), QMessageBox.ButtonRole.AcceptRole), "primary")
        box.exec()


def export_with_dialog(parent: QWidget, db: Database, title: str, formats: tuple[str, ...], stem: str,
                       write, scopes: list[tuple[str, str]] | None = None,
                       documents_option: bool = False) -> list[Path]:
    """Show the dialog, call ``write(choice) -> list[Path]`` and report the result."""
    dialog = ExportDialog(db, parent, title, formats, stem, scopes, documents_option)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return []
    choice = dialog.choice()
    try:
        files = write(choice)
    except OSError as exc:
        show_warning(parent, t("export.failed", error=str(exc)))
        return []
    report_written(parent, files, choice.open_after)
    return files
