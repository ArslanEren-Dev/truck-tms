"""GUI tests: they drive the real windows and dialogs (offscreen, no clicks needed)."""

import time
from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, QTimer
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QGraphicsDropShadowEffect, QPushButton

from truck_tms.database import Database
from truck_tms.demo import seed_demo_data
from truck_tms.i18n import set_language
from truck_tms.statement import compute_statement


@pytest.fixture(scope="session")
def app():
    application = QApplication.instance() or QApplication([])
    yield application
    # close and delete every window before Python shuts down (avoids a crash at interpreter exit)
    for widget in application.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    application.processEvents()


@pytest.fixture(autouse=True)
def _cleanup_windows(request):
    yield
    if "app" in request.fixturenames:
        for widget in QApplication.topLevelWidgets():
            widget.close()
            widget.deleteLater()
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)


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

    changed = []
    win = MainWindow(db, on_file_changed=changed.append)
    win.changed_files = changed
    win.show()
    app.processEvents()
    yield win
    win.close()
    win.deleteLater()
    app.processEvents()


def wait_until(condition, timeout=3.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if condition():
            return True
        QTest.qWait(20)
    return condition()


# ------------------------------------------------------------------- theme / look
def test_light_theme_is_pure_white_and_dark_is_black(app):
    from truck_tms.ui.theme import apply_theme, stylesheet

    apply_theme("light")
    assert app.palette().window().color() == QColor("#FFFFFF")
    assert app.palette().base().color() == QColor("#FFFFFF")
    apply_theme("dark")
    assert app.palette().window().color() == QColor("#121417")
    for theme in ("light", "dark"):
        qss = stylesheet(theme)
        assert "@" not in qss  # every color token was filled in
        assert Path(qss.split('url("')[1].split('")')[0]).is_file()  # chevron icon exists
    apply_theme("light")


def test_icons_render(app):
    from truck_tms.ui.theme import ICON_PATHS, icon

    for name in ICON_PATHS:
        assert not icon(name).pixmap(16, 16).isNull(), name


def test_button_lifts_on_hover_and_sinks_on_press(app):
    from truck_tms.ui.theme import apply_theme, style_button

    apply_theme("light")
    btn = style_button(QPushButton("Add"), "primary", "plus")
    btn.show()
    QApplication.sendEvent(btn, QEvent(QEvent.Type.Enter))
    effect = btn.graphicsEffect()
    assert isinstance(effect, QGraphicsDropShadowEffect)
    assert wait_until(lambda: effect.blurRadius() > 15)
    QApplication.sendEvent(btn, QEvent(QEvent.Type.Leave))
    assert wait_until(lambda: btn.graphicsEffect() is None)  # shadow removed when back at rest
    assert btn.property("variant") == "primary"
    btn.close()


def test_tab_fade_and_button_shadow_never_overlap(app):
    """Nested graphics effects draw black boxes in Qt; the two animations must not overlap."""
    from PySide6.QtWidgets import QVBoxLayout, QWidget

    from truck_tms.ui.theme import fade_in, style_button

    page = QWidget()
    btn = style_button(QPushButton("Edit"), None, "edit")
    QVBoxLayout(page).addWidget(btn)
    page.show()
    fade_in(page)
    assert page.graphicsEffect() is not None
    QApplication.sendEvent(btn, QEvent(QEvent.Type.Enter))
    assert btn.graphicsEffect() is None  # no shadow while the page fades
    assert wait_until(lambda: page.graphicsEffect() is None)
    QApplication.sendEvent(btn, QEvent(QEvent.Type.Enter))
    assert btn.graphicsEffect() is not None  # shadow works once the fade is over
    fade_in(page)
    assert page.graphicsEffect() is None  # and no fade starts while a shadow is showing
    page.close()


# ------------------------------------------------------------------------ splash
def test_splash_truck_drives_to_the_end_of_the_road(app):
    from truck_tms.ui.splash import SplashScreen

    splash = SplashScreen(duration_ms=300)
    done = []
    splash.finished.connect(lambda: done.append(True))
    splash.show()
    splash.start()
    assert splash.status_text() == "Opening your data…"
    assert wait_until(lambda: done)
    assert splash.progress == 1.0
    assert splash.status_text() == "Ready!"
    end = splash.path.pointAtPercent(1.0)
    assert end.x() > splash.path.pointAtPercent(0.0).x()  # the road goes left to right
    assert not splash.grab().isNull()  # painting works
    set_language("tr")
    assert splash.status_text() == "Hazır!"
    splash.close()


# ------------------------------------------------------------------- main window
@pytest.mark.parametrize("language", ["en", "tr"])
@pytest.mark.parametrize("theme", ["light", "dark"])
def test_every_tab_opens(app, db, language, theme):
    from truck_tms.ui.main_window import MainWindow

    db.set_setting("language", language)
    db.set_setting("theme", theme)
    win = MainWindow(db)
    win.show()
    for i in range(win.tabs.count()):
        win.tabs.setCurrentIndex(i)
        app.processEvents()
        assert not win.grab().isNull()
    titles = [win.tabs.tabText(i) for i in range(win.tabs.count())]
    if language == "tr":
        assert titles[:4] == ["Genel Bakış", "Tırlar", "Sürücüler", "Yükler"]
        assert win.menuBar().actions()[0].text() == "&Dosya"
    else:
        assert titles[:4] == ["Overview", "Trucks", "Drivers", "Loads"]
    assert win.tabs.widget(1).table.rowCount() == 3
    win.close()


def test_help_menu_links_to_github(window, monkeypatch):
    import truck_tms
    from truck_tms.ui.main_window import MainWindow

    opened = []
    monkeypatch.setattr(MainWindow, "open_url", staticmethod(opened.append))
    help_menu = window.menuBar().actions()[1].menu()
    texts = [a.text() for a in help_menu.actions() if not a.isSeparator()]
    assert texts == ["Project Website", "Source Code on GitHub", "Report a Problem…", "Keyboard Shortcuts",
                     "Check for Updates…",
                     "About Truck TMS"]
    for action in help_menu.actions()[:3]:
        action.trigger()
    assert opened == [truck_tms.WEBSITE_URL, truck_tms.PROJECT_URL, truck_tms.PROJECT_URL + "/issues"]


def test_status_bar_shows_data_file_and_saves(window, db):
    assert db.path in window.file_label.text()
    assert "saved automatically" in window.saved_label.text()
    from truck_tms.database import Truck

    db.add_truck(Truck(unit_number="900"))
    window._check_saved()
    assert "Saved at" in window.saved_label.text()
    window.save_now()
    assert "Saved at" in window.saved_label.text()


def test_open_another_data_file(window, tmp_path):
    new_path = tmp_path / "second.db"
    assert window.switch_database(str(new_path))
    assert window.db.path == str(new_path)
    assert new_path.is_file()
    assert window.changed_files == [str(new_path.resolve())]
    assert window.tabs.widget(1).table.rowCount() == 0  # empty new file
    assert "second.db" in window.windowTitle()
    window.db.close()


def test_opening_a_bad_file_shows_an_error_and_keeps_the_old_one(window, tmp_path, monkeypatch):
    import truck_tms.ui.main_window as mw

    errors = []
    monkeypatch.setattr(mw, "show_error", lambda parent, err: errors.append(getattr(err, "key", err)))
    bad = tmp_path / "bad.db"
    bad.write_text("not a database" * 100)
    old_path = window.db.path
    assert not window.switch_database(str(bad))
    assert errors == ["file.not_valid"]
    assert window.db.path == old_path
    assert window.db.list_trucks()  # old file still open and working


def test_changing_theme_and_language_in_settings(window, app, db):
    settings_tab = window.tabs.widget(window.tabs.count() - 1)
    settings_tab.theme.setCurrentIndex(settings_tab.theme.findData("dark"))
    settings_tab.language.setCurrentIndex(settings_tab.language.findData("tr"))
    settings_tab.save()
    assert wait_until(lambda: window.tabs.tabText(0) == "Genel Bakış")
    assert app.palette().window().color() == QColor("#121417")
    assert db.get_settings()["theme"] == "dark"
    from truck_tms.ui.theme import apply_theme

    apply_theme("light")


# ----------------------------------------------------------------------- dialogs
def test_add_truck_driver_load_maintenance_expense_through_dialogs(app, db):
    from truck_tms.ui.drivers import DriverDialog
    from truck_tms.ui.expenses import ExpenseDialog
    from truck_tms.ui.loads import LoadDialog
    from truck_tms.ui.maintenance import MaintenanceDialog
    from truck_tms.ui.trucks import TruckDialog

    d = TruckDialog(db, None)
    d.unit_number.setText("777")
    d.make.setCurrentText("Kenworth")
    d.model.setCurrentText("W900")
    d.year.setCurrentText("2024")
    d.odometer.setText("12,500")
    d.save()
    truck = db.find_truck("777")
    assert truck.make == "Kenworth" and truck.year == 2024 and truck.odometer == 12500

    d = DriverDialog(db, None)
    d.name.setText("Test Driver")
    d.pay_rate.setText("0,70")
    d.pay_type.setCurrentIndex(d.pay_type.findData("per_mile"))
    d.save()
    driver = [x for x in db.list_drivers() if x.name == "Test Driver"][0]
    assert driver.pay_rate == 0.7

    d = LoadDialog(db, None)
    d.truck.setCurrentIndex(d.truck.findData(truck.id))
    d.driver.setCurrentIndex(d.driver.findData(driver.id))
    d.load_number.setText("55501")
    d.rate.setText("1500")
    d.loaded_miles.setText("500")
    d.dead_miles.setText("20")
    d.save()
    load = [x for x in db.list_loads() if x.load_number == "#55501"][0]
    assert load.total_miles == 520 and load.driver_id == driver.id
    assert "520" in d.totals.text()

    d = MaintenanceDialog(db, None, default_truck=truck.id)
    d.odometer.setText("13000")
    d.cost.setText("250")
    d.save()
    assert db.get_truck(truck.id).odometer == 13000

    d = ExpenseDialog(db, None, default_truck=truck.id)
    d.amount.setText("80")
    d.save()
    assert db.list_expenses(truck_id=truck.id)[0].amount == 80


def test_statement_dialog_calculates_and_saves(app, db):
    from truck_tms.ui.statements import StatementDialog

    existing = [s for s in db.list_statements() if s.truck_id == 1][0]
    d = StatementDialog(db, existing)
    d.recalc()
    assert "Owner Payout" in d.preview.toPlainText()
    assert d.loads_table.rowCount() == 4

    new = StatementDialog(db, None, default_truck=2)
    new.week.setDate(new.week.date().addDays(-21))
    new.fuel_amount.setText("100")
    new._add_item_row()
    new.items.item(0, 1).setText("Advance")
    new.items.item(0, 2).setText("12,5")
    new.save()
    saved = [s for s in db.list_statements() if s.truck_id == 2 and s.fuel_amount == 100][0]
    assert db.statement_items(saved.id)[0].amount == 12.5


# ------------------------------------------------------------------------ export
def test_export_statement_files(app, db, tmp_path):
    from truck_tms.ui.export import write_statement_files

    summary = compute_statement(db, [s for s in db.list_statements() if s.truck_id == 1][0])
    files = write_statement_files([summary], "all", tmp_path / "out", "my statement", db.get_settings())
    assert [f.name for f in files] == ["my_statement_owner.pdf", "my_statement_driver.pdf", "my_statement.csv"]
    for f in files:
        assert f.stat().st_size > 500
    assert files[0].read_bytes()[:4] == b"%PDF"

    week = summary.week_start
    summaries = [compute_statement(db, s) for s in db.list_statements() if s.week_start == week]
    files = write_statement_files(summaries, "owner_pdf", tmp_path / "week", "ignored", db.get_settings())
    assert len(files) == 2 and len({f.name for f in files}) == 2  # one file per truck, no overwrite


def test_export_report_files(app, db, tmp_path):
    from truck_tms.report import build_truck_report
    from truck_tms.ui.export import write_report_files

    report = build_truck_report(db, 1, "2020-01-01", "2030-12-31")
    files = write_report_files(report, "pdf_csv", tmp_path, "report:1?", db.get_settings())
    assert [f.name for f in files] == ["report_1_.pdf", "report_1_.csv"]


def test_export_dialog_remembers_folder(app, db, tmp_path):
    from truck_tms.ui.export import STATEMENT_FORMATS, ExportDialog

    dialog = ExportDialog(db, None, "Export", STATEMENT_FORMATS, "stmt",
                          scopes=[("one", "This"), ("week", "Week")])
    dialog.folder.setText(str(tmp_path / "exports"))
    dialog.format.setCurrentIndex(dialog.format.findData("csv"))
    dialog.open_after.setChecked(False)
    dialog._accept()
    choice = dialog.choice()
    assert (choice.fmt, choice.scope, choice.stem, choice.open_after) == ("csv", "one", "stmt", False)
    assert db.get_settings()["export_dir"] == str(tmp_path / "exports")
    dialog.scope.setCurrentIndex(1)
    assert not dialog.stem.isEnabled()  # names are automatic for many files
    again = ExportDialog(db, None, "Export", STATEMENT_FORMATS, "stmt")
    assert again.folder.text() == str(tmp_path / "exports")
    assert not again.open_after.isChecked()


# -------------------------------------------------------------- whole program
def test_self_test_mode(app, tmp_path):
    from truck_tms.__main__ import main

    assert main(["--self-test", str(tmp_path)]) == 0
    log = (tmp_path / "self_test.log").read_text(encoding="utf-8")
    assert "FAILED" not in log
    assert "screens tr/dark: Genel Bakış" in log
    assert (tmp_path / "statement_owner.pdf").is_file()

def test_program_starts_with_splash_and_demo_data(app, tmp_path):
    from truck_tms.__main__ import main

    path = tmp_path / "start.db"
    # quit once the main window is up (after the ~2.4 s splash). Polling instead of a fixed delay:
    # app.quit() before app.exec() has started does nothing, so a slow start-up would hang the test.
    def quit_when_window_shows():
        if any(w.objectName() == "MainWindow" and w.isVisible() for w in QApplication.topLevelWidgets()):
            poll.stop()
            QTimer.singleShot(300, app.quit)

    poll = QTimer()
    poll.timeout.connect(quit_when_window_shows)
    poll.start(100)
    assert main(["--db", str(path), "--demo"]) == 0
    poll.stop()
    db = Database(path)
    assert len(db.list_trucks()) == 3
    db.close()
