"""Loads tab: every load detail is optional. Load # always starts with '#'."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QWidget,
)

from ..database import LOAD_STATUSES, Database, Load, ValidationError
from ..i18n import t
from ..printout import money, number
from ..profit import ProfitModel
from ..weeks import week_label, week_start
from .base import CrudTab
from .board import BOARD_STATUSES, LoadBoard
from .detail_panel import LoadDetailPanel
from .dialog_kit import DialogPage, Section
from .documents import DocumentsPanel
from .ifta_tab import StateMilesEditor
from .import_dialog import ImportDialog
from .invoices import InvoiceDialog
from .theme import token
from .toast import show_toast
from .visuals import ProfitGauge, margin_tone
from .widgets import (
    button,
    NumberEdit,
    OptionalDateEdit,
    buttons_box,
    choice_combo,
    driver_combo,
    hint_label,
    set_combo_data,
    Badge,
    STATUS_TONES,
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
        self.profit = hint_label("")
        self.profit.setToolTip(t("load.profit_tip"))
        self.profit_model = ProfitModel(db)
        self.gauge = ProfitGauge(size=70)
        self.gauge.setToolTip(t("load.profit_tip"))

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
        profit_row = QHBoxLayout()
        profit_row.setContentsMargins(0, 0, 0, 0)
        profit_row.addWidget(self.gauge)
        profit_row.addWidget(self.profit, 1)
        self.profit.setWordWrap(True)
        form.addRow("", profit_row)

        form = page.section(t("load.section_details"), "file", 1, 1)
        form.addRow("", self.tonu)
        form.addRow(t("load.weight"), self.weight)
        form.addRow(t("load.commodity"), self.commodity)
        form.addRow(t("load.notes"), self.notes)

        self.state_miles = StateMilesEditor(unit)
        self.states_card = Section(t("ifta.section"), "map")
        self.states_card.body.addWidget(self.state_miles)
        self.states_card.body.addStretch(1)
        page.add_widget(self.states_card, 2, 0)

        self.documents = DocumentsPanel(db, load.id if load else None)
        self.documents_card = Section(t("doc.title"), "paperclip")
        self.documents_card.body.addWidget(self.documents)
        page.add_widget(self.documents_card, 2, 1)
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
            self.state_miles.set_states(db.load_states(load.id))

        self.truck.currentIndexChanged.connect(self._truck_changed)
        for combo in (self.truck, self.driver):
            combo.currentIndexChanged.connect(self._update_totals)
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
                         loaded_miles=self.loaded_miles.value(), dead_miles=self.dead_miles.value(),
                         truck_id=self.truck.currentData(), driver_id=self.driver.currentData(),
                         statement_week=self.week.value(), pickup_date=self.pickup_date.value(),
                         delivery_date=self.delivery_date.value())
        except ValidationError:
            self.totals.setText("")
            self.profit.setText("")
            self.gauge.set_margin(None)
            return
        est = self.profit_model.of(probe)
        self.gauge.set_margin(est.margin if probe.gross else None)
        cur = self.cur
        self.profit.setText(t("load.profit_line", profit=money(est.profit, cur), fee=money(est.dispatch_fee, cur),
                              driver=money(est.driver_pay, cur), fuel=money(est.fuel, cur)) if probe.gross else "")
        rpm = probe.rate_per_mile
        self.state_miles.set_expected(probe.total_miles)
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
            states = self.state_miles.states()
            if load.id is None:
                load.id = self.db.add_load(load)
            else:
                self.db.update_load(load)
            self.db.set_load_states(load.id, states)
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
        self.import_btn = self.add_tool(t("import.button"), "upload", self.import_loads)
        self.invoice_btn = self.add_tool(t("inv.for_load"), "receipt", self.invoice_selected)
        empty_import = button(t("import.from_excel"), None, "upload")
        empty_import.clicked.connect(self.import_loads)
        self.empty.add_button(empty_import)
        self.truck_filter = self.add_truck_filter()
        self.driver_filter = self.add_driver_filter()
        self.status_filter = choice_combo(LOAD_STATUSES, "status.", include_all=True)
        self.status_filter.currentIndexChanged.connect(self.refresh)
        self.add_filter(self.status_filter, t("load.status"))
        self.search = self.add_search()
        self.totals = hint_label("")
        self.totals.setToolTip(t("load.profit_tip"))
        self.layout().addWidget(self.totals)
        profit_column = self.headers().index(t("load.profit"))
        for column in (profit_column, profit_column + 1):
            self.table.horizontalHeaderItem(column).setToolTip(t("load.profit_tip"))

        # list / board switch at the right end of the toolbar
        self.list_btn = QPushButton(t("view.list"))
        self.board_btn = QPushButton(t("view.board"))
        for btn, side in ((self.list_btn, "first"), (self.board_btn, "last")):
            btn.setCheckable(True)
            btn.setProperty("segment", side)
            btn.setProperty("noLift", True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.toolbar.addWidget(btn)
        self.list_btn.clicked.connect(lambda: self.set_view("list"))
        self.board_btn.clicked.connect(lambda: self.set_view("board"))

        self.board = LoadBoard()
        self.board.moved.connect(self.move_load)
        self.board.card_clicked.connect(self.show_details)
        self.board.card_opened.connect(self._open)
        self.body.addWidget(self.board)
        # the details panel slides in next to the list or board
        self.panel = LoadDetailPanel(db)
        self.panel.edit_requested.connect(self._open)
        self.panel.invoice_requested.connect(self.invoice_selected)
        layout = self.layout()
        index = layout.indexOf(self.body)
        layout.removeWidget(self.body)
        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        row.addWidget(self.body, 1)
        row.addWidget(self.panel)
        layout.insertWidget(index, holder, 1)
        self.table.clicked.connect(lambda index: self.show_details(self.table.item(index.row(), 0).data(
            Qt.ItemDataRole.UserRole)))
        close = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        close.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        close.activated.connect(self.panel.close_panel)
        self.view = db.get_settings().get("loads_view", "list")
        self._apply_view_buttons()
        self.refresh()

    # ------------------------------------------------------------ list / board
    @property
    def board_mode(self) -> bool:
        return self.view == "board"

    def _apply_view_buttons(self) -> None:
        self.list_btn.setChecked(not self.board_mode)
        self.board_btn.setChecked(self.board_mode)
        self.status_filter.setEnabled(not self.board_mode)  # the board shows every status as a column
        self.edit_btn.setVisible(not self.board_mode)
        self.delete_btn.setVisible(not self.board_mode)

    def set_view(self, view: str) -> None:
        self.view = view
        self.db.set_setting("loads_view", view)
        self._apply_view_buttons()
        self.refresh()

    def refresh(self) -> None:
        super().refresh()
        if self.board_mode:
            self._fill_board()
            self.body.setCurrentWidget(self.board)
        if self.panel.is_open:
            self.panel.show_load(self.panel.load_id)
            self.board.select(self.panel.load_id)

    def _fill_board(self) -> None:
        cur = self.db.get_settings()["currency"]
        trucks = {tr.id: tr.label for tr in self.db.list_trucks()}
        drivers = {d.id: d.name for d in self.db.list_drivers()}
        cards: dict[str, list[dict]] = {}
        sums: dict[str, float] = {}
        for load in self._loads:
            if load.status not in BOARD_STATUSES:
                continue
            est = self._profits[load.id]
            who = " · ".join(p for p in (trucks.get(load.truck_id), drivers.get(load.driver_id)) if p)
            cards.setdefault(load.status, []).append({
                "id": load.id, "number": load.load_number or "—",
                "route": f"{load.pickup_location or '?'} → {load.delivery_location or '?'}",
                "who": who or t("none"), "gross": money(load.gross, cur),
                "profit": t("board.profit", amount=money(est.profit, cur)) if est.gross else "",
                "profit_tone": margin_tone(est.margin), "date": load.report_date or "",
                "tone": STATUS_TONES.get(load.status, "neutral"),
            })
            sums[load.status] = sums.get(load.status, 0.0) + load.gross
        self.board.set_cards(cards, {s: money(v, cur) for s, v in sums.items()})

    def move_load(self, load_id: int, status: str) -> None:
        """A card was dropped on another column."""
        load = self.db.get_load(load_id)
        if load is None or load.status == status:
            return
        load.status = status
        try:
            self.db.update_load(load)
        except ValidationError as exc:
            show_error(self, exc)
            return
        self.refresh()
        show_toast(t("board.moved", number=load.load_number or "—", status=t("status." + status)))

    def show_details(self, load_id: int | None) -> None:
        if load_id is not None:
            self.panel.show_load(load_id)

    def headers(self) -> list[str]:
        unit = self.db.get_settings()["distance_unit"]
        return [
            t("load.load_number"), t("stmt.week"), t("truck"), t("driver"), t("load.broker"),
            t("load.pickup_location"), t("load.pickup_date"), t("load.delivery_location"),
            t("load.delivery_date"), t("load.loaded_miles"), t("load.dead_miles"), t("load.total_miles"),
            t("load.rate"), t("load.gross"), t("load.rate_per_mile", unit=unit), t("load.profit"),
            t("load.profit_per_mile", unit=unit), t("load.tonu"), t("load.status"),
            t("doc.column"),
        ]

    def invoice_selected(self, load_id: int | None = None) -> bool:
        """Open the invoice of the selected load, or start a new one filled from the load."""
        if not load_id:
            load_id = self.panel.load_id if self.board_mode and self.panel.is_open else self.selected_or_warn()
        if load_id is None:
            return False
        existing = self.db.invoice_for_load(load_id)
        dialog = InvoiceDialog(self.db, existing, self, None if existing else load_id)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        self.refresh()
        show_toast(t("toast.saved"))
        return True

    def import_loads(self) -> bool:
        """Open the Excel/CSV import dialog; returns True when loads were imported."""
        dialog = ImportDialog(self.db, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()
            return True
        return False

    def rows(self):
        cur = self.db.get_settings()["currency"]
        trucks = {tr.id: tr.label for tr in self.db.list_trucks()}
        drivers = {d.id: d.name for d in self.db.list_drivers()}
        loads = self.db.list_loads(
            truck_id=self.truck_filter.currentData(),
            driver_id=self.driver_filter.currentData(),
            status=None if self.board_mode else self.status_filter.currentData(),
            search=self.search.text(),
        )
        counted = [load for load in loads if load.status != "cancelled" or load.is_tonu]
        model = ProfitModel(self.db)
        profits = {load.id: model.of(load) for load in loads}
        self._loads, self._profits = loads, profits
        good, bad = QColor(token("success_fg")), QColor(token("danger_fg"))
        self.totals.setText(
            f"{t('report.load_count')}: {len(loads)} · "
            f"{t('load.total_miles')}: {number(sum(load.total_miles for load in counted))} · "
            f"{t('load.gross')}: {money(sum(load.gross for load in counted), cur)} · "
            f"{t('load.profit')}: {money(sum(p.profit for p in profits.values()), cur)}"
        )
        doc_counts = self.db.document_counts()
        rows = []
        for load in loads:
            week = self.db.load_week(load)
            docs = doc_counts.get(load.id, 0)
            rpm = load.rate_per_mile
            est = profits[load.id]
            ppm = est.per_mile
            color = good if est.profit >= 0 else bad
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
                (money(est.profit, cur) if est.gross else "", est.profit, color),
                (money(ppm, cur) if ppm is not None and est.gross else "", ppm or 0.0, color),
                Badge(t("load.tonu"), "warning") if load.is_tonu else "",
                status_badge("status.", load.status),
                Badge(t("doc.count", n=docs), "info") if docs else "",
            ], STATUS_TONES.get(load.status, "neutral")))
        return rows

    def open_dialog(self, record_id):
        load = self.db.get_load(record_id) if record_id else None
        return LoadDialog(self.db, load, self).exec() == QDialog.DialogCode.Accepted

    def delete(self, record_id: int) -> None:
        self.db.delete_load(record_id)
