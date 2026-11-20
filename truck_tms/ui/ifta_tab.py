"""IFTA tab: quarterly fuel tax worksheet, tax rates, and the miles-by-state editor used by loads."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..database import IFTA_JURISDICTIONS, Database, ValidationError
from ..i18n import t
from ..ifta import IftaReport, compute_ifta, current_quarter, ifta_to_csv, ifta_to_html
from ..numbers import format_number, parse_number
from ..printout import number
from .dialog_kit import with_header
from .export import REPORT_FORMATS, export_with_dialog, paper_preview, print_html, safe_name, write_pdf_csv
from .theme import icon, token
from .widgets import NumberEdit, button, buttons_box, fill_truck_combo, hint_label, show_error, truck_combo


# --------------------------------------------------------------- miles by state
class StateMilesEditor(QWidget):
    """Rows of [state ▾] [miles] [×] with an "Add state" button and a running total.

    ``changed`` fires on every edit; ``expected`` (the load's total miles) is compared with the sum.
    """

    changed = Signal()

    def __init__(self, unit: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.unit = unit
        self.expected: float = 0.0
        self.rows: list[tuple[QWidget, QComboBox, NumberEdit]] = []
        self.list = QVBoxLayout()
        self.list.setSpacing(4)
        self.add_btn = button(t("ifta.add_state"), None, "plus")
        self.add_btn.clicked.connect(lambda: self.add_row())
        self.total = QLabel()
        self.total.setProperty("role", "hint")
        bottom = QHBoxLayout()
        bottom.addWidget(self.add_btn)
        bottom.addStretch(1)
        bottom.addWidget(self.total)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addLayout(self.list)
        layout.addLayout(bottom)
        self._update()

    def add_row(self, state: str | None = None, miles: float | None = None) -> None:
        holder = QWidget()
        combo = QComboBox()
        combo.addItem("—", None)
        for code in IFTA_JURISDICTIONS:
            combo.addItem(code, code)
        combo.setCurrentIndex(max(0, combo.findData(state)))
        edit = NumberEdit()
        edit.setPlaceholderText(self.unit)
        edit.setValue(miles)
        remove = QPushButton()
        remove.setIcon(icon("close", token("muted")))
        remove.setFixedWidth(34)
        remove.setToolTip(t("btn.delete"))
        remove.setProperty("noLift", True)
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(combo, 1)
        row.addWidget(edit, 2)
        row.addWidget(remove)
        entry = (holder, combo, edit)
        self.rows.append(entry)
        self.list.addWidget(holder)
        combo.currentIndexChanged.connect(self._update)
        edit.textChanged.connect(self._update)
        remove.clicked.connect(lambda: self._remove(entry))
        self._update()

    def _remove(self, entry) -> None:
        self.rows.remove(entry)
        entry[0].setParent(None)
        entry[0].deleteLater()
        self._update()

    def set_states(self, states: list[tuple[str, float]]) -> None:
        for entry in list(self.rows):
            self._remove(entry)
        for state, miles in states:
            self.add_row(state, miles)

    def states(self) -> list[tuple[str, float]]:
        """Filled rows; raises ValidationError for text that is not a number."""
        result = []
        for _, combo, edit in self.rows:
            miles = edit.value()
            if combo.currentData() and miles:
                result.append((combo.currentData(), miles))
        return result

    def set_expected(self, miles: float) -> None:
        self.expected = miles or 0.0
        self._update()

    def _update(self) -> None:
        try:
            total = sum(m for _, m in self.states())
        except ValidationError:
            total = 0.0
        if not self.rows:
            self.total.setText(t("ifta.states_hint"))
        else:
            mark = ""
            if self.expected:
                mark = "  ✓" if abs(total - self.expected) < 0.5 else f"  ≠ {number(self.expected)}"
            self.total.setText(f"{t('ifta.total')}: {number(total)} {self.unit}{mark}")
        self.changed.emit()


# --------------------------------------------------------------- tax rates
class IftaRatesDialog(QDialog):
    """Tax rate per gallon for every jurisdiction (the IFTA rate table changes every quarter)."""

    def __init__(self, db: Database, parent: QWidget | None = None):
        super().__init__(parent)
        self.db = db
        self.setMinimumSize(420, 560)
        rates = db.ifta_rates()
        self.table = QTableWidget(len(IFTA_JURISDICTIONS), 2)
        self.table.setHorizontalHeaderLabels([t("ifta.state"), t("ifta.rate")])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        for r, code in enumerate(IFTA_JURISDICTIONS):
            state = QTableWidgetItem(code)
            state.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.table.setItem(r, 0, state)
            self.table.setItem(r, 1, QTableWidgetItem(format_number(rates.get(code))))
        layout = with_header(self, "map", t("ifta.rates_title"), t("ifta.rates_subtitle"))
        layout.addWidget(hint_label(t("ifta.rates_hint")))
        layout.addWidget(self.table, 1)
        layout.addWidget(buttons_box(self, self.save))

    def save(self) -> None:
        rates = {}
        try:
            for r, code in enumerate(IFTA_JURISDICTIONS):
                rates[code] = parse_number(self.table.item(r, 1).text())
            self.db.set_ifta_rates(rates)
        except ValidationError as exc:
            show_error(self, exc)
            return
        self.accept()


# --------------------------------------------------------------- the tab
class IftaTab(QWidget):
    def __init__(self, db: Database, parent: QWidget | None = None):
        super().__init__(parent)
        self.db = db
        self.report: IftaReport | None = None
        self.html = ""
        year, quarter = current_quarter()
        self.year = QSpinBox()
        self.year.setRange(2000, 2100)
        self.year.setValue(year)
        self.quarter = QComboBox()
        for q in range(1, 5):
            self.quarter.addItem(f"Q{q}", q)
        self.quarter.setCurrentIndex(quarter - 1)
        self.truck = truck_combo(db, include_all=True)
        self.generate_btn = button(t("btn.generate"), "primary", "chart")
        self.rates_btn = button(t("ifta.rates_button"), None, "sliders")
        self.export_btn = button(t("btn.export"), None, "export")
        self.print_btn = button(t("btn.print"), None, "print")
        bar = QHBoxLayout()
        bar.addWidget(QLabel(t("ifta.year")))
        bar.addWidget(self.year)
        bar.addWidget(QLabel(t("ifta.quarter")))
        bar.addWidget(self.quarter)
        bar.addWidget(QLabel(t("truck")))
        bar.addWidget(self.truck, 1)
        bar.addWidget(self.generate_btn)
        bar.addStretch(1)
        bar.addWidget(self.rates_btn)
        bar.addWidget(self.export_btn)
        bar.addWidget(self.print_btn)
        self.preview = paper_preview()
        layout = QVBoxLayout(self)
        layout.addLayout(bar)
        layout.addWidget(hint_label(t("ifta.how")))
        layout.addWidget(self.preview, 1)
        self.generate_btn.clicked.connect(self.generate)
        self.rates_btn.clicked.connect(self.edit_rates)
        self.export_btn.clicked.connect(self.export)
        self.print_btn.clicked.connect(self.print_report)
        for combo in (self.quarter, self.truck):
            combo.currentIndexChanged.connect(self.generate)
        self.year.valueChanged.connect(self.generate)
        self.generate()

    def refresh(self) -> None:
        fill_truck_combo(self.truck, self.db, include_all=True)
        self.generate()

    def generate(self) -> None:
        self.report = compute_ifta(self.db, self.year.value(), self.quarter.currentData(), self.truck.currentData())
        truck = self.db.get_truck(self.truck.currentData())
        self.html = ifta_to_html(self.report, self.db.get_settings(), truck.label if truck else None)
        self.preview.setHtml(self.html)

    def edit_rates(self) -> None:
        if IftaRatesDialog(self.db, self).exec() == QDialog.DialogCode.Accepted:
            self.generate()

    def default_stem(self) -> str:
        r = self.report
        return safe_name(f"ifta_{r.year}_Q{r.quarter}")

    def export(self) -> None:
        settings = self.db.get_settings()

        report, html = self.report, self.html
        export_with_dialog(
            self, self.db, t("ifta.export_title"), REPORT_FORMATS, self.default_stem(),
            lambda c: write_pdf_csv(html, lambda path: ifta_to_csv(report, path, settings), c.fmt, c.folder, c.stem),
        )

    def print_report(self) -> None:
        print_html(self, self.html)
