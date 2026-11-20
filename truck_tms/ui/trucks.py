"""Trucks tab: plate and/or unit #, US makes/models, odometer, owner, driver, plate history."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QWidget,
)

from ..database import TRUCK_MAKES, TRUCK_STATUSES, Database, Truck, ValidationError
from ..i18n import t
from .base import CrudTab
from .dialog_kit import DialogPage, with_header
from .theme import warning_color
from .widgets import (
    NumberEdit,
    button,
    buttons_box,
    choice_combo,
    confirm,
    driver_combo,
    fill_table,
    make_table,
    selected_id,
    set_combo_data,
    search_box,
    show_error,
    status_badge,
)


def _editable_combo(items: list[str]) -> QComboBox:
    combo = QComboBox()
    combo.setEditable(True)
    combo.addItem("")
    combo.addItems(items)
    combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
    return combo


class TruckDialog(QDialog):
    def __init__(self, db: Database, truck: Truck | None, parent: QWidget | None = None):
        super().__init__(parent)
        self.db = db
        self.truck = truck
        unit = db.get_settings()["distance_unit"]
        self.setMinimumWidth(860)

        self.plate = QLineEdit()
        self.plate.setPlaceholderText("ABC1234")
        self.unit_number = QLineEdit()
        self.unit_number.setPlaceholderText("101")
        self.make = _editable_combo(list(TRUCK_MAKES))
        self.model = _editable_combo([])
        self.year = _editable_combo([str(y) for y in range(date.today().year + 1, 1989, -1)])
        self.vin = QLineEdit()
        self.vin.setMaxLength(17)
        self.odometer = NumberEdit()
        self.odometer.setPlaceholderText(unit)
        self.owner_name = QLineEdit()
        self.driver = driver_combo(db, include_none=True)
        self.dispatch_fee = NumberEdit()
        self.dispatch_fee.setPlaceholderText(db.get_settings()["dispatch_fee_percent"] + " %")
        self.status = choice_combo(TRUCK_STATUSES, "status.")
        self.notes = QPlainTextEdit()
        self.notes.setFixedHeight(60)
        self.make.currentTextChanged.connect(self._fill_models)

        page = self.page = DialogPage(self, "truck", t("truck.edit") if truck else t("truck.new"),
                                      truck.label if truck else t("truck.plate_or_unit_hint"))
        form = page.section(t("truck.section_identity"), "truck", 0, 0)
        form.addRow(t("truck.plate"), self.plate)
        form.addRow(t("truck.unit_number"), self.unit_number)
        form.addRow(t("truck.vin"), self.vin)
        form.addRow(t("truck.status"), self.status)
        form = page.section(t("truck.section_vehicle"), "wrench", 0, 1)
        form.addRow(t("truck.make"), self.make)
        form.addRow(t("truck.model"), self.model)
        form.addRow(t("truck.year"), self.year)
        form.addRow(f"{t('truck.odometer')} ({unit})", self.odometer)
        form = page.section(t("truck.section_business"), "user", 1, 0)
        form.addRow(t("truck.owner_name"), self.owner_name)
        form.addRow(t("truck.driver"), self.driver)
        form.addRow(t("truck.dispatch_fee"), self.dispatch_fee)
        form = page.section(t("truck.notes"), "file", 1, 1)
        form.addRow(self.notes)
        page.finish(buttons_box(self, self.save))

        if truck:
            self.plate.setText(truck.plate or "")
            self.unit_number.setText(truck.unit_number or "")
            self.make.setCurrentText(truck.make or "")
            self.model.setCurrentText(truck.model or "")
            self.year.setCurrentText(str(truck.year) if truck.year else "")
            self.vin.setText(truck.vin or "")
            self.odometer.setValue(truck.odometer)
            self.owner_name.setText(truck.owner_name or "")
            set_combo_data(self.driver, truck.driver_id)
            self.dispatch_fee.setValue(truck.dispatch_fee_percent)
            set_combo_data(self.status, truck.status)
            self.notes.setPlainText(truck.notes or "")

    def _fill_models(self, make: str) -> None:
        current = self.model.currentText()
        self.model.clear()
        self.model.addItem("")
        self.model.addItems(TRUCK_MAKES.get(make, []))
        self.model.setCurrentText(current)

    def save(self) -> None:
        year_text = self.year.currentText().strip()
        if year_text and not year_text.isdigit():
            show_error(self, "error.invalid_year")
            return
        try:
            truck = Truck(
                id=self.truck.id if self.truck else None,
                plate=self.plate.text(),
                unit_number=self.unit_number.text(),
                make=self.make.currentText(),
                model=self.model.currentText(),
                year=int(year_text) if year_text else None,
                vin=self.vin.text(),
                odometer=self.odometer.int_value(),
                owner_name=self.owner_name.text(),
                driver_id=self.driver.currentData(),
                dispatch_fee_percent=self.dispatch_fee.value(),
                status=self.status.currentData(),
                notes=self.notes.toPlainText(),
            )
            if truck.id is None:
                self.db.add_truck(truck)
            else:
                self.db.update_truck(truck)
        except ValidationError as exc:
            show_error(self, exc)
            return
        self.accept()


class PlateHistoryDialog(QDialog):
    def __init__(self, db: Database, truck: Truck, parent: QWidget | None = None):
        super().__init__(parent)
        self.resize(560, 380)
        layout = with_header(self, "history", t("plate_history.title", plate=truck.label),
                             t("plate_history.subtitle"))
        history = db.plate_history(truck.id)
        if not history:
            empty = QLabel(t("plate_history.empty"))
            empty.setProperty("role", "emptyhint")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(empty, 1)
        else:
            table = make_table([t("plate_history.date"), t("plate_history.old"), t("plate_history.new")])
            fill_table(table, [(h.id, [h.changed_at.replace("T", " "), h.old_plate, h.new_plate]) for h in history])
            layout.addWidget(table, 1)
        close = button(t("btn.close"), "primary")
        close.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(close)
        layout.addLayout(row)


class TrucksTab(CrudTab):
    empty_key = "trucks"
    empty_icon = "truck"

    def __init__(self, db: Database, parent: QWidget | None = None):
        super().__init__(db, parent)
        self.history_btn = button(t("btn.plate_history"), None, "history")
        self.history_btn.clicked.connect(self.show_history)
        self.toolbar.insertWidget(3, self.history_btn)
        self.search = search_box()
        self.search.textChanged.connect(self.refresh)
        self.add_filter(self.search)
        self.refresh()

    def headers(self) -> list[str]:
        return [
            t("truck.unit_number"), t("truck.plate"), t("truck.make"), t("truck.model"), t("truck.year"),
            t("truck.odometer"), t("truck.driver"), t("truck.owner_name"), t("truck.status"),
            t("truck.last_service"), t("truck.vin"),
        ]

    def rows(self):
        drivers = {d.id: d.name for d in self.db.list_drivers()}
        theme = self.db.get_settings()["theme"]
        unit = self.db.get_settings()["distance_unit"]
        rows = []
        for tr in self.db.list_trucks(self.search.text()):
            records = self.db.list_maintenance(truck_id=tr.id)
            last = records[0] if records else None
            due = any(self.db.maintenance_due(m, tr) for m in records)
            last_text = f"{last.date} · {t('service.' + last.service_type)}" if last else ""
            if due:
                last_text = f"⚠ {t('truck.service_due')}  {last_text}"
            rows.append((tr.id, [
                tr.unit_number, tr.plate, tr.make, tr.model, (tr.year or "", tr.year or 0),
                (f"{tr.odometer:,} {unit}" if tr.odometer else "", tr.odometer or 0),
                drivers.get(tr.driver_id, ""), tr.owner_name, status_badge("status.", tr.status),
                (last_text, last.date if last else "", warning_color(theme) if due else None),
                tr.vin,
            ]))
        return rows

    def open_dialog(self, record_id):
        truck = self.db.get_truck(record_id) if record_id else None
        return TruckDialog(self.db, truck, self).exec() == QDialog.DialogCode.Accepted

    def delete_record(self, record_id: int) -> bool:
        truck = self.db.get_truck(record_id)
        if truck is None or not confirm(self, t("confirm.delete_truck", plate=truck.label)):
            return False
        self.db.delete_truck(record_id)
        return True

    def show_history(self) -> None:
        record_id = selected_id(self.table)
        if record_id is None:
            show_error(self, "select_row")
            return
        PlateHistoryDialog(self.db, self.db.get_truck(record_id), self).exec()
