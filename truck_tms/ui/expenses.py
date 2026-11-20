"""Expenses tab: per-truck costs (fuel, maintenance, tolls…)."""

from __future__ import annotations

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QLineEdit,
    QWidget,
)

from ..database import EXPENSE_CATEGORIES, IFTA_JURISDICTIONS, Database, Expense, ValidationError
from ..i18n import t
from ..printout import money, number
from .base import CrudTab
from .dialog_kit import DialogPage
from .widgets import (
    NumberEdit,
    buttons_box,
    choice_combo,
    date_edit,
    hint_label,
    set_combo_data,
    show_error,
    truck_combo,
)


class ExpenseDialog(QDialog):
    def __init__(self, db: Database, expense: Expense | None, parent: QWidget | None = None,
                 default_truck: int | None = None):
        super().__init__(parent)
        self.db = db
        self.expense = expense
        currency = db.get_settings()["currency"]
        self.setMinimumWidth(480)

        self.truck = truck_combo(db)
        self.date = date_edit()
        self.category = choice_combo(EXPENSE_CATEGORIES, "category.")
        self.amount = NumberEdit()
        self.amount.setPlaceholderText(currency)
        self.description = QLineEdit()
        self.gallons = NumberEdit()
        self.state = QComboBox()
        self.state.addItem("—", None)
        for code in IFTA_JURISDICTIONS:
            self.state.addItem(code, code)

        page = self.page = DialogPage(self, "wallet", t("expense.edit") if expense else t("expense.new"),
                                      t("expense.subtitle"))
        form = self.form = page.section(t("expense.section"), "wallet")
        form.addRow(t("truck") + " *", self.truck)
        form.addRow(t("expense.date") + " *", self.date)
        form.addRow(t("expense.category") + " *", self.category)
        form.addRow(f"{t('expense.amount')} ({currency}) *", self.amount)
        form.addRow(t("expense.gallons"), self.gallons)
        form.addRow(t("expense.state"), self.state)
        self.fuel_hint = hint_label(t("expense.fuel_hint"))
        form.addRow("", self.fuel_hint)
        form.addRow(t("expense.description"), self.description)
        page.finish(buttons_box(self, self.save))
        self.category.currentIndexChanged.connect(self._category_changed)

        if expense:
            set_combo_data(self.truck, expense.truck_id)
            self.date.setDate(QDate.fromString(expense.date, "yyyy-MM-dd"))
            set_combo_data(self.category, expense.category)
            self.amount.setValue(expense.amount)
            self.description.setText(expense.description or "")
            self.gallons.setValue(expense.gallons)
            set_combo_data(self.state, expense.state)
        elif default_truck is not None:
            set_combo_data(self.truck, default_truck)
        self._category_changed()

    def _category_changed(self) -> None:
        """Gallons and state matter for fuel only (they feed the IFTA report)."""
        fuel = self.category.currentData() == "fuel"
        for widget in (self.gallons, self.state, self.fuel_hint):
            self.form.setRowVisible(widget, fuel)

    def save(self) -> None:
        try:
            expense = Expense(
                id=self.expense.id if self.expense else None,
                truck_id=self.truck.currentData(),
                date=self.date.date().toString("yyyy-MM-dd"),
                category=self.category.currentData(),
                amount=self.amount.value(),
                description=self.description.text(),
            )
            if expense.category == "fuel":
                expense.gallons, expense.state = self.gallons.value(), self.state.currentData()
            if expense.id is None:
                self.db.add_expense(expense)
            else:
                self.db.update_expense(expense)
        except ValidationError as exc:
            show_error(self, exc)
            return
        self.accept()


class ExpensesTab(CrudTab):
    empty_key = "expenses"
    empty_icon = "wallet"

    def __init__(self, db: Database, parent: QWidget | None = None):
        super().__init__(db, parent)
        self.truck_filter = self.add_truck_filter(label=False)
        self.refresh()

    def headers(self) -> list[str]:
        return [t("expense.date"), t("truck"), t("expense.category"), t("expense.amount"), t("expense.gallons"),
                t("expense.state"), t("expense.description")]

    def rows(self):
        currency = self.db.get_settings()["currency"]
        plates = {tr.id: tr.plate for tr in self.db.list_trucks()}
        return [
            (
                e.id,
                [
                    e.date,
                    plates.get(e.truck_id, ""),
                    t("category." + e.category),
                    (money(e.amount, currency), e.amount),
                    (number(e.gallons, 1) if e.gallons else "", e.gallons or 0.0),
                    e.state or "",
                    e.description,
                ],
            )
            for e in self.db.list_expenses(truck_id=self.truck_filter.currentData())
        ]

    def open_dialog(self, record_id):
        expense = self.db.get_expense(record_id) if record_id else None
        dialog = ExpenseDialog(self.db, expense, self, default_truck=self.truck_filter.currentData())
        return dialog.exec() == QDialog.DialogCode.Accepted

    def delete(self, record_id: int) -> None:
        self.db.delete_expense(record_id)
