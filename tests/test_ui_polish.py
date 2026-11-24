"""Tests for the sidebar, overview page, animations, notifications, badges and empty states."""

import time
from datetime import date

import pytest
from PySide6.QtCore import QEvent
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel

from truck_tms.database import Database, Driver, Truck
from truck_tms.demo import seed_demo_data


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "tms.db")
    seed_demo_data(database)
    yield database
    try:
        database.close()
    except Exception:
        pass


@pytest.fixture
def window(app, db):
    from truck_tms.ui.main_window import MainWindow

    win = MainWindow(db)
    win.resize(1300, 760)
    win.show()
    app.processEvents()
    yield win
    win.close()
    win.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)


def wait_until(condition, timeout=3.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if condition():
            return True
        QTest.qWait(20)
    return condition()


# ------------------------------------------------------------------- sidebar
def test_sidebar_pages_icons_and_header(window):
    tabs = window.tabs
    assert [tabs.tabText(i) for i in range(tabs.count())] == [
        "Overview", "Trucks", "Drivers", "Loads", "Invoices", "Statements", "Driver Pay", "Maintenance", "Expenses",
        "Compliance", "IFTA", "Truck Report", "Settings"]
    assert all(not b.icon().isNull() for b in tabs._buttons)
    tabs.setCurrentIndex(3)
    assert tabs.title.text() == "Loads"
    assert "statement week" in tabs.subtitle.text()
    assert [b.isChecked() for b in tabs._buttons].count(True) == 1 and tabs._buttons[3].isChecked()


def test_selection_highlight_slides_to_the_chosen_page(window):
    tabs = window.tabs
    tabs.setCurrentIndex(5)
    target = tabs._target_rect()
    assert wait_until(lambda: tabs.indicator.geometry() == target)
    tabs.setCurrentIndex(1)
    assert tabs._indicator_anim.state() == tabs._indicator_anim.State.Running  # it moves, it does not jump
    assert wait_until(lambda: tabs.indicator.geometry() == tabs._target_rect())


def test_page_slides_back_into_place(window):
    tabs = window.tabs
    tabs.setCurrentIndex(2)
    page = tabs.currentWidget()
    assert page.pos().x() > 0  # starts a little to the right…
    assert wait_until(lambda: page.pos().x() == 0 and page.graphicsEffect() is None)  # …and settles


def test_theme_button_in_sidebar(window, app, db):
    assert window.theme_btn.text() == "Dark mode"
    window.toggle_theme()
    assert wait_until(lambda: app.palette().window().color() == QColor("#121417"))
    assert db.get_settings()["theme"] == "dark"
    assert wait_until(lambda: window.theme_btn.text() == "Light mode")
    window.toggle_theme()
    assert wait_until(lambda: app.palette().window().color() == QColor("#FFFFFF"))


# ------------------------------------------------------------------ overview
def test_overview_numbers(db):
    from truck_tms.ui.dashboard import compute_overview

    o = compute_overview(db)
    assert o.total_trucks == 3 and o.active_trucks == 2 and o.maintenance_trucks == 1
    assert o.in_progress == 1  # demo has one load in transit
    assert o.unpaid_total > 0 and o.unpaid_drivers >= 1
    assert o.service_due == 1  # truck 102 is past its oil-change odometer
    assert any("CDL" in text for _, text, _ in o.reminders)  # Maria's CDL expires within 30 days


def test_overview_cdl_and_empty_database(tmp_path):
    from truck_tms.ui.dashboard import compute_overview

    db = Database(tmp_path / "empty.db")
    o = compute_overview(db)
    assert (o.week_gross, o.total_trucks, o.unpaid_total, o.reminders) == (0, 0, 0, [])
    db.add_driver(Driver(name="Old CDL", license_expiry="2020-01-01"))
    db.add_truck(Truck(unit_number="1"))
    o = compute_overview(db, today=date(2026, 1, 1))
    assert o.reminders[0][0] == "danger" and "expired" in o.reminders[0][1]
    db.close()


def test_overview_cards_count_up_to_the_real_value(window):
    window.tabs.setCurrentIndex(1)
    window.tabs.setCurrentIndex(0)  # refresh → animated
    card = window.overview.cards["trucks"]
    assert wait_until(lambda: card.value.text() == "2 / 3")
    assert window.overview.recent.rowCount() == 7


def test_quick_action_opens_the_new_truck_dialog(window, monkeypatch):
    from truck_tms.ui.trucks import TrucksTab

    opened = []
    monkeypatch.setattr(TrucksTab, "open_dialog", lambda self, record_id: opened.append(record_id) or False)
    window.quick_action("new_truck")
    assert isinstance(window.tabs.currentWidget(), TrucksTab)
    assert opened == [None]


# ------------------------------------------------------------- notifications
def test_toast_slides_in_and_goes_away(window):
    from truck_tms.ui.toast import Toast, show_toast

    toast = show_toast("Saved", duration_ms=300)
    assert isinstance(toast, Toast) and toast.isVisible()
    assert toast.findChild(QLabel, None) is not None
    assert wait_until(lambda: toast._offset == 1.0)
    rect = toast.geometry()
    assert window.rect().contains(rect)  # inside the window, bottom right
    assert rect.right() > window.width() * 0.6 and rect.bottom() > window.height() * 0.6
    assert wait_until(lambda: not window.findChildren(Toast))  # removed after its time


def test_toast_without_main_window_is_skipped(app):
    from truck_tms.ui.toast import show_toast

    for w in QApplication.topLevelWidgets():
        if w.objectName() == "MainWindow":
            w.hide()
    assert show_toast("nothing to show on") is None


def test_saving_a_record_shows_a_toast(window, monkeypatch):
    from truck_tms.ui.toast import Toast
    from truck_tms.ui.trucks import TrucksTab

    monkeypatch.setattr(TrucksTab, "open_dialog", lambda self, record_id: True)
    window.tabs.setCurrentIndex(1)
    window.tabs.currentWidget()._open(None)
    toasts = window.findChildren(Toast)
    assert toasts and toasts[-1].findChildren(QLabel)[-1].text() == "Saved"


# ------------------------------------------------------------ badges / empty
def test_status_badges_in_tables(window):
    from truck_tms.ui.widgets import BADGE_ROLE

    window.tabs.setCurrentIndex(1)
    table = window.tabs.currentWidget().table
    status_col = [table.horizontalHeaderItem(c).text() for c in range(table.columnCount())].index("Status")
    tones = {table.item(r, status_col).text(): table.item(r, status_col).data(BADGE_ROLE)
             for r in range(table.rowCount())}
    assert tones == {"Active": "success", "In Maintenance": "warning"}
    assert not table.grab().isNull()  # the badge delegate paints


def test_empty_state_and_filtered_message(app, tmp_path):
    from truck_tms.ui.trucks import TrucksTab

    db = Database(tmp_path / "empty.db")
    page = TrucksTab(db)
    assert page.body.currentWidget() is page.empty
    assert page.empty.title.text() == "No trucks yet" and page.empty.add_btn.isVisibleTo(page)
    db.add_truck(Truck(unit_number="7"))
    page.refresh()
    assert page.body.currentWidget() is page.table
    page.search.setText("nothing-like-this")
    assert page.body.currentWidget() is page.empty
    assert page.empty.title.text() == "No matching records" and not page.empty.add_btn.isVisibleTo(page)
    assert not page.search.actions()[0].icon().isNull()  # search icon
    page.deleteLater()
    db.close()


def test_cards_lift_on_hover(window):
    window.tabs.setCurrentIndex(0)
    assert wait_until(lambda: window.overview.graphicsEffect() is None)  # page fade finished
    card = window.overview.cards["gross"]
    QApplication.sendEvent(card, QEvent(QEvent.Type.Enter))
    assert wait_until(lambda: card.graphicsEffect() is not None and card.graphicsEffect().blurRadius() > 15)
    QApplication.sendEvent(card, QEvent(QEvent.Type.Leave))
    assert wait_until(lambda: card.graphicsEffect() is None)


def test_nav_buttons_do_not_get_hover_shadow(window):
    button = window.tabs._buttons[2]
    QApplication.sendEvent(button, QEvent(QEvent.Type.Enter))
    QTest.qWait(50)
    assert button.graphicsEffect() is None


def test_turkish_sidebar(app, db):
    from truck_tms.ui.main_window import MainWindow

    db.set_setting("language", "tr")
    win = MainWindow(db)
    assert win.tabs.tabText(0) == "Genel Bakış" and win.theme_btn.text() == "Koyu tema"
    assert win.overview.cards["gross"].title.text() == "BU HAFTANIN BRÜTÜ"
    win.deleteLater()
