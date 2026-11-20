"""IFTA quarterly fuel tax worksheet (GUI-free).

The calculation follows the IFTA tax return:

* fleet MPG = total miles / total gallons;
* taxable gallons of a jurisdiction = its miles / fleet MPG;
* net taxable gallons = taxable gallons - tax-paid gallons bought there (negative = credit);
* tax = net taxable gallons x the jurisdiction's rate.

Miles come from the "miles by state" of each load in the quarter, gallons from fuel expenses that
have gallons and a state. Rates change every quarter, so the user enters them; the result is a
worksheet to fill in the official return, not the return itself.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .database import Database
from .i18n import t
from .printout import ACCENT, HEAD, TABLE, company_html, esc, facts_html, money, number, page


def quarter_range(year: int, quarter: int) -> tuple[str, str]:
    if quarter not in (1, 2, 3, 4):
        raise ValueError("quarter must be 1-4")
    first = date(year, 3 * quarter - 2, 1)
    last = date(year + (quarter == 4), 1 if quarter == 4 else 3 * quarter + 1, 1)
    return first.isoformat(), date.fromordinal(last.toordinal() - 1).isoformat()


def current_quarter(today: date | None = None) -> tuple[int, int]:
    today = today or date.today()
    return today.year, (today.month - 1) // 3 + 1


@dataclass
class IftaLine:
    state: str
    miles: float
    taxable_gallons: float
    paid_gallons: float
    net_gallons: float
    rate: float | None
    tax: float | None


@dataclass
class IftaReport:
    year: int
    quarter: int
    start: str
    end: str
    truck_id: int | None
    lines: list[IftaLine] = field(default_factory=list)
    total_miles: float = 0.0
    total_gallons: float = 0.0
    mpg: float | None = None
    total_tax: float = 0.0
    unassigned_miles: float = 0.0       # load miles with no state breakdown
    loads_without_states: int = 0
    missing_rates: list[str] = field(default_factory=list)


def compute_ifta(db: Database, year: int, quarter: int, truck_id: int | None = None) -> IftaReport:
    start, end = quarter_range(year, quarter)
    report = IftaReport(year, quarter, start, end, truck_id)
    by_load = db.state_miles_by_load()
    miles: dict[str, float] = {}
    for load in db.list_loads(truck_id=truck_id, start=start, end=end, include_cancelled=False):
        states = by_load.get(load.id, [])
        for state, m in states:
            miles[state] = miles.get(state, 0.0) + m
        assigned = sum(m for _, m in states)
        if load.total_miles - assigned > 0.5:
            report.unassigned_miles += load.total_miles - assigned
            if not states:
                report.loads_without_states += 1
    gallons: dict[str, float] = {}
    for e in db.list_expenses(truck_id=truck_id, start=start, end=end):
        if e.category == "fuel" and e.gallons:
            report.total_gallons += e.gallons
            if e.state:
                gallons[e.state] = gallons.get(e.state, 0.0) + e.gallons
    report.total_miles = round(sum(miles.values()), 1)
    report.total_gallons = round(report.total_gallons, 3)
    report.unassigned_miles = round(report.unassigned_miles, 1)
    if report.total_miles and report.total_gallons:
        report.mpg = round(report.total_miles / report.total_gallons, 2)
    rates = db.ifta_rates()
    for state in sorted(set(miles) | set(gallons)):
        state_miles = miles.get(state, 0.0)
        taxable = round(state_miles / report.mpg, 2) if report.mpg else 0.0
        paid = round(gallons.get(state, 0.0), 2)
        net = round(taxable - paid, 2)
        rate = rates.get(state)
        tax = round(net * rate, 2) if rate is not None else None
        if rate is None:
            report.missing_rates.append(state)
        report.lines.append(IftaLine(state, round(state_miles, 1), taxable, paid, net, rate, tax))
    report.total_tax = round(sum(line.tax for line in report.lines if line.tax is not None), 2)
    return report


# --------------------------------------------------------------------- output

def ifta_headers(unit: str) -> list[str]:
    return [t("ifta.state"), f"{t('ifta.miles')} ({unit})", t("ifta.taxable_gallons"), t("ifta.paid_gallons"),
            t("ifta.net_gallons"), t("ifta.rate"), t("ifta.tax")]


def ifta_to_html(report: IftaReport, settings: dict[str, str], truck_label: str | None = None) -> str:
    cur, unit = settings["currency"], settings["distance_unit"]
    head = "".join(f"<th align='{'left' if i == 0 else 'right'}'>{esc(h)}</th>"
                   for i, h in enumerate(ifta_headers(unit)))
    rows = ""
    for line in report.lines:
        cells = [line.state, number(line.miles, 1), number(line.taxable_gallons, 2), number(line.paid_gallons, 2),
                 number(line.net_gallons, 2), f"{line.rate:.4f}" if line.rate is not None else "—",
                 money(line.tax, cur) if line.tax is not None else "—"]
        rows += "<tr>" + "".join(f"<td align='{'left' if i == 0 else 'right'}'>{esc(c)}</td>"
                                 for i, c in enumerate(cells)) + "</tr>"
    if not report.lines:
        rows = f"<tr><td colspan='7' style='color:#777'>{esc(t('ifta.no_data'))}</td></tr>"
    total = (f"<tr {HEAD}><td><b>{esc(t('ifta.total'))}</b></td>"
             f"<td align='right'><b>{esc(number(report.total_miles, 1))}</b></td>"
             f"<td colspan='4'></td><td align='right'><b>{esc(money(report.total_tax, cur))}</b></td></tr>")

    facts = [
        (t("ifta.period"), f"{report.year} Q{report.quarter} ({report.start} – {report.end})"),
        (t("truck"), truck_label or t("ifta.all_trucks")),
        (t("ifta.total_miles"), f"{number(report.total_miles, 1)} {unit}"),
        (t("ifta.total_gallons"), number(report.total_gallons, 2)),
        (t("ifta.mpg"), number(report.mpg, 2) if report.mpg else "—"),
    ]

    warnings = "".join(f"<p style='color:#B45309'>⚠ {esc(w)}</p>" for w in ifta_warnings(report, unit))
    body = (f"{company_html(settings, 15)}"
            f"<div style='font-size:17pt; font-weight:bold; color:{ACCENT}'>{esc(t('ifta.title'))}</div>"
            f"{facts_html(facts, style='margin:8px 0')}{warnings}"
            f"<table {TABLE}><tr {HEAD}>{head}</tr>{rows}{total}</table>"
            f"<p style='color:#777; font-size:8pt'>{esc(t('ifta.disclaimer'))}</p>")
    return page(body, f"{t('ifta.title')} {report.year} Q{report.quarter}")



def ifta_warnings(report: IftaReport, unit: str) -> list[str]:
    warnings = []
    if report.unassigned_miles:
        warnings.append(t("ifta.warn_unassigned", miles=number(report.unassigned_miles), unit=unit,
                          n=report.loads_without_states))
    if report.total_miles and not report.total_gallons:
        warnings.append(t("ifta.warn_no_gallons"))
    if report.missing_rates:
        warnings.append(t("ifta.warn_rates", states=", ".join(report.missing_rates)))
    return warnings


def ifta_to_csv(report: IftaReport, path: str | Path, settings: dict[str, str]) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow([t("ifta.title"), f"{report.year} Q{report.quarter}", report.start, report.end])
        writer.writerow([t("ifta.mpg"), report.mpg or ""])
        writer.writerow(ifta_headers(settings["distance_unit"]))
        for line in report.lines:
            writer.writerow([line.state, line.miles, line.taxable_gallons, line.paid_gallons, line.net_gallons,
                             "" if line.rate is None else line.rate, "" if line.tax is None else line.tax])
        writer.writerow([t("ifta.total"), report.total_miles, "", "", "", "", report.total_tax])
