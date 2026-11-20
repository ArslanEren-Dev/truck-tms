"""Broker invoices: receivables, aging buckets and the printable invoice (GUI-free)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from .database import Database, Invoice, Load, Truck
from .i18n import t
from .printout import ACCENT, HEAD, TABLE, company_html, esc, facts_html, money, number, page

AGING_BUCKETS = ("current", "1_30", "31_60", "61_90", "90_plus")


def aging_bucket(inv: Invoice, today: date | None = None) -> str | None:
    """Bucket of an unpaid invoice by days past due; None when it is paid."""
    if inv.balance <= 0.005:
        return None
    late = inv.days_overdue(today)
    if late <= 0:
        return "current"
    if late <= 30:
        return "1_30"
    if late <= 60:
        return "31_60"
    return "61_90" if late <= 90 else "90_plus"


@dataclass
class Receivables:
    open_total: float = 0.0
    open_count: int = 0
    overdue_total: float = 0.0
    overdue_count: int = 0
    collected_30d: float = 0.0          # money received in the last 30 days
    avg_days_to_pay: float | None = None  # issue date -> paid date, paid invoices
    buckets: dict[str, float] = field(default_factory=lambda: dict.fromkeys(AGING_BUCKETS, 0.0))


def compute_receivables(db: Database, today: date | None = None,
                        invoices: list[Invoice] | None = None) -> Receivables:
    today = today or date.today()
    r = Receivables()
    since = (today - timedelta(days=30)).isoformat()
    pay_days = []
    for inv in db.list_invoices() if invoices is None else invoices:
        bucket = aging_bucket(inv, today)
        if bucket:
            r.open_total += inv.balance
            r.open_count += 1
            r.buckets[bucket] += inv.balance
            if bucket != "current":
                r.overdue_total += inv.balance
                r.overdue_count += 1
        if inv.paid_date and inv.paid_amount:
            if inv.paid_date >= since:
                r.collected_30d += inv.paid_amount
            if inv.balance <= 0.005:
                pay_days.append((date.fromisoformat(inv.paid_date) - date.fromisoformat(inv.issue_date)).days)
    r.open_total, r.overdue_total = round(r.open_total, 2), round(r.overdue_total, 2)
    r.collected_30d = round(r.collected_30d, 2)
    r.buckets = {k: round(v, 2) for k, v in r.buckets.items()}
    if pay_days:
        r.avg_days_to_pay = round(sum(pay_days) / len(pay_days), 1)
    return r


# ------------------------------------------------------------------ printable invoice

def invoice_to_html(inv: Invoice, load: Load | None, truck: Truck | None, settings: dict[str, str]) -> str:
    cur, unit = settings["currency"], settings["distance_unit"]
    company = company_html(settings, 17)

    facts = [
        (t("inv.number"), inv.invoice_number),
        (t("inv.issue_date"), inv.issue_date),
        (t("inv.terms"), t("inv.terms_days", n=inv.terms_days) if inv.terms_days else t("inv.due_on_receipt")),
        (t("inv.due_date"), inv.due_date),
    ]

    bill_to = esc(inv.bill_to or (load.broker if load else "") or "—").replace("\n", "<br>")

    rows: list[tuple[str, str]] = []
    if load:
        line_haul = load.rate or 0.0
        extra = load.extra_pay or 0.0
        if line_haul:
            rows.append((t("inv.line_haul"), money(line_haul, cur)))
        if extra:
            rows.append((t("inv.accessorials"), money(extra, cur)))
        other = round(inv.amount - line_haul - extra, 2)
        if abs(other) > 0.005:
            rows.append((t("inv.adjustment"), money(other, cur)))
    if not rows:
        rows.append((t("inv.freight_charges"), money(inv.amount, cur)))
    items = "".join(f"<tr><td>{esc(k)}</td><td align='right'>{esc(v)}</td></tr>" for k, v in rows)

    details = ""
    if load:
        info = [
            (t("load.load_number"), load.load_number),
            (t("inv.pickup"), " · ".join(x for x in (load.pickup_location, load.pickup_date) if x)),
            (t("inv.delivery"), " · ".join(x for x in (load.delivery_location, load.delivery_date) if x)),
            (t("truck"), truck.label if truck else None),
            (t("load.commodity"), load.commodity),
            (t("load.weight"), number(load.weight) if load.weight else None),
            (t("load.loaded_miles"), f"{number(load.loaded_miles)} {unit}" if load.loaded_miles else None),
        ]
        details = facts_html(info, bold=False, cellpadding="3", style="margin-top:10px")


    paid = ""
    if inv.paid_amount or inv.fee:
        paid_rows = []
        if inv.paid_amount:
            paid_rows.append((t("inv.received") + (f" ({inv.paid_date})" if inv.paid_date else ""),
                              "−" + money(inv.paid_amount, cur)))
        if inv.fee:
            paid_rows.append((t("inv.fee") + f" ({t('inv.method.' + inv.method)})", "−" + money(inv.fee, cur)))
        paid = "".join(f"<tr><td>{esc(k)}</td><td align='right'>{esc(v)}</td></tr>" for k, v in paid_rows)
        paid += (f"<tr {HEAD}><td><b>{esc(t('inv.balance'))}</b></td>"
                 f"<td align='right'><b>{esc(money(inv.balance, cur))}</b></td></tr>")
    notes = f"<p><b>{esc(t('load.notes'))}:</b> {esc(inv.notes)}</p>" if inv.notes else ""
    body = (
        "<table width='100%'><tr>"
        f"<td valign='top'>{company}</td>"
        "<td valign='top' align='right'>"
        f"<div style='font-size:22pt; font-weight:bold; color:{ACCENT}'>{esc(t('inv.title').upper())}</div>"
        f"{facts_html(facts, align='right')}</td></tr></table>"
        f"<p style='margin-top:18px'><span style='color:#555'>{esc(t('inv.bill_to'))}</span><br><b>{bill_to}</b></p>"
        f"{details}"
        f"<table {TABLE.replace('collapse', 'collapse; margin-top:14px')}>"
        f"<tr {HEAD}><th align='left'>{esc(t('inv.description'))}</th>"
        f"<th align='right'>{esc(t('inv.amount'))}</th></tr>{items}"
        f"<tr><td><b>{esc(t('inv.total'))}</b></td><td align='right'><b>{esc(money(inv.amount, cur))}</b></td></tr>"
        f"{paid}</table>{notes}"
        f"<p style='color:#555; margin-top:18px'>{esc(t('inv.footer', number=inv.invoice_number))}</p>"
    )
    return page(body, f"{t('inv.title')} {inv.invoice_number}")

