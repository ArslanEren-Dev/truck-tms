"""Search across loads, trucks, drivers and invoices at once (GUI-free; used by Ctrl+K)."""

from __future__ import annotations

from dataclasses import dataclass

from .database import Database
from .i18n import t
from .printout import money, vehicle_text


@dataclass
class Hit:
    kind: str  # "load", "truck", "driver" or "invoice"
    record_id: int
    title: str
    detail: str


def search_records(db: Database, text: str, limit: int = 6) -> list[Hit]:
    """Up to ``limit`` matches of each kind, loads first; nothing for an empty text."""
    text = text.strip()
    if not text:
        return []
    cur = db.get_settings()["currency"]
    hits: list[Hit] = []
    for load in db.list_loads(search=text.lstrip("#") or text, limit=limit):
        route = f"{load.pickup_location or '?'} → {load.delivery_location or '?'}"
        detail = " · ".join(p for p in (load.broker, route, load.report_date, money(load.gross, cur)) if p)
        hits.append(Hit("load", load.id, load.load_number or t("tab.loads"), detail))
    for truck in db.list_trucks(search=text)[:limit]:
        hits.append(Hit("truck", truck.id, truck.label, vehicle_text(truck) or truck.owner_name or ""))
    for driver in db.list_drivers(search=text)[:limit]:
        hits.append(Hit("driver", driver.id, driver.name, driver.phone or driver.email or ""))
    needle = text.lower()
    invoices = [inv for inv in db.list_invoices()
                if needle in inv.invoice_number.lower() or needle in (inv.bill_to or "").lower()]
    for inv in invoices[:limit]:
        bill_to = (inv.bill_to or "").splitlines()[0] if inv.bill_to else ""  # name only, not the address
        detail = " · ".join(p for p in (bill_to, inv.issue_date, money(inv.amount, cur)) if p)
        hits.append(Hit("invoice", inv.id, inv.invoice_number, detail))
    return hits
