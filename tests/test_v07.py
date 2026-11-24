"""v0.7: load profit, driver pay summary, quick search and keyboard shortcuts."""

from datetime import date

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit

from truck_tms.database import Database, Driver, Expense, Invoice, Load, Truck
from truck_tms.profit import ProfitModel, compute_driver_pay, driver_pay_to_csv, driver_pay_to_html, load_driver_pay
from truck_tms.search import search_records
from truck_tms.ui.driver_pay import period_range


@pytest.fixture
def db():
    database = Database()
    yield database
    database.close()


def _fleet(db):
    pct = db.add_driver(Driver(name="Pat", pay_type="percent", pay_rate=25))
    mile = db.add_driver(Driver(name="Mo", pay_type="per_mile", pay_rate=0.5))
    week = db.add_driver(Driver(name="Wes", pay_type="weekly", pay_rate=1000))
    t1 = db.add_truck(Truck(plate="T1", unit_number="101", driver_id=pct, dispatch_fee_percent=10))
    t2 = db.add_truck(Truck(plate="T2", unit_number="102"))
    return pct, mile, week, t1, t2


# ------------------------------------------------------------------ profit
def test_load_driver_pay():
    load = Load(rate=2000, extra_pay=100, loaded_miles=800, dead_miles=200)
    assert load_driver_pay(load, Driver(name="a", pay_type="percent", pay_rate=30)) == 630
    assert load_driver_pay(load, Driver(name="b", pay_type="per_mile", pay_rate=0.6)) == 600
    assert load_driver_pay(load, Driver(name="c", pay_type="weekly", pay_rate=900)) is None
    assert load_driver_pay(load, Driver(name="d", pay_rate=None)) is None
    assert load_driver_pay(load, None) is None


def test_profit_uses_fee_driver_and_truck_fuel_cost(db):
    pct, mile, _, t1, t2 = _fleet(db)
    # truck 1: 1,000 mi of loads and $500 of fuel -> $0.50 per mile
    db.add_load(Load(truck_id=t1, rate=1500, loaded_miles=900, dead_miles=100, delivery_date="2026-03-03"))
    db.add_expense(Expense(truck_id=t1, date="2026-03-03", category="fuel", amount=500))
    model = ProfitModel(db)
    assert model.fuel_per_mile[t1] == pytest.approx(0.5)
    probe = Load(truck_id=t1, rate=2000, loaded_miles=500, delivery_date="2026-03-04")  # default driver: Pat 25%
    est = model.of(probe)
    assert (est.gross, est.dispatch_fee, est.driver_pay, est.fuel) == (2000, 200, 500, 250)
    assert est.profit == 1050
    assert est.per_mile == pytest.approx(2.1)
    assert est.margin == pytest.approx(52.5)
    # truck 2 has no fuel data: the fleet average is used
    other = model.of(Load(truck_id=t2, driver_id=mile, rate=1000, loaded_miles=400))
    assert other.fuel == 200 and other.driver_pay == 200 and other.dispatch_fee == 0
    assert other.profit == 600


def test_profit_of_cancelled_and_tonu_loads(db):
    _, _, _, t1, _ = _fleet(db)
    model = ProfitModel(db)
    cancelled = model.of(Load(truck_id=t1, rate=1000, loaded_miles=300, status="cancelled"))
    assert cancelled.profit == 0 and cancelled.per_mile is None
    tonu = model.of(Load(truck_id=t1, rate=250, status="cancelled", is_tonu=True))
    assert tonu.gross == 250 and tonu.fuel == 0


def test_weekly_salary_is_shared_by_the_weeks_loads(db):
    _, _, week, _, t2 = _fleet(db)
    for day in ("2026-03-03", "2026-03-04"):
        db.add_load(Load(truck_id=t2, driver_id=week, rate=1000, delivery_date=day))
    model = ProfitModel(db)
    assert [model.of(load).driver_pay for load in db.list_loads()] == [500, 500]


# --------------------------------------------------------------- driver pay
def test_driver_pay_report(db, tmp_path):
    pct, mile, week, t1, t2 = _fleet(db)
    db.add_load(Load(truck_id=t1, rate=2000, loaded_miles=800, dead_miles=200, delivery_date="2026-03-03"))
    db.add_load(Load(truck_id=t2, driver_id=mile, rate=1000, loaded_miles=600, delivery_date="2026-03-05"))
    db.add_load(Load(truck_id=t2, driver_id=week, rate=900, delivery_date="2026-03-03"))
    db.add_load(Load(truck_id=t2, driver_id=week, rate=900, delivery_date="2026-03-04"))  # same week
    db.add_load(Load(truck_id=t2, driver_id=week, rate=900, delivery_date="2026-03-12"))  # next week
    db.add_load(Load(truck_id=t2, rate=700, delivery_date="2026-03-06"))  # no driver
    db.add_load(Load(truck_id=t1, rate=5000, delivery_date="2026-04-02"))  # outside the period
    report = compute_driver_pay(db, "2026-03-01", "2026-03-31")
    pay = {line.driver.name: line for line in report.lines}
    assert pay["Pat"].pay == 500 and pay["Pat"].loads == 1 and pay["Pat"].total_miles == 1000
    assert pay["Mo"].pay == 300 and pay["Mo"].pay_per_mile == pytest.approx(0.5)
    assert pay["Wes"].pay == 2000 and pay["Wes"].loads == 3
    assert [line.driver.name for line in report.lines] == ["Wes", "Pat", "Mo"]  # biggest pay first
    assert report.total_pay == 2800 and report.total_loads == 5
    assert report.loads_without_driver == 1
    html = driver_pay_to_html(report, db.get_settings())
    assert "Pat" in html and "$2,800.00" in html and "no driver" in html
    csv_path = tmp_path / "pay.csv"
    driver_pay_to_csv(report, csv_path, db.get_settings())
    text = csv_path.read_text(encoding="utf-8-sig")
    assert "Wes" in text and "2800" in text


def test_period_range():
    today = date(2026, 2, 14)
    assert period_range("this_month", today) == ("2026-02-01", "2026-02-28")
    assert period_range("last_month", today) == ("2026-01-01", "2026-01-31")
    assert period_range("this_quarter", today) == ("2026-01-01", "2026-03-31")
    assert period_range("this_year", today) == ("2026-01-01", "2026-12-31")
    assert period_range("last_month", date(2026, 1, 5)) == ("2025-12-01", "2025-12-31")
    assert period_range("this_month", date(2026, 12, 9)) == ("2026-12-01", "2026-12-31")
    assert period_range("custom", today) is None


# ------------------------------------------------------------------ search
def test_search_records(db):
    pct, _, _, t1, _ = _fleet(db)
    load_id = db.add_load(Load(truck_id=t1, load_number="#4410055", broker="Acme Logistics",
                               pickup_location="Dallas, TX", delivery_location="Atlanta, GA", rate=2550))
    db.add_invoice(Invoice(invoice_number="INV-0007", issue_date="2026-03-01", amount=2550, load_id=load_id,
                           bill_to="Acme Logistics"))
    assert search_records(db, "  ") == []
    hits = search_records(db, "acme")
    assert [(h.kind, h.record_id) for h in hits][0] == ("load", load_id)
    assert {h.kind for h in hits} == {"load", "invoice"}
    assert "Dallas, TX → Atlanta, GA" in hits[0].detail
    assert [h.kind for h in search_records(db, "#4410")] == ["load"]
    assert [(h.kind, h.record_id) for h in search_records(db, "pat")] == [("driver", pct)]
    assert [(h.kind, h.title) for h in search_records(db, "101")] == [("truck", "T1 (101)")]


# --------------------------------------------------------------------- GUI
@pytest.fixture
def window(db):
    from truck_tms.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    _fleet(db)
    db.add_load(Load(truck_id=1, load_number="#777", rate=1000, loaded_miles=400,
                     delivery_date=date.today().isoformat()))
    win = MainWindow(db)
    win.show()
    app.processEvents()
    yield win
    win.close()
    win.deleteLater()
    app.processEvents()


def test_loads_page_shows_profit_columns(window):
    from truck_tms.ui.loads import LoadsTab

    page = window.tabs.widget(window.page_index(LoadsTab))
    headers = [page.table.horizontalHeaderItem(c).text() for c in range(page.table.columnCount())]
    column = headers.index("Est. Profit")
    assert headers[column + 1] == "Profit/mi"
    # $1,000 − 10% fee − 25% driver pay, no fuel data yet
    assert page.table.item(0, column).text() == "$650.00"
    assert "Est. Profit: $650.00" in page.totals.text()


def test_driver_pay_page(window):
    from truck_tms.ui.driver_pay import DriverPayTab

    window.go_to_page(window.page_index(DriverPayTab))
    page = window.tabs.currentWidget()
    assert isinstance(page, DriverPayTab)
    assert "Pat" in page.html and "$250.00" in page.html
    page.period.setCurrentIndex(page.period.findData("last_month"))
    assert page.report.start < date.today().replace(day=1).isoformat()
    page.start.setDate(page.start.date().addDays(-3))  # editing a date switches to custom
    assert page.period.currentData() == "custom"


def test_page_shortcuts_and_search_focus(window):
    from truck_tms.ui.loads import LoadsTab

    QTest.keySequence(window, "Ctrl+4")
    assert isinstance(window.tabs.currentWidget(), LoadsTab)
    window.focus_search()
    assert isinstance(QApplication.focusWidget(), QLineEdit)
    window.go_to_page(99)  # out of range: nothing happens
    assert isinstance(window.tabs.currentWidget(), LoadsTab)


def test_quick_search_dialog_and_choices(window, monkeypatch):
    from truck_tms.ui.loads import LoadsTab
    from truck_tms.ui.quick_search import QuickSearch

    dialog = QuickSearch(window.db, window.page_info, window)
    dialog.box.setText("777")
    dialog.update_results()
    assert dialog.list.count() == 1
    assert dialog.list.item(0).data(Qt.ItemDataRole.UserRole)[0] == "open"
    dialog.box.setText("loads")
    dialog.update_results()
    kinds = [dialog.list.item(i).data(Qt.ItemDataRole.UserRole)[0] for i in range(dialog.list.count())]
    assert kinds[:2] == ["page", "new"]
    QTest.keyClick(dialog.box, Qt.Key.Key_Down)
    assert dialog.list.currentRow() == 1
    dialog.box.setText("zzzz-nothing")
    dialog.accept_current()
    assert dialog.choice is None and dialog.list.item(0).text() == "Nothing found"
    dialog.deleteLater()

    opened = []
    monkeypatch.setattr(LoadsTab, "_open", lambda self, record_id: opened.append(record_id))
    window.run_choice(("open", "load", 1))
    window.run_choice(("new", window.page_index(LoadsTab)))
    window.new_record()
    assert opened == [1, None, None]
    window.run_choice(("page", 0))
    assert window.tabs.currentIndex() == 0


def test_table_keys_edit_and_delete(window, monkeypatch):
    from truck_tms.ui.loads import LoadsTab

    page = window.tabs.widget(window.page_index(LoadsTab))
    window.go_to_page(window.page_index(LoadsTab))
    calls = []
    monkeypatch.setattr(LoadsTab, "open_dialog", lambda self, record_id: calls.append(("edit", record_id)) or False)
    monkeypatch.setattr(LoadsTab, "delete_record", lambda self, record_id: calls.append(("delete", record_id)) or False)
    page.table.setFocus()
    page.table.selectRow(0)
    QTest.keyClick(page.table, Qt.Key.Key_Return)
    QTest.keyClick(page.table, Qt.Key.Key_Delete)
    assert calls == [("edit", 1), ("delete", 1)]


def test_shortcut_help_lists_every_line(window, monkeypatch):
    shown = []
    monkeypatch.setattr("truck_tms.ui.main_window.show_info", lambda parent, text: shown.append(text))
    window.show_shortcuts()
    assert shown[0].count("<tr>") == 12 and "Ctrl+K" in shown[0]


def test_dialog_profit_line(db):
    from truck_tms.ui.loads import LoadDialog

    QApplication.instance() or QApplication([])
    _, _, _, t1, _ = _fleet(db)
    dialog = LoadDialog(db, None)
    dialog.truck.setCurrentIndex(dialog.truck.findData(t1))
    dialog.rate.setText("2000")
    assert dialog.profit.text().startswith("Est. profit $1,300.00")
    dialog.rate.setText("abc")
    assert dialog.profit.text() == ""
    dialog.deleteLater()
