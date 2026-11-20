"""Invoices tab: bill brokers for loads, track what is still owed and how late it is."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from PySide6.QtCore import QDate
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..database import INVOICE_METHODS, Database, Invoice, Load, ValidationError
from ..i18n import t
from ..invoicing import AGING_BUCKETS, compute_receivables, invoice_to_html
from ..printout import money
from .base import CrudTab
from .charts import DonutChart
from .dashboard import StatCard
from .dialog_kit import DialogPage
from .export import default_export_folder, html_to_pdf, report_written, safe_name
from .theme import token
from .widgets import (
    NumberEdit,
    OptionalDateEdit,
    button,
    buttons_box,
    choice_combo,
    date_edit,
    hint_label,
    set_combo_data,
    show_error,
    show_warning,
    status_badge,
)

STATUS_FILTERS = ("all", "unpaid", "overdue", "paid")
AGING_COLORS = ("accent", "#F5A623", "#E8743B", "#D63A3A", "#8E1E1E")  # not due → very late


def load_label(load: Load, currency: str) -> str:
    route = f"{load.pickup_location or '?'} → {load.delivery_location or '?'}"
    return f"{load.load_number or '—'} · {route} · {money(load.gross, currency)}"


def aging_colors() -> list[QColor]:
    return [QColor(token(c) if not c.startswith("#") else c) for c in AGING_COLORS]


class InvoiceDialog(QDialog):
    def __init__(self, db: Database, invoice: Invoice | None, parent: QWidget | None = None,
                 load_id: int | None = None):
        super().__init__(parent)
        self.db = db
        self.invoice = invoice
        settings = db.get_settings()
        self.cur = settings["currency"]
        self.setMinimumWidth(860)
        self._auto_amount: float | None = None

        self.load = QComboBox()
        self.load.addItem(t("inv.no_load"), None)
        invoiced = {inv.load_id for inv in db.list_invoices() if inv.load_id and (not invoice or inv.id != invoice.id)}
        self.loads = {}
        for load in db.list_loads():
            if load.id in invoiced or (load.status == "cancelled" and not load.is_tonu):
                continue
            self.loads[load.id] = load
            self.load.addItem(load_label(load, self.cur), load.id)
        self.number = QLineEdit(invoice.invoice_number if invoice else db.next_invoice_number())
        self.issue_date = date_edit()
        self.terms = QSpinBox()
        self.terms.setRange(0, 365)
        self.terms.setSuffix(" " + t("inv.days"))
        try:
            self.terms.setValue(int(settings.get("invoice_terms") or 30))
        except ValueError:
            self.terms.setValue(30)
        self.due = hint_label("")
        self.due.setWordWrap(False)
        self.bill_to = QPlainTextEdit()
        self.bill_to.setFixedHeight(64)
        self.bill_to.setPlaceholderText(t("inv.bill_to_hint"))
        self.amount = NumberEdit()
        self.amount.setPlaceholderText(self.cur)
        self.method = choice_combo(INVOICE_METHODS, "inv.method.")
        self.fee = NumberEdit()
        self.fee.setPlaceholderText(t("inv.fee_hint"))
        self.paid_amount = NumberEdit()
        self.paid_date = OptionalDateEdit()
        self.paid_full = button(t("inv.mark_paid"), None, "check")
        self.paid_full.clicked.connect(self._mark_paid)
        self.balance = QLabel()
        self.balance.setProperty("role", "metric")
        self.notes = QPlainTextEdit()
        self.notes.setFixedHeight(56)

        page = self.page = DialogPage(self, "receipt", t("inv.edit") if invoice else t("inv.new"), t("inv.subtitle"))
        form = page.section(t("inv.section"), "receipt", 0, 0)
        form.addRow(t("inv.load"), self.load)
        form.addRow(t("inv.number") + " *", self.number)
        form.addRow(t("inv.issue_date") + " *", self.issue_date)
        form.addRow(t("inv.terms"), self.terms)
        form.addRow("", self.due)
        form.addRow(t("inv.bill_to"), self.bill_to)
        form = page.section(t("inv.section_payment"), "dollar", 0, 1)
        form.addRow(f"{t('inv.amount')} ({self.cur}) *", self.amount)
        form.addRow(t("inv.method"), self.method)
        form.addRow(f"{t('inv.fee')} ({self.cur})", self.fee)
        form.addRow(f"{t('inv.received')} ({self.cur})", self.paid_amount)
        form.addRow(t("inv.paid_date"), self.paid_date)
        form.addRow("", self.paid_full)
        form.addRow("", self.balance)
        form = page.section(t("load.notes"), "file", 1, 0)
        form.addRow(self.notes)
        page.add_widget(QWidget(), 1, 1)
        page.finish(buttons_box(self, self.save))

        if invoice:
            set_combo_data(self.load, invoice.load_id)
            self.issue_date.setDate(QDate.fromString(invoice.issue_date, "yyyy-MM-dd"))
            self.terms.setValue(invoice.terms_days)
            self.bill_to.setPlainText(invoice.bill_to or "")
            self.amount.setValue(invoice.amount)
            set_combo_data(self.method, invoice.method)
            self.fee.setValue(invoice.fee)
            self.paid_amount.setValue(invoice.paid_amount)
            self.paid_date.setValue(invoice.paid_date)
            self.notes.setPlainText(invoice.notes or "")
        elif load_id is not None:
            set_combo_data(self.load, load_id)
            self._load_changed()

        self.load.currentIndexChanged.connect(self._load_changed)
        self.terms.valueChanged.connect(self._update)
        self.issue_date.dateChanged.connect(self._update)
        for w in (self.amount, self.fee, self.paid_amount, self.number):
            w.textChanged.connect(self._update)
        self._update()

    def _load_changed(self) -> None:
        """Fill the amount and "bill to" from the load unless the user already typed their own."""
        load = self.loads.get(self.load.currentData())
        if not load:
            return
        try:
            current = self.amount.value()
        except ValidationError:
            current = None
        if current is None or current == self._auto_amount:
            self.amount.setValue(load.gross)
            self._auto_amount = load.gross
        if not self.bill_to.toPlainText().strip() and load.broker:
            self.bill_to.setPlainText(load.broker)

    def _values(self) -> tuple[float, float, float]:
        try:
            return self.amount.value() or 0.0, self.fee.value() or 0.0, self.paid_amount.value() or 0.0
        except ValidationError:
            return 0.0, 0.0, 0.0

    def _update(self) -> None:
        due = self.issue_date.date().addDays(self.terms.value()).toString("yyyy-MM-dd")
        self.due.setText(t("inv.due_on", date=due))
        amount, fee, paid = self._values()
        balance = round(amount - fee - paid, 2)
        self.balance.setText(f"{t('inv.balance')}: <b>{money(balance, self.cur)}</b>")
        number = self.number.text().strip()
        self.page.header.set_subtitle(" · ".join(x for x in (number, money(amount, self.cur) if amount else "") if x)
                                      or t("inv.subtitle"))

    def _mark_paid(self) -> None:
        amount, fee, _ = self._values()
        self.paid_amount.setValue(round(amount - fee, 2))
        if not self.paid_date.value():
            self.paid_date.setValue(date.today().isoformat())

    def save(self) -> None:
        try:
            inv = Invoice(
                id=self.invoice.id if self.invoice else None,
                load_id=self.load.currentData(),
                invoice_number=self.number.text(),
                issue_date=self.issue_date.date().toString("yyyy-MM-dd"),
                terms_days=self.terms.value(),
                bill_to=self.bill_to.toPlainText(),
                amount=self.amount.value(),
                method=self.method.currentData(),
                fee=self.fee.value(),
                paid_amount=self.paid_amount.value(),
                paid_date=self.paid_date.value(),
                notes=self.notes.toPlainText(),
            )
            if inv.id is None:
                inv.id = self.db.add_invoice(inv)
            else:
                self.db.update_invoice(inv)
        except ValidationError as exc:
            show_error(self, exc)
            return
        self.accept()


def save_invoice_pdf(parent: QWidget, db: Database, inv: Invoice) -> Path | None:
    folder = default_export_folder(db) / "invoices"
    suggested = folder / f"{safe_name(inv.invoice_number)}.pdf"
    path, _ = QFileDialog.getSaveFileName(parent, t("inv.save_pdf"), str(suggested), "PDF (*.pdf)")
    if not path:
        return None
    target = Path(path if path.lower().endswith(".pdf") else path + ".pdf")
    load = db.get_load(inv.load_id)
    truck = db.get_truck(load.truck_id) if load else None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        html_to_pdf(invoice_to_html(inv, load, truck, db.get_settings()), target)
    except OSError as exc:
        show_warning(parent, t("export.failed", error=str(exc)))
        return None
    report_written(parent, [target], False)
    return target


class InvoicesTab(CrudTab):
    empty_key = "invoices"
    empty_icon = "receipt"

    def __init__(self, db: Database, parent: QWidget | None = None):
        super().__init__(db, parent)
        self.pdf_btn = self.add_tool(t("inv.save_pdf"), "export", self.save_pdf)
        self.status_filter = QComboBox()
        for key in STATUS_FILTERS:
            self.status_filter.addItem(t("inv.filter." + key), key)
        self.status_filter.currentIndexChanged.connect(self.refresh)
        self.add_filter(self.status_filter)

        # receivables summary: four numbers and the aging ring
        self.cards = {
            "open": StatCard(t("inv.kpi_open"), "receipt"),
            "overdue": StatCard(t("inv.kpi_overdue"), "alert"),
            "collected": StatCard(t("inv.kpi_collected"), "dollar"),
            "days": StatCard(t("inv.kpi_days"), "clock"),
        }
        grid = QGridLayout()
        grid.setSpacing(10)
        for i, card in enumerate(self.cards.values()):
            grid.addWidget(card, i // 2, i % 2)
        self.aging = DonutChart()
        self.aging.setMinimumHeight(150)
        aging_box = QFrame()
        aging_box.setObjectName("Card")
        inner = QVBoxLayout(aging_box)
        inner.setContentsMargins(14, 10, 14, 8)
        heading = QLabel(t("inv.aging"))
        heading.setProperty("role", "section")
        inner.addWidget(heading)
        inner.addWidget(self.aging, 1)
        header = QHBoxLayout()
        header.setSpacing(12)
        header.addLayout(grid, 3)
        header.addWidget(aging_box, 2)
        self.layout().insertLayout(1, header)
        self.refresh(animate=False)

    def headers(self) -> list[str]:
        return [t("inv.number"), t("load.load_number"), t("inv.bill_to"), t("inv.issue_date"), t("inv.due_date"),
                t("inv.amount"), t("inv.received"), t("inv.balance"), t("inv.status"), t("inv.late")]

    def refresh(self, animate: bool = True) -> None:
        super().refresh()
        cur = self.db.get_settings()["currency"]
        r = compute_receivables(self.db, invoices=self._invoices)
        c = self.cards
        c["open"].set_value(r.open_total, lambda v: money(v, cur), t("inv.kpi_open_sub", n=r.open_count), animate)
        c["overdue"].set_value(r.overdue_total, lambda v: money(v, cur), t("inv.kpi_overdue_sub", n=r.overdue_count),
                               animate)
        c["overdue"].set_tone("danger" if r.overdue_count else "success")
        c["collected"].set_value(r.collected_30d, lambda v: money(v, cur), t("inv.kpi_collected_sub"), animate)
        c["collected"].set_tone("success")
        days = r.avg_days_to_pay
        c["days"].set_value(days or 0, lambda v: t("inv.n_days", n=f"{v:.0f}") if days is not None else "—",
                            t("inv.kpi_days_sub"), animate)
        self.aging.fmt = lambda v: money(v, cur)
        self.aging.colors = aging_colors()
        self.aging.center_title = t("inv.kpi_open")
        self.aging.set_data([t("inv.bucket." + b) for b in AGING_BUCKETS], [r.buckets[b] for b in AGING_BUCKETS],
                            animate)

    def rows(self):
        cur = self.db.get_settings()["currency"]
        loads = {load.id: load for load in self.db.list_loads()}
        self._invoices = self.db.list_invoices()
        today = date.today()
        wanted = self.status_filter.currentData()
        rows = []
        for inv in self._invoices:
            status = inv.status(today)
            if wanted == "unpaid" and status == "paid" or wanted == "paid" and status != "paid" \
                    or wanted == "overdue" and status != "overdue":
                continue
            load = loads.get(inv.load_id)
            late = inv.days_overdue(today)
            rows.append((inv.id, [
                inv.invoice_number,
                load.load_number if load else "—",
                (inv.bill_to or (load.broker if load else "") or "").split("\n")[0],
                inv.issue_date,
                inv.due_date,
                (money(inv.amount, cur), inv.amount),
                (money(inv.paid_amount, cur) if inv.paid_amount else "", inv.paid_amount or 0.0),
                (money(inv.balance, cur), inv.balance),
                status_badge("inv.status.", status),
                (t("inv.n_days", n=late) if late else "", late),
            ]))
        return rows

    def has_filters(self) -> bool:
        return self.status_filter.currentIndex() > 0

    def open_dialog(self, record_id):
        invoice = self.db.get_invoice(record_id) if record_id else None
        return InvoiceDialog(self.db, invoice, self).exec() == QDialog.DialogCode.Accepted

    def save_pdf(self) -> None:
        record_id = self.selected_or_warn()
        if record_id is not None:
            save_invoice_pdf(self, self.db, self.db.get_invoice(record_id))

    def delete(self, record_id: int) -> None:
        self.db.delete_invoice(record_id)
