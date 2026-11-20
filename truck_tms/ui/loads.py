"""Loads tab: every load detail is optional. Load # always starts with '#'."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QWidget,
)

from ..database import LOAD_STATUSES, Database, Load, ValidationError
from ..i18n import t
from ..report import money, number
from ..weeks import week_label, week_start
from .base import CrudTab
from .dialog_kit import DialogPage, Section
from .documents import DocumentsPanel
from .import_dialog import ImportDialog
from .widgets import (
    button,
    NumberEdit,
    OptionalDateEdit,
    buttons_box,
    choice_combo,
    driver_combo,
    fill_driver_combo,
    fill_truck_combo,
    hint_label,
    set_combo_data,
    Badge,
    search_box,
    show_error,
    status_badge,
    truck_combo,
)


class LoadDialog(QDialog):
    def __init__(self, db: Database, load: Load | None, parent: QWidget | None = None):
        super().__init__(parent)
        self.db = db
        self.load = load
        settings = db.get_settings()
        cur, unit = settings["currency"], settings["distance_unit"]
        self.cur, self.unit = cur, unit
        self.setMinimumWidth(900)

        self.truck = truck_combo(db, include_unassigned=True)
        self.driver = driver_combo(db, include_none=True)
        self.load_number = QLineEdit()
        self.load_number.setPlaceholderText("#123456")
        self.broker = QLineEdit()
        self.pickup_location = QLineEdit()
        self.pickup_date = OptionalDateEdit()
        self.delivery_location = QLineEdit()
        self.delivery_date = OptionalDateEdit()
        self.week = OptionalDateEdit()
        self.week.setToolTip(t("load.week_hint"))
        self.week_info = hint_label("")
        self.week_info.setWordWrap(False)  # wrapping labels make Qt mis-size the form rows
        self.status = choice_combo(LOAD_STATUSES, "status.")
        self.rate = NumberEdit()
        self.extra_pay = NumberEdit()
        self.extra_pay.setPlaceholderText(t("load.extra_pay_hint"))
        self.loaded_miles = NumberEdit()
        self.dead_miles = NumberEdit()
        self.tonu = QCheckBox(t("load.tonu_check"))
        self.weight = NumberEdit()
        self.commodity = QLineEdit()
        self.notes = QPlainTextEdit()
        self.notes.setFixedHeight(56)
        self.totals = QLabel()
        self.totals.setProperty("role", "metric")

        page = self.page = DialogPage(self, "layers", t("load.edit") if load else t("load.new"),
                                      t("load.optional_hint"))
        form = page.section(t("load.section_load"), "layers", 0, 0)
        form.addRow(t("load.load_number"), self.load_number)
        form.addRow(t("truck"), self.truck)
        form.addRow(t("driver"), self.driver)
        form.addRow(t("load.broker"), self.broker)
        form.addRow(t("load.status"), self.status)

        form = page.section(t("load.section_route"), "route", 1, 0)
        form.addRow(t("load.pickup_location"), self.pickup_location)
        form.addRow(t("load.pickup_date"), self.pickup_date)
        form.addRow(t("load.delivery_location"), self.delivery_location)
        form.addRow(t("load.delivery_date"), self.delivery_date)
        form.addRow(t("load.week"), self.week)
        form.addRow("", self.week_info)

        form = page.section(t("load.section_money"), "dollar", 0, 1)
        form.addRow(f"{t('load.rate')} ({cur})", self.rate)
        form.addRow(f"{t('load.extra_pay')} ({cur})", self.extra_pay)
        form.addRow(f"{t('load.loaded_miles')} ({unit})", self.loaded_miles)
        form.addRow(f"{t('load.dead_miles')} ({unit})", self.dead_miles)
        form.addRow("", self.totals)

        form = page.section(t("load.section_details"), "file", 1, 1)
        form.addRow("", self.tonu)
        form.addRow(t("load.weight"), self.weight)
        form.addRow(t("load.commodity"), self.commodity)
        form.addRow(t("load.notes"), self.notes)

        self.documents = DocumentsPanel(db, load.id if load else None)
        self.documents_card = Section(t("doc.title"), "paperclip")
        self.documents_card.body.addWidget(self.documents)
        page.add_widget(self.documents_card, 2, 0, 1, 2)
        page.finish(buttons_box(self, self.save))

        if load:
            set_combo_data(self.truck, load.truck_id)
            set_combo_data(self.driver, load.driver_id)
            self.load_number.setText(load.load_number or "")
            self.broker.setText(load.broker or "")
            self.pickup_location.setText(load.pickup_location or "")
            self.pickup_date.setValue(load.pickup_date)
            self.delivery_location.setText(load.delivery_location or "")
            self.delivery_date.setValue(load.delivery_date)
            self.week.setValue(load.statement_week)
            self.rate.setValue(load.rate)
            self.extra_pay.setValue(load.extra_pay)
            self.loaded_miles.setValue(load.loaded_miles)
            self.dead_miles.setValue(load.dead_miles)
            self.tonu.setChecked(load.is_tonu)
            self.weight.setValue(load.weight)
            self.commodity.setText(load.commodity or "")
            set_combo_data(self.status, load.status)
            self.notes.setPlainText(load.notes or "")

        self.truck.currentIndexChanged.connect(self._truck_changed)
        for w in (self.rate, self.extra_pay, self.loaded_miles, self.dead_miles):
            w.textChanged.connect(self._update_totals)
        for w in (self.pickup_date, self.delivery_date, self.week):
            w.changed.connect(self._update_week)
        for w in (self.load_number, self.pickup_location, self.delivery_location, self.rate, self.extra_pay):
            w.textChanged.connect(self._update_header)
        self._update_totals()
        self._update_week()
        self._update_header()

    def _update_header(self) -> None:
        """The header shows what is being edited: '#4410055 · Dallas, TX → Atlanta, GA · $2,550.00'."""
        parts = []
        number = self.load_number.text().strip().lstrip("#")
        if number:
            parts.append("#" + number)
        pickup, delivery = self.pickup_location.text().strip(), self.delivery_location.text().strip()
        if pickup or delivery:
            parts.append(f"{pickup or '?'} → {delivery or '?'}")
        try:
            gross = (self.rate.value() or 0) + (self.extra_pay.value() or 0)
        except ValidationError:
            gross = 0
        if gross:
            parts.append(money(gross, self.cur))
        self.page.header.set_subtitle(" · ".join(parts) if parts else t("load.optional_hint"))

    def _truck_changed(self) -> None:
        """Pre-select the truck's default driver when no driver is chosen yet."""
        truck = self.db.get_truck(self.truck.currentData())
        if truck and truck.driver_id and self.driver.currentData() is None:
            set_combo_data(self.driver, truck.driver_id)

    def _update_totals(self) -> None:
        try:
            probe = Load(rate=self.rate.value(), extra_pay=self.extra_pay.value(),
                         loaded_miles=self.loaded_miles.value(), dead_miles=self.dead_miles.value())
        except ValidationError:
            self.totals.setText("")
            return
        rpm = probe.rate_per_mile
        self.totals.setText(
            f"{t('load.total_miles')}: <b>{number(probe.total_miles)} {self.unit}</b> · "
            f"{t('load.gross')}: <b>{money(probe.gross, self.cur)}</b> · "
            f"{t('load.rate_per_mile', unit=self.unit)}: <b>{money(rpm, self.cur)}</b>"
        )

    def _update_week(self) -> None:
        manual = self.week.value()
        if manual:
            week = week_start(manual, self.db.week_start_dow).isoformat()
        else:
            week = self.db.load_week(Load(pickup_date=self.pickup_date.value(),
                                          delivery_date=self.delivery_date.value()))
        self.week_info.setText(f"→ {week_label(week)}" if week else t("load.week_hint"))

    def save(self) -> None:
        try:
            load = Load(
                id=self.load.id if self.load else None,
                truck_id=self.truck.currentData(),
                driver_id=self.driver.currentData(),
                load_number=self.load_number.text(),
                broker=self.broker.text(),
                pickup_location=self.pickup_location.text(),
                pickup_date=self.pickup_date.value(),
                delivery_location=self.delivery_location.text(),
                delivery_date=self.delivery_date.value(),
                statement_week=self.week.value(),
                rate=self.rate.value(),
                extra_pay=self.extra_pay.value(),
                loaded_miles=self.loaded_miles.value(),
                dead_miles=self.dead_miles.value(),
                is_tonu=self.tonu.isChecked(),
                weight=self.weight.value(),
                commodity=self.commodity.text(),
                status=self.status.currentData(),
                notes=self.notes.toPlainText(),
            )
            if load.id is None:
                load.id = self.db.add_load(load)
            else:
                self.db.update_load(load)
            self.documents.commit(load.id)  # files added before the load had an id
        except ValidationError as exc:
            show_error(self, exc)
            return
        self.saved_id = load.id
        self.accept()


class LoadsTab(CrudTab):
    empty_key = "loads"
    empty_icon = "layers"

    def __init__(self, db: Database, parent: QWidget | None = None):
        super().__init__(db, parent)
        self.import_btn = button(t("import.button"), None, "upload")
        self.import_btn.clicked.connect(self.import_loads)
        self.toolbar.insertWidget(3, self.import_btn)
        empty_import = button(t("import.from_excel"), None, "upload")
        empty_import.clicked.connect(self.import_loads)
        self.empty.add_button(empty_import)
        self.truck_filter = truck_combo(db, include_all=True)
        self.driver_filter = driver_combo(db, include_all=True)
        self.status_filter = choice_combo(LOAD_STATUSES, "status.", include_all=True)
        self.search = search_box()
        for label, w in ((t("truck"), self.truck_filter), (t("driver"), self.driver_filter),
                         (t("load.status"), self.status_filter), (None, self.search)):
            if label:
                self.add_filter(QLabel(label))
            self.add_filter(w)
        for combo in (self.truck_filter, self.driver_filter, self.status_filter):
            combo.currentIndexChanged.connect(self.refresh)
        self.search.textChanged.connect(self.refresh)
        self.totals = hint_label("")
        self.layout().addWidget(self.totals)
        self.refresh()

    def headers(self) -> list[str]:
        unit = self.db.get_settings()["distance_unit"]
        return [
            t("load.load_number"), t("stmt.week"), t("truck"), t("driver"), t("load.broker"),
            t("load.pickup_location"), t("load.pickup_date"), t("load.delivery_location"),
            t("load.delivery_date"), t("load.loaded_miles"), t("load.dead_miles"), t("load.total_miles"),
            t("load.rate"), t("load.gross"), t("load.rate_per_mile", unit=unit), t("load.tonu"), t("load.status"),
            t("doc.column"),
        ]

    def import_loads(self) -> bool:
        """Open the Excel/CSV import dialog; returns True when loads were imported."""
        dialog = ImportDialog(self.db, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()
            return True
        return False

    def refresh(self) -> None:
        fill_truck_combo(self.truck_filter, self.db, include_all=True)
        fill_driver_combo(self.driver_filter, self.db, include_all=True)
        super().refresh()

    def rows(self):
        cur = self.db.get_settings()["currency"]
        trucks = {tr.id: tr.label for tr in self.db.list_trucks()}
        drivers = {d.id: d.name for d in self.db.list_drivers()}
        loads = self.db.list_loads(
            truck_id=self.truck_filter.currentData(),
            driver_id=self.driver_filter.currentData(),
            status=self.status_filter.currentData(),
            search=self.search.text(),
        )
        counted = [l for l in loads if l.status != "cancelled" or l.is_tonu]
        self.totals.setText(
            f"{t('report.load_count')}: {len(loads)} · "
            f"{t('load.total_miles')}: {number(sum(l.total_miles for l in counted))} · "
            f"{t('load.gross')}: {money(sum(l.gross for l in counted), cur)}"
        )
        doc_counts = self.db.document_counts()
        rows = []
        for load in loads:
            week = self.db.load_week(load)
            docs = doc_counts.get(load.id, 0)
            rpm = load.rate_per_mile
            rows.append((load.id, [
                load.load_number,
                (week_label(week) + (" *" if load.statement_week else ""), week or ""),
                trucks.get(load.truck_id, t("none")),
                drivers.get(load.driver_id, ""),
                load.broker,
                load.pickup_location,
                load.pickup_date,
                load.delivery_location,
                load.delivery_date,
                (number(load.loaded_miles) if load.loaded_miles is not None else "", load.loaded_miles or 0.0),
                (number(load.dead_miles) if load.dead_miles is not None else "", load.dead_miles or 0.0),
                (number(load.total_miles), load.total_miles),
                (money(load.rate, cur) if load.rate is not None else "", load.rate or 0.0),
                (money(load.gross, cur), load.gross),
                (money(rpm, cur) if rpm is not None else "", rpm or 0.0),
                Badge(t("load.tonu"), "warning") if load.is_tonu else "",
                status_badge("status.", load.status),
                Badge(t("doc.count", n=docs), "info") if docs else "",
            ]))
        return rows

    def open_dialog(self, record_id):
        load = self.db.get_load(record_id) if record_id else None
        return LoadDialog(self.db, load, self).exec() == QDialog.DialogCode.Accepted

    def delete(self, record_id: int) -> None:
        self.db.delete_load(record_id)
