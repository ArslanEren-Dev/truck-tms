"""Overview page: key numbers for this statement week, recent loads and reminders."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from html import escape
from datetime import date, datetime, timedelta

from PySide6.QtCore import QDate, QLocale, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..compliance import attention_needed, compliance_entries
from ..database import Database, Load
from ..i18n import t
from ..invoicing import compute_receivables
from ..printout import money, number
from ..statement import driver_balances
from ..today import compute_today, onboarding_steps
from ..weeks import week_label, week_start
from .charts import BarChart, DonutChart, LineChart, RankChart, compact
from .theme import count_up, icon, token
from .visuals import HeroBand, Sparkline, stagger_in
from .widgets import STATUS_TONES, button, fill_table, make_table, status_badge

IN_PROGRESS = ("dispatched", "in_transit")
LOAD_FIELDS = {f.name for f in fields(Load)}


@dataclass
class Overview:
    """The numbers shown on the overview page (GUI-free, easy to test)."""

    week_start: str
    week_gross: float
    week_miles: float
    week_loads: int
    in_progress: int
    active_trucks: int
    total_trucks: int
    maintenance_trucks: int
    unpaid_total: float
    unpaid_drivers: int
    service_due: int
    reminders: list[tuple[str, str, str]]  # (tone, title, detail)
    receivable_total: float = 0.0
    overdue_invoices: int = 0
    compliance_alerts: int = 0
    compliance_expired: int = 0


def compute_overview(db: Database, today: date | None = None) -> Overview:
    today = today or date.today()
    settings = db.get_settings()
    start = week_start(today, db.week_start_dow).isoformat()
    week_loads = db.list_loads(week=start, include_cancelled=False)
    trucks = db.list_trucks()
    labels = {tr.id: tr for tr in trucks}
    balances = {k: v for k, v in driver_balances(db).items() if v > 0.005}

    reminders: list[tuple[str, str, str]] = []
    due_trucks = set()
    for m in db.list_maintenance():
        truck = labels.get(m.truck_id)
        if db.maintenance_due(m, truck, today):
            due_trucks.add(m.truck_id)
            detail = m.next_due_date or (f"{m.next_due_odometer:,}" if m.next_due_odometer else "")
            reminders.append(("danger", t("dash.service_due", truck=truck.label if truck else "?",
                                          service=t("service." + m.service_type)), detail))
    alerts = attention_needed(compliance_entries(db, today))
    for e in alerts:
        what = t("comp.kind." + e.kind) + (f" · {e.owner}" if e.owner else "")
        key = "dash.comp_expired" if e.status == "expired" else "dash.comp_soon"
        reminders.append(("danger" if e.status == "expired" else "warning", t(key, what=what), e.expiry_date))
    invoices = db.list_invoices()
    receivables = compute_receivables(db, today, invoices)
    for inv in sorted(invoices, key=lambda i: -i.days_overdue(today)):
        late = inv.days_overdue(today)
        if late:
            reminders.append(("danger", t("dash.invoice_late", number=inv.invoice_number, n=late),
                              money(inv.balance, settings["currency"])))
    order = {"danger": 0, "warning": 1}
    reminders.sort(key=lambda r: order.get(r[0], 2))
    return Overview(
        week_start=start,
        week_gross=sum(load.gross for load in week_loads),
        week_miles=sum(load.total_miles for load in week_loads),
        week_loads=len(week_loads),
        in_progress=db.conn.execute(
            f"SELECT COUNT(*) FROM loads WHERE status IN ({','.join('?' * len(IN_PROGRESS))})", IN_PROGRESS
        ).fetchone()[0],
        active_trucks=sum(1 for tr in trucks if tr.status == "active"),
        total_trucks=len(trucks),
        maintenance_trucks=sum(1 for tr in trucks if tr.status == "maintenance"),
        unpaid_total=round(sum(balances.values()), 2),
        unpaid_drivers=len(balances),
        service_due=len(due_trucks),
        reminders=reminders,
        receivable_total=receivables.open_total,
        overdue_invoices=receivables.overdue_count,
        compliance_alerts=len(alerts),
        compliance_expired=sum(1 for e in alerts if e.status == "expired"),
    )


@dataclass
class Trends:
    """Numbers behind the overview charts (GUI-free)."""

    weeks: list[str]                 # week start dates, oldest first
    gross: list[float]               # gross per week
    miles: list[float]               # total miles per week
    rate_per_mile: list[float]       # gross / total miles per week (0 when there were no miles)
    top_brokers: list[tuple[str, float]]  # (broker, gross) of the last 90 days, biggest first
    expenses: list[tuple[str, float]] = field(default_factory=list)  # (category, amount), last 90 days


def compute_trends(db: Database, weeks: int = 8, today: date | None = None, broker_days: int = 90,
                   top: int = 5) -> Trends:
    today = today or date.today()
    dow = db.week_start_dow
    current = week_start(today, dow)
    starts = [(current - timedelta(days=7 * i)).isoformat() for i in range(weeks - 1, -1, -1)]
    gross = dict.fromkeys(starts, 0.0)
    miles = dict.fromkeys(starts, 0.0)
    brokers: dict[str, float] = {}
    since = (today - timedelta(days=broker_days)).isoformat()
    # only loads that can land in the charted weeks (a manual statement week may differ from the
    # date, so loads with one are always read)
    first = (date.fromisoformat(starts[0]) - timedelta(days=7)).isoformat()
    oldest = min(first, since)
    rows = db.conn.execute(
        "SELECT * FROM loads WHERE (status != 'cancelled' OR is_tonu = 1)"
        " AND (statement_week IS NOT NULL OR COALESCE(delivery_date, pickup_date) >= ?)", (oldest,))
    for load in (Load(**{k: r[k] for k in LOAD_FIELDS.intersection(r.keys())}) for r in rows):
        week = load.statement_week or (week_start(load.report_date, dow).isoformat() if load.report_date else None)
        if week in gross:
            gross[week] += load.gross
            miles[week] += load.total_miles
        if load.broker and (load.report_date or "") >= since:
            brokers[load.broker] = brokers.get(load.broker, 0.0) + load.gross
    spent: dict[str, float] = {}
    for e in db.list_expenses(start=since, end=today.isoformat()):
        spent[e.category] = spent.get(e.category, 0.0) + e.amount
    return Trends(
        weeks=starts,
        gross=[round(gross[s], 2) for s in starts],
        miles=[round(miles[s], 1) for s in starts],
        rate_per_mile=[round(gross[s] / miles[s], 2) if miles[s] else 0.0 for s in starts],
        top_brokers=sorted(brokers.items(), key=lambda kv: -kv[1])[:top],
        expenses=sorted(((k, round(v, 2)) for k, v in spent.items() if v > 0), key=lambda kv: -kv[1]),
    )


def card() -> QFrame:
    frame = QFrame()
    frame.setObjectName("Card")
    frame.setProperty("lift", True)
    return frame


def delta_text(values: list[float]) -> tuple[str, str] | None:
    """('▲ 12%', 'success') comparing the last value with the one before; None without a base."""
    if len(values) < 2 or not values[-2]:
        return None
    change = (values[-1] - values[-2]) / abs(values[-2]) * 100
    if abs(change) < 0.5:
        return "● 0%", "neutral"
    return (f"▲ {change:.0f}%", "success") if change > 0 else (f"▼ {abs(change):.0f}%", "danger")


def greeting(now: datetime | None = None) -> str:
    hour = (now or datetime.now()).hour
    return t("dash.morning" if 5 <= hour < 12 else "dash.afternoon" if hour < 18 else "dash.evening")


class StatCard(QFrame):
    """A key number with an icon; the number counts up when it changes, with an optional trend line."""

    def __init__(self, title: str, icon_name: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setProperty("lift", True)
        self.chip = QLabel()
        self.chip.setProperty("role", "chip")
        self.chip.setFixedSize(40, 40)
        self.chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_name = icon_name
        self.title = QLabel(title.upper())
        self.title.setProperty("role", "cardtitle")
        self.value = QLabel("0")
        self.value.setProperty("role", "kpi")
        self.sub = QLabel()
        self.sub.setProperty("role", "kpisub")
        self.delta = QLabel()
        self.delta.setProperty("role", "delta")
        self.delta.hide()
        self.spark = Sparkline()
        self.spark.hide()
        value_row = QHBoxLayout()
        value_row.setSpacing(8)
        value_row.addWidget(self.value)
        value_row.addWidget(self.delta, 0, Qt.AlignmentFlag.AlignVCenter)
        value_row.addStretch(1)
        text = QVBoxLayout()
        text.setSpacing(0)
        text.addWidget(self.title)
        text.addLayout(value_row)
        text.addWidget(self.sub)
        text.addWidget(self.spark)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(14)
        layout.addWidget(self.chip, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(text, 1)
        self.set_tone("info")

    def set_tone(self, tone: str) -> None:
        self.chip.setProperty("tone", tone)
        color = {"danger": token("danger_fg"), "success": token("success_fg")}.get(tone, token("accent"))
        self.chip.setPixmap(icon(self.icon_name, color).pixmap(22, 22))
        self.chip.style().unpolish(self.chip)
        self.chip.style().polish(self.chip)

    def set_value(self, value: float, fmt, sub: str = "", animate: bool = True) -> None:
        self.sub.setText(sub)
        if animate:
            count_up(self.value, value, fmt)
        else:
            self.value.setText(fmt(value))
            self.value._count_value = float(value)

    def set_trend(self, values: list[float], animate: bool = True) -> None:
        """Weekly values, oldest first: a sparkline plus the change against the week before."""
        self.spark.set_values(values, animate)
        delta = delta_text(values)
        self.delta.setVisible(delta is not None)
        if delta:
            self.delta.setText(delta[0])
            self.delta.setProperty("tone", delta[1])
            self.delta.setToolTip(t("dash.vs_last_week"))
            self.delta.style().unpolish(self.delta)
            self.delta.style().polish(self.delta)


class OverviewTab(QWidget):
    #: "new_load" / "new_truck" / "new_statement" / "new_driver"
    action_requested = Signal(str)

    def __init__(self, db: Database, parent: QWidget | None = None):
        super().__init__(parent)
        self.db = db
        self.overview: Overview | None = None

        # hero band: greeting, date and the quick actions on a gradient
        self.hero = HeroBand()
        self.hello = QLabel()
        self.hello.setProperty("role", "herotitle")
        self.today_label = QLabel()
        self.today_label.setProperty("role", "herosub")
        actions = QHBoxLayout()
        actions.setSpacing(8)
        for key, text_key, icon_name, variant in (
            ("new_load", "dash.new_load", "layers", "primary"),
            ("new_truck", "dash.new_truck", "truck", None),
            ("new_driver", "dash.new_driver", "user", None),
            ("new_statement", "dash.new_statement", "file", None),
            ("new_invoice", "dash.new_invoice", "receipt", None),
        ):
            btn = button(t(text_key), variant, icon_name)
            if variant == "primary":  # white button on the gradient: the icon takes the accent colour
                btn.setIcon(icon(icon_name, token("accent")))
            btn.clicked.connect(lambda _=False, k=key: self.action_requested.emit(k))
            actions.addWidget(btn)
        actions.addStretch(1)
        self.week = QLabel()
        self.week.setProperty("role", "herosub")
        actions.addWidget(self.week)
        hero_layout = QVBoxLayout(self.hero)
        hero_layout.setContentsMargins(24, 20, 24, 18)
        hero_layout.setSpacing(4)
        hero_layout.addWidget(self.hello)
        hero_layout.addWidget(self.today_label)
        hero_layout.addSpacing(10)
        hero_layout.addLayout(actions)

        # getting started (only while the file is still empty)
        self.onboarding = card()
        self.onboarding.setProperty("lift", False)
        self.steps_box = QVBoxLayout(self.onboarding)
        self.steps_box.setContentsMargins(18, 14, 18, 14)
        self.steps_box.setSpacing(8)

        # today: pickups, deliveries, late loads, loads to invoice
        self.today_card = card()
        self.today_card.setProperty("lift", False)
        self.today_box = QVBoxLayout(self.today_card)
        self.today_box.setContentsMargins(16, 14, 16, 14)
        self.today_box.setSpacing(6)

        # key numbers
        self.cards = {
            "gross": StatCard(t("kpi.week_gross"), "dollar"),
            "miles": StatCard(t("kpi.week_miles"), "route"),
            "moving": StatCard(t("kpi.in_progress"), "truck"),
            "trucks": StatCard(t("kpi.active_trucks"), "check"),
            "unpaid": StatCard(t("kpi.unpaid"), "wallet"),
            "receivable": StatCard(t("kpi.receivable"), "receipt"),
            "service": StatCard(t("kpi.service_due"), "wrench"),
            "compliance": StatCard(t("kpi.compliance"), "shield"),
        }
        grid = QGridLayout()
        grid.setSpacing(12)
        for i, key in enumerate(self.cards):
            grid.addWidget(self.cards[key], i // 4, i % 4)

        # charts (drawn by the app itself, see charts.py), two by two
        self.gross_chart = BarChart()
        self.rpm_chart = LineChart()
        self.broker_chart = RankChart()
        self.expense_chart = DonutChart()
        charts = QGridLayout()
        charts.setSpacing(12)
        for i, (title_key, chart) in enumerate((
            ("chart.weekly_gross", self.gross_chart), ("chart.rate_per_mile", self.rpm_chart),
            ("chart.top_brokers", self.broker_chart), ("chart.expenses", self.expense_chart),
        )):
            box = card()
            box.setProperty("lift", False)
            inner_layout = QVBoxLayout(box)
            inner_layout.setContentsMargins(16, 14, 16, 10)
            heading = QLabel(t(title_key))
            heading.setProperty("role", "section")
            inner_layout.addWidget(heading)
            inner_layout.addWidget(chart, 1)
            charts.addWidget(box, i // 2, i % 2)
            chart.setMinimumHeight(210)

        # recent loads + reminders
        self.recent = make_table([t("load.load_number"), t("report.route"), t("truck"), t("load.gross"),
                                  t("load.status")])
        self.recent.setSortingEnabled(False)
        self.recent.setMinimumHeight(300)  # 7 rows without a scroll bar
        head = self.recent.horizontalHeader()
        head.setStretchLastSection(False)
        for column in range(self.recent.columnCount()):
            head.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        head.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)  # the route takes the free space
        self.recent.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        recent_card = card()
        recent_card.setProperty("lift", False)
        rc = QVBoxLayout(recent_card)
        rc.setContentsMargins(16, 14, 16, 14)
        title = QLabel(t("dash.recent_loads"))
        title.setProperty("role", "section")
        rc.addWidget(title)
        rc.addWidget(self.recent)

        reminders_card = card()
        reminders_card.setProperty("lift", False)
        self.reminder_box = QVBoxLayout(reminders_card)
        self.reminder_box.setContentsMargins(16, 14, 16, 14)
        self.reminder_box.setSpacing(8)

        middle = QHBoxLayout()
        middle.setSpacing(12)
        middle.addWidget(self.today_card, 3)
        middle.addWidget(reminders_card, 2)

        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(8, 4, 8, 8)
        layout.setSpacing(14)
        layout.addWidget(self.hero)
        layout.addWidget(self.onboarding)
        layout.addLayout(grid)
        layout.addLayout(middle)
        layout.addLayout(charts)
        layout.addWidget(recent_card, 1)
        self.chart_cards = [charts.itemAt(i).widget() for i in range(charts.count())]
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(inner)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        self.refresh(animate=False)

    def refresh(self, animate: bool = True) -> None:
        s = self.db.get_settings()
        cur, unit = s["currency"], s["distance_unit"]
        o = self.overview = compute_overview(self.db)
        self.week.setText(t("dash.week", week=week_label(o.week_start)))
        company = s.get("company_name", "").strip()
        self.hello.setText(greeting() + (f", {company}" if company else ""))
        self.today_label.setText(QLocale().toString(QDate.currentDate(), QLocale.FormatType.LongFormat))
        c = self.cards
        c["gross"].set_value(o.week_gross, lambda v: money(v, cur), t("dash.loads_count", n=o.week_loads), animate)
        c["miles"].set_value(o.week_miles, lambda v: f"{number(v)} {unit}", week_label(o.week_start), animate)
        c["moving"].set_value(o.in_progress, lambda v: number(v), t("dash.in_progress_sub"), animate)
        total = o.total_trucks
        c["trucks"].set_value(o.active_trucks, lambda v: f"{number(v)} / {total}",
                              t("dash.trucks_sub", n=o.maintenance_trucks), animate)
        c["unpaid"].set_value(o.unpaid_total, lambda v: money(v, cur), t("dash.unpaid_sub", n=o.unpaid_drivers),
                              animate)
        c["unpaid"].set_tone("danger" if o.unpaid_total > 0 else "success")
        c["service"].set_value(o.service_due, lambda v: number(v), t("dash.service_sub"), animate)
        c["service"].set_tone("danger" if o.service_due else "success")
        c["receivable"].set_value(o.receivable_total, lambda v: money(v, cur),
                                  t("dash.receivable_sub", n=o.overdue_invoices), animate)
        c["receivable"].set_tone("danger" if o.overdue_invoices else "info")
        c["compliance"].set_value(o.compliance_alerts, lambda v: number(v),
                                  t("dash.compliance_sub", n=o.compliance_expired), animate)
        c["compliance"].set_tone("danger" if o.compliance_expired else ("info" if o.compliance_alerts else "success"))

        trends = self.trends = compute_trends(self.db)
        week_labels = [w[5:] for w in trends.weeks]  # MM-DD
        self.gross_chart.fmt = lambda v: money(v, cur)
        self.gross_chart.axis_fmt = lambda v: cur + compact(v)
        self.gross_chart.set_data(week_labels, trends.gross, animate)
        c["gross"].set_trend(trends.gross, animate)
        c["miles"].set_trend(trends.miles, animate)
        self.rpm_chart.fmt = lambda v: f"{money(v, cur)}/{unit}"
        self.rpm_chart.axis_fmt = lambda v: f"{cur}{v:.2f}"
        self.rpm_chart.set_data(week_labels, trends.rate_per_mile, animate)
        self.broker_chart.fmt = lambda v: money(v, cur)
        self.broker_chart.set_data([b for b, _ in trends.top_brokers], [g for _, g in trends.top_brokers], animate)
        self.expense_chart.fmt = lambda v: money(v, cur)
        self.expense_chart.center_title = t("chart.expenses_total")
        self.expense_chart.set_data([t("category." + k) for k, _ in trends.expenses], [v for _, v in trends.expenses],
                                    animate)

        trucks = {tr.id: tr.label for tr in self.db.list_trucks()}
        loads = self.db.list_loads(limit=7)
        fill_table(self.recent, [
            (load.id, [
                load.load_number or "—",
                f"{load.pickup_location or '?'} → {load.delivery_location or '?'}",
                trucks.get(load.truck_id, "—"),
                (money(load.gross, cur), load.gross),
                status_badge("status.", load.status),
            ], STATUS_TONES.get(load.status, "neutral"))
            for load in loads
        ])
        self._fill_reminders(o)
        self._fill_today()
        self._fill_onboarding()
        if animate:
            stagger_in(list(self.cards.values()) + self.chart_cards)

    def _clear(self, box: QVBoxLayout) -> None:
        while box.count():
            item = box.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._clear(item.layout())

    def _fill_today(self) -> None:
        self._clear(self.today_box)
        title = QLabel(t("today.title"))
        title.setProperty("role", "section")
        self.today_box.addWidget(title)
        items = compute_today(self.db)
        if not items:
            calm = QLabel(t("today.nothing"))
            calm.setProperty("role", "kpisub")
            calm.setWordWrap(True)
            self.today_box.addWidget(calm)
        icons = {"pickup": "upload", "delivery": "check", "late": "alert", "invoice": "receipt"}
        for item in items:
            row = QHBoxLayout()
            row.setSpacing(10)
            mark = QLabel()
            mark.setPixmap(icon(icons[item.kind], token(f"{item.tone}_fg")).pixmap(18, 18))
            text = QLabel(f"<b>{escape(item.title)}</b><br>"
                          f"<span style='color:{token('muted')}'>{escape(item.detail)}</span>")
            go = QPushButton(t("today.invoice_btn") if item.kind == "invoice" else t("today.open"))
            go.setProperty("noLift", True)
            go.setCursor(Qt.CursorShape.PointingHandCursor)
            action = f"{'invoice' if item.kind == 'invoice' else 'load'}:{item.load_id}"
            go.clicked.connect(lambda _=False, a=action: self.action_requested.emit(a))
            row.addWidget(mark, 0, Qt.AlignmentFlag.AlignTop)
            row.addWidget(text, 1)
            row.addWidget(go, 0, Qt.AlignmentFlag.AlignVCenter)
            holder = QWidget()
            holder.setLayout(row)
            self.today_box.addWidget(holder)
        self.today_box.addStretch(1)

    def _fill_onboarding(self) -> None:
        steps = onboarding_steps(self.db)
        self.onboarding.setVisible(not all(done for _, done in steps))
        if not self.onboarding.isVisibleTo(self):
            return
        self._clear(self.steps_box)
        title = QLabel(t("start.title"))
        title.setProperty("role", "section")
        hint = QLabel(t("start.hint"))
        hint.setProperty("role", "kpisub")
        self.steps_box.addWidget(title)
        self.steps_box.addWidget(hint)
        actions = {"truck": "new_truck", "driver": "new_driver", "load": "new_load"}
        for n, (step, done) in enumerate(steps, 1):
            row = QHBoxLayout()
            badge = QLabel("✓" if done else str(n))
            badge.setProperty("role", "step")
            badge.setProperty("done", "true" if done else "false")
            badge.setFixedSize(26, 26)
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label = QLabel(t(f"start.{step}"))
            if done:
                label.setProperty("role", "kpisub")
            row.addWidget(badge)
            row.addWidget(label, 1)
            if not done:
                go = button(t(f"start.{step}_btn"), "primary" if n == next(
                    i for i, (_, d) in enumerate(steps, 1) if not d) else None, "plus")
                go.clicked.connect(lambda _=False, a=actions[step]: self.action_requested.emit(a))
                row.addWidget(go)
            holder = QWidget()
            holder.setLayout(row)
            self.steps_box.addWidget(holder)

    def _fill_reminders(self, o: Overview) -> None:
        while self.reminder_box.count():
            item = self.reminder_box.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        title = QLabel(t("dash.reminders"))
        title.setProperty("role", "section")
        self.reminder_box.addWidget(title)
        if not o.reminders:
            ok = QLabel(t("dash.no_reminders"))
            ok.setProperty("role", "kpisub")
            ok.setWordWrap(True)
            self.reminder_box.addWidget(ok)
        for tone, text, detail in o.reminders[:6]:
            row = QHBoxLayout()
            mark = QLabel()
            mark.setPixmap(icon("alert", token(f"{tone}_fg")).pixmap(18, 18))
            label = QLabel(text)
            label.setWordWrap(True)
            when = QLabel(detail)
            when.setProperty("role", "kpisub")
            row.addWidget(mark, 0, Qt.AlignmentFlag.AlignTop)
            row.addWidget(label, 1)
            row.addWidget(when)
            holder = QWidget()
            holder.setLayout(row)
            self.reminder_box.addWidget(holder)
        self.reminder_box.addStretch(1)
