"""Per-truck report for any period: loads, miles, gross, expenses, maintenance and net.

GUI-free: produces data, HTML and CSV. The Qt layer only renders the HTML.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .database import Database, Expense, Load, Maintenance, Truck, ValidationError
from .i18n import t
from .printout import HEAD, TABLE, LoadTotals, company_html, esc, facts_html, money, number, page, vehicle_text


@dataclass
class TruckReport(LoadTotals):
    truck: Truck
    start: str
    end: str
    loads: list[Load] = field(default_factory=list)
    expenses: list[Expense] = field(default_factory=list)
    maintenance: list[Maintenance] = field(default_factory=list)


    @property
    def maintenance_cost(self) -> float:
        return sum(m.cost or 0 for m in self.maintenance)

    @property
    def total_expenses(self) -> float:
        return sum(e.amount for e in self.expenses) + self.maintenance_cost

    @property
    def net(self) -> float:
        return self.gross - self.total_expenses

    @property
    def expenses_by_category(self) -> dict[str, float]:
        totals: dict[str, float] = defaultdict(float)
        for e in self.expenses:
            totals[t("category." + e.category)] += e.amount
        if self.maintenance_cost:
            totals[t("tab.maintenance")] += self.maintenance_cost
        return dict(sorted(totals.items(), key=lambda kv: -kv[1]))


def build_truck_report(db: Database, truck_id: int, start: str, end: str) -> TruckReport:
    """Collect a truck's loads (cancelled excluded unless TONU), expenses and maintenance in the period."""
    truck = db.get_truck(truck_id)
    if truck is None:
        raise ValidationError("error.not_found")
    if start > end:
        raise ValidationError("error.invalid_range")
    loads = db.list_loads(truck_id=truck_id, start=start, end=end, include_cancelled=False)
    loads.sort(key=lambda load: (load.report_date or "", load.id or 0))
    expenses = db.list_expenses(truck_id=truck_id, start=start, end=end)
    expenses.sort(key=lambda e: (e.date, e.id or 0))
    maintenance = db.list_maintenance(truck_id=truck_id, start=start, end=end)
    maintenance.sort(key=lambda m: (m.date, m.id or 0))
    return TruckReport(truck, start, end, loads, expenses, maintenance)


HALF = TABLE.replace("width='100%'", "width='50%'")



def _table(headers: list[str], rows: list[list[str]], numeric: set[int]) -> str:
    head = "".join(f"<th>{esc(h)}</th>" for h in headers)
    body = "".join(
        "<tr>" + "".join(
            f"<td{' align=right' if i in numeric else ''}>{c}</td>" for i, c in enumerate(row)
        ) + "</tr>"
        for row in rows
    )
    return f"<table {TABLE}><tr {HEAD}>{head}</tr>{body}</table>"


def report_to_html(report: TruckReport, settings: dict[str, str]) -> str:
    cur = settings.get("currency", "$")
    unit = settings.get("distance_unit", "mi")
    truck = report.truck


    info_rows = [
        (t("truck.plate"), truck.plate),
        (t("truck.unit_number"), truck.unit_number),
        (t("truck.vehicle"), vehicle_text(truck)),
        (t("truck.vin"), truck.vin),
        (t("truck.odometer"), f"{truck.odometer:,} {unit}" if truck.odometer else None),
        (t("truck.owner_name"), truck.owner_name),
        (t("report.period"), f"{report.start} — {report.end}"),
    ]


    summary_rows = [
        (t("report.load_count"), str(len(report.loads))),
        (t("load.loaded_miles"), f"{number(report.loaded_miles)} {unit}"),
        (t("load.dead_miles"), f"{number(report.dead_miles)} {unit}"),
        (t("report.total_distance"), f"{number(report.total_miles)} {unit}"),
        (t("report.revenue"), money(report.gross, cur)),
        (t("load.rate_per_mile", unit=unit), money(report.rate_per_mile, cur)),
        (t("report.expenses"), money(report.total_expenses, cur)),
        (t("report.net"), money(report.net, cur)),
    ]
    summary = "".join(
        f"<tr><td>{esc(k)}</td><td align='right'>"
        f"{'<b>' + esc(v) + '</b>' if k == t('report.net') else esc(v)}</td></tr>"
        for k, v in summary_rows
    )

    if report.loads:
        rows = [
            [
                esc(load.report_date or "—"),
                esc(load.load_number or "—") + (f" <b>[{esc(t('load.tonu'))}]</b>" if load.is_tonu else ""),
                esc(load.broker or "—"),
                f"{esc(load.pickup_location or '?')} → {esc(load.delivery_location or '?')}",
                number(load.loaded_miles or 0),
                number(load.dead_miles or 0),
                money(load.gross, cur),
                esc(t("status." + load.status)),
            ]
            for load in report.loads
        ]
        rows.append([f"<b>{esc(t('report.total'))}</b>", "", "", "",
                     f"<b>{number(report.loaded_miles)}</b>", f"<b>{number(report.dead_miles)}</b>",
                     f"<b>{money(report.gross, cur)}</b>", ""])
        loads_html = _table(
            [t("report.date"), t("load.load_number"), t("load.broker"), t("report.route"),
             f"{t('load.loaded_miles')} ({unit})", f"{t('load.dead_miles')} ({unit})",
             t("load.gross"), t("load.status")],
            rows, {4, 5, 6},
        )
    else:
        loads_html = f"<p style='color:#777'>{esc(t('report.no_loads'))}</p>"

    cost_rows = [
        [esc(e.date), esc(t("category." + e.category)), esc(e.description or ""), money(e.amount, cur)]
        for e in report.expenses
    ] + [
        [esc(m.date), esc(t("tab.maintenance") + " — " + t("service." + m.service_type)),
         esc(" · ".join(p for p in (m.vendor, m.description) if p)), money(m.cost or 0, cur)]
        for m in report.maintenance
    ]
    if cost_rows:
        cost_rows.sort(key=lambda r: r[0])
        cost_rows.append([f"<b>{esc(t('report.total'))}</b>", "", "",
                          f"<b>{money(report.total_expenses, cur)}</b>"])
        expenses_html = _table(
            [t("expense.date"), t("expense.category"), t("expense.description"), t("expense.amount")],
            cost_rows, {3},
        )
        cat_rows = "".join(
            f"<tr><td>{esc(c)}</td><td align='right'>{money(v, cur)}</td></tr>"
            for c, v in report.expenses_by_category.items()
        )
        expenses_html += f"<h3>{esc(t('report.expenses_by_category'))}</h3><table {HALF}>{cat_rows}</table>"
    else:
        expenses_html = f"<p style='color:#777'>{esc(t('report.no_expenses'))}</p>"

    generated = datetime.now().strftime("%Y-%m-%d %H:%M")
    body = (f"{company_html(settings)}<h1>{esc(t('report.title'))}</h1>{facts_html(info_rows)}"
            f"<h2>{esc(t('report.summary'))}</h2><table {HALF}>{summary}</table>"
            f"<h2>{esc(t('report.loads'))}</h2>{loads_html}"
            f"<h2>{esc(t('report.expenses'))}</h2>{expenses_html}"
            f"<p style='color:#777; font-size:8pt'>{esc(t('report.cancelled_note'))}<br>"
            f"{esc(t('report.generated', when=generated))}</p>")
    return page(body, f"{t('report.title')} {truck.label}")


def report_to_csv(report: TruckReport, path: str | Path, settings: dict[str, str]) -> None:
    """Write the report as CSV (UTF-8 with BOM so Excel shows Turkish characters correctly)."""
    unit = settings.get("distance_unit", "mi")
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow([t("report.title"), report.truck.label, f"{report.start} — {report.end}"])
        w.writerow([])
        w.writerow([t("report.summary")])
        w.writerow([t("report.load_count"), len(report.loads)])
        w.writerow([t("report.total_distance") + f" ({unit})", round(report.total_miles, 2)])
        w.writerow([t("report.revenue"), round(report.gross, 2)])
        w.writerow([t("report.expenses"), round(report.total_expenses, 2)])
        w.writerow([t("report.net"), round(report.net, 2)])
        w.writerow([])
        w.writerow([t("report.loads")])
        w.writerow([
            t("report.date"), t("load.load_number"), t("load.broker"),
            t("load.pickup_location"), t("load.delivery_location"),
            f"{t('load.loaded_miles')} ({unit})", f"{t('load.dead_miles')} ({unit})",
            t("load.rate"), t("load.extra_pay"), t("load.gross"), t("load.tonu"), t("load.status"),
        ])
        for load in report.loads:
            w.writerow([
                load.report_date or "", load.load_number or "", load.broker or "",
                load.pickup_location or "", load.delivery_location or "",
                load.loaded_miles or 0, load.dead_miles or 0, load.rate or 0, load.extra_pay or 0,
                load.gross, "TONU" if load.is_tonu else "", t("status." + load.status),
            ])
        w.writerow([])
        w.writerow([t("report.expenses")])
        w.writerow([t("expense.date"), t("expense.category"), t("expense.description"), t("expense.amount")])
        for e in report.expenses:
            w.writerow([e.date, t("category." + e.category), e.description or "", e.amount])
        for m in report.maintenance:
            w.writerow([m.date, t("tab.maintenance") + " — " + t("service." + m.service_type),
                        m.description or "", m.cost or 0])
