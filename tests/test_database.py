import sqlite3

import pytest

from truck_tms.database import (
    Database,
    Driver,
    Expense,
    Load,
    Maintenance,
    Truck,
    ValidationError,
    normalize_load_number,
    normalize_plate,
)


@pytest.fixture
def db():
    database = Database(":memory:")
    yield database
    database.close()


def test_normalize_plate():
    assert normalize_plate("  34 abc   123 ") == "34 ABC 123"


def test_normalize_load_number():
    assert normalize_load_number("1234") == "#1234"
    assert normalize_load_number(" #1234 ") == "#1234"
    assert normalize_load_number("##1234") == "#1234"
    assert normalize_load_number("  ") is None


def test_add_and_get_truck(db):
    truck_id = db.add_truck(Truck(plate="34 abc 123", make="Volvo", year=2020))
    truck = db.get_truck(truck_id)
    assert truck.plate == "34 ABC 123"
    assert truck.make == "Volvo"
    assert truck.unit_number is None  # empty optional fields stay NULL


def test_truck_needs_plate_or_unit(db):
    with pytest.raises(ValidationError) as exc:
        db.add_truck(Truck(plate="   "))
    assert exc.value.key == "error.plate_or_unit_required"
    unit_only = db.add_truck(Truck(unit_number="101"))
    second_unit_only = db.add_truck(Truck(unit_number="102"))  # two NULL plates are fine
    assert db.get_truck(unit_only).label == "101"
    assert db.get_truck(second_unit_only).plate is None
    both = db.add_truck(Truck(plate="ab1", unit_number="103"))
    assert db.get_truck(both).label == "AB1 (103)"


def test_unit_number_unique(db):
    db.add_truck(Truck(unit_number="T-1"))
    with pytest.raises(ValidationError) as exc:
        db.add_truck(Truck(unit_number="t-1"))
    assert exc.value.key == "error.unit_exists"


def test_find_truck_by_plate_or_unit(db):
    tid = db.add_truck(Truck(plate="ABC1", unit_number="77"))
    assert db.find_truck("abc1").id == tid
    assert db.find_truck("77").id == tid


def test_duplicate_plate_is_case_insensitive(db):
    db.add_truck(Truck(plate="34 ABC 123"))
    with pytest.raises(ValidationError) as exc:
        db.add_truck(Truck(plate="34 abc 123"))
    assert exc.value.key == "error.plate_exists"


def test_change_plate_records_history(db):
    truck_id = db.add_truck(Truck(plate="34 ABC 123"))
    load_id = db.add_load(Load(truck_id=truck_id, rate=1000))
    db.change_plate(truck_id, "06 xyz 999")
    assert db.get_truck(truck_id).plate == "06 XYZ 999"
    history = db.plate_history(truck_id)
    assert [(h.old_plate, h.new_plate) for h in history] == [("34 ABC 123", "06 XYZ 999")]
    assert db.get_load(load_id).truck_id == truck_id


def test_change_plate_to_existing_plate_fails(db):
    db.add_truck(Truck(plate="A1"))
    other = db.add_truck(Truck(plate="B2"))
    with pytest.raises(ValidationError):
        db.change_plate(other, "a1")
    assert db.plate_history(other) == []


def test_saving_without_plate_change_adds_no_history(db):
    truck_id = db.add_truck(Truck(plate="A1"))
    truck = db.get_truck(truck_id)
    truck.make = "Mack"
    db.update_truck(truck)
    assert db.plate_history(truck_id) == []


def test_load_with_no_details(db):
    load_id = db.add_load(Load())
    load = db.get_load(load_id)
    assert load.status == "planned"
    assert load.truck_id is None and load.rate is None and load.is_tonu is False


def test_load_number_gets_hash(db):
    load_id = db.add_load(Load(load_number="55501"))
    assert db.get_load(load_id).load_number == "#55501"


def test_load_miles_and_gross(db):
    load = db.get_load(db.add_load(Load(rate=2000, extra_pay=100, loaded_miles=600, dead_miles=100)))
    assert load.total_miles == 700
    assert load.gross == 2100
    assert load.rate_per_mile == 3


def test_load_delivery_before_pickup(db):
    with pytest.raises(ValidationError) as exc:
        db.add_load(Load(pickup_date="2026-05-10", delivery_date="2026-05-01"))
    assert exc.value.key == "error.delivery_before_pickup"


def test_load_negative_rate(db):
    with pytest.raises(ValidationError):
        db.add_load(Load(rate=-5))


def test_load_week_auto_and_manual(db):
    # 2026-11-18 is a Wednesday; default weeks start on Monday
    auto = db.get_load(db.add_load(Load(delivery_date="2026-11-18")))
    assert db.load_week(auto) == "2026-11-16"
    manual = db.get_load(db.add_load(Load(delivery_date="2026-11-18", statement_week="2026-11-26")))
    assert manual.statement_week == "2026-11-23"  # snapped to week start
    assert {load.id for load in db.list_loads(week="2026-11-16")} == {auto.id}
    db.set_setting("week_start", "6")  # Sunday
    assert db.load_week(auto) == "2026-11-15"
    assert {load.id for load in db.list_loads(week="2026-11-15")} == {auto.id}


def test_list_loads_filters(db):
    t1 = db.add_truck(Truck(plate="A1"))
    t2 = db.add_truck(Truck(plate="B2"))
    d1 = db.add_driver(Driver(name="Ann"))
    db.add_load(Load(truck_id=t1, driver_id=d1, load_number="X1", delivery_date="2026-01-05"))
    db.add_load(Load(truck_id=t1, load_number="X2", pickup_date="2026-02-01", status="cancelled"))
    db.add_load(Load(truck_id=t1, load_number="X3", pickup_date="2026-02-01", status="cancelled", is_tonu=True))
    db.add_load(Load(truck_id=t2, load_number="Y1", broker="Acme", delivery_date="2026-01-10"))

    assert {load.load_number for load in db.list_loads(truck_id=t1)} == {"#X1", "#X2", "#X3"}
    assert [load.load_number for load in db.list_loads(search="acme")] == ["#Y1"]
    assert [load.load_number for load in db.list_loads(driver_id=d1)] == ["#X1"]
    assert {load.load_number for load in db.list_loads(start="2026-01-01", end="2026-01-31")} == {"#X1", "#Y1"}
    assert {load.load_number for load in db.list_loads(truck_id=t1, include_cancelled=False)} == {"#X1", "#X3"}


def test_delete_truck_keeps_loads_removes_expenses(db):
    truck_id = db.add_truck(Truck(plate="A1"))
    load_id = db.add_load(Load(truck_id=truck_id))
    db.add_expense(Expense(truck_id=truck_id, date="2026-01-01", category="fuel", amount=100))
    db.add_maintenance(Maintenance(truck_id=truck_id, date="2026-01-01", service_type="tires"))
    db.delete_truck(truck_id)
    assert db.get_load(load_id).truck_id is None
    assert db.list_expenses() == []
    assert db.list_maintenance() == []


def test_delete_driver_unassigns(db):
    driver_id = db.add_driver(Driver(name="Bob"))
    truck_id = db.add_truck(Truck(unit_number="1", driver_id=driver_id))
    load_id = db.add_load(Load(driver_id=driver_id))
    db.delete_driver(driver_id)
    assert db.get_truck(truck_id).driver_id is None
    assert db.get_load(load_id).driver_id is None


def test_driver_validation(db):
    with pytest.raises(ValidationError) as exc:
        db.add_driver(Driver(name=" "))
    assert exc.value.key == "error.name_required"
    with pytest.raises(ValidationError):
        db.add_driver(Driver(name="X", pay_type="hourly"))


def test_maintenance_updates_odometer_and_due(db):
    from datetime import date

    tid = db.add_truck(Truck(unit_number="1", odometer=100_000))
    mid = db.add_maintenance(Maintenance(truck_id=tid, date="2026-01-01", service_type="oil_change",
                                         odometer=120_000, next_due_odometer=130_000))
    assert db.get_truck(tid).odometer == 120_000
    db.add_maintenance(Maintenance(truck_id=tid, date="2025-01-01", service_type="tires", odometer=90_000))
    assert db.get_truck(tid).odometer == 120_000  # never goes down
    m = db.get_maintenance(mid)
    assert not db.maintenance_due(m, today=date(2026, 1, 2))
    truck = db.get_truck(tid)
    truck.odometer = 130_500
    db.update_truck(truck)
    assert db.maintenance_due(m, today=date(2026, 1, 2))
    m2 = Maintenance(truck_id=tid, date="2026-01-01", service_type="pm_service", next_due_date="2026-01-02")
    assert db.maintenance_due(m2, today=date(2026, 1, 2))


def test_expense_validation(db):
    truck_id = db.add_truck(Truck(plate="A1"))
    with pytest.raises(ValidationError) as exc:
        db.add_expense(Expense(truck_id=truck_id, date="2026-01-01", category="fuel", amount=None))
    assert exc.value.key == "error.amount_required"
    with pytest.raises(ValidationError) as exc:
        db.add_expense(Expense(truck_id=None, date="2026-01-01", category="fuel", amount=5))
    assert exc.value.key == "error.truck_required"


def test_settings_defaults_and_update(db):
    assert db.get_settings()["currency"] == "$"
    assert db.get_settings()["theme"] == "light"
    db.set_setting("currency", "₺")
    db.set_setting("currency", "€")
    assert db.get_settings()["currency"] == "€"


V01_SCHEMA = """
CREATE TABLE trucks (id INTEGER PRIMARY KEY, plate TEXT NOT NULL UNIQUE COLLATE NOCASE, unit_number TEXT,
    make TEXT, model TEXT, year INTEGER, vin TEXT, status TEXT NOT NULL DEFAULT 'active', notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE plate_history (id INTEGER PRIMARY KEY, truck_id INTEGER NOT NULL REFERENCES trucks(id) ON DELETE CASCADE,
    old_plate TEXT NOT NULL, new_plate TEXT NOT NULL, changed_at TEXT NOT NULL);
CREATE TABLE loads (id INTEGER PRIMARY KEY, truck_id INTEGER REFERENCES trucks(id) ON DELETE SET NULL,
    load_number TEXT, broker TEXT, pickup_location TEXT, pickup_date TEXT, delivery_location TEXT,
    delivery_date TEXT, rate REAL, miles REAL, weight REAL, commodity TEXT,
    status TEXT NOT NULL DEFAULT 'planned', notes TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE expenses (id INTEGER PRIMARY KEY, truck_id INTEGER NOT NULL REFERENCES trucks(id) ON DELETE CASCADE,
    date TEXT NOT NULL, category TEXT NOT NULL, amount REAL NOT NULL, description TEXT);
CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT);
INSERT INTO trucks (id, plate, make) VALUES (1, '34 ABC 123', 'Volvo');
INSERT INTO plate_history (truck_id, old_plate, new_plate, changed_at) VALUES (1, 'OLD', '34 ABC 123', '2026-01-01');
INSERT INTO loads (truck_id, load_number, rate, miles) VALUES (1, 'L-1', 1000, 500);
INSERT INTO expenses (truck_id, date, category, amount) VALUES (1, '2026-01-01', 'fuel', 50);
"""


def test_migrates_v01_database(tmp_path):
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.executescript(V01_SCHEMA)
    conn.close()

    db = Database(path)
    truck = db.get_truck(1)
    assert truck.plate == "34 ABC 123" and truck.make == "Volvo"
    load = db.list_loads()[0]
    assert load.load_number == "#L-1" and load.loaded_miles == 500
    assert len(db.plate_history(1)) == 1
    db.add_truck(Truck(unit_number="900"))  # plate is optional now
    # foreign keys still point at the rebuilt trucks table
    db.delete_truck(1)
    assert db.list_expenses() == [] and db.plate_history(1) == []
    assert db.list_loads()[0].truck_id is None
    db.close()
    Database(path).close()  # re-opening an upgraded database is a no-op
