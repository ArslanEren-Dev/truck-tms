"""Drivers tab: contact, CDL, pay settings and unpaid balance."""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QLineEdit, QPlainTextEdit, QWidget

from ..database import DRIVER_STATUSES, PAY_TYPES, Database, Driver, ValidationError
from ..i18n import t
from ..report import money
from ..statement import driver_balances, percent
from .base import CrudTab
from .dialog_kit import DialogPage
from .theme import warning_color
from .widgets import (
    NumberEdit,
    OptionalDateEdit,
    buttons_box,
    choice_combo,
    confirm,
    hint_label,
    set_combo_data,
    search_box,
    show_error,
    status_badge,
)


def pay_description(driver: Driver, currency: str, unit: str) -> str:
    if driver.pay_rate is None:
        return ""
    rate = f"{driver.pay_rate:g}"
    if driver.pay_type == "percent":
        return t("pay.desc_percent", rate=percent(driver.pay_rate))
    if driver.pay_type == "per_mile":
        return t("pay.desc_per_mile", amount=f"{currency}{rate}", unit=t("unit." + unit))
    return t("pay.desc_weekly", amount=money(driver.pay_rate, currency))


class DriverDialog(QDialog):
    def __init__(self, db: Database, driver: Driver | None, parent: QWidget | None = None):
        super().__init__(parent)
        self.db = db
        self.driver = driver
        self.setMinimumWidth(820)

        self.name = QLineEdit()
        self.phone = QLineEdit()
        self.email = QLineEdit()
        self.license_number = QLineEdit()
        self.license_expiry = OptionalDateEdit()
        self.pay_type = choice_combo(PAY_TYPES, "pay.")
        self.pay_rate = NumberEdit()
        self.status = choice_combo(DRIVER_STATUSES, "status.")
        self.notes = QPlainTextEdit()
        self.notes.setFixedHeight(60)

        page = self.page = DialogPage(self, "user", t("driver.edit") if driver else t("driver.new"),
                                      driver.name if driver else t("driver.subtitle"))
        form = page.section(t("driver.section_contact"), "user", 0, 0)
        form.addRow(t("driver.name") + " *", self.name)
        form.addRow(t("driver.phone"), self.phone)
        form.addRow(t("driver.email"), self.email)
        form.addRow(t("truck.status"), self.status)
        form = page.section(t("driver.section_license"), "file", 1, 0)
        form.addRow(t("driver.license_number"), self.license_number)
        form.addRow(t("driver.license_expiry"), self.license_expiry)
        form = page.section(t("driver.section_pay"), "dollar", 0, 1)
        form.addRow(t("driver.pay_type"), self.pay_type)
        form.addRow(t("driver.pay_rate"), self.pay_rate)
        form.addRow("", hint_label(t("pay.rate_hint")))
        form = page.section(t("truck.notes"), "edit", 1, 1)
        form.addRow(self.notes)
        page.finish(buttons_box(self, self.save))

        if driver:
            self.name.setText(driver.name)
            self.phone.setText(driver.phone or "")
            self.email.setText(driver.email or "")
            self.license_number.setText(driver.license_number or "")
            self.license_expiry.setValue(driver.license_expiry)
            set_combo_data(self.pay_type, driver.pay_type)
            self.pay_rate.setValue(driver.pay_rate)
            set_combo_data(self.status, driver.status)
            self.notes.setPlainText(driver.notes or "")

    def save(self) -> None:
        try:
            driver = Driver(
                id=self.driver.id if self.driver else None,
                name=self.name.text(),
                phone=self.phone.text(),
                email=self.email.text(),
                license_number=self.license_number.text(),
                license_expiry=self.license_expiry.value(),
                pay_type=self.pay_type.currentData(),
                pay_rate=self.pay_rate.value(),
                status=self.status.currentData(),
                notes=self.notes.toPlainText(),
            )
            if driver.pay_type == "percent" and (driver.pay_rate or 0) > 100:
                raise ValidationError("error.invalid_percent")
            if driver.id is None:
                self.db.add_driver(driver)
            else:
                self.db.update_driver(driver)
        except ValidationError as exc:
            show_error(self, exc)
            return
        self.accept()


class DriversTab(CrudTab):
    empty_key = "drivers"
    empty_icon = "user"

    def __init__(self, db: Database, parent: QWidget | None = None):
        super().__init__(db, parent)
        self.search = search_box()
        self.search.textChanged.connect(self.refresh)
        self.add_filter(self.search)
        self.refresh()

    def headers(self) -> list[str]:
        return [t("driver.name"), t("driver.phone"), t("driver.email"), t("driver.license_number"),
                t("driver.license_expiry"), t("driver.pay"), t("driver.trucks"), t("driver.unpaid"),
                t("truck.status")]

    def rows(self):
        s = self.db.get_settings()
        balances = driver_balances(self.db)
        trucks: dict[int, list[str]] = {}
        for tr in self.db.list_trucks():
            if tr.driver_id:
                trucks.setdefault(tr.driver_id, []).append(tr.label)
        rows = []
        for d in self.db.list_drivers(self.search.text()):
            balance = balances.get(d.id, 0.0)
            rows.append((d.id, [
                d.name, d.phone, d.email, d.license_number, d.license_expiry,
                pay_description(d, s["currency"], s["distance_unit"]),
                ", ".join(trucks.get(d.id, [])),
                (money(balance, s["currency"]) if balance else "", balance,
                 warning_color(s["theme"]) if balance > 0 else None),
                status_badge("status.", d.status),
            ]))
        return rows

    def open_dialog(self, record_id):
        driver = self.db.get_driver(record_id) if record_id else None
        return DriverDialog(self.db, driver, self).exec() == QDialog.DialogCode.Accepted

    def delete_record(self, record_id: int) -> bool:
        driver = self.db.get_driver(record_id)
        if driver is None or not confirm(self, t("confirm.delete_driver", name=driver.name)):
            return False
        self.db.delete_driver(record_id)
        return True
