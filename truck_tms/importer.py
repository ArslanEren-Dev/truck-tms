"""Import loads from a spreadsheet (CSV or Excel .xlsx). GUI-free, standard library only.

1. ``read_table(path)`` reads the first sheet into a header row + data rows.
2. ``auto_map(headers)`` guesses which column holds which field (English and Turkish headers).
3. ``import_loads(db, rows, mapping)`` creates the loads, row by row, and reports what happened.
"""

from __future__ import annotations

import csv
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree

from .database import LOAD_STATUSES, Database, Driver, Load, Truck, ValidationError, normalize_load_number
from .i18n import STRINGS
from .numbers import parse_date, parse_number

# ------------------------------------------------------------------ fields
FIELDS = (
    "load_number", "truck", "driver", "broker", "pickup_location", "pickup_date", "delivery_location",
    "delivery_date", "rate", "extra_pay", "loaded_miles", "dead_miles", "weight", "commodity", "status",
    "tonu", "notes",
)
NUMBER_FIELDS = {"rate", "extra_pay", "loaded_miles", "dead_miles", "weight"}
DATE_FIELDS = {"pickup_date", "delivery_date"}

# Header spellings that point to each field (compared after lower-casing and removing punctuation).
SYNONYMS = {
    "load_number": ["load", "load #", "load no", "load number", "load id", "order", "order #", "pro", "pro #",
                    "reference", "ref", "yük no", "yük numarası", "load numarası"],
    "truck": ["truck", "unit", "unit #", "truck #", "tractor", "plate", "plaka", "tır", "araç", "araç kodu"],
    "driver": ["driver", "driver name", "sürücü", "şoför"],
    "broker": ["broker", "customer", "client", "shipper", "müşteri", "broker müşteri"],
    "pickup_location": ["pickup", "pick up", "pu", "origin", "from", "shipper city", "pickup location",
                        "yükleme", "yükleme yeri", "çıkış"],
    "pickup_date": ["pickup date", "pu date", "pick up date", "ship date", "yükleme tarihi"],
    "delivery_location": ["delivery", "drop", "destination", "to", "consignee", "delivery location", "dest",
                          "teslim", "teslimat", "teslimat yeri", "varış"],
    "delivery_date": ["delivery date", "del date", "drop date", "teslimat tarihi", "teslim tarihi"],
    "rate": ["rate", "linehaul", "line haul", "amount", "pay", "revenue", "gross", "ücret", "navlun", "tutar"],
    "extra_pay": ["extra", "extra pay", "accessorial", "accessorials", "detention", "lumper", "ek ödeme"],
    "loaded_miles": ["miles", "loaded miles", "loaded", "mi", "distance", "yüklü mil", "mil", "mesafe"],
    "dead_miles": ["dead miles", "deadhead", "dh", "empty miles", "boş mil", "dead mile"],
    "weight": ["weight", "lbs", "ağırlık"],
    "commodity": ["commodity", "product", "freight", "yük cinsi", "ürün"],
    "status": ["status", "state", "durum"],
    "tonu": ["tonu"],
    "notes": ["notes", "note", "comments", "remarks", "notlar", "not", "açıklama"],
}


def _key(text: str) -> str:
    text = (text or "").lower().replace("ı", "i").replace("İ", "i")
    return re.sub(r"[^0-9a-zçğöşü# ]+", " ", text).replace("#", " #").split("(")[0].strip()


def _norm(text: str) -> str:
    return " ".join(_key(text).replace("#", "").split())


_SYNONYM_INDEX = {_norm(s): f for f, words in SYNONYMS.items() for s in words}


def auto_map(headers: list[str]) -> dict[str, int]:
    """Guess field → column index from the header names (exact synonym first, then 'contains')."""
    mapping: dict[str, int] = {}
    normalized = [_norm(h) for h in headers]
    for i, name in enumerate(normalized):
        field_name = _SYNONYM_INDEX.get(name)
        if field_name and field_name not in mapping:
            mapping[field_name] = i
    # second pass: "Pickup City", "Total Rate ($)", ... — longest synonym contained in the header wins
    for i, name in enumerate(normalized):
        if i in mapping.values() or not name:
            continue
        best = None
        for synonym, field_name in _SYNONYM_INDEX.items():
            if field_name in mapping or len(synonym) < 3:
                continue
            if re.search(rf"\b{re.escape(synonym)}\b", name) and (best is None or len(synonym) > len(best[0])):
                best = (synonym, field_name)
        if best:
            mapping[best[1]] = i
    return mapping


# ------------------------------------------------------------------ reading
def read_table(path: str | Path) -> tuple[list[str], list[list[str]]]:
    """First sheet of a .csv / .tsv / .txt / .xlsx file → (headers, rows). Empty rows are dropped."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in (".xlsx", ".xlsm"):
        table = _read_xlsx(path)
    elif suffix in (".csv", ".tsv", ".txt"):
        table = _read_csv(path)
    else:
        raise ValidationError("import.unsupported")
    table = [[("" if c is None else c) for c in row] for row in table]
    table = [row for row in table if any(str(c).strip() for c in row)]
    if not table:
        raise ValidationError("import.empty")
    width = max(len(r) for r in table)
    table = [row + [""] * (width - len(row)) for row in table]
    headers = [str(h).strip() or f"#{i + 1}" for i, h in enumerate(table[0])]
    return headers, table[1:]


def _read_csv(path: Path) -> list[list[str]]:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "cp1254", "latin-1"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
    return [row for row in csv.reader(text.splitlines(), delimiter=delimiter)]


_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
_REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


def _col_index(ref: str) -> int:
    letters = "".join(ch for ch in ref if ch.isalpha())
    index = 0
    for ch in letters:
        index = index * 26 + (ord(ch.upper()) - 64)
    return index - 1


def _read_xlsx(path: Path) -> list[list]:
    """Minimal reader for the first worksheet of an .xlsx file (values only, no formulas)."""
    try:
        book = zipfile.ZipFile(path)
    except zipfile.BadZipFile as exc:
        raise ValidationError("import.unsupported") from exc
    with book:
        names = book.namelist()
        shared: list[str] = []
        if "xl/sharedStrings.xml" in names:
            root = ElementTree.fromstring(book.read("xl/sharedStrings.xml"))
            for si in root.findall("m:si", _NS):
                shared.append("".join(node.text or "" for node in si.iter(f"{{{_NS['m']}}}t")))
        sheet = _first_sheet(book, names)
        root = ElementTree.fromstring(book.read(sheet))
        rows: list[list] = []
        for row in root.iter(f"{{{_NS['m']}}}row"):
            values: dict[int, object] = {}
            for cell in row.findall("m:c", _NS):
                kind = cell.get("t")
                ref = cell.get("r") or ""
                col = _col_index(ref) if ref else len(values)
                if kind == "inlineStr":
                    value = "".join(node.text or "" for node in cell.iter(f"{{{_NS['m']}}}t"))
                else:
                    node = cell.find("m:v", _NS)
                    text = node.text if node is not None else None
                    if text is None:
                        continue
                    if kind == "s":
                        value = shared[int(text)]
                    elif kind in ("str", "e"):
                        value = text
                    elif kind == "b":
                        value = "TRUE" if text == "1" else "FALSE"
                    else:
                        number = float(text)
                        value = int(number) if number.is_integer() else number
                values[col] = value
            if values:
                rows.append([values.get(i, "") for i in range(max(values) + 1)])
        return rows


def _first_sheet(book: zipfile.ZipFile, names: list[str]) -> str:
    """Path of the first sheet listed in the workbook (falls back to sheet1.xml)."""
    try:
        workbook = ElementTree.fromstring(book.read("xl/workbook.xml"))
        first = workbook.find("m:sheets/m:sheet", _NS)
        rel_id = first.get(_REL_NS) if first is not None else None
        rels = ElementTree.fromstring(book.read("xl/_rels/workbook.xml.rels"))
        for rel in rels:
            if rel.get("Id") == rel_id:
                target = rel.get("Target").lstrip("/")
                target = target if target.startswith("xl/") else "xl/" + target
                if target in names:
                    return target
    except (KeyError, ElementTree.ParseError, AttributeError):
        pass
    sheets = sorted(n for n in names if n.startswith("xl/worksheets/sheet"))
    if not sheets:
        raise ValidationError("import.empty")
    return sheets[0]


# ------------------------------------------------------------------ importing
def _status_lookup() -> dict[str, str]:
    """'Delivered', 'teslim edildi', 'in transit', 'yolda'… → status key."""
    table = {}
    for status in LOAD_STATUSES:
        table[_norm(status.replace("_", " "))] = status
        for text in STRINGS[f"status.{status}"].values():
            table[_norm(text)] = status
    table.update({"canceled": "cancelled", "complete": "delivered", "completed": "delivered",
                  "booked": "planned", "assigned": "dispatched", "loaded": "in_transit"})
    return table


@dataclass
class ImportResult:
    imported: int = 0
    duplicates: int = 0
    errors: list[tuple[int, str]] = field(default_factory=list)  # (spreadsheet row number, i18n key)
    created_trucks: list[str] = field(default_factory=list)
    created_drivers: list[str] = field(default_factory=list)


def import_loads(db: Database, rows: list[list], mapping: dict[str, int], create_missing: bool = True,
                 skip_duplicates: bool = True) -> ImportResult:
    """Create one load per row. Bad rows are reported and skipped; they never stop the import."""
    result = ImportResult()
    statuses = _status_lookup()
    existing = {load.load_number for load in db.list_loads() if load.load_number}
    trucks = {}
    for truck in db.list_trucks():
        for code in (truck.plate, truck.unit_number):
            if code:
                trucks[code.upper()] = truck.id
    drivers = {d.name.casefold(): d.id for d in db.list_drivers()}

    def cell(row: list, name: str):
        index = mapping.get(name)
        if index is None or index >= len(row):
            return None
        value = row[index]
        return value.strip() if isinstance(value, str) else value

    for number, row in enumerate(rows, start=2):  # row 1 is the header in the spreadsheet
        try:
            load = Load()
            for name in ("broker", "pickup_location", "delivery_location", "commodity", "notes"):
                value = cell(row, name)
                setattr(load, name, str(value) if value not in (None, "") else None)
            for name in NUMBER_FIELDS:
                setattr(load, name, parse_number(cell(row, name)))
            for name in DATE_FIELDS:
                setattr(load, name, parse_date(cell(row, name)))
            raw_number = cell(row, "load_number")
            if isinstance(raw_number, float) and raw_number.is_integer():
                raw_number = int(raw_number)
            load.load_number = normalize_load_number(str(raw_number) if raw_number not in (None, "") else None)
            status = cell(row, "status")
            if status not in (None, ""):
                load.status = statuses.get(_norm(str(status)))
                if load.status is None:
                    raise ValidationError("error.invalid_status")
            tonu = cell(row, "tonu")
            load.is_tonu = str(tonu).strip().lower() in ("1", "yes", "y", "true", "x", "evet", "tonu")
            if not any(getattr(load, f) for f in ("load_number", "pickup_location", "delivery_location", "rate")):
                continue  # nothing useful in this row (e.g. a totals line)

            if skip_duplicates and load.load_number and load.load_number in existing:
                result.duplicates += 1
                continue

            truck_code = cell(row, "truck")
            if truck_code not in (None, ""):
                code = str(int(truck_code) if isinstance(truck_code, float) and truck_code.is_integer()
                           else truck_code).strip()
                load.truck_id = trucks.get(code.upper())
                if load.truck_id is None:
                    if not create_missing:
                        raise ValidationError("import.unknown_truck")
                    load.truck_id = db.add_truck(Truck(unit_number=code))
                    trucks[code.upper()] = load.truck_id
                    result.created_trucks.append(code)

            driver_name = cell(row, "driver")
            if driver_name not in (None, ""):
                name = str(driver_name).strip()
                load.driver_id = drivers.get(name.casefold())
                if load.driver_id is None:
                    if not create_missing:
                        raise ValidationError("import.unknown_driver")
                    load.driver_id = db.add_driver(Driver(name=name))
                    drivers[name.casefold()] = load.driver_id
                    result.created_drivers.append(name)

            db.add_load(load)
            if load.load_number:
                existing.add(load.load_number)
            result.imported += 1
        except ValidationError as exc:
            result.errors.append((number, exc.key))
    return result


TEMPLATE_HEADERS = ["Load #", "Truck", "Driver", "Broker", "Pickup", "Pickup Date", "Delivery", "Delivery Date",
                    "Rate", "Extra Pay", "Loaded Miles", "Dead Miles", "Weight", "Commodity", "Status", "TONU", "Notes"]


def write_template(path: str | Path) -> Path:
    """A CSV with the expected headers and one example row, to start a spreadsheet from."""
    path = Path(path)
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(TEMPLATE_HEADERS)
        writer.writerow(["123456", "101", "John Miller", "Acme Logistics", "Chicago, IL", "2026-01-05",
                         "Dallas, TX", "2026-01-07", "2850", "150", "925", "40", "42000", "Paper goods",
                         "Delivered", "", ""])
    return path
