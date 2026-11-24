"""What needs attention today, and the getting-started checklist of an empty file (GUI-free)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from .database import Database
from .i18n import t

ON_THE_ROAD = ("planned", "dispatched", "in_transit")
INVOICE_AFTER_DAYS = 2  # a delivered load without an invoice is flagged after this many days


@dataclass
class TodayItem:
    kind: str       # "pickup", "delivery", "late", "invoice"
    tone: str       # badge tone: "info", "warning", "danger"
    title: str
    detail: str
    load_id: int


def _route(load) -> str:
    return f"{load.pickup_location or '?'} → {load.delivery_location or '?'}"


def compute_today(db: Database, today: date | None = None, limit: int = 8) -> list[TodayItem]:
    """Pickups and deliveries due today, late deliveries and delivered loads still waiting for an invoice."""
    today = today or date.today()
    day = today.isoformat()
    items: list[TodayItem] = []
    marks = ",".join("?" * len(ON_THE_ROAD))
    rows = db.conn.execute(
        f"SELECT id FROM loads WHERE status IN ({marks}) AND (pickup_date = ? OR delivery_date <= ?)",
        (*ON_THE_ROAD, day, day))
    for (load_id,) in rows.fetchall():
        load = db.get_load(load_id)
        number = load.load_number or "—"
        if load.delivery_date and load.delivery_date < day:
            late = (today - date.fromisoformat(load.delivery_date)).days
            items.append(TodayItem("late", "danger", t("today.late", number=number, n=late), _route(load), load.id))
        elif load.delivery_date == day:
            items.append(TodayItem("delivery", "info", t("today.delivery", number=number), _route(load), load.id))
        elif load.pickup_date == day and load.status != "in_transit":
            items.append(TodayItem("pickup", "info", t("today.pickup", number=number), _route(load), load.id))
    cutoff = (today - timedelta(days=INVOICE_AFTER_DAYS)).isoformat()
    rows = db.conn.execute(
        "SELECT id FROM loads WHERE status = 'delivered' AND COALESCE(delivery_date, pickup_date) <= ?"
        " AND id NOT IN (SELECT load_id FROM invoices WHERE load_id IS NOT NULL)"
        " ORDER BY COALESCE(delivery_date, pickup_date)", (cutoff,))
    for (load_id,) in rows.fetchall():
        load = db.get_load(load_id)
        items.append(TodayItem("invoice", "warning", t("today.invoice", number=load.load_number or "—"),
                               _route(load), load.id))
    order = {"late": 0, "delivery": 1, "pickup": 2, "invoice": 3}
    items.sort(key=lambda item: order[item.kind])
    return items[:limit]


def onboarding_steps(db: Database) -> list[tuple[str, bool]]:
    """(step, done) for the first things to set up: a truck, a driver and a load."""
    count = lambda table: db.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: E731
    return [("truck", count("trucks") > 0), ("driver", count("drivers") > 0), ("load", count("loads") > 0)]
