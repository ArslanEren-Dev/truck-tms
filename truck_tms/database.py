"""SQLite storage layer for Truck TMS.

All data lives in a single SQLite file. The UI never runs SQL directly;
it goes through :class:`Database`, which keeps validation in one place
and makes the logic easy to test without a GUI.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
from dataclasses import dataclass, fields
from datetime import date, datetime
from pathlib import Path

from .weeks import sqlite_week_expr, week_start

SCHEMA_VERSION = 2

TRUCK_STATUSES = ("active", "maintenance", "inactive")
DRIVER_STATUSES = ("active", "inactive")
PAY_TYPES = ("percent", "per_mile", "weekly")
LOAD_STATUSES = (
    "planned",
    "dispatched",
    "in_transit",
    "delivered",
    "invoiced",
    "paid",
    "cancelled",
)
EXPENSE_CATEGORIES = (
    "fuel",
    "maintenance",
    "repair",
    "tolls",
    "insurance",
    "permits",
    "other",
)
SERVICE_TYPES = (
    "pm_service",
    "oil_change",
    "tires",
    "brakes",
    "engine",
    "transmission",
    "dot_inspection",
    "repair",
    "other",
)
STATEMENT_STATUSES = ("draft", "final", "paid")
DOCUMENT_KINDS = ("rate_con", "bol", "pod", "invoice", "receipt", "other")
ITEM_KINDS = ("driver_addition", "driver_deduction", "owner_addition", "owner_deduction")

# Common US truck makes and models (the make/model fields still accept any text).
TRUCK_MAKES = {
    "Freightliner": ["Cascadia", "Columbia", "Coronado", "M2 106", "122SD"],
    "Kenworth": ["T680", "T880", "W900", "W990", "T800", "T370"],
    "Peterbilt": ["579", "589", "389", "567", "567 Heritage", "348"],
    "Volvo": ["VNL 300", "VNL 640", "VNL 760", "VNL 860", "VNR", "VHD"],
    "Mack": ["Anthem", "Pinnacle", "Granite", "LR"],
    "International": ["LT", "LT625", "RH", "HX", "ProStar", "LoneStar", "MV"],
    "Western Star": ["49X", "57X", "47X", "5700XE", "4900"],
    "Navistar": ["ProStar", "9900i"],
    "Ford": ["F-750", "F-650"],
    "Hino": ["L6", "XL8"],
    "Isuzu": ["NRR", "FTR"],
}

DEFAULT_SETTINGS = {
    "language": "en",
    "theme": "light",
    "company_name": "",
    "company_address": "",
    "currency": "$",
    "distance_unit": "mi",
    "week_start": "0",  # 0 = Monday … 6 = Sunday
    "dispatch_fee_percent": "0",
}

TABLES = """
CREATE TABLE IF NOT EXISTS drivers (
    id             INTEGER PRIMARY KEY,
    name           TEXT NOT NULL,
    phone          TEXT,
    email          TEXT,
    license_number TEXT,
    license_expiry TEXT,
    pay_type       TEXT NOT NULL DEFAULT 'percent',
    pay_rate       REAL,
    status         TEXT NOT NULL DEFAULT 'active',
    notes          TEXT,
    created_at     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS trucks (
    id                   INTEGER PRIMARY KEY,
    plate                TEXT UNIQUE COLLATE NOCASE,
    unit_number          TEXT,
    make                 TEXT,
    model                TEXT,
    year                 INTEGER,
    vin                  TEXT,
    odometer             INTEGER,
    owner_name           TEXT,
    driver_id            INTEGER REFERENCES drivers(id) ON DELETE SET NULL,
    dispatch_fee_percent REAL,
    status               TEXT NOT NULL DEFAULT 'active',
    notes                TEXT,
    created_at           TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS plate_history (
    id         INTEGER PRIMARY KEY,
    truck_id   INTEGER NOT NULL REFERENCES trucks(id) ON DELETE CASCADE,
    old_plate  TEXT NOT NULL,
    new_plate  TEXT NOT NULL,
    changed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS loads (
    id                INTEGER PRIMARY KEY,
    truck_id          INTEGER REFERENCES trucks(id) ON DELETE SET NULL,
    driver_id         INTEGER REFERENCES drivers(id) ON DELETE SET NULL,
    load_number       TEXT,
    broker            TEXT,
    pickup_location   TEXT,
    pickup_date       TEXT,
    delivery_location TEXT,
    delivery_date     TEXT,
    rate              REAL,
    extra_pay         REAL,
    loaded_miles      REAL,
    dead_miles        REAL,
    is_tonu           INTEGER NOT NULL DEFAULT 0,
    weight            REAL,
    commodity         TEXT,
    statement_week    TEXT,
    status            TEXT NOT NULL DEFAULT 'planned',
    notes             TEXT,
    created_at        TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS expenses (
    id          INTEGER PRIMARY KEY,
    truck_id    INTEGER NOT NULL REFERENCES trucks(id) ON DELETE CASCADE,
    date        TEXT NOT NULL,
    category    TEXT NOT NULL,
    amount      REAL NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS maintenance (
    id                INTEGER PRIMARY KEY,
    truck_id          INTEGER NOT NULL REFERENCES trucks(id) ON DELETE CASCADE,
    date              TEXT NOT NULL,
    service_type      TEXT NOT NULL,
    odometer          INTEGER,
    cost              REAL,
    vendor            TEXT,
    description       TEXT,
    next_due_date     TEXT,
    next_due_odometer INTEGER
);

CREATE TABLE IF NOT EXISTS statements (
    id                   INTEGER PRIMARY KEY,
    truck_id             INTEGER NOT NULL REFERENCES trucks(id) ON DELETE CASCADE,
    week_start           TEXT NOT NULL,
    fuel_amount          REAL NOT NULL DEFAULT 0,
    fuel_gallons         REAL,
    tolls                REAL NOT NULL DEFAULT 0,
    dispatch_fee_percent REAL NOT NULL DEFAULT 0,
    dispatch_fee_fixed   REAL NOT NULL DEFAULT 0,
    driver_pay_override  REAL,
    deduct_driver_pay    INTEGER NOT NULL DEFAULT 1,
    driver_paid_amount   REAL,
    driver_paid_date     TEXT,
    status               TEXT NOT NULL DEFAULT 'draft',
    notes                TEXT,
    UNIQUE (truck_id, week_start)
);

CREATE TABLE IF NOT EXISTS statement_items (
    id           INTEGER PRIMARY KEY,
    statement_id INTEGER NOT NULL REFERENCES statements(id) ON DELETE CASCADE,
    kind         TEXT NOT NULL,
    description  TEXT,
    amount       REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
    id        INTEGER PRIMARY KEY,
    load_id   INTEGER NOT NULL REFERENCES loads(id) ON DELETE CASCADE,
    kind      TEXT NOT NULL DEFAULT 'other',
    file_name TEXT NOT NULL,
    stored_as TEXT NOT NULL,
    size      INTEGER NOT NULL DEFAULT 0,
    added_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""

INDEXES = """
CREATE INDEX IF NOT EXISTS idx_loads_truck ON loads(truck_id);
CREATE INDEX IF NOT EXISTS idx_loads_driver ON loads(driver_id);
CREATE INDEX IF NOT EXISTS idx_expenses_truck ON expenses(truck_id);
CREATE INDEX IF NOT EXISTS idx_maintenance_truck ON maintenance(truck_id);
CREATE INDEX IF NOT EXISTS idx_statements_truck ON statements(truck_id);
CREATE INDEX IF NOT EXISTS idx_documents_load ON documents(load_id);
"""

# Columns added after v0.1 — added with ALTER TABLE to databases created by older versions.
ADDED_COLUMNS = {
    "loads": {
        "driver_id": "INTEGER REFERENCES drivers(id) ON DELETE SET NULL",
        "extra_pay": "REAL",
        "loaded_miles": "REAL",
        "dead_miles": "REAL",
        "is_tonu": "INTEGER NOT NULL DEFAULT 0",
        "statement_week": "TEXT",
    },
}


class ValidationError(ValueError):
    """Raised for invalid user input.

    ``key`` is an i18n key so the UI can show a translated message.
    """

    def __init__(self, key: str):
        super().__init__(key)
        self.key = key


# --------------------------------------------------------------------- records
@dataclass
class Driver:
    name: str
    phone: str | None = None
    email: str | None = None
    license_number: str | None = None
    license_expiry: str | None = None
    pay_type: str = "percent"
    pay_rate: float | None = None
    status: str = "active"
    notes: str | None = None
    id: int | None = None


@dataclass
class Truck:
    plate: str | None = None
    unit_number: str | None = None
    make: str | None = None
    model: str | None = None
    year: int | None = None
    vin: str | None = None
    odometer: int | None = None
    owner_name: str | None = None
    driver_id: int | None = None
    dispatch_fee_percent: float | None = None
    status: str = "active"
    notes: str | None = None
    id: int | None = None

    @property
    def label(self) -> str:
        """'34 ABC 123 (#101)', or whichever of plate / unit number exists."""
        if self.plate and self.unit_number:
            return f"{self.plate} ({self.unit_number})"
        return self.plate or self.unit_number or "?"


@dataclass
class Load:
    truck_id: int | None = None
    driver_id: int | None = None
    load_number: str | None = None
    broker: str | None = None
    pickup_location: str | None = None
    pickup_date: str | None = None
    delivery_location: str | None = None
    delivery_date: str | None = None
    rate: float | None = None
    extra_pay: float | None = None
    loaded_miles: float | None = None
    dead_miles: float | None = None
    is_tonu: bool = False
    weight: float | None = None
    commodity: str | None = None
    statement_week: str | None = None  # manual override; None = automatic
    status: str = "planned"
    notes: str | None = None
    id: int | None = None

    @property
    def report_date(self) -> str | None:
        """Date used to place the load in a week / period."""
        return self.delivery_date or self.pickup_date

    @property
    def gross(self) -> float:
        """Rate plus extra pay (detention, layover, lumper…)."""
        return (self.rate or 0) + (self.extra_pay or 0)

    @property
    def total_miles(self) -> float:
        return (self.loaded_miles or 0) + (self.dead_miles or 0)

    @property
    def rate_per_mile(self) -> float | None:
        return self.gross / self.total_miles if self.total_miles else None


@dataclass
class Expense:
    truck_id: int
    date: str
    category: str
    amount: float
    description: str | None = None
    id: int | None = None


@dataclass
class Maintenance:
    truck_id: int
    date: str
    service_type: str
    odometer: int | None = None
    cost: float | None = None
    vendor: str | None = None
    description: str | None = None
    next_due_date: str | None = None
    next_due_odometer: int | None = None
    id: int | None = None


@dataclass
class Statement:
    truck_id: int
    week_start: str
    fuel_amount: float = 0
    fuel_gallons: float | None = None
    tolls: float = 0
    dispatch_fee_percent: float = 0
    dispatch_fee_fixed: float = 0
    driver_pay_override: float | None = None
    deduct_driver_pay: bool = True
    driver_paid_amount: float | None = None
    driver_paid_date: str | None = None
    status: str = "draft"
    notes: str | None = None
    id: int | None = None


@dataclass
class StatementItem:
    kind: str
    amount: float
    description: str | None = None
    statement_id: int | None = None
    id: int | None = None


@dataclass
class Document:
    """A file attached to a load (rate confirmation, BOL, POD…). The file itself is copied
    into the documents folder next to the data file; ``stored_as`` is its path in that folder."""

    load_id: int
    kind: str
    file_name: str
    stored_as: str
    size: int = 0
    added_at: str = ""
    id: int | None = None


@dataclass
class PlateChange:
    truck_id: int
    old_plate: str
    new_plate: str
    changed_at: str
    id: int | None = None


# --------------------------------------------------------------------- helpers
def default_db_path() -> Path:
    """Database location: ``$TRUCK_TMS_DB`` or ``~/.truck_tms/tms.db``."""
    env = os.environ.get("TRUCK_TMS_DB")
    if env:
        return Path(env)
    return Path.home() / ".truck_tms" / "tms.db"


def backups_folder(db_path: str | Path) -> Path:
    return Path(db_path).resolve().parent / "backups"


def auto_backup(db_path: str | Path, keep: int = 14, today: date | None = None) -> Path | None:
    """Copy the data file to ``backups/<name>_<date>.db`` once a day and keep the newest ``keep`` copies."""
    path = Path(db_path)
    if str(db_path) == ":memory:" or not path.is_file():
        return None
    folder = backups_folder(path)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{path.stem}_{(today or date.today()).isoformat()}.db"
    if not target.exists():
        src = sqlite3.connect(str(path))
        dst = sqlite3.connect(str(target))
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
    copies = sorted(folder.glob(f"{path.stem}_????-??-??.db"))
    for old in copies[:-keep]:
        old.unlink()
    return target


def normalize_plate(plate: str | None) -> str:
    """Upper-case a plate and collapse repeated spaces: ' 34 abc  123 ' -> '34 ABC 123'."""
    return " ".join((plate or "").split()).upper()


def normalize_load_number(value: str | None) -> str | None:
    """Load numbers always start with '#': '1234' -> '#1234'."""
    value = (value or "").strip().lstrip("#").strip()
    return f"#{value}" if value else None


def _clean(value):
    """Turn empty strings into None so optional fields stay NULL."""
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def _clean_all(obj) -> None:
    for f in fields(obj):
        setattr(obj, f.name, _clean(getattr(obj, f.name)))


def _check_date(value: str | None) -> None:
    if value is None:
        return
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ValidationError("error.invalid_date") from exc


def _non_negative(obj, *names: str, integer: bool = False) -> None:
    for name in names:
        value = getattr(obj, name)
        if value is None:
            continue
        value = int(round(float(value))) if integer else float(value)
        if value < 0:
            raise ValidationError("error.negative_number")
        setattr(obj, name, value)


def _columns(cls) -> list[str]:
    return [f.name for f in fields(cls) if f.name != "id"]


def _from_row(cls, row: sqlite3.Row):
    obj = cls(**{f.name: row[f.name] for f in fields(cls)})
    for flag in ("is_tonu", "deduct_driver_pay"):
        if hasattr(obj, flag):
            setattr(obj, flag, bool(getattr(obj, flag)))
    return obj


class Database:
    def __init__(self, path: str | Path = ":memory:"):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = str(path)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        try:
            self.conn.executescript(TABLES)
            self._migrate()
            self.conn.executescript(INDEXES)
        except sqlite3.DatabaseError as exc:  # e.g. a file that is not an SQLite database
            self.conn.close()
            raise ValidationError("file.not_valid") from exc
        self.conn.execute("PRAGMA foreign_keys = ON")

    def close(self) -> None:
        self.conn.close()

    @property
    def change_count(self) -> int:
        """Number of rows changed since the file was opened (used for the 'saved' indicator)."""
        return self.conn.total_changes

    def backup_to(self, target: str | Path) -> Path:
        """Write a consistent copy of the whole database to ``target``."""
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.resolve() == Path(self.path).resolve():
            raise ValidationError("file.backup_same")
        dst = sqlite3.connect(str(target))
        try:
            self.conn.backup(dst)
        finally:
            dst.close()
        # attached documents live next to the data file; copy them next to the backup the same way
        documents = self.documents_folder(create=False)
        if self.path != ":memory:" and documents.is_dir() and any(documents.iterdir()):
            shutil.copytree(documents, target.with_name(f"{target.stem}_documents"), dirs_exist_ok=True)
        return target

    # ---------------------------------------------------------------- migration
    def _table_info(self, table: str) -> dict[str, sqlite3.Row]:
        return {r["name"]: r for r in self.conn.execute(f"PRAGMA table_info({table})")}

    def _migrate(self) -> None:
        """Upgrade databases created by older versions (foreign keys are still off here)."""
        version = self.conn.execute("PRAGMA user_version").fetchone()[0]
        if version >= SCHEMA_VERSION:
            return
        with self.conn:
            trucks = self._table_info("trucks")
            if trucks["plate"]["notnull"] or "odometer" not in trucks:
                # v0.1: plate was NOT NULL — rebuild so a truck can have only a unit number.
                # Build trucks_new, copy, drop the old table, rename (the documented SQLite
                # way; other tables keep referencing "trucks" by name).
                start = TABLES.index("CREATE TABLE IF NOT EXISTS trucks (")
                create = TABLES[start:TABLES.index(";", start)]
                create = create.replace("IF NOT EXISTS trucks (", "trucks_new (")
                cols = ", ".join(c for c in trucks if c in self._new_truck_columns())
                self.conn.execute(create)
                self.conn.execute(f"INSERT INTO trucks_new ({cols}) SELECT {cols} FROM trucks")
                self.conn.execute("DROP TABLE trucks")
                self.conn.execute("ALTER TABLE trucks_new RENAME TO trucks")
            for table, columns in ADDED_COLUMNS.items():
                existing = self._table_info(table)
                for name, decl in columns.items():
                    if name not in existing:
                        self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")
            if "miles" in self._table_info("loads"):
                self.conn.execute(
                    "UPDATE loads SET loaded_miles = miles WHERE loaded_miles IS NULL AND miles IS NOT NULL"
                )
            self.conn.execute(
                "UPDATE loads SET load_number = '#' || load_number"
                " WHERE load_number IS NOT NULL AND load_number NOT LIKE '#%'"
            )
            self.conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    @staticmethod
    def _new_truck_columns() -> set[str]:
        return set(_columns(Truck)) | {"id", "created_at"}

    # ------------------------------------------------------------------ helpers
    def _insert(self, table: str, obj) -> int:
        cols = _columns(type(obj))
        sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})"
        cur = self.conn.execute(sql, [getattr(obj, c) for c in cols])
        return cur.lastrowid

    def _update(self, table: str, obj) -> None:
        cols = _columns(type(obj))
        sql = f"UPDATE {table} SET {', '.join(f'{c} = ?' for c in cols)} WHERE id = ?"
        self.conn.execute(sql, [getattr(obj, c) for c in cols] + [obj.id])

    def _get(self, cls, table: str, record_id: int | None):
        if record_id is None:
            return None
        row = self.conn.execute(f"SELECT * FROM {table} WHERE id = ?", (record_id,)).fetchone()
        return _from_row(cls, row) if row else None

    def _delete(self, table: str, record_id: int) -> None:
        with self.conn:
            self.conn.execute(f"DELETE FROM {table} WHERE id = ?", (record_id,))

    @property
    def week_start_dow(self) -> int:
        try:
            return int(self.get_settings()["week_start"]) % 7
        except ValueError:
            return 0

    # ------------------------------------------------------------------ drivers
    def _validate_driver(self, driver: Driver) -> Driver:
        _clean_all(driver)
        if not driver.name:
            raise ValidationError("error.name_required")
        if driver.pay_type not in PAY_TYPES:
            raise ValidationError("error.invalid_pay_type")
        if driver.status not in DRIVER_STATUSES:
            raise ValidationError("error.invalid_status")
        _check_date(driver.license_expiry)
        _non_negative(driver, "pay_rate")
        return driver

    def add_driver(self, driver: Driver) -> int:
        driver = self._validate_driver(driver)
        with self.conn:
            driver.id = self._insert("drivers", driver)
        return driver.id

    def update_driver(self, driver: Driver) -> None:
        driver = self._validate_driver(driver)
        with self.conn:
            self._update("drivers", driver)

    def delete_driver(self, driver_id: int) -> None:
        """Delete a driver; their loads and trucks are kept without a driver."""
        self._delete("drivers", driver_id)

    def get_driver(self, driver_id: int | None) -> Driver | None:
        return self._get(Driver, "drivers", driver_id)

    def list_drivers(self, search: str | None = None, active_only: bool = False) -> list[Driver]:
        where, params = [], []
        if search:
            like = f"%{search.strip()}%"
            where.append("(name LIKE ? OR phone LIKE ? OR email LIKE ? OR license_number LIKE ?)")
            params += [like] * 4
        if active_only:
            where.append("status = 'active'")
        sql = "SELECT * FROM drivers" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY name"
        return [_from_row(Driver, r) for r in self.conn.execute(sql, params)]

    # ------------------------------------------------------------------- trucks
    def _validate_truck(self, truck: Truck) -> Truck:
        _clean_all(truck)
        truck.plate = normalize_plate(truck.plate) or None
        if truck.unit_number:
            truck.unit_number = truck.unit_number.upper()
        if not truck.plate and not truck.unit_number:
            raise ValidationError("error.plate_or_unit_required")
        if truck.status not in TRUCK_STATUSES:
            raise ValidationError("error.invalid_status")
        if truck.vin:
            truck.vin = truck.vin.upper()
        if truck.year is not None:
            truck.year = int(truck.year)
            if not 1950 <= truck.year <= 2100:
                raise ValidationError("error.invalid_year")
        _non_negative(truck, "odometer", integer=True)
        _non_negative(truck, "dispatch_fee_percent")
        if truck.dispatch_fee_percent is not None and truck.dispatch_fee_percent > 100:
            raise ValidationError("error.invalid_percent")
        if truck.driver_id is not None and self.get_driver(truck.driver_id) is None:
            raise ValidationError("error.not_found")
        if truck.unit_number:
            row = self.conn.execute(
                "SELECT id FROM trucks WHERE unit_number = ? COLLATE NOCASE AND id IS NOT ?",
                (truck.unit_number, truck.id),
            ).fetchone()
            if row:
                raise ValidationError("error.unit_exists")
        return truck

    def add_truck(self, truck: Truck) -> int:
        truck = self._validate_truck(truck)
        try:
            with self.conn:
                truck.id = self._insert("trucks", truck)
        except sqlite3.IntegrityError as exc:
            raise ValidationError("error.plate_exists") from exc
        return truck.id

    def update_truck(self, truck: Truck) -> None:
        """Save a truck. A plate change is recorded in the plate history."""
        if truck.id is None:
            raise ValueError("truck.id is required for update")
        old = self.get_truck(truck.id)
        if old is None:
            raise ValidationError("error.not_found")
        truck = self._validate_truck(truck)
        try:
            with self.conn:
                self._update("trucks", truck)
                if (old.plate or "") != (truck.plate or ""):
                    self.conn.execute(
                        "INSERT INTO plate_history (truck_id, old_plate, new_plate, changed_at)"
                        " VALUES (?, ?, ?, ?)",
                        (truck.id, old.plate or "—", truck.plate or "—",
                         datetime.now().isoformat(timespec="seconds")),
                    )
        except sqlite3.IntegrityError as exc:
            raise ValidationError("error.plate_exists") from exc

    def change_plate(self, truck_id: int, new_plate: str) -> None:
        truck = self.get_truck(truck_id)
        if truck is None:
            raise ValidationError("error.not_found")
        truck.plate = new_plate
        self.update_truck(truck)

    def delete_truck(self, truck_id: int) -> None:
        """Delete a truck. Its loads are kept (unassigned); expenses, maintenance and statements are removed."""
        self._delete("trucks", truck_id)

    def get_truck(self, truck_id: int | None) -> Truck | None:
        return self._get(Truck, "trucks", truck_id)

    def find_truck(self, code: str) -> Truck | None:
        """Find a truck by plate or unit number."""
        row = self.conn.execute(
            "SELECT * FROM trucks WHERE plate = ? OR unit_number = ? COLLATE NOCASE",
            (normalize_plate(code), code.strip()),
        ).fetchone()
        return _from_row(Truck, row) if row else None

    def list_trucks(self, search: str | None = None) -> list[Truck]:
        sql = "SELECT * FROM trucks"
        params: list = []
        if search:
            like = f"%{search.strip()}%"
            sql += (" WHERE plate LIKE ? OR unit_number LIKE ? OR make LIKE ? OR model LIKE ?"
                    " OR vin LIKE ? OR owner_name LIKE ?")
            params = [like] * 6
        sql += " ORDER BY COALESCE(unit_number, plate), plate"
        return [_from_row(Truck, r) for r in self.conn.execute(sql, params)]

    def plate_history(self, truck_id: int) -> list[PlateChange]:
        rows = self.conn.execute(
            "SELECT * FROM plate_history WHERE truck_id = ? ORDER BY changed_at DESC, id DESC",
            (truck_id,),
        )
        return [_from_row(PlateChange, r) for r in rows]

    def _bump_odometer(self, truck_id: int, odometer: int | None) -> None:
        if odometer is not None:
            self.conn.execute(
                "UPDATE trucks SET odometer = ? WHERE id = ? AND (odometer IS NULL OR odometer < ?)",
                (odometer, truck_id, odometer),
            )

    # -------------------------------------------------------------------- loads
    def _validate_load(self, load: Load) -> Load:
        _clean_all(load)
        load.load_number = normalize_load_number(load.load_number)
        load.is_tonu = bool(load.is_tonu)
        if load.status is None:
            load.status = "planned"
        if load.status not in LOAD_STATUSES:
            raise ValidationError("error.invalid_status")
        _check_date(load.pickup_date)
        _check_date(load.delivery_date)
        _check_date(load.statement_week)
        if load.pickup_date and load.delivery_date and load.delivery_date < load.pickup_date:
            raise ValidationError("error.delivery_before_pickup")
        _non_negative(load, "rate", "extra_pay", "loaded_miles", "dead_miles", "weight")
        if load.statement_week:
            load.statement_week = week_start(load.statement_week, self.week_start_dow).isoformat()
        if load.truck_id is not None and self.get_truck(load.truck_id) is None:
            raise ValidationError("error.not_found")
        if load.driver_id is not None and self.get_driver(load.driver_id) is None:
            raise ValidationError("error.not_found")
        return load

    def add_load(self, load: Load) -> int:
        load = self._validate_load(load)
        with self.conn:
            load.id = self._insert("loads", load)
        return load.id

    def update_load(self, load: Load) -> None:
        if load.id is None:
            raise ValueError("load.id is required for update")
        load = self._validate_load(load)
        with self.conn:
            self._update("loads", load)

    def delete_load(self, load_id: int) -> None:
        """Delete a load together with its attached documents (rows and files)."""
        folder = self.documents_folder(create=False) / f"load_{load_id}"
        self._delete("loads", load_id)
        if folder.is_dir():
            shutil.rmtree(folder, ignore_errors=True)

    # ---------------------------------------------------------------- documents
    def documents_folder(self, create: bool = True) -> Path:
        """Attached files live next to the data file: ``tms.db`` → ``tms_documents/load_<id>/…``."""
        if self.path == ":memory:":
            if getattr(self, "_memory_docs", None) is None:
                self._memory_docs = Path(tempfile.mkdtemp(prefix="truck_tms_documents_"))
            folder = self._memory_docs
        else:
            db_file = Path(self.path).resolve()
            folder = db_file.with_name(f"{db_file.stem}_documents")
        if create:
            folder.mkdir(parents=True, exist_ok=True)
        return folder

    def add_document(self, load_id: int, source: str | Path, kind: str = "other") -> Document:
        """Copy ``source`` into the documents folder and attach it to the load."""
        source = Path(source)
        if self.get_load(load_id) is None:
            raise ValidationError("error.not_found")
        if kind not in DOCUMENT_KINDS:
            raise ValidationError("error.invalid_category")
        if not source.is_file():
            raise ValidationError("doc.missing_file")
        target_dir = self.documents_folder() / f"load_{load_id}"
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / source.name
        counter = 2
        while target.exists():  # never overwrite another attachment with the same name
            target = target_dir / f"{source.stem} ({counter}){source.suffix}"
            counter += 1
        shutil.copy2(source, target)
        doc = Document(load_id=load_id, kind=kind, file_name=target.name,
                       stored_as=target.relative_to(self.documents_folder()).as_posix(),
                       size=target.stat().st_size, added_at=datetime.now().isoformat(timespec="seconds"))
        with self.conn:
            doc.id = self._insert("documents", doc)
        return doc

    def list_documents(self, load_id: int | None = None) -> list[Document]:
        sql, params = "SELECT * FROM documents", []
        if load_id is not None:
            sql += " WHERE load_id = ?"
            params.append(load_id)
        sql += " ORDER BY id"
        return [_from_row(Document, r) for r in self.conn.execute(sql, params)]

    def document_counts(self) -> dict[int, int]:
        rows = self.conn.execute("SELECT load_id, COUNT(*) AS n FROM documents GROUP BY load_id")
        return {r["load_id"]: r["n"] for r in rows}

    def document_path(self, doc: Document) -> Path:
        return self.documents_folder(create=False) / doc.stored_as

    def update_document_kind(self, document_id: int, kind: str) -> None:
        if kind not in DOCUMENT_KINDS:
            raise ValidationError("error.invalid_category")
        with self.conn:
            self.conn.execute("UPDATE documents SET kind = ? WHERE id = ?", (kind, document_id))

    def delete_document(self, document_id: int) -> None:
        doc = self._get(Document, "documents", document_id)
        if doc is None:
            return
        self._delete("documents", document_id)
        path = self.document_path(doc)
        if path.is_file():
            path.unlink()

    def get_load(self, load_id: int | None) -> Load | None:
        return self._get(Load, "loads", load_id)

    def load_week(self, load: Load) -> str | None:
        """Statement week (start date) the load belongs to."""
        if load.statement_week:
            return load.statement_week
        if load.report_date:
            return week_start(load.report_date, self.week_start_dow).isoformat()
        return None

    def list_loads(
        self,
        truck_id: int | None = None,
        status: str | None = None,
        search: str | None = None,
        start: str | None = None,
        end: str | None = None,
        include_cancelled: bool = True,
        driver_id: int | None = None,
        week: str | None = None,
    ) -> list[Load]:
        """List loads.

        ``start``/``end`` (inclusive, YYYY-MM-DD) filter on the delivery date, or the
        pickup date when there is no delivery date. ``week`` filters on the statement week.
        With ``include_cancelled=False`` cancelled loads are skipped unless they are TONU.
        """
        where, params = [], []
        if truck_id is not None:
            where.append("truck_id = ?")
            params.append(truck_id)
        if driver_id is not None:
            where.append("driver_id = ?")
            params.append(driver_id)
        if status:
            where.append("status = ?")
            params.append(status)
        if not include_cancelled:
            where.append("(status != 'cancelled' OR is_tonu = 1)")
        if search:
            like = f"%{search.strip()}%"
            where.append(
                "(load_number LIKE ? OR broker LIKE ? OR pickup_location LIKE ?"
                " OR delivery_location LIKE ? OR commodity LIKE ?)"
            )
            params += [like] * 5
        report_date = "COALESCE(delivery_date, pickup_date)"
        if start:
            where.append(f"{report_date} >= ?")
            params.append(start)
        if end:
            where.append(f"{report_date} <= ?")
            params.append(end)
        if week:
            expr = f"COALESCE(statement_week, {sqlite_week_expr(report_date, self.week_start_dow)})"
            where.append(f"{expr} = ?")
            params.append(week)
        sql = "SELECT * FROM loads"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += f" ORDER BY {report_date} IS NULL, {report_date} DESC, id DESC"
        return [_from_row(Load, r) for r in self.conn.execute(sql, params)]

    # ----------------------------------------------------------------- expenses
    def _validate_expense(self, expense: Expense) -> Expense:
        _clean_all(expense)
        if expense.truck_id is None or self.get_truck(expense.truck_id) is None:
            raise ValidationError("error.truck_required")
        if not expense.date:
            raise ValidationError("error.date_required")
        _check_date(expense.date)
        if expense.category not in EXPENSE_CATEGORIES:
            raise ValidationError("error.invalid_category")
        if expense.amount is None:
            raise ValidationError("error.amount_required")
        _non_negative(expense, "amount")
        return expense

    def add_expense(self, expense: Expense) -> int:
        expense = self._validate_expense(expense)
        with self.conn:
            expense.id = self._insert("expenses", expense)
        return expense.id

    def update_expense(self, expense: Expense) -> None:
        if expense.id is None:
            raise ValueError("expense.id is required for update")
        expense = self._validate_expense(expense)
        with self.conn:
            self._update("expenses", expense)

    def delete_expense(self, expense_id: int) -> None:
        self._delete("expenses", expense_id)

    def get_expense(self, expense_id: int | None) -> Expense | None:
        return self._get(Expense, "expenses", expense_id)

    def list_expenses(self, truck_id: int | None = None, start: str | None = None,
                      end: str | None = None) -> list[Expense]:
        where, params = [], []
        if truck_id is not None:
            where.append("truck_id = ?")
            params.append(truck_id)
        if start:
            where.append("date >= ?")
            params.append(start)
        if end:
            where.append("date <= ?")
            params.append(end)
        sql = "SELECT * FROM expenses" + (" WHERE " + " AND ".join(where) if where else "")
        sql += " ORDER BY date DESC, id DESC"
        return [_from_row(Expense, r) for r in self.conn.execute(sql, params)]

    # -------------------------------------------------------------- maintenance
    def _validate_maintenance(self, m: Maintenance) -> Maintenance:
        _clean_all(m)
        if m.truck_id is None or self.get_truck(m.truck_id) is None:
            raise ValidationError("error.truck_required")
        if not m.date:
            raise ValidationError("error.date_required")
        _check_date(m.date)
        _check_date(m.next_due_date)
        if m.service_type not in SERVICE_TYPES:
            raise ValidationError("error.invalid_category")
        _non_negative(m, "cost")
        _non_negative(m, "odometer", "next_due_odometer", integer=True)
        return m

    def add_maintenance(self, m: Maintenance) -> int:
        m = self._validate_maintenance(m)
        with self.conn:
            m.id = self._insert("maintenance", m)
            self._bump_odometer(m.truck_id, m.odometer)
        return m.id

    def update_maintenance(self, m: Maintenance) -> None:
        if m.id is None:
            raise ValueError("maintenance.id is required for update")
        m = self._validate_maintenance(m)
        with self.conn:
            self._update("maintenance", m)
            self._bump_odometer(m.truck_id, m.odometer)

    def delete_maintenance(self, maintenance_id: int) -> None:
        self._delete("maintenance", maintenance_id)

    def get_maintenance(self, maintenance_id: int | None) -> Maintenance | None:
        return self._get(Maintenance, "maintenance", maintenance_id)

    def list_maintenance(self, truck_id: int | None = None, start: str | None = None,
                         end: str | None = None) -> list[Maintenance]:
        where, params = [], []
        if truck_id is not None:
            where.append("truck_id = ?")
            params.append(truck_id)
        if start:
            where.append("date >= ?")
            params.append(start)
        if end:
            where.append("date <= ?")
            params.append(end)
        sql = "SELECT * FROM maintenance" + (" WHERE " + " AND ".join(where) if where else "")
        sql += " ORDER BY date DESC, id DESC"
        return [_from_row(Maintenance, r) for r in self.conn.execute(sql, params)]

    def maintenance_due(self, m: Maintenance, truck: Truck | None = None, today: date | None = None) -> bool:
        """True when the record's next service date or odometer has been reached."""
        today = today or date.today()
        if m.next_due_date and m.next_due_date <= today.isoformat():
            return True
        truck = truck or self.get_truck(m.truck_id)
        return bool(m.next_due_odometer and truck and truck.odometer and truck.odometer >= m.next_due_odometer)

    # --------------------------------------------------------------- statements
    def _validate_statement(self, s: Statement, items: list[StatementItem]) -> Statement:
        _clean_all(s)
        if s.truck_id is None or self.get_truck(s.truck_id) is None:
            raise ValidationError("error.truck_required")
        if not s.week_start:
            raise ValidationError("error.date_required")
        _check_date(s.week_start)
        _check_date(s.driver_paid_date)
        s.week_start = week_start(s.week_start, self.week_start_dow).isoformat()
        for name in ("fuel_amount", "tolls", "dispatch_fee_percent", "dispatch_fee_fixed"):
            if getattr(s, name) is None:
                setattr(s, name, 0.0)
        _non_negative(s, "fuel_amount", "fuel_gallons", "tolls", "dispatch_fee_percent",
                      "dispatch_fee_fixed", "driver_pay_override", "driver_paid_amount")
        if s.dispatch_fee_percent > 100:
            raise ValidationError("error.invalid_percent")
        s.deduct_driver_pay = bool(s.deduct_driver_pay)
        if s.status not in STATEMENT_STATUSES:
            raise ValidationError("error.invalid_status")
        for item in items:
            _clean_all(item)
            if item.kind not in ITEM_KINDS:
                raise ValidationError("error.invalid_category")
            if item.amount is None:
                raise ValidationError("error.amount_required")
            _non_negative(item, "amount")
        return s

    def save_statement(self, s: Statement, items: list[StatementItem]) -> int:
        """Insert or update a statement together with its additions/deductions."""
        s = self._validate_statement(s, items)
        try:
            with self.conn:
                if s.id is None:
                    s.id = self._insert("statements", s)
                else:
                    self._update("statements", s)
                    self.conn.execute("DELETE FROM statement_items WHERE statement_id = ?", (s.id,))
                for item in items:
                    item.statement_id = s.id
                    item.id = self._insert("statement_items", item)
        except sqlite3.IntegrityError as exc:
            raise ValidationError("error.statement_exists") from exc
        return s.id

    def delete_statement(self, statement_id: int) -> None:
        self._delete("statements", statement_id)

    def get_statement(self, statement_id: int | None) -> Statement | None:
        return self._get(Statement, "statements", statement_id)

    def statement_items(self, statement_id: int) -> list[StatementItem]:
        rows = self.conn.execute(
            "SELECT * FROM statement_items WHERE statement_id = ? ORDER BY id", (statement_id,)
        )
        return [_from_row(StatementItem, r) for r in rows]

    def list_statements(self, truck_id: int | None = None) -> list[Statement]:
        sql, params = "SELECT * FROM statements", []
        if truck_id is not None:
            sql += " WHERE truck_id = ?"
            params.append(truck_id)
        sql += " ORDER BY week_start DESC, id DESC"
        return [_from_row(Statement, r) for r in self.conn.execute(sql, params)]

    # ----------------------------------------------------------------- settings
    def get_settings(self) -> dict[str, str]:
        settings = dict(DEFAULT_SETTINGS)
        for row in self.conn.execute("SELECT key, value FROM settings"):
            settings[row["key"]] = row["value"] if row["value"] is not None else ""
        return settings

    def set_setting(self, key: str, value: str) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?)"
                " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
