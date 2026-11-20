"""Expiring documents and filings: which ones are expired, which expire soon (GUI-free)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .database import ComplianceItem, Database

SOON_DAYS = 30  # "expires soon" window, the common 30-day reminder


def days_left(expiry: str, today: date | None = None) -> int:
    return (date.fromisoformat(expiry) - (today or date.today())).days


def expiry_status(expiry: str, today: date | None = None, soon: int = SOON_DAYS) -> str:
    """``expired`` / ``soon`` / ``ok``."""
    left = days_left(expiry, today)
    if left < 0:
        return "expired"
    return "soon" if left <= soon else "ok"


@dataclass
class ComplianceEntry:
    """One row of the compliance list.

    Most rows are saved ``ComplianceItem`` records. A driver's CDL expiry typed on the driver
    form also shows up here (``item`` is then None and ``driver_id`` says whose it is), unless a
    CDL record exists for that driver.
    """

    kind: str
    expiry_date: str
    owner: str
    status: str
    days_left: int
    item: ComplianceItem | None = None
    driver_id: int | None = None
    truck_id: int | None = None
    reference: str | None = None

    @property
    def row_id(self) -> int:
        """Positive: compliance record id. Negative: -driver_id (CDL from the driver form)."""
        return self.item.id if self.item else -(self.driver_id or 0)


def compliance_entries(db: Database, today: date | None = None) -> list[ComplianceEntry]:
    today = today or date.today()
    drivers = {d.id: d for d in db.list_drivers()}
    trucks = {tr.id: tr for tr in db.list_trucks()}
    entries: list[ComplianceEntry] = []
    cdl_records = set()
    for item in db.list_compliance():
        if item.scope == "driver":
            driver = drivers.get(item.driver_id)
            owner = driver.name if driver else "?"
            if item.kind == "cdl":
                cdl_records.add(item.driver_id)
        elif item.scope == "truck":
            truck = trucks.get(item.truck_id)
            owner = truck.label if truck else "?"
        else:
            owner = ""
        entries.append(ComplianceEntry(item.kind, item.expiry_date, owner, expiry_status(item.expiry_date, today),
                                       days_left(item.expiry_date, today), item, item.driver_id, item.truck_id,
                                       item.reference))
    for driver in drivers.values():
        if driver.license_expiry and driver.status == "active" and driver.id not in cdl_records:
            entries.append(ComplianceEntry("cdl", driver.license_expiry, driver.name,
                                           expiry_status(driver.license_expiry, today),
                                           days_left(driver.license_expiry, today), None, driver.id, None,
                                           driver.license_number))
    entries.sort(key=lambda e: (e.expiry_date, e.kind))
    return entries


def attention_needed(entries: list[ComplianceEntry]) -> list[ComplianceEntry]:
    """Expired or expiring soon, most urgent first."""
    return [e for e in entries if e.status != "ok"]
