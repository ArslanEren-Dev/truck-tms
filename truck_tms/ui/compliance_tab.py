"""Compliance tab: CDL, medical cards, registrations, insurance, UCR… and when they expire."""

from __future__ import annotations

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QComboBox, QDialog, QLineEdit, QPlainTextEdit, QWidget

from ..compliance import SOON_DAYS, attention_needed, compliance_entries
from ..database import (
    COMPANY_COMPLIANCE,
    DRIVER_COMPLIANCE,
    TRUCK_COMPLIANCE,
    ComplianceItem,
    Database,
    ValidationError,
)
from ..i18n import t
from .base import CrudTab
from .dialog_kit import DialogPage
from .widgets import (
    STATUS_TONES,
    buttons_box,
    date_edit,
    driver_combo,
    hint_label,
    set_combo_data,
    show_error,
    status_badge,
    truck_combo,
)

FILTERS = ("all", "attention", "expired")


def kind_combo() -> QComboBox:
    """Kinds grouped as driver / truck / company, each group under a disabled heading."""
    combo = QComboBox()
    for group, kinds in (("driver", DRIVER_COMPLIANCE), ("truck", TRUCK_COMPLIANCE),
                         ("company", COMPANY_COMPLIANCE)):
        combo.addItem(f"— {t('comp.group.' + group)} —", None)
        combo.model().item(combo.count() - 1).setEnabled(False)
        for kind in kinds:
            combo.addItem("   " + t("comp.kind." + kind), kind)
    combo.setCurrentIndex(1)
    return combo


class ComplianceDialog(QDialog):
    def __init__(self, db: Database, item: ComplianceItem | None, parent: QWidget | None = None):
        super().__init__(parent)
        self.db = db
        self.item = item
        self.setMinimumWidth(520)
        self.kind = kind_combo()
        self.driver = driver_combo(db)
        self.truck = truck_combo(db)
        self.expiry = date_edit(QDate.currentDate().addYears(1))
        self.reference = QLineEdit()
        self.reference.setPlaceholderText(t("comp.reference_hint"))
        self.notes = QPlainTextEdit()
        self.notes.setFixedHeight(56)

        new = item is None or item.id is None
        page = self.page = DialogPage(self, "shield", t("comp.new") if new else t("comp.edit"), t("comp.subtitle"))
        form = self.form = page.section(t("comp.section"), "shield")
        form.addRow(t("comp.kind") + " *", self.kind)
        form.addRow(t("driver") + " *", self.driver)
        form.addRow(t("truck") + " *", self.truck)
        form.addRow(t("comp.expiry") + " *", self.expiry)
        form.addRow(t("comp.reference"), self.reference)
        form.addRow(t("load.notes"), self.notes)
        form.addRow("", hint_label(t("comp.hint", days=SOON_DAYS)))
        page.finish(buttons_box(self, self.save))

        if item:
            set_combo_data(self.kind, item.kind)
            set_combo_data(self.driver, item.driver_id)
            set_combo_data(self.truck, item.truck_id)
            self.expiry.setDate(QDate.fromString(item.expiry_date, "yyyy-MM-dd"))
            self.reference.setText(item.reference or "")
            self.notes.setPlainText(item.notes or "")
        self.kind.currentIndexChanged.connect(self._kind_changed)
        self._kind_changed()

    def _kind_changed(self) -> None:
        kind = self.kind.currentData()
        self.form.setRowVisible(self.driver, kind in DRIVER_COMPLIANCE)
        self.form.setRowVisible(self.truck, kind in TRUCK_COMPLIANCE)

    def save(self) -> None:
        kind = self.kind.currentData()
        item = ComplianceItem(
            id=self.item.id if self.item else None,
            kind=kind,
            expiry_date=self.expiry.date().toString("yyyy-MM-dd"),
            driver_id=self.driver.currentData() if kind in DRIVER_COMPLIANCE else None,
            truck_id=self.truck.currentData() if kind in TRUCK_COMPLIANCE else None,
            reference=self.reference.text(),
            notes=self.notes.toPlainText(),
        )
        try:
            if item.id is None:
                item.id = self.db.add_compliance(item)
            else:
                self.db.update_compliance(item)
        except ValidationError as exc:
            show_error(self, exc)
            return
        self.accept()


class ComplianceTab(CrudTab):
    empty_key = "compliance"
    empty_icon = "shield"

    def __init__(self, db: Database, parent: QWidget | None = None):
        super().__init__(db, parent)
        self.filter = QComboBox()
        for key in FILTERS:
            self.filter.addItem(t("comp.filter." + key), key)
        self.filter.currentIndexChanged.connect(self.refresh)
        self.add_filter(self.filter)
        self.summary = hint_label("")
        self.layout().addWidget(self.summary)
        self.refresh()

    def headers(self) -> list[str]:
        return [t("comp.kind"), t("comp.owner"), t("comp.expiry"), t("comp.days_left"), t("comp.status"),
                t("comp.reference")]

    def rows(self):
        entries = compliance_entries(self.db)
        attention = attention_needed(entries)
        expired = [e for e in entries if e.status == "expired"]
        self.summary.setText(t("comp.summary", total=len(entries), expired=len(expired),
                               soon=len(attention) - len(expired)))
        shown = {"all": entries, "attention": attention, "expired": expired}[self.filter.currentData()]
        rows = []
        for e in shown:
            if e.days_left < 0:
                left = t("comp.days_ago", n=-e.days_left)
            elif e.days_left == 0:
                left = t("comp.today")
            else:
                left = t("comp.in_days", n=e.days_left)
            owner = e.owner or t("comp.group.company")
            kind = t("comp.kind." + e.kind) + ("" if e.item else f" ({t('comp.from_driver')})")
            rows.append((e.row_id, [
                kind,
                owner,
                e.expiry_date,
                (left, e.days_left),
                status_badge("comp.status.", e.status),
                e.reference or "",
            ], STATUS_TONES.get(e.status, "neutral")))
        return rows

    def open_dialog(self, record_id):
        if record_id is not None and record_id < 0:
            # a CDL date typed on the driver form: edit it as a proper compliance record
            driver = self.db.get_driver(-record_id)
            item = ComplianceItem(kind="cdl", expiry_date=driver.license_expiry, driver_id=driver.id,
                                  reference=driver.license_number)
        else:
            item = self.db.get_compliance(record_id) if record_id else None
        return ComplianceDialog(self.db, item, self).exec() == QDialog.DialogCode.Accepted

    def delete(self, record_id: int) -> None:
        if record_id < 0:
            driver = self.db.get_driver(-record_id)
            driver.license_expiry = None
            self.db.update_driver(driver)
        else:
            self.db.delete_compliance(record_id)
