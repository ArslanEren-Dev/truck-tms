"""GUI tests for v0.6: invoices, compliance, IFTA pages, the update check and the new chart behavior."""

import time
from datetime import date, timedelta

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog

from truck_tms.database import Database, Load
from truck_tms.demo import seed_demo_data
from truck_tms.updates import Release


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
    win.resize(1360, 800)
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


def page(window, cls):
    index = window.page_index(cls)
    window.tabs.setCurrentIndex(index)
    return window.tabs.widget(index)


def run_dialog(monkeypatch, cls, act):
    """Make ``cls.exec`` call ``act(dialog)`` instead of blocking; ``act`` saves or rejects."""
    def fake_exec(self):
        act(self)
        return self.result()
    monkeypatch.setattr(cls, "exec", fake_exec)


# ----------------------------------------------------------------- demo / overview
def test_demo_has_v06_data(db):
    from truck_tms.compliance import attention_needed, compliance_entries
    from truck_tms.ifta import compute_ifta
    from truck_tms.invoicing import compute_receivables

    r = compute_receivables(db)
    assert r.open_count >= 2 and r.overdue_count >= 1 and r.collected_30d > 0
    assert len(attention_needed(compliance_entries(db))) >= 3
    last_week = date.today() - timedelta(days=7)
    year, quarter = last_week.year, (last_week.month - 1) // 3 + 1
    assert compute_ifta(db, year, quarter).total_miles > 0


def test_overview_shows_receivables_compliance_and_expense_chart(window):
    o = window.overview.overview
    assert o.receivable_total > 0 and o.overdue_invoices >= 1
    assert o.compliance_alerts >= 3 and o.compliance_expired >= 1
    assert any("Invoice" in text and "late" in text for _, text, _ in o.reminders)
    assert any("expired" in text for _, text, _ in o.reminders)
    assert window.overview.expense_chart.has_data()
    assert len(window.overview.cards) == 8


# ----------------------------------------------------------------- invoices
def test_invoices_page_summary_and_rows(window):
    from truck_tms.ui.invoices import InvoicesTab

    tab = page(window, InvoicesTab)
    assert tab.table.rowCount() == len(window.db.list_invoices())
    assert tab.aging.has_data() and len(tab.aging.values) == 5
    tab.status_filter.setCurrentIndex(tab.status_filter.findData("overdue"))
    assert 1 <= tab.table.rowCount() < len(window.db.list_invoices())
    tab.status_filter.setCurrentIndex(tab.status_filter.findData("paid"))
    statuses = {tab.table.item(r, 8).text() for r in range(tab.table.rowCount())}
    assert statuses == {"Paid"}


def test_invoice_from_load_prefills_and_saves(window, monkeypatch):
    from truck_tms.ui.invoices import InvoiceDialog
    from truck_tms.ui.loads import LoadsTab

    db = window.db
    load_id = db.add_load(Load(load_number="5550001", broker="River Freight", rate=1800, extra_pay=75,
                               status="delivered", delivery_date=date.today().isoformat()))
    tab = page(window, LoadsTab)
    tab.refresh()
    row = next(r for r in range(tab.table.rowCount()) if tab.table.item(r, 0).text() == "#5550001")
    tab.table.selectRow(row)
    seen = {}

    def act(dialog):
        seen["amount"] = dialog.amount.value()
        seen["bill_to"] = dialog.bill_to.toPlainText()
        seen["number"] = dialog.number.text()
        dialog._mark_paid()
        dialog.save()
    run_dialog(monkeypatch, InvoiceDialog, act)
    assert tab.invoice_selected()
    assert seen["amount"] == 1875 and seen["bill_to"] == "River Freight" and seen["number"].startswith("INV-")
    inv = db.invoice_for_load(load_id)
    assert inv.paid_amount == 1875 and inv.status() == "paid" and db.get_load(load_id).status == "paid"


def test_invoice_dialog_balance_and_header(app, db):
    from truck_tms.ui.invoices import InvoiceDialog

    dialog = InvoiceDialog(db, None)
    dialog.amount.setText("1000")
    dialog.fee.setText("30")
    dialog.paid_amount.setText("500")
    assert "470.00" in dialog.balance.text()
    dialog.terms.setValue(15)
    assert dialog.issue_date.date().addDays(15).toString("yyyy-MM-dd") in dialog.due.text()
    assert dialog.number.text() in dialog.page.header.subtitle.text()
    dialog.close()


def test_invoice_pdf(window, tmp_path, monkeypatch):
    from truck_tms.ui import invoices

    inv = window.db.list_invoices()[0]
    target = tmp_path / "out" / "invoice.pdf"
    monkeypatch.setattr(invoices.QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(target), "")))
    assert invoices.save_invoice_pdf(window, window.db, inv) == target
    assert target.read_bytes()[:4] == b"%PDF"


# ----------------------------------------------------------------- compliance
def test_compliance_page_filters_and_driver_cdl(window, monkeypatch):
    from truck_tms.ui.compliance_tab import ComplianceDialog, ComplianceTab

    tab = page(window, ComplianceTab)
    total = tab.table.rowCount()
    assert total >= 9 and "expired" in tab.summary.text()
    tab.filter.setCurrentIndex(tab.filter.findData("expired"))
    assert 1 <= tab.table.rowCount() < total
    tab.filter.setCurrentIndex(0)
    # Maria's CDL comes from the driver form (negative id); editing turns it into a record
    def from_form():
        return [r for r in range(tab.table.rowCount()) if "driver form" in tab.table.item(r, 0).text()]
    before = len(from_form())
    cdl_id = tab.table.item(from_form()[0], 0).data(Qt.ItemDataRole.UserRole)
    assert cdl_id < 0

    def act(dialog):
        assert dialog.kind.currentData() == "cdl" and dialog.driver.isVisibleTo(dialog)
        assert not dialog.truck.isVisibleTo(dialog)
        dialog.save()
    run_dialog(monkeypatch, ComplianceDialog, act)
    assert tab.open_dialog(cdl_id)
    tab.refresh()
    assert len(from_form()) == before - 1
    assert [i.driver_id for i in window.db.list_compliance() if i.kind == "cdl"] == [-cdl_id]


def test_compliance_dialog_switches_owner_field(app, db):
    from truck_tms.ui.compliance_tab import ComplianceDialog

    dialog = ComplianceDialog(db, None)
    dialog.show()
    dialog.kind.setCurrentIndex(dialog.kind.findData("insurance"))
    assert dialog.truck.isVisible() and not dialog.driver.isVisible()
    dialog.kind.setCurrentIndex(dialog.kind.findData("ucr"))
    assert not dialog.truck.isVisible() and not dialog.driver.isVisible()
    assert not dialog.kind.model().item(0).isEnabled()  # group headings cannot be picked
    dialog.save()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert sum(i.kind == "ucr" for i in db.list_compliance()) == 2  # the demo one + this one
    dialog.close()


# ----------------------------------------------------------------- IFTA
def test_ifta_page_generates_for_the_demo_quarter(window):
    from truck_tms.ui.ifta_tab import IftaTab

    tab = page(window, IftaTab)
    last_week = date.today() - timedelta(days=7)
    tab.year.setValue(last_week.year)
    tab.quarter.setCurrentIndex((last_week.month - 1) // 3)
    assert tab.report.total_miles > 0 and tab.report.mpg
    assert "IFTA" in tab.preview.toPlainText() and "TX" in tab.preview.toPlainText()


def test_ifta_rates_dialog_saves(app, db):
    from truck_tms.ui.ifta_tab import IftaRatesDialog

    dialog = IftaRatesDialog(db)
    row = [dialog.table.item(r, 0).text() for r in range(dialog.table.rowCount())].index("WY")
    dialog.table.item(row, 1).setText("0.24")
    dialog.save()
    assert db.ifta_rates()["WY"] == 0.24
    dialog.table.item(row, 1).setText("")
    dialog.save()
    assert "WY" not in db.ifta_rates()


def test_load_dialog_miles_by_state(app, db):
    from truck_tms.ui.loads import LoadDialog

    load = db.list_loads(search="4410021")[0]
    dialog = LoadDialog(db, load)
    editor = dialog.state_miles
    assert [s for s, _ in editor.states()] == ["IL", "MO", "OK", "TX"]
    assert "✓" in editor.total.text()  # the split matches loaded + empty miles
    editor.add_row("AR", 50)
    assert "≠" in editor.total.text()
    editor._remove(editor.rows[-1])
    editor._remove(editor.rows[0])
    dialog.save()
    assert [s for s, _ in db.load_states(load.id)] == ["MO", "OK", "TX"]
    dialog.close()


def test_expense_dialog_fuel_fields(app, db):
    from truck_tms.ui.expenses import ExpenseDialog

    dialog = ExpenseDialog(db, None)
    dialog.show()
    dialog.category.setCurrentIndex(dialog.category.findData("tolls"))
    assert not dialog.gallons.isVisible()
    dialog.category.setCurrentIndex(dialog.category.findData("fuel"))
    assert dialog.gallons.isVisible() and dialog.state.isVisible()
    dialog.amount.setText("400")
    dialog.gallons.setText("100")
    dialog.state.setCurrentIndex(dialog.state.findData("NV"))
    dialog.save()
    saved = [e for e in db.list_expenses() if e.state == "NV"]
    assert saved and saved[0].gallons == 100
    dialog.close()


# ----------------------------------------------------------------- updates
def test_update_found_shows_button_and_toast(window, monkeypatch):
    shown = []
    monkeypatch.setattr("truck_tms.ui.main_window.show_toast", lambda *a, **k: shown.append(a))
    assert not window.update_btn.isVisibleTo(window)
    window._update_checked(Release("99.0.0", "https://example/r", "https://example/exe"))
    assert window.update_btn.isVisibleTo(window) and "99.0.0" in shown[0][0]
    assert window.db.get_settings()["update_checked"] == date.today().isoformat()
    opened = []
    monkeypatch.setattr(type(window), "open_url", staticmethod(opened.append))
    window.update_btn.click()
    assert opened == ["https://example/r"]


def test_manual_check_reports_latest_or_failure(window, monkeypatch):
    messages = []
    monkeypatch.setattr("truck_tms.ui.main_window.show_info", lambda _p, text: messages.append(text))
    window._manual_check = True
    window._update_checked(Release("0.0.1", "u", "u"))
    window._manual_check = True
    window._update_checked(None)
    assert "latest version" in messages[0] and "Could not reach" in messages[1]
    assert not window.update_btn.isVisibleTo(window)


def test_update_checker_thread_reports_back(app):
    from truck_tms.ui.update_check import UpdateChecker

    checker = UpdateChecker(fetch=lambda: Release("1.2.3", "u", "u"))
    got = []
    checker.finished.connect(got.append)
    checker.start()
    assert wait_until(lambda: got)
    assert got[0].version == "1.2.3"
    failing = UpdateChecker(fetch=lambda: 1 / 0)
    failing.finished.connect(got.append)
    failing.start()
    assert wait_until(lambda: len(got) == 2) and got[1] is None


def test_settings_save_invoice_and_update_options(window):
    from truck_tms.ui.settings import SettingsTab

    tab = page(window, SettingsTab)
    tab.invoice_prefix.setText("TT-")
    tab.invoice_terms.setValue(45)
    tab.check_updates.setChecked(False)
    tab.save()
    s = window.db.get_settings()
    assert (s["invoice_prefix"], s["invoice_terms"], s["check_updates"]) == ("TT-", "45", "0")
    assert window.db.next_invoice_number() == "TT-0001"


# ----------------------------------------------------------------- charts & tables
def _move(widget, x, y):
    event = QMouseEvent(QEvent.Type.MouseMove, QPointF(x, y), QPointF(x, y), Qt.MouseButton.NoButton,
                        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(widget, event)


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_donut_and_hover_bubbles(app, theme):
    from truck_tms.ui.charts import BarChart, DonutChart, LineChart, compact, nice_max
    from truck_tms.ui.theme import apply_theme

    apply_theme(theme)
    donut = DonutChart()
    donut.resize(360, 200)
    donut.set_data(["Fuel", "Tolls", "Repair"], [600, 100, 300], animate=False)
    ring, _ = donut._geometry()
    _move(donut, ring.center().x() + ring.width() * 0.42, ring.center().y())  # right side: 3 o'clock
    assert donut.hover == 0  # fuel covers 0°–216° clockwise from 12 o'clock
    assert not donut.grab().isNull()
    for chart in (BarChart(), LineChart()):
        chart.resize(400, 220)
        chart.set_data(["a", "b", "c", "d"], [10, 40, 0, 25], animate=False)
        rect = chart.plot_rect()
        _move(chart, rect.left() + rect.width() * 0.3, rect.center().y())
        assert chart.hover == 1
        assert wait_until(lambda c=chart: c.hover_pos == 1.0)
        assert not chart.grab().isNull()
        chart.leaveEvent(None)
        assert chart.hover == -1
    assert (compact(950), compact(12_400), compact(3_200_000), compact(0)) == ("950", "12.4k", "3.2M", "0")
    assert (nice_max(87), nice_max(1200), nice_max(0)) == (100, 2000, 1.0)
    apply_theme("light")


def test_bars_grow_one_after_another(app):
    from truck_tms.ui.charts import BarChart

    chart = BarChart()
    chart.set_data(["a", "b", "c"], [1, 1, 1], animate=False)
    chart.progress = 0.4
    first, last = chart.item_progress(0, 3), chart.item_progress(2, 3)
    assert first > last >= 0
    chart.progress = 1.0
    assert chart.item_progress(2, 3) == 1.0


def test_table_row_hover_tints_whole_row(window):
    from truck_tms.ui.loads import LoadsTab

    tab = page(window, LoadsTab)
    table = tab.table
    delegate = table.itemDelegate()
    y = table.visualRect(table.model().index(1, 0)).center().y()
    _move(table.viewport(), 20, y)
    assert delegate.hover.row == 1
    QApplication.sendEvent(table.viewport(), QEvent(QEvent.Type.Leave))
    assert delegate.hover.row == -1


def test_new_pages_render_in_both_themes_and_languages(app, db):
    from truck_tms.i18n import set_language
    from truck_tms.ui.main_window import MainWindow
    from truck_tms.ui.compliance_tab import ComplianceTab
    from truck_tms.ui.ifta_tab import IftaTab
    from truck_tms.ui.invoices import InvoicesTab

    for language, theme in (("tr", "dark"), ("en", "light")):
        db.set_setting("language", language)
        db.set_setting("theme", theme)
        win = MainWindow(db)
        win.resize(1360, 800)
        win.show()
        for cls in (InvoicesTab, ComplianceTab, IftaTab):
            p = page(win, cls)
            QTest.qWait(10)
            assert not p.grab().isNull()
        if language == "tr":
            assert win.tabs.tabText(win.page_index(InvoicesTab)) == "Faturalar"
        win.close()
        win.deleteLater()
    set_language("en")


def test_invoice_rows_need_unique_numbers_in_dialog(app, db, monkeypatch):
    from truck_tms.ui.invoices import InvoiceDialog

    errors = []
    monkeypatch.setattr("truck_tms.ui.invoices.show_error", lambda _p, e: errors.append(e.key))
    first = db.list_invoices()[0]
    dialog = InvoiceDialog(db, None)
    dialog.number.setText(first.invoice_number)
    dialog.amount.setText("10")
    dialog.save()
    assert errors == ["error.invoice_number_exists"] and dialog.result() != QDialog.DialogCode.Accepted
    dialog.close()
