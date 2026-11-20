"""Maintenance tab: service records per truck with next-due date / odometer."""

from __future__ import annotations

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QDialog, QLineEdit, QPlainTextEdit, QWidget

from ..database import SERVICE_TYPES, Database, Maintenance, ValidationError
from ..i18n import t
from ..printout import money
from .base import CrudTab
from .dialog_kit import DialogPage
from .widgets import (
    NumberEdit,
    OptionalDateEdit,
    buttons_box,
    choice_combo,
    date_edit,
    fill_truck_combo,
    hint_label,
    set_combo_data,
    Badge,
    show_error,
    truck_combo,
)


class MaintenanceDialog(QDialog):
    def __init__(self, db: Database, record: Maintenance | None, parent: QWidget | None = None,
                 default_truck: int | None = None):
        super().__init__(parent)
        self.db = db
        self.record = record
        s = db.get_settings()
        self.setMinimumWidth(820)

        self.truck = truck_combo(db)
        self.date = date_edit()
        self.service_type = choice_combo(SERVICE_TYPES, "service.")
        self.odometer = NumberEdit()
        self.odometer.setPlaceholderText(s["distance_unit"])
        self.cost = NumberEdit()
        self.cost.setPlaceholderText(s["currency"])
        self.vendor = QLineEdit()
        self.description = QPlainTextEdit()
        self.description.setFixedHeight(70)
        self.next_due_date = OptionalDateEdit()
        self.next_due_odometer = NumberEdit()

        page = self.page = DialogPage(self, "wrench", t("maint.edit") if record else t("maint.new"),
                                      t("maint.subtitle"))
        form = page.section(t("maint.section_service"), "wrench", 0, 0)
        form.addRow(t("truck") + " *", self.truck)
        form.addRow(t("maint.date") + " *", self.date)
        form.addRow(t("maint.service_type") + " *", self.service_type)
        form.addRow(f"{t('maint.cost')} ({s['currency']})", self.cost)
        form.addRow(t("maint.vendor"), self.vendor)
        form = page.section(t("maint.section_odometer"), "route", 0, 1)
        form.addRow(f"{t('maint.odometer')} ({s['distance_unit']})", self.odometer)
        form.addRow("", hint_label(t("maint.odometer_hint")))
        form.addRow(t("maint.next_due_date"), self.next_due_date)
        form.addRow(f"{t('maint.next_due_odometer')} ({s['distance_unit']})", self.next_due_odometer)
        form = page.section(t("maint.description"), "edit", 1, 0, 1, 2)
        form.addRow(self.description)
        page.finish(buttons_box(self, self.save))

        if record:
            set_combo_data(self.truck, record.truck_id)
            self.date.setDate(QDate.fromString(record.date, "yyyy-MM-dd"))
            set_combo_data(self.service_type, record.service_type)
            self.odometer.setValue(record.odometer)
            self.cost.setValue(record.cost)
            self.vendor.setText(record.vendor or "")
            self.description.setPlainText(record.description or "")
            self.next_due_date.setValue(record.next_due_date)
            self.next_due_odometer.setValue(record.next_due_odometer)
        elif default_truck is not None:
            set_combo_data(self.truck, default_truck)

    def save(self) -> None:
        try:
            record = Maintenance(
                id=self.record.id if self.record else None,
                truck_id=self.truck.currentData(),
                date=self.date.date().toString("yyyy-MM-dd"),
                service_type=self.service_type.currentData(),
                odometer=self.odometer.int_value(),
                cost=self.cost.value(),
                vendor=self.vendor.text(),
                description=self.description.toPlainText(),
                next_due_date=self.next_due_date.value(),
                next_due_odometer=self.next_due_odometer.int_value(),
            )
            if record.id is None:
                self.db.add_maintenance(record)
            else:
                self.db.update_maintenance(record)
        except ValidationError as exc:
            show_error(self, exc)
            return
        self.accept()


class MaintenanceTab(CrudTab):
    empty_key = "maintenance"
    empty_icon = "wrench"

    def __init__(self, db: Database, parent: QWidget | None = None):
        super().__init__(db, parent)
        self.truck_filter = self.add_truck_filter()
        self.refresh()

    def headers(self) -> list[str]:
        return [t("maint.date"), t("truck"), t("maint.service_type"), t("maint.odometer"), t("maint.cost"),
                t("maint.vendor"), t("maint.next_due_date"), t("maint.next_due_odometer"), t("maint.due"),
                t("maint.description")]

    def refresh(self) -> None:
        fill_truck_combo(self.truck_filter, self.db, include_all=True)
        super().refresh()

    def rows(self):
        s = self.db.get_settings()
        trucks = {tr.id: tr for tr in self.db.list_trucks()}
        rows = []
        for m in self.db.list_maintenance(truck_id=self.truck_filter.currentData()):
            truck = trucks.get(m.truck_id)
            due = self.db.maintenance_due(m, truck)
            rows.append((m.id, [
                m.date,
                truck.label if truck else "",
                t("service." + m.service_type),
                (f"{m.odometer:,}" if m.odometer is not None else "", m.odometer or 0),
                (money(m.cost, s["currency"]) if m.cost is not None else "", m.cost or 0.0),
                m.vendor,
                m.next_due_date,
                (f"{m.next_due_odometer:,}" if m.next_due_odometer else "", m.next_due_odometer or 0),
                Badge(t("truck.service_due"), "danger") if due else "",
                (m.description or "").replace("\n", " "),
            ]))
        return rows

    def open_dialog(self, record_id):
        record = self.db.get_maintenance(record_id) if record_id else None
        dialog = MaintenanceDialog(self.db, record, self, default_truck=self.truck_filter.currentData())
        return dialog.exec() == QDialog.DialogCode.Accepted

    def delete(self, record_id: int) -> None:
        self.db.delete_maintenance(record_id)
