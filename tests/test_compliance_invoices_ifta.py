"""v0.6: compliance reminders, invoices / receivables, IFTA worksheet, update check."""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from truck_tms import compliance, ifta, invoicing, updates
from truck_tms.database import ComplianceItem, Database, Driver, Expense, Invoice, Load, Truck, ValidationError

TODAY = date(2026, 5, 15)


@pytest.fixture
def db():
    database = Database(":memory:")
    yield database
    database.close()


@pytest.fixture
def fleet(db):
    driver = db.add_driver(Driver(name="Ali", license_expiry="2026-05-01"))
    truck = db.add_truck(Truck(plate="TX1", unit_number="#101", driver_id=driver))
    return db, driver, truck


# ------------------------------------------------------------------ compliance
def test_expiry_status_windows():
    assert compliance.expiry_status("2026-05-14", TODAY) == "expired"
    assert compliance.expiry_status("2026-05-15", TODAY) == "soon"
    assert compliance.expiry_status("2026-06-14", TODAY) == "soon"
    assert compliance.expiry_status("2026-06-15", TODAY) == "ok"


def test_compliance_needs_owner_for_driver_and_truck_kinds(fleet):
    db, driver, truck = fleet
    with pytest.raises(ValidationError) as err:
        db.add_compliance(ComplianceItem(kind="medical_card", expiry_date="2026-07-01"))
    assert err.value.key == "error.driver_required"
    with pytest.raises(ValidationError) as err:
        db.add_compliance(ComplianceItem(kind="insurance", expiry_date="2026-07-01"))
    assert err.value.key == "error.truck_required"
    with pytest.raises(ValidationError):
        db.add_compliance(ComplianceItem(kind="nope", expiry_date="2026-07-01"))
    # company items drop any owner they were given
    item_id = db.add_compliance(ComplianceItem(kind="ucr", expiry_date="2026-12-31", truck_id=truck))
    assert db.get_compliance(item_id).truck_id is None


def test_compliance_entries_merge_driver_cdl_and_records(fleet):
    db, driver, truck = fleet
    db.add_compliance(ComplianceItem(kind="registration", expiry_date="2026-06-01", truck_id=truck))
    db.add_compliance(ComplianceItem(kind="medical_card", expiry_date="2027-01-01", driver_id=driver))
    entries = compliance.compliance_entries(db, TODAY)
    kinds = [(e.kind, e.status) for e in entries]
    assert kinds == [("cdl", "expired"), ("registration", "soon"), ("medical_card", "ok")]
    cdl = entries[0]
    assert cdl.item is None and cdl.row_id == -driver and cdl.owner == "Ali"
    assert [e.kind for e in compliance.attention_needed(entries)] == ["cdl", "registration"]
    # a CDL record replaces the date typed on the driver form
    db.add_compliance(ComplianceItem(kind="cdl", expiry_date="2030-01-01", driver_id=driver))
    cdls = [e for e in compliance.compliance_entries(db, TODAY) if e.kind == "cdl"]
    assert len(cdls) == 1 and cdls[0].item is not None and cdls[0].status == "ok"


def test_deleting_driver_removes_its_compliance(fleet):
    db, driver, _ = fleet
    db.add_compliance(ComplianceItem(kind="drug_test", expiry_date="2026-09-01", driver_id=driver))
    db.delete_driver(driver)
    assert db.list_compliance() == []


# ------------------------------------------------------------------ invoices
def test_invoice_numbers_increase_and_respect_prefix(db):
    assert db.next_invoice_number() == "INV-0001"
    db.add_invoice(Invoice(invoice_number="INV-0007", issue_date="2026-05-01", amount=100))
    db.add_invoice(Invoice(invoice_number="manual", issue_date="2026-05-01", amount=100))
    assert db.next_invoice_number() == "INV-0008"
    db.set_setting("invoice_prefix", "TT")
    assert db.next_invoice_number() == "TT0001"


def test_invoice_status_balance_and_aging():
    inv = Invoice(invoice_number="1", issue_date="2026-03-01", amount=1000, terms_days=30)
    assert inv.due_date == "2026-03-31"
    assert inv.status(date(2026, 3, 20)) == "open"
    assert inv.status(TODAY) == "overdue" and inv.days_overdue(TODAY) == 45
    assert invoicing.aging_bucket(inv, TODAY) == "31_60"
    inv.paid_amount = 400
    assert inv.balance == 600 and inv.status(date(2026, 3, 20)) == "partial"
    inv.paid_amount, inv.fee = 970, 30  # factoring kept 3 %
    assert inv.balance == 0 and inv.status(TODAY) == "paid"
    assert invoicing.aging_bucket(inv, TODAY) is None and inv.days_overdue(TODAY) == 0


def test_invoice_updates_load_status_and_blocks_duplicates(fleet):
    db, _, truck = fleet
    load_id = db.add_load(Load(truck_id=truck, load_number="55", rate=2000, status="delivered"))
    inv = Invoice(invoice_number="INV-0001", issue_date="2026-05-01", amount=2000, load_id=load_id)
    inv.id = db.add_invoice(inv)
    assert db.get_load(load_id).status == "invoiced"
    assert db.invoice_for_load(load_id).id == inv.id
    with pytest.raises(ValidationError) as err:
        db.add_invoice(Invoice(invoice_number="INV-0002", issue_date="2026-05-01", amount=1, load_id=load_id))
    assert err.value.key == "error.load_invoiced"
    with pytest.raises(ValidationError) as err:
        db.add_invoice(Invoice(invoice_number="inv-0001", issue_date="2026-05-01", amount=1))
    assert err.value.key == "error.invoice_number_exists"
    inv.paid_amount, inv.paid_date = 2000, "2026-05-20"
    db.update_invoice(inv)
    assert db.get_load(load_id).status == "paid"
    # deleting the load keeps the invoice (accounting record)
    db.delete_load(load_id)
    assert db.get_invoice(inv.id).load_id is None


def test_invoice_validation(db):
    for bad, key in ((dict(invoice_number=""), "error.invoice_number_required"),
                     (dict(amount=-5), "error.negative_number"),
                     (dict(method="cash"), "error.invalid_method"),
                     (dict(issue_date="05/01/2026"), "error.invalid_date")):
        fields = dict(invoice_number="X1", issue_date="2026-05-01", amount=10) | bad
        with pytest.raises(ValidationError) as err:
            db.add_invoice(Invoice(**fields))
        assert err.value.key == key


def test_receivables_summary(db):
    db.add_invoice(Invoice(invoice_number="A", issue_date="2026-05-10", amount=1000))           # current
    db.add_invoice(Invoice(invoice_number="B", issue_date="2026-03-01", amount=500))            # 45 days late
    db.add_invoice(Invoice(invoice_number="C", issue_date="2026-01-01", amount=300, terms_days=0))  # 134 late
    db.add_invoice(Invoice(invoice_number="D", issue_date="2026-04-01", amount=800, paid_amount=800,
                           paid_date="2026-05-01"))
    r = invoicing.compute_receivables(db, TODAY)
    assert r.open_total == 1800 and r.open_count == 3
    assert r.overdue_total == 800 and r.overdue_count == 2
    assert r.buckets == {"current": 1000, "1_30": 0, "31_60": 500, "61_90": 0, "90_plus": 300}
    assert r.collected_30d == 800 and r.avg_days_to_pay == 30


def test_invoice_html_lists_charges_and_balance(fleet):
    db, _, truck = fleet
    load_id = db.add_load(Load(truck_id=truck, load_number="77", broker="CH Robinson", rate=2000, extra_pay=150,
                               pickup_location="Dallas, TX", delivery_location="Atlanta, GA"))
    inv = Invoice(invoice_number="INV-0009", issue_date="2026-05-01", amount=2150, load_id=load_id,
                  paid_amount=1000)
    html = invoicing.invoice_to_html(inv, db.get_load(load_id), db.get_truck(truck), db.get_settings())
    for text in ("INV-0009", "CH Robinson", "Dallas, TX", "2,000.00", "150.00", "2,150.00", "1,150.00"):
        assert text in html


# ------------------------------------------------------------------ IFTA
def test_quarter_range():
    assert ifta.quarter_range(2026, 1) == ("2026-01-01", "2026-03-31")
    assert ifta.quarter_range(2024, 1)[1] == "2024-03-31"
    assert ifta.quarter_range(2026, 4) == ("2026-10-01", "2026-12-31")
    assert ifta.current_quarter(date(2026, 8, 2)) == (2026, 3)
    with pytest.raises(ValueError):
        ifta.quarter_range(2026, 5)


def test_load_states_merge_and_validate(fleet):
    db, _, truck = fleet
    load_id = db.add_load(Load(truck_id=truck, loaded_miles=500))
    db.set_load_states(load_id, [("tx", 200), ("LA", 100), ("TX", 50), ("OK", 0), ("", 10)])
    assert db.load_states(load_id) == [("TX", 250), ("LA", 100)]
    with pytest.raises(ValidationError) as err:
        db.set_load_states(load_id, [("ZZ", 10)])
    assert err.value.key == "error.invalid_state"
    db.delete_load(load_id)
    assert db.state_miles_by_load() == {}


def test_ifta_worksheet(fleet):
    db, _, truck = fleet
    a = db.add_load(Load(truck_id=truck, delivery_date="2026-02-10", loaded_miles=900, dead_miles=100))
    db.set_load_states(a, [("TX", 600), ("LA", 400)])
    db.add_load(Load(truck_id=truck, delivery_date="2026-02-20", loaded_miles=300))  # no state split
    db.add_load(Load(truck_id=truck, delivery_date="2026-04-02", loaded_miles=999))  # next quarter
    db.add_expense(Expense(truck_id=truck, date="2026-02-09", category="fuel", amount=600, gallons=120, state="TX"))
    db.add_expense(Expense(truck_id=truck, date="2026-02-11", category="fuel", amount=300, gallons=80, state="la"))
    db.set_ifta_rates({"TX": 0.20, "LA": 0.20})
    report = ifta.compute_ifta(db, 2026, 1)
    assert report.total_miles == 1000 and report.total_gallons == 200 and report.mpg == 5
    lines = {line.state: line for line in report.lines}
    assert lines["TX"].taxable_gallons == 120 and lines["TX"].net_gallons == 0 and lines["TX"].tax == 0
    assert lines["LA"].taxable_gallons == 80 and lines["LA"].paid_gallons == 80
    assert report.unassigned_miles == 300 and report.loads_without_states == 1
    db.set_ifta_rates({"LA": None, "TX": 0.5})
    db.add_expense(Expense(truck_id=truck, date="2026-03-01", category="fuel", amount=10, gallons=50))  # no state
    report = ifta.compute_ifta(db, 2026, 1)
    assert report.mpg == 4  # 1000 mi / 250 gal
    lines = {line.state: line for line in report.lines}
    assert lines["TX"].taxable_gallons == 150 and lines["TX"].net_gallons == 30 and lines["TX"].tax == 15
    assert lines["LA"].tax is None and report.missing_rates == ["LA"] and report.total_tax == 15
    html = ifta.ifta_to_html(report, db.get_settings(), "TX1")
    assert "Q1" in html and "TX" in html and "300" in html


def test_ifta_csv(tmp_path, fleet):
    db, _, truck = fleet
    load_id = db.add_load(Load(truck_id=truck, delivery_date="2026-05-02", loaded_miles=100))
    db.set_load_states(load_id, [("OK", 100)])
    db.add_expense(Expense(truck_id=truck, date="2026-05-02", category="fuel", amount=80, gallons=20, state="OK"))
    path = tmp_path / "ifta.csv"
    ifta.ifta_to_csv(ifta.compute_ifta(db, 2026, 2), path, db.get_settings())
    text = path.read_text(encoding="utf-8-sig")
    assert "OK,100.0,20.0,20.0,0.0" in text


def test_expense_state_is_checked(fleet):
    db, _, truck = fleet
    with pytest.raises(ValidationError):
        db.add_expense(Expense(truck_id=truck, date="2026-05-01", category="fuel", amount=1, state="XX"))
    with pytest.raises(ValidationError):
        db.add_expense(Expense(truck_id=truck, date="2026-05-01", category="fuel", amount=1, gallons=-3))


# ------------------------------------------------------------------ migration / settings
def test_v2_database_gets_new_tables_and_columns(tmp_path):
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE trucks (id INTEGER PRIMARY KEY, plate TEXT UNIQUE COLLATE NOCASE, unit_number TEXT,
            make TEXT, model TEXT, year INTEGER, vin TEXT, odometer INTEGER, owner_name TEXT, driver_id INTEGER,
            dispatch_fee_percent REAL, status TEXT NOT NULL DEFAULT 'active', notes TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE expenses (id INTEGER PRIMARY KEY, truck_id INTEGER NOT NULL, date TEXT NOT NULL,
            category TEXT NOT NULL, amount REAL NOT NULL, description TEXT);
        INSERT INTO trucks (plate) VALUES ('OLD1');
        INSERT INTO expenses (truck_id, date, category, amount) VALUES (1, '2025-01-01', 'fuel', 99);
        PRAGMA user_version = 2;
    """)
    conn.close()
    db = Database(path)
    try:
        expense = db.list_expenses()[0]
        assert expense.amount == 99 and expense.gallons is None and expense.state is None
        assert db.list_invoices() == [] and db.list_compliance() == [] and db.ifta_rates() == {}
        assert db.conn.execute("PRAGMA user_version").fetchone()[0] == 3
    finally:
        db.close()


def test_settings_are_cached_but_writes_show_up(db):
    first = db.get_settings()
    first["currency"] = "changed"  # callers get a copy
    assert db.get_settings()["currency"] == "$"
    db.set_setting("currency", "€")
    assert db.get_settings()["currency"] == "€"
    assert db.get_settings()["check_updates"] == "1"


# ------------------------------------------------------------------ updates
def test_version_compare():
    assert updates.parse_version("v0.6.0") == (0, 6, 0)
    assert updates.parse_version("junk") == ()
    assert updates.is_newer("v0.6.1", "0.6.0")
    assert updates.is_newer("1.0", "0.9.9")
    assert not updates.is_newer("0.6", "0.6.0")
    assert not updates.is_newer("v0.5.0", "0.6.0")
    assert not updates.is_newer("", "0.6.0")


def test_parse_release_picks_exe_and_skips_prereleases():
    data = {"tag_name": "v0.7.0", "html_url": "https://example/r", "assets": [
        {"name": "TruckTMS.exe.sha256", "browser_download_url": "https://example/sha"},
        {"name": "TruckTMS.exe", "browser_download_url": "https://example/exe"}]}
    release = updates.parse_release(data)
    assert (release.version, release.url, release.download) == ("0.7.0", "https://example/r", "https://example/exe")
    assert updates.parse_release(data | {"prerelease": True}) is None
    assert updates.parse_release({"tag_name": "nightly"}) is None
    assert updates.parse_release({"tag_name": "v1.0"}).download.endswith("/releases/latest")


def test_check_due_once_a_day():
    assert updates.check_due(None, TODAY)
    assert updates.check_due("2026-05-14", TODAY)
    assert not updates.check_due("2026-05-15", TODAY)


def test_fetch_latest_handles_network_errors(monkeypatch):
    def boom(*_a, **_k):
        raise OSError("offline")
    monkeypatch.setattr(updates.urllib.request, "urlopen", boom)
    assert updates.fetch_latest() is None
