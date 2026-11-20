"""Overview page: key numbers for this statement week, recent loads and reminders."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..database import Database
from ..i18n import t
from ..report import money, number
from ..statement import driver_balances
from ..weeks import week_label, week_start
from .charts import BarChart, LineChart, RankChart
from .theme import count_up, icon, token
from .widgets import button, fill_table, make_table, status_badge

IN_PROGRESS = ("dispatched", "in_transit")


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


def compute_overview(db: Database, today: date | None = None) -> Overview:
    today = today or date.today()
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
    soon = (today + timedelta(days=30)).isoformat()
    for d in db.list_drivers(active_only=True):
        if d.license_expiry and d.license_expiry <= soon:
            expired = d.license_expiry < today.isoformat()
            reminders.append(("danger" if expired else "warning",
                              t("dash.cdl_expired" if expired else "dash.cdl_soon", name=d.name), d.license_expiry))
    return Overview(
        week_start=start,
        week_gross=sum(load.gross for load in week_loads),
        week_miles=sum(load.total_miles for load in week_loads),
        week_loads=len(week_loads),
        in_progress=sum(1 for load in db.list_loads() if load.status in IN_PROGRESS),
        active_trucks=sum(1 for tr in trucks if tr.status == "active"),
        total_trucks=len(trucks),
        maintenance_trucks=sum(1 for tr in trucks if tr.status == "maintenance"),
        unpaid_total=round(sum(balances.values()), 2),
        unpaid_drivers=len(balances),
        service_due=len(due_trucks),
        reminders=reminders,
    )


@dataclass
class Trends:
    """Numbers behind the overview charts (GUI-free)."""

    weeks: list[str]                 # week start dates, oldest first
    gross: list[float]               # gross per week
    rate_per_mile: list[float]       # gross / total miles per week (0 when there were no miles)
    top_brokers: list[tuple[str, float]]  # (broker, gross) of the last 90 days, biggest first


def compute_trends(db: Database, weeks: int = 8, today: date | None = None, broker_days: int = 90,
                   top: int = 5) -> Trends:
    today = today or date.today()
    current = week_start(today, db.week_start_dow)
    starts = [(current - timedelta(days=7 * i)).isoformat() for i in range(weeks - 1, -1, -1)]
    gross = {s: 0.0 for s in starts}
    miles = {s: 0.0 for s in starts}
    brokers: dict[str, float] = {}
    since = (today - timedelta(days=broker_days)).isoformat()
    for load in db.list_loads(include_cancelled=False):
        week = db.load_week(load)
        if week in gross:
            gross[week] += load.gross
            miles[week] += load.total_miles
        if load.broker and (load.report_date or "") >= since:
            brokers[load.broker] = brokers.get(load.broker, 0.0) + load.gross
    return Trends(
        weeks=starts,
        gross=[round(gross[s], 2) for s in starts],
        rate_per_mile=[round(gross[s] / miles[s], 2) if miles[s] else 0.0 for s in starts],
        top_brokers=sorted(brokers.items(), key=lambda kv: -kv[1])[:top],
    )


def card() -> QFrame:
    frame = QFrame()
    frame.setObjectName("Card")
    frame.setProperty("lift", True)
    return frame


class StatCard(QFrame):
    """A key number with an icon; the number counts up when it changes."""

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
        text = QVBoxLayout()
        text.setSpacing(0)
        text.addWidget(self.title)
        text.addWidget(self.value)
        text.addWidget(self.sub)
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


class OverviewTab(QWidget):
    #: "new_load" / "new_truck" / "new_statement" / "new_driver"
    action_requested = Signal(str)

    def __init__(self, db: Database, parent: QWidget | None = None):
        super().__init__(parent)
        self.db = db
        self.overview: Overview | None = None

        # quick actions
        actions = QHBoxLayout()
        actions.setSpacing(8)
        for key, text_key, icon_name, variant in (
            ("new_load", "dash.new_load", "layers", "primary"),
            ("new_truck", "dash.new_truck", "truck", None),
            ("new_driver", "dash.new_driver", "user", None),
            ("new_statement", "dash.new_statement", "file", None),
        ):
            btn = button(t(text_key), variant, icon_name)
            btn.clicked.connect(lambda _=False, k=key: self.action_requested.emit(k))
            actions.addWidget(btn)
        actions.addStretch(1)
        self.week = QLabel()
        self.week.setProperty("role", "kpisub")
        actions.addWidget(self.week)

        # key numbers
        self.cards = {
            "gross": StatCard(t("kpi.week_gross"), "dollar"),
            "miles": StatCard(t("kpi.week_miles"), "route"),
            "moving": StatCard(t("kpi.in_progress"), "truck"),
            "trucks": StatCard(t("kpi.active_trucks"), "check"),
            "unpaid": StatCard(t("kpi.unpaid"), "wallet"),
            "service": StatCard(t("kpi.service_due"), "wrench"),
        }
        grid = QGridLayout()
        grid.setSpacing(12)
        for i, key in enumerate(self.cards):
            grid.addWidget(self.cards[key], i // 3, i % 3)

        # charts (drawn by the app itself, see charts.py)
        self.gross_chart = BarChart()
        self.rpm_chart = LineChart()
        self.broker_chart = RankChart()
        charts = QHBoxLayout()
        charts.setSpacing(12)
        for title_key, chart in (("chart.weekly_gross", self.gross_chart), ("chart.rate_per_mile", self.rpm_chart),
                                 ("chart.top_brokers", self.broker_chart)):
            box = card()
            box.setProperty("lift", False)
            inner_layout = QVBoxLayout(box)
            inner_layout.setContentsMargins(16, 14, 16, 10)
            heading = QLabel(t(title_key))
            heading.setProperty("role", "section")
            inner_layout.addWidget(heading)
            inner_layout.addWidget(chart, 1)
            charts.addWidget(box, 1)

        # recent loads + reminders
        self.recent = make_table([t("load.load_number"), t("report.route"), t("truck"), t("load.gross"),
                                  t("load.status")])
        self.recent.setSortingEnabled(False)
        self.recent.setMinimumHeight(230)
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

        bottom = QHBoxLayout()
        bottom.setSpacing(12)
        bottom.addWidget(recent_card, 3)
        bottom.addWidget(reminders_card, 2)

        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(8, 4, 8, 8)
        layout.setSpacing(14)
        layout.addLayout(actions)
        layout.addLayout(grid)
        layout.addLayout(charts)
        layout.addLayout(bottom, 1)
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
        c = self.cards
        c["gross"].set_value(o.week_gross, lambda v: money(v, cur), t("dash.loads_count", n=o.week_loads), animate)
        c["miles"].set_value(o.week_miles, lambda v: f"{number(v)} {unit}", week_label(o.week_start), animate)
        c["moving"].set_value(o.in_progress, lambda v: number(v), t("dash.in_progress_sub"), animate)
        total = o.total_trucks
        c["trucks"].set_value(o.active_trucks, lambda v: f"{number(v)} / {total}",
                              t("dash.trucks_sub", n=o.maintenance_trucks), animate)
        c["unpaid"].set_value(o.unpaid_total, lambda v: money(v, cur), t("dash.unpaid_sub", n=o.unpaid_drivers), animate)
        c["unpaid"].set_tone("danger" if o.unpaid_total > 0 else "success")
        c["service"].set_value(o.service_due, lambda v: number(v), t("dash.service_sub"), animate)
        c["service"].set_tone("danger" if o.service_due else "success")

        trends = self.trends = compute_trends(self.db)
        week_labels = [w[5:] for w in trends.weeks]  # MM-DD
        self.gross_chart.fmt = lambda v: money(v, cur)
        self.gross_chart.set_data(week_labels, trends.gross, animate)
        self.rpm_chart.fmt = lambda v: f"{money(v, cur)}/{unit}"
        self.rpm_chart.set_data(week_labels, trends.rate_per_mile, animate)
        self.broker_chart.fmt = lambda v: money(v, cur)
        self.broker_chart.set_data([b for b, _ in trends.top_brokers], [g for _, g in trends.top_brokers], animate)

        trucks = {tr.id: tr.label for tr in self.db.list_trucks()}
        loads = self.db.list_loads()[:7]
        fill_table(self.recent, [
            (load.id, [
                load.load_number or "—",
                f"{load.pickup_location or '?'} → {load.delivery_location or '?'}",
                trucks.get(load.truck_id, "—"),
                (money(load.gross, cur), load.gross),
                status_badge("status.", load.status),
            ])
            for load in loads
        ])
        self._fill_reminders(o)

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
