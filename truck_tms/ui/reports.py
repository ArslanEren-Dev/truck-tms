"""Truck report tab: pick a truck and a period, preview, export (PDF/CSV) or print."""

from __future__ import annotations

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ..database import Database, ValidationError
from ..i18n import t
from ..report import TruckReport, build_truck_report, report_to_html
from .export import REPORT_FORMATS, export_with_dialog, paper_preview, print_html, safe_name, write_report_files
from .widgets import button, date_edit, fill_truck_combo, show_error, truck_combo


class ReportsTab(QWidget):
    def __init__(self, db: Database, parent: QWidget | None = None):
        super().__init__(parent)
        self.db = db
        self.report: TruckReport | None = None
        self.html = ""

        today = QDate.currentDate()
        self.truck = truck_combo(db)
        self.start = date_edit(QDate(today.year(), today.month(), 1))
        self.end = date_edit(today)
        self.generate_btn = button(t("btn.generate"), "primary", "chart")
        self.export_btn = button(t("btn.export"), None, "export")
        self.print_btn = button(t("btn.print"), None, "print")
        for btn in (self.export_btn, self.print_btn):
            btn.setEnabled(False)

        bar = QHBoxLayout()
        bar.addWidget(QLabel(t("truck")))
        bar.addWidget(self.truck, 1)
        bar.addWidget(QLabel(t("report.from")))
        bar.addWidget(self.start)
        bar.addWidget(QLabel(t("report.to")))
        bar.addWidget(self.end)
        bar.addWidget(self.generate_btn)
        bar.addStretch(1)
        bar.addWidget(self.export_btn)
        bar.addWidget(self.print_btn)

        self.preview = paper_preview()
        layout = QVBoxLayout(self)
        layout.addLayout(bar)
        layout.addWidget(self.preview)

        self.generate_btn.clicked.connect(self.generate)
        self.export_btn.clicked.connect(self.export)
        self.print_btn.clicked.connect(self.print_report)

    def refresh(self) -> None:
        fill_truck_combo(self.truck, self.db)

    def generate(self) -> None:
        truck_id = self.truck.currentData()
        if truck_id is None:
            show_error(self, "report.pick_truck")
            return
        try:
            self.report = build_truck_report(
                self.db,
                truck_id,
                self.start.date().toString("yyyy-MM-dd"),
                self.end.date().toString("yyyy-MM-dd"),
            )
        except ValidationError as exc:
            show_error(self, exc)
            return
        self.html = report_to_html(self.report, self.db.get_settings())
        self.preview.setHtml(self.html)
        for btn in (self.export_btn, self.print_btn):
            btn.setEnabled(True)

    def default_stem(self) -> str:
        r = self.report
        truck = r.truck.unit_number or r.truck.plate or ""
        return safe_name(f"truck_report_{truck}_{r.start}_{r.end}")

    def export(self) -> None:
        if not self.report:
            return
        settings = self.db.get_settings()
        export_with_dialog(
            self, self.db, t("report.export_title"), REPORT_FORMATS, self.default_stem(),
            lambda c: write_report_files(self.report, c.fmt, c.folder, c.stem, settings),
        )

    def print_report(self) -> None:
        if not self.report:
            return
        print_html(self, self.html)
