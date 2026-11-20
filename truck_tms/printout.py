"""Shared pieces of the printable documents (statements, truck reports, invoices, IFTA) — GUI-free.

Number formatting, HTML escaping, the page wrapper, the company header and the small
"label: value" table live here once instead of in every document module.
"""

from __future__ import annotations

from html import escape

from .database import Load, Truck

TABLE = "border='1' cellspacing='0' cellpadding='4' width='100%' style='border-collapse:collapse'"
HEAD = "style='background-color:#e8eef5'"
ACCENT = "#1E63C6"


def money(value: float | None, currency: str) -> str:
    """1234.5 -> '$1,234.50'; negative amounts get a leading minus; None -> '—'."""
    if value is None:
        return "—"
    sign = "-" if value < 0 else ""
    return f"{sign}{currency}{abs(value):,.2f}"


def number(value: float | None, decimals: int = 0) -> str:
    return "—" if value is None else f"{value:,.{decimals}f}"


def esc(value) -> str:
    """HTML-escape any value; None becomes an empty string."""
    return escape("" if value is None else str(value))


def page(body: str, title: str = "") -> str:
    """A complete HTML document in the style every printout uses."""
    head = f"<title>{esc(title)}</title>" if title else ""
    return (f"<html><head><meta charset='utf-8'>{head}</head>"
            f"<body style='font-family:Arial, Helvetica, sans-serif; font-size:10pt'>{body}</body></html>")


def company_html(settings: dict[str, str], size_pt: int = 16) -> str:
    """Company name and address from the settings (empty when not filled in)."""
    html = ""
    if settings.get("company_name"):
        html += f"<div style='font-size:{size_pt}pt; font-weight:bold'>{esc(settings['company_name'])}</div>"
    if settings.get("company_address"):
        html += f"<div style='color:#555'>{esc(settings['company_address']).replace(chr(10), '<br>')}</div>"
    return html


def facts_html(rows, bold: bool = True, **table_attrs: str) -> str:
    """A borderless two-column table of (label, value) pairs; rows without a value are skipped."""
    attrs = "".join(f" {k}='{v}'" for k, v in ({"cellspacing": "0", "cellpadding": "2"} | table_attrs).items())
    b1, b2 = ("<b>", "</b>") if bold else ("", "")
    cells = "".join(f"<tr><td style='color:#555; padding-right:14px'>{esc(k)}</td><td>{b1}{esc(v)}{b2}</td></tr>"
                    for k, v in rows if v)
    return f"<table{attrs}>{cells}</table>"


def vehicle_text(truck: Truck) -> str:
    """'2022 Freightliner Cascadia' from whichever parts are known."""
    return " ".join(str(p) for p in (truck.year, truck.make, truck.model) if p)


class LoadTotals:
    """Totals of ``self.loads`` shared by the statement and the truck report."""

    loads: list[Load]

    @property
    def gross(self) -> float:
        return sum(load.gross for load in self.loads)

    @property
    def loaded_miles(self) -> float:
        return sum(load.loaded_miles or 0 for load in self.loads)

    @property
    def dead_miles(self) -> float:
        return sum(load.dead_miles or 0 for load in self.loads)

    @property
    def total_miles(self) -> float:
        return self.loaded_miles + self.dead_miles

    @property
    def rate_per_mile(self) -> float | None:
        return self.gross / self.total_miles if self.total_miles else None
