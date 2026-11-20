"""Statements tab: weekly settlement per truck (owner payout + driver pay)."""

from __future__ import annotations

from datetime import date, timedelta
from html import escape

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ..database import ITEM_KINDS, STATEMENT_STATUSES, Database, Statement, StatementItem, ValidationError
from ..i18n import t
from ..printout import money, number
from ..statement import StatementSummary, compute_statement, percent
from ..weeks import week_label, week_start
from .base import CrudTab
from .dialog_kit import DialogPage, Section
from .export import STATEMENT_FORMATS, export_with_dialog, statement_file_stem, write_statement_files
from .theme import warning_color
from .widgets import (
    NumberEdit,
    OptionalDateEdit,
    button,
    buttons_box,
    choice_combo,
    date_edit,
    fill_table,
    hint_label,
    make_table,
    parse_number,
    set_combo_data,
    show_error,
    status_badge,
    truck_combo,
)


def export_statement(parent: QWidget, db: Database, summary: StatementSummary) -> list:
    """Open the export dialog for one statement (or every statement of the same week)."""
    settings = db.get_settings()
    scopes = [("one", t("export.scope_one")),
              ("week", t("export.scope_week", week=week_label(summary.week_start)))]

    def write(choice):
        if choice.scope == "week":
            summaries = [compute_statement(db, s) for s in db.list_statements()
                         if s.week_start == summary.week_start]
            if summary.statement.id is None:  # unsaved statement shown in the dialog
                summaries.append(summary)
        else:
            summaries = [summary]
        return write_statement_files(summaries, choice.fmt, choice.folder, choice.stem, settings,
                                     db=db, include_documents=choice.include_documents)

    return export_with_dialog(parent, db, t("stmt.export_title"), STATEMENT_FORMATS,
                              statement_file_stem(summary), write, scopes, documents_option=True)


class StatementDialog(QDialog):
    def __init__(self, db: Database, statement: Statement | None, parent: QWidget | None = None,
                 default_truck: int | None = None):
        super().__init__(parent)
        self.db = db
        self.statement = statement
        s = db.get_settings()
        self.cur, self.unit, self.theme = s["currency"], s["distance_unit"], s["theme"]
        self.setMinimumWidth(1160)

        # --- header fields
        self.truck = truck_combo(db)
        self.week = date_edit()
        self.week_info = QLabel()
        self.status = choice_combo(STATEMENT_STATUSES, "stmt_status.")
        # --- money fields
        self.fuel_amount = NumberEdit()
        self.fuel_gallons = NumberEdit()
        self.tolls = NumberEdit()
        self.fee_percent = NumberEdit()
        self.fee_fixed = NumberEdit()
        self.driver_override = NumberEdit()
        self.override_hint = hint_label("")
        self.deduct_driver = QCheckBox(t("stmt.deduct_driver_pay"))
        self.deduct_driver.setChecked(True)
        self.driver_paid = NumberEdit()
        self.driver_paid_date = OptionalDateEdit()
        self.notes = QPlainTextEdit()
        self.notes.setFixedHeight(50)

        page = self.page = DialogPage(self, "file", t("stmt.edit") if statement else t("stmt.new"),
                                      t("stmt.subtitle"))
        week_row = QHBoxLayout()
        week_row.addWidget(self.week)
        week_row.addWidget(self.week_info, 1)
        form = page.section(t("stmt.section_week"), "clock", 0, 0)
        form.addRow(t("truck") + " *", self.truck)
        form.addRow(t("stmt.week") + " *", week_row)
        form.addRow(t("stmt.status"), self.status)
        form.addRow(t("load.notes"), self.notes)
        form = page.section(t("stmt.section_costs"), "wallet", 1, 0)
        form.addRow(f"{t('stmt.fuel')} ({self.cur})", self.fuel_amount)
        form.addRow(t("stmt.fuel_gallons"), self.fuel_gallons)
        form.addRow(f"{t('stmt.tolls')} ({self.cur})", self.tolls)
        form.addRow(t("stmt.dispatch_fee_percent"), self.fee_percent)
        form.addRow(f"{t('stmt.dispatch_fee_fixed')} ({self.cur})", self.fee_fixed)
        form = page.section(t("stmt.section_driver"), "user", 2, 0)
        form.addRow(f"{t('stmt.driver_pay_override')} ({self.cur})", self.driver_override)
        form.addRow("", self.override_hint)
        form.addRow("", self.deduct_driver)
        form.addRow(f"{t('stmt.driver_paid')} ({self.cur})", self.driver_paid)
        form.addRow(t("stmt.driver_paid_date"), self.driver_paid_date)

        # --- the result: a big payout figure, then the full summary (paper look in both themes)
        self.payout_value = QLabel()
        self.payout_value.setProperty("role", "payoutvalue")
        self.payout_sub = QLabel()
        self.payout_sub.setProperty("role", "payoutsub")
        payout_card = QFrame()
        payout_card.setObjectName("PayoutCard")
        payout_layout = QVBoxLayout(payout_card)
        payout_layout.setContentsMargins(18, 14, 18, 14)
        payout_layout.setSpacing(2)
        payout_title = QLabel(t("stmt.owner_payout").upper())
        payout_title.setProperty("role", "payouttitle")
        payout_layout.addWidget(payout_title)
        payout_layout.addWidget(self.payout_value)
        payout_layout.addWidget(self.payout_sub)
        self.preview = QTextBrowser()
        self.preview.setStyleSheet("QTextBrowser { background: #FFFFFF; color: #000000; border-radius: 8px; }")
        self.preview.setMinimumHeight(330)
        summary = Section(t("stmt.section_summary"), "chart")
        summary.body.addWidget(payout_card)
        summary.body.addWidget(self.preview, 1)
        page.add_widget(summary, 0, 1, 3, 1)
        page.grid.setColumnStretch(0, 5)
        page.grid.setColumnStretch(1, 6)

        # --- loads of the week
        self.loads_table = make_table([
            t("load.load_number"), t("driver"), t("report.route"), t("report.date"),
            t("load.loaded_miles"), t("load.dead_miles"), t("load.total_miles"),
            t("load.rate"), t("load.extra_pay"), t("load.gross"), t("load.tonu"),
        ])
        self.loads_table.setMinimumHeight(170)
        loads_box = Section(t("stmt.loads_in_week"), "layers")
        loads_box.body.addWidget(self.loads_table)

        # --- additions / deductions
        self.items = QTableWidget(0, 3)
        self.items.setHorizontalHeaderLabels([t("stmt.item_type"), t("expense.description"),
                                              f"{t('expense.amount')} ({self.cur})"])
        self.items.horizontalHeader().setStretchLastSection(True)
        self.items.setColumnWidth(0, 220)
        self.items.setColumnWidth(1, 300)
        add_item = button(t("btn.add_item"), None, "plus")
        remove_item = button(t("btn.remove_item"), "danger", "trash")
        add_item.clicked.connect(lambda: self._add_item_row())
        remove_item.clicked.connect(self._remove_item_row)
        item_buttons = QHBoxLayout()
        item_buttons.addWidget(add_item)
        item_buttons.addWidget(remove_item)
        item_buttons.addStretch(1)
        self.items.setMinimumHeight(140)
        items_box = Section(t("stmt.items"), "plus")
        items_box.body.addLayout(item_buttons)
        items_box.body.addWidget(self.items)

        page.add_widget(loads_box, 3, 0, 1, 2)
        page.add_widget(items_box, 4, 0, 1, 2)

        # --- buttons
        export_btn = button(t("btn.export"), None, "export")
        export_btn.clicked.connect(self._export)
        page.finish(buttons_box(self, self.save), extra_left=export_btn)

        # --- load values
        if statement:
            set_combo_data(self.truck, statement.truck_id)
            self.truck.setEnabled(False)
            self.week.setDate(QDate.fromString(statement.week_start, "yyyy-MM-dd"))
            set_combo_data(self.status, statement.status)
            self.fuel_amount.setValue(statement.fuel_amount)
            self.fuel_gallons.setValue(statement.fuel_gallons)
            self.tolls.setValue(statement.tolls)
            self.fee_percent.setValue(statement.dispatch_fee_percent)
            self.fee_fixed.setValue(statement.dispatch_fee_fixed)
            self.driver_override.setValue(statement.driver_pay_override)
            self.deduct_driver.setChecked(statement.deduct_driver_pay)
            self.driver_paid.setValue(statement.driver_paid_amount)
            self.driver_paid_date.setValue(statement.driver_paid_date)
            self.notes.setPlainText(statement.notes or "")
            for item in db.statement_items(statement.id):
                self._add_item_row(item)
        else:
            set_combo_data(self.truck, default_truck)
            last_week = week_start(date.today() - timedelta(days=7), db.week_start_dow)
            self.week.setDate(QDate(last_week.year, last_week.month, last_week.day))
            self._default_fee()
            self.truck.currentIndexChanged.connect(self._default_fee)

        # --- live updates
        self.week.dateChanged.connect(self._snap_week)
        self.truck.currentIndexChanged.connect(self.recalc)
        for w in (self.fuel_amount, self.fuel_gallons, self.tolls, self.fee_percent, self.fee_fixed,
                  self.driver_override, self.driver_paid):
            w.textChanged.connect(self.recalc)
        self.deduct_driver.toggled.connect(self.recalc)
        self.status.currentIndexChanged.connect(self.recalc)
        self.driver_paid_date.changed.connect(self.recalc)
        self.items.itemChanged.connect(self.recalc)
        self._snap_week()

    # ------------------------------------------------------------- helpers
    def _default_fee(self) -> None:
        truck = self.db.get_truck(self.truck.currentData())
        if truck and truck.dispatch_fee_percent is not None:
            self.fee_percent.setValue(truck.dispatch_fee_percent)
        else:
            try:
                self.fee_percent.setValue(float(self.db.get_settings()["dispatch_fee_percent"] or 0))
            except ValueError:
                self.fee_percent.setValue(0)

    def _snap_week(self) -> None:
        d = self.week.date()
        start = week_start(date(d.year(), d.month(), d.day()), self.db.week_start_dow)
        if start != date(d.year(), d.month(), d.day()):
            self.week.blockSignals(True)
            self.week.setDate(QDate(start.year, start.month, start.day))
            self.week.blockSignals(False)
        self.week_info.setText(week_label(start))
        self.recalc()

    def _add_item_row(self, item: StatementItem | None = None) -> None:
        self.items.blockSignals(True)
        row = self.items.rowCount()
        self.items.insertRow(row)
        kind = QComboBox()
        for k in ITEM_KINDS:
            kind.addItem(t("kind." + k), k)
        if item:
            set_combo_data(kind, item.kind)
        kind.currentIndexChanged.connect(self.recalc)
        self.items.setCellWidget(row, 0, kind)
        self.items.setItem(row, 1, QTableWidgetItem((item.description or "") if item else ""))
        amount = QTableWidgetItem(f"{item.amount:g}" if item else "")
        self.items.setItem(row, 2, amount)
        self.items.blockSignals(False)
        self.recalc()

    def _remove_item_row(self) -> None:
        row = self.items.currentRow()
        if row >= 0:
            self.items.removeRow(row)
            self.recalc()

    def read_items(self) -> list[StatementItem]:
        items = []
        for row in range(self.items.rowCount()):
            desc = self.items.item(row, 1).text() if self.items.item(row, 1) else ""
            amount_text = self.items.item(row, 2).text() if self.items.item(row, 2) else ""
            amount = parse_number(amount_text)
            if amount is None and not desc.strip():
                continue  # empty row
            if amount is None:
                raise ValidationError("error.amount_required")
            items.append(StatementItem(kind=self.items.cellWidget(row, 0).currentData(),
                                       description=desc, amount=amount))
        return items

    def read_statement(self) -> Statement:
        return Statement(
            id=self.statement.id if self.statement else None,
            truck_id=self.truck.currentData(),
            week_start=self.week.date().toString("yyyy-MM-dd"),
            fuel_amount=self.fuel_amount.value() or 0,
            fuel_gallons=self.fuel_gallons.value(),
            tolls=self.tolls.value() or 0,
            dispatch_fee_percent=self.fee_percent.value() or 0,
            dispatch_fee_fixed=self.fee_fixed.value() or 0,
            driver_pay_override=self.driver_override.value(),
            deduct_driver_pay=self.deduct_driver.isChecked(),
            driver_paid_amount=self.driver_paid.value(),
            driver_paid_date=self.driver_paid_date.value(),
            status=self.status.currentData(),
            notes=self.notes.toPlainText().strip() or None,
        )

    def summary(self) -> StatementSummary:
        return compute_statement(self.db, self.read_statement(), self.read_items())

    # ------------------------------------------------------------- live view
    def recalc(self) -> None:
        if self.truck.currentData() is None:
            return
        try:
            s = self.summary()
        except ValidationError:
            return
        self.override_hint.setText(t("stmt.override_hint", amount=money(s.driver_salary_auto, self.cur)))
        fill_table(self.loads_table, [
            (load.id, [
                load.load_number, s.drivers[load.driver_id].name if load.driver_id in s.drivers else "",
                f"{load.pickup_location or '?'} → {load.delivery_location or '?'}", load.report_date,
                (number(load.loaded_miles or 0), load.loaded_miles or 0),
                (number(load.dead_miles or 0), load.dead_miles or 0),
                (number(load.total_miles), load.total_miles),
                (money(load.rate or 0, self.cur), load.rate or 0),
                (money(load.extra_pay or 0, self.cur), load.extra_pay or 0),
                (money(load.gross, self.cur), load.gross),
                t("load.tonu") if load.is_tonu else "",
            ])
            for load in s.loads
        ])
        c = self.cur
        st = s.statement
        rows = [
            (t("stmt.week"), week_label(s.week_start), False),
            (t("driver"), s.driver_names or "—", False),
            (t("report.load_count"), str(len(s.loads)), False),
            (t("load.loaded_miles"), f"{number(s.loaded_miles)} {self.unit}", False),
            (t("load.dead_miles"), f"{number(s.dead_miles)} {self.unit}", False),
            (t("stmt.total_weekly_miles"), f"{number(s.total_miles)} {self.unit}", True),
            (t("stmt.total_gross"), money(s.gross, c), True),
            (t("load.rate_per_mile", unit=self.unit), money(s.rate_per_mile, c), False),
            ("− " + t("stmt.dispatch_fee")
             + (f" ({percent(st.dispatch_fee_percent)})" if st.dispatch_fee_percent else ""),
             money(s.dispatch_fee, c), False),
            ("− " + t("stmt.fuel") + (f" ({st.fuel_gallons:,.1f} {t('unit.gal')})" if st.fuel_gallons else ""),
             money(s.fuel, c), False),
            ("− " + t("stmt.tolls"), money(s.tolls, c), False),
            (("− " if st.deduct_driver_pay else "(") + t("stmt.driver_net") + ("" if st.deduct_driver_pay else ")"),
             money(s.driver_net, c), False),
            ("+ " + t("stmt.owner_additions"), money(s.owner_additions, c), False),
            ("− " + t("stmt.owner_deductions"), money(s.owner_deductions, c), False),
            (t("stmt.owner_payout"), money(s.owner_payout, c), True),
            ("", "", False),
            (t("stmt.driver_salary"), money(s.driver_salary, c), False),
            ("+ " + t("stmt.driver_additions"), money(s.driver_additions, c), False),
            ("− " + t("stmt.driver_deductions"), money(s.driver_deductions, c), False),
            (t("stmt.driver_net"), money(s.driver_net, c), True),
            (t("stmt.driver_paid"), money(s.driver_paid, c), False),
            (t("stmt.driver_balance"), money(s.driver_balance, c), True),
        ]
        html = "".join(
            f"<tr><td>{'<b>' if b else ''}{escape(k)}{'</b>' if b else ''}</td>"
            f"<td align='right'>{'<b>' if b else ''}{escape(v)}{'</b>' if b else ''}</td></tr>"
            for k, v, b in rows
        )
        warn = ""
        if s.driver_balance > 0.005 and st.status != "draft":
            warn = (f"<p style='color:#c00'><b>⚠ {escape(t('stmt.driver_balance'))}: "
                    f"{money(s.driver_balance, c)}</b></p>")
        self.payout_value.setText(money(s.owner_payout, c))
        self.payout_sub.setText(t("stmt.payout_sub", gross=money(s.gross, c),
                                  miles=f"{number(s.total_miles)} {self.unit}",
                                  net=money(s.driver_net, c)))
        self.page.header.set_subtitle(f"{s.truck.label} · {week_label(s.week_start)}")
        self.preview.setHtml(
            f"<h3>{escape(t('stmt.title'))} — {escape(s.truck.label)}</h3>{warn}"
            f"<table cellpadding='3' cellspacing='0' width='100%'>{html}</table>"
        )

    # ------------------------------------------------------------- actions
    def _export(self) -> None:
        try:
            summary = self.summary()
        except ValidationError as exc:
            show_error(self, exc)
            return
        export_statement(self, self.db, summary)

    def save(self) -> None:
        try:
            statement = self.read_statement()
            self.db.save_statement(statement, self.read_items())
        except ValidationError as exc:
            show_error(self, exc)
            return
        self.accept()


class StatementsTab(CrudTab):
    empty_key = "statements"
    empty_icon = "file"

    def __init__(self, db: Database, parent: QWidget | None = None):
        super().__init__(db, parent)
        self.export_btn = self.add_tool(t("btn.export"), "export", self._export_selected)
        self.truck_filter = self.add_truck_filter()
        self.refresh()

    def headers(self) -> list[str]:
        return [t("stmt.week"), t("truck"), t("driver"), t("report.load_count"), t("stmt.total_weekly_miles"),
                t("stmt.total_gross"), t("stmt.dispatch_fee"), t("stmt.fuel"), t("stmt.tolls"),
                t("stmt.driver_net"), t("stmt.driver_paid"), t("stmt.driver_paid_date"),
                t("stmt.driver_balance"), t("stmt.owner_payout"), t("stmt.status")]

    def rows(self):
        st = self.db.get_settings()
        c, warn = st["currency"], warning_color(st["theme"])
        rows = []
        for statement in self.db.list_statements(self.truck_filter.currentData()):
            s = compute_statement(self.db, statement)
            m = lambda v: (money(v, c), v)  # noqa: E731
            balance = s.driver_balance
            rows.append((statement.id, [
                (week_label(s.week_start), s.week_start),
                s.truck.label,
                s.driver_names,
                (str(len(s.loads)), len(s.loads)),
                (number(s.total_miles), s.total_miles),
                m(s.gross), m(s.dispatch_fee), m(s.fuel), m(s.tolls), m(s.driver_net),
                m(s.driver_paid),
                statement.driver_paid_date or "",
                (money(balance, c), balance, warn if balance > 0.005 else None),
                m(s.owner_payout),
                status_badge("stmt_status.", statement.status),
            ]))
        return rows

    def open_dialog(self, record_id):
        statement = self.db.get_statement(record_id) if record_id else None
        dialog = StatementDialog(self.db, statement, self, default_truck=self.truck_filter.currentData())
        return dialog.exec() == QDialog.DialogCode.Accepted

    def delete(self, record_id: int) -> None:
        self.db.delete_statement(record_id)

    def _export_selected(self) -> None:
        record_id = self.selected_or_warn()
        if record_id is not None:
            export_statement(self, self.db, compute_statement(self.db, self.db.get_statement(record_id)))
