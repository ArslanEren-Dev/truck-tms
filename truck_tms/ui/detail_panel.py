"""Load details in a panel that slides in from the right of the Loads page."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, Signal
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ..database import Database
from ..i18n import t
from ..printout import money, number
from ..profit import ProfitModel
from .theme import icon, token
from .visuals import ProfitGauge, margin_tone
from .widgets import STATUS_TONES, button

PANEL_WIDTH = 340


def pill(text: str, tone: str) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet(f"background: {token(tone + '_bg')}; color: {token(tone + '_fg')}; border-radius: 9px;"
                        " padding: 2px 10px; font-weight: 700;")
    return label


class LoadDetailPanel(QFrame):
    edit_requested = Signal(int)
    invoice_requested = Signal(int)

    def __init__(self, db: Database, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("DetailPanel")
        self.db = db
        self.load_id: int | None = None
        self.setMaximumWidth(0)
        self.setMinimumWidth(0)
        self.anim = QPropertyAnimation(self, b"maximumWidth", self)
        self.anim.setDuration(240)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.body = QVBoxLayout()
        self.body.setSpacing(10)
        close = QPushButton()
        close.setIcon(icon("close", token("muted")))
        close.setFixedSize(30, 30)
        close.setProperty("noLift", True)
        close.setToolTip(t("btn.close"))
        close.clicked.connect(self.close_panel)
        self.close_btn = close
        self.edit_btn = button(t("btn.edit"), "primary", "edit")
        self.edit_btn.clicked.connect(lambda: self.load_id and self.edit_requested.emit(self.load_id))
        self.invoice_btn = button(t("inv.for_load"), None, "receipt")
        self.invoice_btn.clicked.connect(lambda: self.load_id and self.invoice_requested.emit(self.load_id))
        actions = QHBoxLayout()
        actions.addWidget(self.edit_btn)
        actions.addWidget(self.invoice_btn)
        actions.addStretch(1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.addLayout(self.body)
        layout.addStretch(1)
        layout.addLayout(actions)

    # ----------------------------------------------------------------- showing
    @property
    def is_open(self) -> bool:
        return self.load_id is not None

    def show_load(self, load_id: int) -> bool:
        """Fill the panel with a load and slide it in; False when the load no longer exists."""
        load = self.db.get_load(load_id)
        if load is None:
            self.close_panel()
            return False
        was_open = self.is_open
        self.load_id = load_id
        self._fill(load)
        if not was_open:
            self._slide(PANEL_WIDTH)
        return True

    def close_panel(self) -> None:
        if self.is_open:
            self.load_id = None
            self._slide(0)

    def _slide(self, width: int) -> None:
        self.anim.stop()
        self.anim.setStartValue(self.maximumWidth())
        self.anim.setEndValue(width)
        self.anim.start()

    def _clear(self) -> None:
        def wipe(layout) -> None:
            while layout.count():
                item = layout.takeAt(0)
                if item.widget() is not None and item.widget() is not self.close_btn:
                    item.widget().deleteLater()
                elif item.layout() is not None:
                    wipe(item.layout())
        wipe(self.body)

    def _fill(self, load) -> None:
        self._clear()
        settings = self.db.get_settings()
        cur, unit = settings["currency"], settings["distance_unit"]
        model = ProfitModel(self.db)
        est = model.of(load)
        truck = self.db.get_truck(load.truck_id)
        driver = model.driver_of(load)

        head = QHBoxLayout()
        title = QLabel(load.load_number or t("load.edit"))
        title.setProperty("role", "detailtitle")
        head.addWidget(title)
        head.addWidget(pill(t("status." + load.status), STATUS_TONES.get(load.status, "neutral")))
        head.addStretch(1)
        head.addWidget(self.close_btn)
        self.body.addLayout(head)
        route = QLabel(f"{load.pickup_location or '?'}  →  {load.delivery_location or '?'}")
        route.setProperty("role", "section")
        route.setWordWrap(True)
        self.body.addWidget(route)

        facts = QGridLayout()
        facts.setHorizontalSpacing(14)
        facts.setVerticalSpacing(4)
        rows = [
            (t("load.pickup_date"), load.pickup_date or "—"),
            (t("load.delivery_date"), load.delivery_date or "—"),
            (t("truck"), truck.label if truck else "—"),
            (t("driver"), driver.name if driver else "—"),
            (t("load.broker"), load.broker or "—"),
            (t("load.total_miles"), f"{number(load.total_miles)} {unit}"),
        ]
        for i, (key, value) in enumerate(rows):
            name = QLabel(key)
            name.setProperty("role", "kpisub")
            facts.addWidget(name, i, 0)
            facts.addWidget(QLabel(value), i, 1)
        self.body.addLayout(facts)

        money_card = QFrame()
        money_card.setObjectName("Section")
        grid = QGridLayout(money_card)
        grid.setContentsMargins(12, 10, 12, 10)
        gauge = ProfitGauge(size=110)
        gauge.set_margin(est.margin if est.gross else None)
        gauge.setToolTip(t("load.profit_tip"))
        grid.addWidget(gauge, 0, 0, 1, 2, Qt.AlignmentFlag.AlignHCenter)
        lines = [(t("load.gross"), est.gross), (t("stmt.dispatch_fee"), -est.dispatch_fee),
                 (t("stmt.driver_salary"), -est.driver_pay), (t("stmt.fuel"), -est.fuel)]
        for i, (key, value) in enumerate(lines):
            name = QLabel(key)
            name.setProperty("role", "kpisub")
            grid.addWidget(name, i + 1, 0)
            amount = QLabel(money(value, cur))
            amount.setAlignment(Qt.AlignmentFlag.AlignRight)
            grid.addWidget(amount, i + 1, 1)
        profit_name = QLabel(t("load.profit"))
        profit_name.setProperty("role", "section")
        profit = QLabel(money(est.profit, cur) if est.gross else "—")
        profit.setProperty("role", "section")
        profit.setAlignment(Qt.AlignmentFlag.AlignRight)
        profit.setStyleSheet(f"color: {token(margin_tone(est.margin) + '_fg')};" if est.gross else "")
        grid.addWidget(profit_name, len(lines) + 1, 0)
        grid.addWidget(profit, len(lines) + 1, 1)
        self.body.addWidget(money_card)

        invoice = self.db.invoice_for_load(load.id)
        if invoice:
            status = invoice.status(date.today())
            row = QHBoxLayout()
            row.addWidget(QLabel(f"{invoice.invoice_number} · {money(invoice.balance, cur)}"))
            row.addStretch(1)
            row.addWidget(pill(t("inv.status." + status), STATUS_TONES.get(status, "neutral")))
            self.body.addLayout(row)
        else:
            hint = QLabel(t("detail.no_invoice"))
            hint.setProperty("role", "kpisub")
            self.body.addWidget(hint)
        docs = len(self.db.list_documents(load.id))
        if docs:
            label = QLabel(t("doc.count", n=docs))
            label.setProperty("role", "kpisub")
            self.body.addWidget(label)
        if load.notes:
            notes = QLabel(load.notes)
            notes.setWordWrap(True)
            notes.setProperty("role", "kpisub")
            self.body.addWidget(notes)
        self.invoice_btn.setText(t("inv.edit") if invoice else t("inv.for_load"))
