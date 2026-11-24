"""v0.7 interface: Today list, getting started, load board, details panel, trends, stripes and animations."""

from datetime import date, datetime, timedelta

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel

from truck_tms.database import Database, Driver, Invoice, Load, Truck
from truck_tms.today import compute_today, onboarding_steps

TODAY = date(2026, 3, 10)


@pytest.fixture
def db():
    database = Database()
    yield database
    database.close()


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


def _day(offset: int) -> str:
    return (TODAY + timedelta(days=offset)).isoformat()


# ------------------------------------------------------------------ today
def test_today_lists_pickups_deliveries_late_and_invoices(db):
    truck = db.add_truck(Truck(plate="T1"))
    db.add_load(Load(truck_id=truck, load_number="#P", pickup_date=_day(0), delivery_date=_day(2), status="planned"))
    db.add_load(Load(truck_id=truck, load_number="#D", pickup_date=_day(-1), delivery_date=_day(0),
                     status="in_transit"))
    db.add_load(Load(truck_id=truck, load_number="#L", pickup_date=_day(-5), delivery_date=_day(-3),
                     status="dispatched"))
    ready = db.add_load(Load(truck_id=truck, load_number="#I", delivery_date=_day(-4), status="delivered", rate=900))
    billed = db.add_load(Load(truck_id=truck, load_number="#B", delivery_date=_day(-4), status="delivered", rate=900))
    db.add_invoice(Invoice(invoice_number="INV-1", issue_date=_day(-3), amount=900, load_id=billed))
    db.add_load(Load(truck_id=truck, load_number="#R", delivery_date=_day(-1), status="delivered"))  # too recent
    db.add_load(Load(truck_id=truck, load_number="#X", pickup_date=_day(0), status="cancelled"))
    items = compute_today(db, TODAY)
    assert [(i.kind, i.title) for i in items] == [
        ("late", "#L is 3 day(s) late"), ("delivery", "Delivery today: #D"), ("pickup", "Pickup today: #P"),
        ("invoice", "Ready to invoice: #I")]
    assert items[-1].load_id == ready and items[0].tone == "danger"
    assert len(compute_today(db, TODAY, limit=2)) == 2


def test_onboarding_steps(db):
    assert onboarding_steps(db) == [("truck", False), ("driver", False), ("load", False)]
    db.add_driver(Driver(name="D"))
    assert onboarding_steps(db)[1] == ("driver", True)


# ------------------------------------------------------------------ overview helpers
def test_delta_text_and_greeting():
    from truck_tms.ui.dashboard import delta_text, greeting

    assert delta_text([100, 150]) == ("▲ 50%", "success")
    assert delta_text([200, 100]) == ("▼ 50%", "danger")
    assert delta_text([100, 100.2]) == ("● 0%", "neutral")
    assert delta_text([0, 10]) is None and delta_text([5]) is None
    assert greeting(datetime(2026, 1, 1, 8)) == "Good morning"
    assert greeting(datetime(2026, 1, 1, 14)) == "Good afternoon"
    assert greeting(datetime(2026, 1, 1, 21)) == "Good evening"


def test_trends_include_weekly_miles(db):
    from truck_tms.ui.dashboard import compute_trends

    truck = db.add_truck(Truck(plate="T1"))
    db.add_load(Load(truck_id=truck, rate=1000, loaded_miles=400, dead_miles=50, delivery_date=TODAY.isoformat()))
    trends = compute_trends(db, today=TODAY)
    assert trends.miles[-1] == 450 and len(trends.miles) == len(trends.gross) == 8


# ------------------------------------------------------------------ widgets
def test_sparkline_gauge_and_check(app):
    from truck_tms.ui.visuals import AnimatedCheck, ProfitGauge, Sparkline, margin_tone

    spark = Sparkline()
    spark.resize(120, 30)
    spark.set_values([1, 3, 2], animate=False)
    assert not spark.isHidden() and len(spark.points()) == 3
    spark.set_values([0, 0, 0], animate=False)
    assert spark.isHidden()  # nothing to show for an empty file
    gauge = ProfitGauge()
    gauge.set_margin(30, animate=False)
    assert gauge.shown == 30
    gauge.grab()  # paints without errors
    gauge.set_margin(None, animate=False)
    gauge.grab()
    assert [margin_tone(m) for m in (None, -5, 10, 40)] == ["neutral", "danger", "warning", "success"]
    AnimatedCheck().grab()


def test_count_up_glides_from_the_shown_value(app):
    from truck_tms.ui.theme import count_up

    label = QLabel()
    first = count_up(label, 100, lambda v: f"{v:.0f}")
    assert first.startValue() == 0
    second = count_up(label, 150, lambda v: f"{v:.0f}")
    assert second.startValue() == 100 and label.text() == "100"


def test_fill_table_stripes_and_flash(app):
    from truck_tms.ui.visuals import flash_row
    from truck_tms.ui.widgets import STRIPE_ROLE, fill_table, make_table

    table = make_table(["A", "B"])
    fill_table(table, [(1, ["x", "y"], "success"), (2, ["z", "w"])])
    assert table.item(0, 0).data(STRIPE_ROLE) == "success"
    assert table.item(1, 0).data(STRIPE_ROLE) is None
    called = []
    flash_row(table, 0, "danger", lambda: called.append(True))  # hidden table: no animation, done at once
    assert called == [True]


def test_splash_night_falls(app):
    from truck_tms.ui.splash import SplashScreen, _mix

    assert _mix("#000000", "#FFFFFF", 0.5).red() == 127
    splash = SplashScreen()
    for progress in (0.0, 0.5, 1.0):
        splash.progress = progress
        splash.grab()


# ------------------------------------------------------------------ main window
@pytest.fixture
def window(app, db):
    from truck_tms.ui.main_window import MainWindow

    truck = db.add_truck(Truck(plate="T1", unit_number="101"))
    driver = db.add_driver(Driver(name="Pat", pay_type="percent", pay_rate=25))
    db.add_load(Load(truck_id=truck, driver_id=driver, load_number="#100", rate=1000, loaded_miles=400,
                     status="planned", delivery_date=date.today().isoformat()))
    win = MainWindow(db)
    win.show()
    app.processEvents()
    yield win
    win.close()
    win.deleteLater()
    app.processEvents()


def test_overview_hero_today_and_onboarding(window):
    page = window.overview
    assert page.hello.text().startswith(("Good morning", "Good afternoon", "Good evening"))
    assert not page.onboarding.isVisible()  # a truck, a driver and a load exist
    labels = [w.text() for w in page.today_card.findChildren(QLabel)]
    assert any("Delivery today: #100" in text for text in labels)


def test_onboarding_shows_on_an_empty_file(app):
    from truck_tms.ui.main_window import MainWindow

    empty = Database()
    win = MainWindow(empty)
    win.show()
    app.processEvents()
    assert win.overview.onboarding.isVisible()
    texts = [w.text() for w in win.overview.onboarding.findChildren(QLabel)]
    assert "Add your first truck" in texts
    win.close()
    empty.close()


def test_board_view_moves_loads_and_remembers_the_view(window, db):
    from truck_tms.ui.loads import LoadsTab

    window.go_to_page(window.page_index(LoadsTab))
    page = window.tabs.currentWidget()
    page.set_view("board")
    assert page.body.currentWidget() is page.board
    assert db.get_settings()["loads_view"] == "board"
    planned = page.board.columns["planned"].list
    assert planned.count() == 1 and page.board.columns["planned"].count.text() == "1"
    page.move_load(1, "dispatched")
    assert db.get_load(1).status == "dispatched"
    assert page.board.columns["dispatched"].list.count() == 1 and planned.count() == 0
    page.set_view("list")
    assert page.body.currentWidget() is page.table


def test_details_panel_opens_and_closes(window):
    from truck_tms.ui.loads import LoadsTab

    window.quick_action("load:1")
    page = window.tabs.currentWidget()
    assert isinstance(page, LoadsTab) and page.panel.load_id == 1
    texts = [w.text() for w in page.panel.findChildren(QLabel)]
    assert "#100" in texts and "No invoice yet" in texts
    page.panel.close_panel()
    assert not page.panel.is_open
    assert page.panel.show_load(999) is False  # a load that no longer exists


def test_today_invoice_button_opens_the_invoice(window, monkeypatch):
    from truck_tms.ui.loads import LoadsTab

    opened = []
    monkeypatch.setattr(LoadsTab, "invoice_selected", lambda self, load_id=None: opened.append(load_id))
    window.quick_action("invoice:1")
    assert opened == [1]


def test_board_card_click_shows_details(window):
    from truck_tms.ui.loads import LoadsTab

    window.go_to_page(window.page_index(LoadsTab))
    page = window.tabs.currentWidget()
    page.set_view("board")
    item = page.board.columns["planned"].list.item(0)
    page.board.columns["planned"].list.itemClicked.emit(item)
    assert page.panel.load_id == item.data(Qt.ItemDataRole.UserRole)
    page.set_view("list")
