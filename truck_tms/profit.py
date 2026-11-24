"""Estimated profit of every load, and driver pay over a period (GUI-free).

Load profit = gross
            − company / dispatcher fee (the truck's fee %)
            − driver pay (from the driver's pay settings)
            − fuel (the load's miles × the truck's fuel cost per mile)

Fuel cost per mile is the truck's fuel expenses divided by the miles of its loads; trucks
without fuel data use the fleet average. A weekly salary is shared by the driver's loads of
that week. The numbers are an estimate for comparing loads, not a statement.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

from .database import Database, Driver, Load, Truck
from .i18n import t
from .printout import ACCENT, HEAD, TABLE, company_html, esc, facts_html, money, number, page


def load_driver_pay(load: Load, driver: Driver | None) -> float | None:
    """Pay earned on one load by a percent / per-mile driver; None when it does not depend on the load."""
    if driver is None or driver.pay_rate is None or driver.pay_type not in ("percent", "per_mile"):
        return None
    if driver.pay_type == "percent":
        return round(load.gross * driver.pay_rate / 100, 2)
    return round(load.total_miles * driver.pay_rate, 2)


@dataclass
class LoadProfit:
    gross: float
    dispatch_fee: float
    driver_pay: float
    fuel: float
    miles: float

    @property
    def profit(self) -> float:
        return round(self.gross - self.dispatch_fee - self.driver_pay - self.fuel, 2)

    @property
    def per_mile(self) -> float | None:
        return self.profit / self.miles if self.miles else None

    @property
    def margin(self) -> float | None:
        """Profit as a percentage of the gross."""
        return self.profit / self.gross * 100 if self.gross else None


class ProfitModel:
    """Everything needed to estimate any load's profit, read from the database once."""

    def __init__(self, db: Database):
        self.db = db
        self.trucks: dict[int, Truck] = {tr.id: tr for tr in db.list_trucks()}
        self.drivers: dict[int, Driver] = {d.id: d for d in db.list_drivers()}
        fuel = dict(db.conn.execute(
            "SELECT truck_id, SUM(amount) FROM expenses WHERE category = 'fuel' GROUP BY truck_id"))
        miles = dict(db.conn.execute(
            "SELECT truck_id, SUM(COALESCE(loaded_miles, 0) + COALESCE(dead_miles, 0)) FROM loads"
            " WHERE truck_id IS NOT NULL AND (status != 'cancelled' OR is_tonu = 1) GROUP BY truck_id"))
        self.fuel_per_mile: dict[int, float] = {
            truck_id: fuel[truck_id] / miles[truck_id] for truck_id in fuel if miles.get(truck_id)
        }
        used = list(self.fuel_per_mile)
        total_miles = sum(miles[truck_id] for truck_id in used)
        self.fleet_fuel_per_mile = sum(fuel[truck_id] for truck_id in used) / total_miles if total_miles else 0.0
        self._weekly_shares: dict[tuple[int, str], int] | None = None

    def driver_of(self, load: Load) -> Driver | None:
        """The load's driver, or the truck's default driver (as on statements)."""
        driver_id = load.driver_id
        if driver_id is None and load.truck_id in self.trucks:
            driver_id = self.trucks[load.truck_id].driver_id
        return self.drivers.get(driver_id) if driver_id else None

    def _weekly_count(self, driver: Driver, week: str) -> int:
        """How many loads a weekly-paid driver had in ``week`` (counted once, on first use)."""
        if self._weekly_shares is None:
            counts: dict[tuple[int, str], int] = {}
            weekly = {d.id for d in self.drivers.values() if d.pay_type == "weekly"}
            if weekly:
                for load in self.db.list_loads(include_cancelled=False):
                    other = self.driver_of(load)
                    other_week = self.db.load_week(load)
                    if other and other.id in weekly and other_week:
                        counts[(other.id, other_week)] = counts.get((other.id, other_week), 0) + 1
            self._weekly_shares = counts
        return self._weekly_shares.get((driver.id, week), 0)

    def driver_pay(self, load: Load) -> float:
        driver = self.driver_of(load)
        pay = load_driver_pay(load, driver)
        if pay is not None:
            return pay
        if driver and driver.pay_type == "weekly" and driver.pay_rate:
            week = self.db.load_week(load)
            count = self._weekly_count(driver, week) if week else 0
            return round(driver.pay_rate / count, 2) if count else 0.0
        return 0.0

    def of(self, load: Load) -> LoadProfit:
        truck = self.trucks.get(load.truck_id)
        fee = round(load.gross * (truck.dispatch_fee_percent or 0) / 100, 2) if truck else 0.0
        per_mile = self.fuel_per_mile.get(load.truck_id, self.fleet_fuel_per_mile)
        cancelled = load.status == "cancelled" and not load.is_tonu
        return LoadProfit(
            gross=0.0 if cancelled else load.gross,
            dispatch_fee=0.0 if cancelled else fee,
            driver_pay=0.0 if cancelled else self.driver_pay(load),
            fuel=0.0 if cancelled or load.is_tonu else round(load.total_miles * per_mile, 2),
            miles=0.0 if cancelled else load.total_miles,
        )


# ------------------------------------------------------------------ driver pay
@dataclass
class DriverPayLine:
    driver: Driver
    loads: int = 0
    loaded_miles: float = 0.0
    total_miles: float = 0.0
    gross: float = 0.0
    pay: float = 0.0
    weeks: set[str] = field(default_factory=set)

    @property
    def pay_per_mile(self) -> float | None:
        return self.pay / self.total_miles if self.total_miles else None

    @property
    def pay_share(self) -> float | None:
        """Pay as a percentage of the gross the driver hauled."""
        return self.pay / self.gross * 100 if self.gross else None


@dataclass
class DriverPayReport:
    start: str
    end: str
    lines: list[DriverPayLine] = field(default_factory=list)
    loads_without_driver: int = 0

    @property
    def total_pay(self) -> float:
        return round(sum(line.pay for line in self.lines), 2)

    @property
    def total_gross(self) -> float:
        return round(sum(line.gross for line in self.lines), 2)

    @property
    def total_miles(self) -> float:
        return sum(line.total_miles for line in self.lines)

    @property
    def total_loads(self) -> int:
        return sum(line.loads for line in self.lines)


def compute_driver_pay(db: Database, start: str, end: str) -> DriverPayReport:
    """Loads, miles, gross and pay of every driver for loads delivered from ``start`` to ``end``.

    Percent and per-mile pay come from each load; a weekly salary is counted once for every
    statement week in which the driver had a load.
    """
    model = ProfitModel(db)
    report = DriverPayReport(start, end)
    lines: dict[int, DriverPayLine] = {}
    for load in db.list_loads(start=start, end=end, include_cancelled=False):
        driver = model.driver_of(load)
        if driver is None:
            report.loads_without_driver += 1
            continue
        line = lines.setdefault(driver.id, DriverPayLine(driver))
        line.loads += 1
        line.loaded_miles += load.loaded_miles or 0
        line.total_miles += load.total_miles
        line.gross += load.gross
        pay = load_driver_pay(load, driver)
        if pay is not None:
            line.pay += pay
        elif driver.pay_type == "weekly" and driver.pay_rate:
            week = db.load_week(load)
            if week and week not in line.weeks:
                line.weeks.add(week)
                line.pay += driver.pay_rate
    for line in lines.values():
        line.pay = round(line.pay, 2)
        line.gross = round(line.gross, 2)
    report.lines = sorted(lines.values(), key=lambda line: (-line.pay, line.driver.name.lower()))
    return report


def pay_description(driver: Driver, currency: str, unit: str) -> str:
    """'25% of gross', '$0.65 per mile' or '$1,200.00 per week' ('' without a rate)."""
    if driver.pay_rate is None:
        return ""
    if driver.pay_type == "percent":
        return t("pay.desc_percent", rate=t("fmt.percent", v=f"{driver.pay_rate:g}"))
    if driver.pay_type == "per_mile":
        text = t("pay.desc_per_mile", amount=f"{currency}{driver.pay_rate:g}", unit=t("unit." + unit))
        return text[:1].upper() + text[1:]  # Turkish puts the unit first: "Mil başına $0.65"
    return t("pay.desc_weekly", amount=money(driver.pay_rate, currency))


def driver_pay_headers(unit: str) -> list[str]:
    return [t("driver"), t("dpay.basis"), t("report.load_count"), f"{t('load.loaded_miles')} ({unit})",
            f"{t('load.total_miles')} ({unit})", t("load.gross"), t("dpay.earned"), t("dpay.per_mile", unit=unit),
            t("dpay.share")]


def _line_cells(line: DriverPayLine, cur: str, unit: str) -> list[str]:
    share = line.pay_share
    return [line.driver.name, pay_description(line.driver, cur, unit) or "—", str(line.loads),
            number(line.loaded_miles),
            number(line.total_miles), money(line.gross, cur), money(line.pay, cur),
            money(line.pay_per_mile, cur), "—" if share is None else t("fmt.percent", v=f"{share:.1f}")]


def driver_pay_to_html(report: DriverPayReport, settings: dict[str, str]) -> str:
    cur, unit = settings["currency"], settings["distance_unit"]
    head = "".join(f"<th align='{'left' if i < 2 else 'right'}'>{esc(h)}</th>"
                   for i, h in enumerate(driver_pay_headers(unit)))
    rows = ""
    for line in report.lines:
        rows += "<tr>" + "".join(f"<td align='{'left' if i < 2 else 'right'}'>{esc(c)}</td>"
                                 for i, c in enumerate(_line_cells(line, cur, unit))) + "</tr>"
    if not report.lines:
        rows = f"<tr><td colspan='9' style='color:#777'>{esc(t('dpay.no_data'))}</td></tr>"
    total = (f"<tr {HEAD}><td colspan='2'><b>{esc(t('report.total'))}</b></td>"
             f"<td align='right'><b>{report.total_loads}</b></td><td></td>"
             f"<td align='right'><b>{esc(number(report.total_miles))}</b></td>"
             f"<td align='right'><b>{esc(money(report.total_gross, cur))}</b></td>"
             f"<td align='right'><b>{esc(money(report.total_pay, cur))}</b></td><td></td><td></td></tr>")
    facts = [(t("ifta.period"), f"{report.start} – {report.end}"),
             (t("dpay.total"), money(report.total_pay, cur)),
             (t("dpay.drivers"), str(len(report.lines)))]
    note = ""
    if report.loads_without_driver:
        note = f"<p style='color:#B45309'>⚠ {esc(t('dpay.warn_no_driver', n=report.loads_without_driver))}</p>"
    body = (f"{company_html(settings, 15)}"
            f"<div style='font-size:17pt; font-weight:bold; color:{ACCENT}'>{esc(t('dpay.title'))}</div>"
            f"{facts_html(facts, style='margin:8px 0')}{note}"
            f"<table {TABLE}><tr {HEAD}>{head}</tr>{rows}{total}</table>"
            f"<p style='color:#777; font-size:8pt'>{esc(t('dpay.disclaimer'))}</p>")
    return page(body, f"{t('dpay.title')} {report.start} {report.end}")


def driver_pay_to_csv(report: DriverPayReport, path: str | Path, settings: dict[str, str]) -> None:
    cur, unit = settings["currency"], settings["distance_unit"]
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow([t("dpay.title"), report.start, report.end])
        writer.writerow(driver_pay_headers(unit))
        for line in report.lines:
            writer.writerow([line.driver.name, pay_description(line.driver, cur, unit) or "—", line.loads,
                             round(line.loaded_miles, 1), round(line.total_miles, 1), line.gross, line.pay,
                             "" if line.pay_per_mile is None else round(line.pay_per_mile, 3),
                             "" if line.pay_share is None else round(line.pay_share, 1)])
        writer.writerow([t("report.total"), "", report.total_loads, "", round(report.total_miles, 1),
                         report.total_gross, report.total_pay, "", ""])
