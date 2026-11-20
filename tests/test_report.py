import csv

import pytest

from truck_tms.database import Database, Expense, Load, Truck, ValidationError
from truck_tms.demo import seed_demo_data
from truck_tms.i18n import set_language, t
from truck_tms.report import build_truck_report, money, report_to_csv, report_to_html


@pytest.fixture
def db():
    database = Database(":memory:")
    yield database
    database.close()
    set_language("en")


@pytest.fixture
def truck_id(db):
    tid = db.add_truck(Truck(plate="34 ABC 123", make="Volvo", model="FH", year=2020))
    db.add_load(Load(truck_id=tid, load_number="L1", rate=2000, loaded_miles=800, delivery_date="2026-03-05"))
    db.add_load(Load(truck_id=tid, load_number="L2", rate=1000, loaded_miles=200, pickup_date="2026-03-20"))
    db.add_load(Load(truck_id=tid, load_number="L3", rate=999, delivery_date="2026-03-21", status="cancelled"))
    db.add_load(Load(truck_id=tid, load_number="L4", rate=500, delivery_date="2026-04-02"))
    db.add_expense(Expense(truck_id=tid, date="2026-03-06", category="fuel", amount=300))
    db.add_expense(Expense(truck_id=tid, date="2026-03-07", category="fuel", amount=200))
    db.add_expense(Expense(truck_id=tid, date="2026-03-08", category="tolls", amount=50))
    db.add_expense(Expense(truck_id=tid, date="2026-04-01", category="fuel", amount=999))
    return tid


def test_report_totals(db, truck_id):
    r = build_truck_report(db, truck_id, "2026-03-01", "2026-03-31")
    assert [load.load_number for load in r.loads] == ["#L1", "#L2"]  # cancelled and April excluded
    assert r.gross == 3000
    assert r.total_miles == 1000
    assert r.rate_per_mile == 3
    assert r.total_expenses == 550
    assert r.net == 2450
    assert r.expenses_by_category == {"Fuel": 500, "Tolls": 50}


def test_report_invalid_range(db, truck_id):
    with pytest.raises(ValidationError):
        build_truck_report(db, truck_id, "2026-04-01", "2026-03-01")


def test_report_html_contains_data(db, truck_id):
    r = build_truck_report(db, truck_id, "2026-03-01", "2026-03-31")
    html = report_to_html(r, {**db.get_settings(), "company_name": "Eren <Trucking>"})
    assert "34 ABC 123" in html
    assert "$3,000.00" in html
    assert "$2,450.00" in html
    assert "Eren &lt;Trucking&gt;" in html  # escaped


def test_report_html_turkish(db, truck_id):
    set_language("tr")
    r = build_truck_report(db, truck_id, "2026-03-01", "2026-03-31")
    html = report_to_html(r, {**db.get_settings(), "currency": "₺"})
    assert "Tır Raporu" in html
    assert "₺3,000.00" in html


def test_report_csv(db, truck_id, tmp_path):
    r = build_truck_report(db, truck_id, "2026-03-01", "2026-03-31")
    path = tmp_path / "report.csv"
    report_to_csv(r, path, db.get_settings())
    rows = list(csv.reader(path.open(encoding="utf-8-sig")))
    assert rows[0][1] == "34 ABC 123"
    assert ["Net", "2450.0"] in rows


def test_money_negative():
    assert money(-12.5, "$") == "-$12.50"


def test_all_keys_translated():
    from truck_tms.i18n import STRINGS
    missing = [k for k, v in STRINGS.items() if not v.get("tr") or not v.get("en")]
    assert missing == []


def test_status_and_category_keys_exist():
    from truck_tms.database import EXPENSE_CATEGORIES, LOAD_STATUSES, TRUCK_STATUSES
    from truck_tms.i18n import STRINGS
    for s in TRUCK_STATUSES + LOAD_STATUSES:
        assert f"status.{s}" in STRINGS
    for c in EXPENSE_CATEGORIES:
        assert f"category.{c}" in STRINGS
    assert t("status.paid") == "Paid"


def test_demo_data(db):
    seed_demo_data(db)
    assert len(db.list_trucks()) == 3
    seed_demo_data(db)  # idempotent on a non-empty db
    assert len(db.list_trucks()) == 3
