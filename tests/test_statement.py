import csv

import pytest

from truck_tms.database import Database, Driver, Load, Statement, StatementItem, Truck, ValidationError
from truck_tms.i18n import set_language
from truck_tms.statement import (
    compute_statement,
    driver_balances,
    driver_statement_to_html,
    statement_to_csv,
    statement_to_html,
)

WEEK = "2026-11-16"  # Monday


@pytest.fixture
def db():
    database = Database(":memory:")
    yield database
    database.close()
    set_language("en")


@pytest.fixture
def setup(db):
    john = db.add_driver(Driver(name="John", pay_type="percent", pay_rate=30))
    truck = db.add_truck(Truck(unit_number="101", owner_name="Owner LLC", driver_id=john))
    db.add_load(Load(truck_id=truck, driver_id=john, load_number="1", rate=2000, extra_pay=100,
                     loaded_miles=800, dead_miles=50, delivery_date="2026-11-17"))
    db.add_load(Load(truck_id=truck, load_number="2", rate=1000, loaded_miles=400, dead_miles=50,
                     pickup_date="2026-11-21"))  # no driver -> truck's default driver
    db.add_load(Load(truck_id=truck, load_number="3", rate=300, is_tonu=True, status="cancelled",
                     delivery_date="2026-11-19"))  # TONU counts
    db.add_load(Load(truck_id=truck, load_number="4", rate=999, status="cancelled",
                     delivery_date="2026-11-19"))  # cancelled: excluded
    db.add_load(Load(truck_id=truck, load_number="5", rate=777, delivery_date="2026-11-24"))  # next week
    db.add_load(Load(truck_id=truck, load_number="6", rate=500, loaded_miles=100,
                     delivery_date="2026-11-24", statement_week="2026-11-16"))  # moved into this week
    return truck, john


def make_statement(db, truck, **kw):
    s = Statement(truck_id=truck, week_start=WEEK, fuel_amount=600, fuel_gallons=150, tolls=40,
                  dispatch_fee_percent=10, **kw)
    items = [
        StatementItem(kind="driver_addition", description="Bonus", amount=50),
        StatementItem(kind="driver_deduction", description="Advance", amount=200),
        StatementItem(kind="owner_deduction", description="Insurance", amount=300),
        StatementItem(kind="owner_addition", description="Fuel rebate", amount=20),
    ]
    db.save_statement(s, items)
    return s


def test_statement_totals(db, setup):
    truck, john = setup
    s = make_statement(db, truck)
    summary = compute_statement(db, db.get_statement(s.id))

    assert [l.load_number for l in summary.loads] == ["#1", "#3", "#2", "#6"]
    assert summary.gross == 2100 + 300 + 1000 + 500 == 3900
    assert summary.loaded_miles == 1300
    assert summary.dead_miles == 100
    assert summary.total_miles == 1400
    assert summary.dispatch_fee == 390
    assert summary.driver_salary == pytest.approx(0.30 * 3900)  # 1170
    assert summary.driver_net == pytest.approx(1170 + 50 - 200)  # 1020
    assert summary.owner_payout == pytest.approx(3900 - 390 - 600 - 40 - 1020 + 20 - 300)  # 1570
    assert summary.driver_names == "John"


def test_driver_pay_override_and_not_deducted(db, setup):
    truck, _ = setup
    s = make_statement(db, truck, driver_pay_override=1000, deduct_driver_pay=False)
    summary = compute_statement(db, db.get_statement(s.id))
    assert summary.driver_salary == 1000
    assert summary.driver_net == 850
    assert summary.owner_payout == pytest.approx(3900 - 390 - 600 - 40 + 20 - 300)


def test_per_mile_and_weekly_pay(db):
    per_mile = db.add_driver(Driver(name="M", pay_type="per_mile", pay_rate=0.5))
    weekly = db.add_driver(Driver(name="W", pay_type="weekly", pay_rate=1200))
    truck = db.add_truck(Truck(unit_number="1"))
    db.add_load(Load(truck_id=truck, driver_id=per_mile, rate=1000, loaded_miles=900, dead_miles=100,
                     delivery_date="2026-11-17"))
    db.add_load(Load(truck_id=truck, driver_id=weekly, rate=1000, delivery_date="2026-11-18"))
    db.add_load(Load(truck_id=truck, driver_id=weekly, rate=1000, delivery_date="2026-11-19"))
    summary = compute_statement(db, Statement(truck_id=truck, week_start=WEEK), [])
    assert summary.driver_salary == 500 + 1200  # weekly salary only once


def test_driver_payment_balance(db, setup):
    truck, john = setup
    s = make_statement(db, truck, driver_paid_amount=900, driver_paid_date="2026-11-25")
    summary = compute_statement(db, db.get_statement(s.id))
    assert summary.driver_paid == 900
    assert summary.driver_balance == pytest.approx(120)
    assert driver_balances(db) == {john: pytest.approx(120)}


def test_one_statement_per_truck_and_week(db, setup):
    truck, _ = setup
    make_statement(db, truck)
    with pytest.raises(ValidationError) as exc:
        db.save_statement(Statement(truck_id=truck, week_start="2026-11-18"), [])  # same week, snapped
    assert exc.value.key == "error.statement_exists"


def test_save_statement_replaces_items(db, setup):
    truck, _ = setup
    s = make_statement(db, truck)
    db.save_statement(db.get_statement(s.id), [StatementItem(kind="owner_deduction", amount=10)])
    assert [i.amount for i in db.statement_items(s.id)] == [10]


def test_statement_html_and_csv(db, setup, tmp_path):
    truck, _ = setup
    s = make_statement(db, truck)
    summary = compute_statement(db, db.get_statement(s.id))
    settings = db.get_settings()
    html = statement_to_html(summary, settings)
    assert "$3,900.00" in html and "TONU" in html and "Owner LLC" in html and "$1,570.00" in html
    driver_html = driver_statement_to_html(summary, settings)
    assert "$1,020.00" in driver_html
    assert "Owner Payout" not in driver_html

    set_language("tr")
    assert "Tır Sahibine Ödeme" in statement_to_html(summary, settings)

    path = tmp_path / "s.csv"
    statement_to_csv(summary, path, settings)
    rows = list(csv.reader(path.open(encoding="utf-8-sig")))
    assert rows[0][1] == "101"
    assert any(r and r[-1] == "1570.0" for r in rows)
