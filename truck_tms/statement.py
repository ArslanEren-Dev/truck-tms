"""Weekly statements (settlements) for a truck.

Owner payout = gross
             − company / dispatcher fee
             − fuel − tolls
             − driver net pay (when the driver is paid out of this statement)
             + owner additions − owner deductions

Driver net pay = driver salary (automatic from the driver's pay settings, or a manual
override) + driver additions − driver deductions. What was actually paid to the driver,
and when, is tracked separately — it can differ from what the statement says.

GUI-free: produces numbers, HTML and CSV.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .database import Database, Driver, Load, Statement, StatementItem, Truck, ValidationError
from .i18n import t
from .profit import load_driver_pay
from .printout import HEAD, TABLE, LoadTotals, company_html, esc, facts_html, money, page, vehicle_text
from .weeks import week_end, week_label


@dataclass
class PayLine:
    driver: Driver | None
    description: str
    amount: float


@dataclass
class StatementSummary(LoadTotals):
    statement: Statement
    truck: Truck
    loads: list[Load]
    items: list[StatementItem]
    drivers: dict[int, Driver] = field(default_factory=dict)
    pay_lines: list[PayLine] = field(default_factory=list)

    # -- week / loads --------------------------------------------------------
    @property
    def week_start(self) -> str:
        return self.statement.week_start

    @property
    def week_end(self) -> str:
        return week_end(self.statement.week_start).isoformat()


    # -- company side --------------------------------------------------------
    @property
    def dispatch_fee(self) -> float:
        s = self.statement
        return round(self.gross * (s.dispatch_fee_percent or 0) / 100 + (s.dispatch_fee_fixed or 0), 2)

    @property
    def fuel(self) -> float:
        return self.statement.fuel_amount or 0

    @property
    def tolls(self) -> float:
        return self.statement.tolls or 0

    # -- driver --------------------------------------------------------------
    def _items(self, kind: str) -> list[StatementItem]:
        return [i for i in self.items if i.kind == kind]

    def _sum(self, kind: str) -> float:
        return sum(i.amount for i in self._items(kind))

    @property
    def driver_salary_auto(self) -> float:
        return round(sum(line.amount for line in self.pay_lines), 2)

    @property
    def driver_salary(self) -> float:
        override = self.statement.driver_pay_override
        return override if override is not None else self.driver_salary_auto

    @property
    def driver_additions(self) -> float:
        return self._sum("driver_addition")

    @property
    def driver_deductions(self) -> float:
        return self._sum("driver_deduction")

    @property
    def driver_net(self) -> float:
        return round(self.driver_salary + self.driver_additions - self.driver_deductions, 2)

    @property
    def driver_paid(self) -> float:
        return self.statement.driver_paid_amount or 0

    @property
    def driver_balance(self) -> float:
        """Still owed to the driver (negative = overpaid)."""
        return round(self.driver_net - self.driver_paid, 2)

    @property
    def driver_names(self) -> str:
        return ", ".join(sorted(d.name for d in self.drivers.values()))

    # -- owner ---------------------------------------------------------------
    @property
    def owner_additions(self) -> float:
        return self._sum("owner_addition")

    @property
    def owner_deductions(self) -> float:
        return self._sum("owner_deduction")

    @property
    def driver_cost_to_owner(self) -> float:
        return self.driver_net if self.statement.deduct_driver_pay else 0.0

    @property
    def owner_payout(self) -> float:
        return round(
            self.gross - self.dispatch_fee - self.fuel - self.tolls - self.driver_cost_to_owner
            + self.owner_additions - self.owner_deductions,
            2,
        )


def percent(value: float) -> str:
    """'10%' in English, '%10' in Turkish."""
    return t("fmt.percent", v=f"{value:g}")


def _pay_lines(loads: list[Load], drivers: dict[int, Driver], currency: str, unit: str) -> list[PayLine]:
    lines: list[PayLine] = []
    weekly_done: set[int] = set()
    for load in loads:
        driver = drivers.get(load.driver_id) if load.driver_id else None
        if driver is None or driver.pay_rate is None:
            continue
        rate = driver.pay_rate
        amount = load_driver_pay(load, driver)
        if driver.pay_type == "percent":
            desc = f"{load.load_number or ''} {percent(rate)} × {currency}{load.gross:,.2f}"
        elif driver.pay_type == "per_mile":
            desc = f"{load.load_number or ''} {load.total_miles:,.0f} {unit} × {currency}{rate:g}"
        else:  # weekly — once per driver per statement
            if driver.id in weekly_done:
                continue
            weekly_done.add(driver.id)
            amount = rate
            desc = t("pay.weekly_line")
        lines.append(PayLine(driver, desc.strip(), round(amount, 2)))
    return lines


def compute_statement(db: Database, statement: Statement, items: list[StatementItem] | None = None) -> StatementSummary:
    """Collect the truck's loads for the statement week and compute every total.

    Loads without a driver fall back to the truck's default driver.
    """
    truck = db.get_truck(statement.truck_id)
    if truck is None:
        raise ValidationError("error.truck_required")
    if items is None:
        items = db.statement_items(statement.id) if statement.id else []
    loads = db.list_loads(truck_id=truck.id, week=statement.week_start, include_cancelled=False)
    loads.sort(key=lambda load: (load.report_date or "", load.id or 0))
    for load in loads:
        if load.driver_id is None:
            load.driver_id = truck.driver_id
    drivers = {d.id: d for d in (db.get_driver(i) for i in {load.driver_id for load in loads if load.driver_id}) if d}
    settings = db.get_settings()
    summary = StatementSummary(statement, truck, loads, list(items), drivers)
    summary.pay_lines = _pay_lines(loads, drivers, settings["currency"], settings["distance_unit"])
    return summary


def driver_balances(db: Database) -> dict[int, float]:
    """Unpaid amount per driver over all statements (statements with one driver only)."""
    balances: dict[int, float] = {}
    for s in db.list_statements():
        summary = compute_statement(db, s)
        if len(summary.drivers) == 1:
            driver_id = next(iter(summary.drivers))
            balances[driver_id] = round(balances.get(driver_id, 0) + summary.driver_balance, 2)
    return balances


# ------------------------------------------------------------------- output
HALF = TABLE.replace("width='100%'", "width='60%'")



def _rows(rows: list[tuple[str, str]], bold_last: bool = False) -> str:
    out = []
    for i, (label, value) in enumerate(rows):
        b1, b2 = ("<b>", "</b>") if bold_last and i == len(rows) - 1 else ("", "")
        out.append(f"<tr><td>{b1}{esc(label)}{b2}</td><td align='right'>{b1}{esc(value)}{b2}</td></tr>")
    return "".join(out)


def _loads_table(s: StatementSummary, cur: str, unit: str, show_money: bool = True) -> str:
    if not s.loads:
        return f"<p style='color:#777'>{esc(t('report.no_loads'))}</p>"
    heads = [t("load.load_number"), t("report.date"), t("driver"), t("report.route"),
             t("load.loaded_miles"), t("load.dead_miles"), t("load.total_miles")]
    if show_money:
        heads += [t("load.rate"), t("load.extra_pay"), t("load.gross"), t("load.rate_per_mile", unit=unit)]
    rows = []
    for load in s.loads:
        driver = s.drivers.get(load.driver_id)
        tonu = f" <b>[{esc(t('load.tonu'))}]</b>" if load.is_tonu else ""
        cells = [
            esc(load.load_number or "—") + tonu,
            esc(load.report_date or "—"),
            esc(driver.name if driver else "—"),
            f"{esc(load.pickup_location or '?')} → {esc(load.delivery_location or '?')}",
            f"<div align='right'>{load.loaded_miles or 0:,.0f}</div>",
            f"<div align='right'>{load.dead_miles or 0:,.0f}</div>",
            f"<div align='right'>{load.total_miles:,.0f}</div>",
        ]
        if show_money:
            rpm = load.rate_per_mile
            cells += [
                f"<div align='right'>{money(load.rate or 0, cur)}</div>",
                f"<div align='right'>{money(load.extra_pay or 0, cur)}</div>",
                f"<div align='right'>{money(load.gross, cur)}</div>",
                f"<div align='right'>{money(rpm, cur) if rpm is not None else '—'}</div>",
            ]
        rows.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
    total = [
        f"<td colspan='4'><b>{esc(t('report.total'))}</b></td>",
        f"<td align='right'><b>{s.loaded_miles:,.0f}</b></td>",
        f"<td align='right'><b>{s.dead_miles:,.0f}</b></td>",
        f"<td align='right'><b>{s.total_miles:,.0f}</b></td>",
    ]
    if show_money:
        rpm = s.rate_per_mile
        total += [
            "<td></td><td></td>",
            f"<td align='right'><b>{money(s.gross, cur)}</b></td>",
            f"<td align='right'><b>{money(rpm, cur) if rpm is not None else '—'}</b></td>",
        ]
    head = "".join(f"<th>{esc(h)}</th>" for h in heads)
    return f"<table {TABLE}><tr {HEAD}>{head}</tr>{''.join(rows)}<tr>{''.join(total)}</tr></table>"


def _items_list(s: StatementSummary, kind: str, cur: str) -> list[tuple[str, str]]:
    sign = "−" if kind.endswith("deduction") else "+"
    return [(f"  {sign} {i.description or t('kind.' + kind)}", money(i.amount, cur)) for i in s._items(kind)]


def _driver_rows(s: StatementSummary, cur: str) -> list[tuple[str, str]]:
    rows = [(f"  {line.description}", money(line.amount, cur)) for line in s.pay_lines]
    if s.statement.driver_pay_override is not None:
        rows.append((t("stmt.driver_pay_override"), money(s.statement.driver_pay_override, cur)))
    rows.append((t("stmt.driver_salary"), money(s.driver_salary, cur)))
    rows += _items_list(s, "driver_addition", cur)
    rows += _items_list(s, "driver_deduction", cur)
    rows.append((t("stmt.driver_net"), money(s.driver_net, cur)))
    return rows


def _header(settings: dict[str, str], title: str, s: StatementSummary) -> str:
    truck = s.truck
    info = [
        (t("stmt.week"), week_label(s.week_start)),
        (t("truck"), truck.label),
        (t("truck.vehicle"), vehicle_text(truck)),
        (t("truck.owner_name"), truck.owner_name),
        (t("driver"), s.driver_names),
        (t("stmt.status"), t("stmt_status." + s.statement.status)),
    ]
    return f"{company_html(settings)}<h1>{esc(title)}</h1>{facts_html(info)}"


def _footer(s: StatementSummary) -> str:
    generated = datetime.now().strftime("%Y-%m-%d %H:%M")
    notes = f"<p><b>{esc(t('load.notes'))}:</b> {esc(s.statement.notes)}</p>" if s.statement.notes else ""
    return (f"{notes}<p style='color:#777; font-size:8pt'>{esc(t('stmt.week_note'))}<br>"
            f"{esc(t('report.generated', when=generated))}</p>")



def statement_to_html(s: StatementSummary, settings: dict[str, str]) -> str:
    """Full (owner) statement."""
    cur = settings.get("currency", "$")
    unit = settings.get("distance_unit", "mi")
    st = s.statement
    gallons = f" ({st.fuel_gallons:,.1f} {t('unit.gal')})" if st.fuel_gallons else ""
    fee_label = t("stmt.dispatch_fee")
    if st.dispatch_fee_percent:
        fee_label += f" ({percent(st.dispatch_fee_percent)})"
    weekly = [
        (t("report.load_count"), str(len(s.loads))),
        (t("load.loaded_miles"), f"{s.loaded_miles:,.0f} {unit}"),
        (t("load.dead_miles"), f"{s.dead_miles:,.0f} {unit}"),
        (t("stmt.total_weekly_miles"), f"{s.total_miles:,.0f} {unit}"),
        (t("stmt.total_gross"), money(s.gross, cur)),
        (t("load.rate_per_mile", unit=unit), money(s.rate_per_mile, cur)),
    ]
    owner = [(t("stmt.total_gross"), money(s.gross, cur)),
             ("− " + fee_label, money(s.dispatch_fee, cur)),
             ("− " + t("stmt.fuel") + gallons, money(s.fuel, cur)),
             ("− " + t("stmt.tolls"), money(s.tolls, cur))]
    if st.deduct_driver_pay:
        owner.append(("− " + t("stmt.driver_net"), money(s.driver_net, cur)))
    owner += _items_list(s, "owner_addition", cur)
    owner += _items_list(s, "owner_deduction", cur)
    owner.append((t("stmt.owner_payout"), money(s.owner_payout, cur)))

    driver = _driver_rows(s, cur)
    driver.append((t("stmt.driver_paid"), money(s.driver_paid, cur)))
    if st.driver_paid_date:
        driver.append((t("stmt.driver_paid_date"), st.driver_paid_date))
    driver.append((t("stmt.driver_balance"), money(s.driver_balance, cur)))

    title = t("stmt.title")
    body = (
        _header(settings, title, s)
        + f"<h2>{esc(t('report.loads'))}</h2>" + _loads_table(s, cur, unit)
        + f"<h2>{esc(t('stmt.weekly_summary'))}</h2><table {HALF}>{_rows(weekly)}</table>"
        + f"<h2>{esc(t('stmt.owner_section'))}</h2><table {HALF}>{_rows(owner, bold_last=True)}</table>"
        + f"<h2>{esc(t('stmt.driver_section'))}</h2><table {HALF}>{_rows(driver, bold_last=True)}</table>"
        + _footer(s)
    )
    return page(body, f"{title} {s.truck.label} {s.week_start}")


def driver_statement_to_html(s: StatementSummary, settings: dict[str, str]) -> str:
    """Statement for the driver: loads, miles, pay, additions/deductions and payment — no owner figures."""
    cur = settings.get("currency", "$")
    unit = settings.get("distance_unit", "mi")
    st = s.statement
    show_money = any(d.pay_type == "percent" for d in s.drivers.values())
    driver = _driver_rows(s, cur)
    driver.append((t("stmt.driver_paid"), money(s.driver_paid, cur)))
    if st.driver_paid_date:
        driver.append((t("stmt.driver_paid_date"), st.driver_paid_date))
    driver.append((t("stmt.driver_balance"), money(s.driver_balance, cur)))
    miles = [
        (t("load.loaded_miles"), f"{s.loaded_miles:,.0f} {unit}"),
        (t("load.dead_miles"), f"{s.dead_miles:,.0f} {unit}"),
        (t("stmt.total_weekly_miles"), f"{s.total_miles:,.0f} {unit}"),
    ]
    title = t("stmt.driver_title")
    body = (
        _header(settings, title, s)
        + f"<h2>{esc(t('report.loads'))}</h2>" + _loads_table(s, cur, unit, show_money=show_money)
        + f"<h2>{esc(t('stmt.weekly_summary'))}</h2><table {HALF}>{_rows(miles)}</table>"
        + f"<h2>{esc(t('stmt.driver_section'))}</h2><table {HALF}>{_rows(driver, bold_last=True)}</table>"
        + _footer(s)
    )
    return page(body, f"{title} {s.truck.label} {s.week_start}")


def statement_to_csv(s: StatementSummary, path: str | Path, settings: dict[str, str]) -> None:
    unit = settings.get("distance_unit", "mi")
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow([t("stmt.title"), s.truck.label, s.week_start, s.week_end])
        w.writerow([])
        w.writerow([t("load.load_number"), t("report.date"), t("driver"), t("load.pickup_location"),
                    t("load.delivery_location"), f"{t('load.loaded_miles')} ({unit})",
                    f"{t('load.dead_miles')} ({unit})", f"{t('load.total_miles')} ({unit})",
                    t("load.rate"), t("load.extra_pay"), t("load.gross"), t("load.tonu")])
        for load in s.loads:
            d = s.drivers.get(load.driver_id)
            w.writerow([load.load_number or "", load.report_date or "", d.name if d else "",
                        load.pickup_location or "", load.delivery_location or "",
                        load.loaded_miles or 0, load.dead_miles or 0, load.total_miles,
                        load.rate or 0, load.extra_pay or 0, load.gross, "TONU" if load.is_tonu else ""])
        w.writerow([])
        for label, value in [
            (t("stmt.total_weekly_miles"), s.total_miles),
            (t("stmt.total_gross"), s.gross),
            (t("stmt.dispatch_fee"), s.dispatch_fee),
            (t("stmt.fuel"), s.fuel),
            (t("stmt.fuel_gallons"), s.statement.fuel_gallons or ""),
            (t("stmt.tolls"), s.tolls),
            (t("stmt.driver_salary"), s.driver_salary),
            (t("stmt.driver_additions"), s.driver_additions),
            (t("stmt.driver_deductions"), s.driver_deductions),
            (t("stmt.driver_net"), s.driver_net),
            (t("stmt.driver_paid"), s.driver_paid),
            (t("stmt.driver_paid_date"), s.statement.driver_paid_date or ""),
            (t("stmt.driver_balance"), s.driver_balance),
            (t("stmt.owner_additions"), s.owner_additions),
            (t("stmt.owner_deductions"), s.owner_deductions),
            (t("stmt.owner_payout"), s.owner_payout),
        ]:
            w.writerow([label, value])
        if s.items:
            w.writerow([])
            for item in s.items:
                w.writerow([t("kind." + item.kind), item.description or "", item.amount])
