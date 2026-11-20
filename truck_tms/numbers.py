"""Reading numbers and dates typed (or exported from Excel) the US or the Turkish way. GUI-free."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from .database import ValidationError

EXCEL_EPOCH = date(1899, 12, 30)  # Excel's day 0 (with its 1900 leap-year quirk already accounted for)


def parse_number(text) -> float | None:
    """Read numbers typed the US or the Turkish way; '' -> None. Raises ValidationError.

    '1,234.5' and '1.234,5' -> 1234.5 (the last separator is the decimal one)
    '12,500' and '12.500'   -> 12500  (one separator + exactly 3 digits = thousands)
    '0,70', '1234,5', '0.650' -> decimals
    A leading currency sign ('$', '€', '₺') is ignored.
    """
    if isinstance(text, (int, float)):
        return float(text)
    text = (text or "").strip().replace(" ", "").replace(" ", "")
    for sign in ("$", "€", "₺", "£", "TL", "USD"):
        text = text.replace(sign, "")
    if not text:
        return None
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text or "." in text:
        sep = "," if "," in text else "."
        parts = text.split(sep)
        whole = parts[0].lstrip("+-")
        thousands = len(parts) > 2 or (len(parts[1]) == 3 and whole not in ("", "0"))
        if thousands and all(len(p) == 3 and p.isdigit() for p in parts[1:]):
            text = "".join(parts)
        elif len(parts) == 2:
            text = parts[0] + "." + parts[1]
        else:
            raise ValidationError("error.invalid_number")
    try:
        return float(text)
    except ValueError as exc:
        raise ValidationError("error.invalid_number") from exc


def format_number(value: float | None) -> str:
    if value is None:
        return ""
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")


DATE_FORMATS = (
    "%Y-%m-%d", "%Y/%m/%d",
    "%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y",    # US
    "%d.%m.%Y", "%d.%m.%y",                # Turkish / European
    "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%m/%d/%Y %H:%M",
    "%b %d, %Y", "%d %b %Y",
)


def parse_date(value) -> str | None:
    """Return 'YYYY-MM-DD' from many date spellings or an Excel serial number; '' -> None.

    Slashes are read the US way (month/day/year); dots the Turkish way (day.month.year).
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (int, float)):
        if 1 <= value < 2958466:  # Excel serial date
            return (EXCEL_EPOCH + timedelta(days=int(value))).isoformat()
        raise ValidationError("error.invalid_date")
    text = str(value).strip()
    if not text:
        return None
    if text.replace(".", "", 1).isdigit() and "." not in text[:3]:
        return parse_date(float(text))  # serial number stored as text
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    raise ValidationError("error.invalid_date")
