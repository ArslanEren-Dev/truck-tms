"""Driver pay tab: what every driver earned in a period, with PDF/CSV export and printing."""

from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ..database import Database
from ..i18n import t
from ..ifta import current_quarter, quarter_range
from ..profit import DriverPayReport, compute_driver_pay, driver_pay_to_csv, driver_pay_to_html
from .export import REPORT_FORMATS, export_with_dialog, paper_preview, print_html, safe_name, write_pdf_csv
from .widgets import button, date_edit

PERIODS = ("this_month", "last_month", "this_quarter", "this_year", "custom")


def period_range(period: str, today: date | None = None) -> tuple[str, str] | None:
    """(first day, last day) of a preset period; None for "custom"."""
    today = today or date.today()
    if period == "this_month":
        first = today.replace(day=1)
    elif period == "last_month":
        end = today.replace(day=1) - timedelta(days=1)
        return end.replace(day=1).isoformat(), end.isoformat()
    elif period == "this_quarter":
        return quarter_range(*current_quarter(today))
    elif period == "this_year":
        return date(today.year, 1, 1).isoformat(), date(today.year, 12, 31).isoformat()
    else:
        return None
    following = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
    return first.isoformat(), (following - timedelta(days=1)).isoformat()


class DriverPayTab(QWidget):
    def __init__(self, db: Database, parent: QWidget | None = None):
        super().__init__(parent)
        self.db = db
        self.report: DriverPayReport | None = None
        self.html = ""
        self.period = QComboBox()
        for key in PERIODS:
            self.period.addItem(t("dpay." + key), key)
        start, end = period_range("this_month")
        self.start = date_edit(QDate.fromString(start, "yyyy-MM-dd"))
        self.end = date_edit(QDate.fromString(end, "yyyy-MM-dd"))
        self.export_btn = button(t("btn.export"), None, "export")
        self.print_btn = button(t("btn.print"), None, "print")
        bar = QHBoxLayout()
        bar.addWidget(QLabel(t("dpay.period")))
        bar.addWidget(self.period)
        bar.addWidget(QLabel(t("report.from")))
        bar.addWidget(self.start)
        bar.addWidget(QLabel(t("report.to")))
        bar.addWidget(self.end)
        bar.addStretch(1)
        bar.addWidget(self.export_btn)
        bar.addWidget(self.print_btn)
        self.preview = paper_preview()
        layout = QVBoxLayout(self)
        layout.addLayout(bar)
        layout.addWidget(self.preview, 1)
        self.period.currentIndexChanged.connect(self._period_changed)
        self.start.dateChanged.connect(self._dates_edited)
        self.end.dateChanged.connect(self._dates_edited)
        self.export_btn.clicked.connect(self.export)
        self.print_btn.clicked.connect(lambda: print_html(self, self.html))
        self._setting_dates = False
        self.generate()

    def refresh(self) -> None:
        self.generate()

    def _period_changed(self) -> None:
        dates = period_range(self.period.currentData())
        if dates is None:
            return
        self._setting_dates = True
        self.start.setDate(QDate.fromString(dates[0], "yyyy-MM-dd"))
        self.end.setDate(QDate.fromString(dates[1], "yyyy-MM-dd"))
        self._setting_dates = False
        self.generate()

    def _dates_edited(self) -> None:
        if self._setting_dates:
            return
        self.period.blockSignals(True)
        self.period.setCurrentIndex(PERIODS.index("custom"))
        self.period.blockSignals(False)
        self.generate()

    def generate(self) -> None:
        start = self.start.date().toString("yyyy-MM-dd")
        end = self.end.date().toString("yyyy-MM-dd")
        self.report = compute_driver_pay(self.db, min(start, end), max(start, end))
        self.html = driver_pay_to_html(self.report, self.db.get_settings())
        self.preview.setHtml(self.html)

    def export(self) -> None:
        settings = self.db.get_settings()
        report, html = self.report, self.html
        export_with_dialog(
            self, self.db, t("dpay.export_title"), REPORT_FORMATS, safe_name(f"driver_pay_{report.start}_{report.end}"),
            lambda c: write_pdf_csv(html, lambda path: driver_pay_to_csv(report, path, settings), c.fmt, c.folder,
                                    c.stem),
        )
