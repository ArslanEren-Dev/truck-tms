"""Excel/CSV import, load documents and overview charts."""

import csv
import time
import zipfile
from datetime import date
from pathlib import Path

import pytest
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from truck_tms.database import Database, Load, Truck, ValidationError
from truck_tms.demo import seed_demo_data
from truck_tms.importer import auto_map, import_loads, read_table, write_template
from truck_tms.numbers import parse_date


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "tms.db")
    yield database
    database.close()


def wait_until(condition, timeout=3.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if condition():
            return True
        QTest.qWait(20)
    return condition()


def make_xlsx(path: Path, rows: list[list]) -> Path:
    """Write a tiny but valid .xlsx (shared strings + numbers) without any library."""
    strings: list[str] = []
    cells_xml = []
    for r, row in enumerate(rows, start=1):
        cells = []
        for c, value in enumerate(row):
            ref = f"{chr(65 + c)}{r}"
            if isinstance(value, (int, float)):
                cells.append(f'<c r="{ref}"><v>{value}</v></c>')
            elif value is None:
                continue
            else:
                strings.append(str(value))
                cells.append(f'<c r="{ref}" t="s"><v>{len(strings) - 1}</v></c>')
        cells_xml.append(f'<row r="{r}">{"".join(cells)}</row>')
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    rel_ns = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        z.writestr("xl/workbook.xml", f'<workbook {ns} {rel_ns}><sheets><sheet name="Loads" sheetId="1" '
                                      f'r:id="rId1"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels",
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Target="worksheets/sheet1.xml" '
                   'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"/>'
                   '</Relationships>')
        z.writestr("xl/sharedStrings.xml",
                   f'<sst {ns}>' + "".join(f"<si><t>{s}</t></si>" for s in strings) + "</sst>")
        z.writestr("xl/worksheets/sheet1.xml", f'<worksheet {ns}><sheetData>{"".join(cells_xml)}</sheetData></worksheet>')
    return path


# ---------------------------------------------------------------- parsing
@pytest.mark.parametrize("text, expected", [
    ("2026-03-05", "2026-03-05"), ("03/05/2026", "2026-03-05"), ("3/5/26", "2026-03-05"),
    ("05.03.2026", "2026-03-05"), (46086, "2026-03-05"), ("46086", "2026-03-05"), ("", None),
    ("Mar 05, 2026", "2026-03-05"),
])
def test_parse_date(text, expected):
    assert parse_date(text) == expected


def test_parse_date_rejects_garbage():
    with pytest.raises(ValidationError):
        parse_date("next tuesday")


def test_auto_map_english_turkish_and_broker_headers():
    assert auto_map(["Load #", "Rate", "Pickup", "Delivery", "DH"]) == {
        "load_number": 0, "rate": 1, "pickup_location": 2, "delivery_location": 3, "dead_miles": 4}
    tr = auto_map(["Yük No", "Plaka", "Şoför", "Navlun", "Yüklü Mil", "Boş Mil", "Teslimat Tarihi"])
    assert tr == {"load_number": 0, "truck": 1, "driver": 2, "rate": 3, "loaded_miles": 4, "dead_miles": 5,
                  "delivery_date": 6}
    broker = auto_map(["PRO #", "Origin City", "Destination", "Linehaul ($)", "Miles", "Comments"])
    assert broker["rate"] == 3 and broker["pickup_location"] == 1 and broker["notes"] == 5


def test_read_csv_semicolon_and_turkish_encoding(tmp_path):
    path = tmp_path / "loads.csv"
    path.write_bytes("Yük No;Navlun;Müşteri\n1001;1.250,50;Şahin Lojistik\n\n".encode("cp1254"))
    headers, rows = read_table(path)
    assert headers == ["Yük No", "Navlun", "Müşteri"]
    assert rows == [["1001", "1.250,50", "Şahin Lojistik"]]


def test_read_xlsx(tmp_path):
    path = make_xlsx(tmp_path / "loads.xlsx", [["Load #", "Rate", "Pickup Date"], [5001, 2850.5, 46086],
                                               [None, None, None], ["5002", "1,900", "03/07/2026"]])
    headers, rows = read_table(path)
    assert headers == ["Load #", "Rate", "Pickup Date"]
    assert rows == [[5001, 2850.5, 46086], ["5002", "1,900", "03/07/2026"]]


def test_read_table_rejects_other_files(tmp_path):
    bad = tmp_path / "photo.png"
    bad.write_bytes(b"\x89PNG")
    with pytest.raises(ValidationError):
        read_table(bad)
    fake = tmp_path / "broken.xlsx"
    fake.write_text("not a zip")
    with pytest.raises(ValidationError):
        read_table(fake)


# ----------------------------------------------------------------- import
def test_import_loads_end_to_end(db, tmp_path):
    db.add_truck(Truck(plate="ABC123", unit_number="101"))
    db.add_load(Load(load_number="9000"))
    path = make_xlsx(tmp_path / "loads.xlsx", [
        ["Load #", "Truck", "Driver", "Broker", "Pickup", "PU Date", "Delivery", "Del Date", "Rate", "Miles", "DH",
         "Status", "TONU"],
        [5001, "101", "Ann Driver", "Acme", "Chicago, IL", 46086, "Dallas, TX", "03/06/2026", 2850, 925, 40,
         "Delivered", ""],
        [5002, "999", "Ann Driver", "Acme", "Dallas, TX", "2026-03-07", "Austin, TX", None, "1,200", 195, 0,
         "Teslim Edildi", ""],
        [9000, "101", None, None, "x", None, None, None, 1, None, None, None, None],        # duplicate
        [5003, "101", None, None, "x", "next week", None, None, 1, None, None, None, None],  # bad date
        [5004, None, None, "Peach", "Atlanta", None, None, None, 250, None, None, "Cancelled", "yes"],
        [None, None, None, None, None, None, None, None, None, None, None, None, None],
    ])
    headers, rows = read_table(path)
    result = import_loads(db, rows, auto_map(headers))
    assert result.imported == 3
    assert result.duplicates == 1
    assert result.errors == [(5, "error.invalid_date")]
    assert result.created_trucks == ["999"] and result.created_drivers == ["Ann Driver"]
    loads = {load.load_number: load for load in db.list_loads()}
    first = loads["#5001"]
    assert (first.pickup_date, first.delivery_date, first.rate, first.total_miles, first.status) == (
        "2026-03-05", "2026-03-06", 2850, 965, "delivered")
    assert db.get_truck(first.truck_id).plate == "ABC123"
    assert loads["#5002"].rate == 1200 and loads["#5002"].status == "delivered"
    assert loads["#5004"].is_tonu and loads["#5004"].status == "cancelled"


def test_import_without_creating_missing(db):
    rows = [["7001", "NOPE"]]
    result = import_loads(db, rows, {"load_number": 0, "truck": 1}, create_missing=False)
    assert result.imported == 0 and result.errors == [(2, "import.unknown_truck")]


def test_template_round_trip(db, tmp_path):
    path = write_template(tmp_path / "template.csv")
    headers, rows = read_table(path)
    mapping = auto_map(headers)
    assert len(mapping) == len(headers)  # every template column is recognised
    assert import_loads(db, rows, mapping).imported == 1


def test_import_dialog(app, db, tmp_path):
    from truck_tms.ui.import_dialog import ImportDialog

    path = tmp_path / "loads.csv"
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["Load #", "Rate", "Pickup"])
        writer.writerow(["111", "1000", "Reno, NV"])
        writer.writerow(["222", "2000", "Boise, ID"])
    dialog = ImportDialog(db)
    dialog.quiet = True
    assert not dialog.import_btn.isEnabled()
    assert dialog.load_file(path)
    assert dialog.preview.rowCount() == 2 and dialog.import_btn.isEnabled()
    assert dialog.combos["rate"].currentText() == "Rate"
    dialog.combos["pickup_location"].setCurrentIndex(0)  # user chooses not to import this column
    dialog.run_import()
    assert dialog.result.imported == 2
    assert all(load.pickup_location is None for load in db.list_loads())


# -------------------------------------------------------------- documents
def test_documents_are_copied_listed_and_removed(db, tmp_path):
    load_id = db.add_load(Load(load_number="1"))
    source = tmp_path / "POD signed.pdf"
    source.write_bytes(b"%PDF-1.4 test")
    first = db.add_document(load_id, source, "pod")
    second = db.add_document(load_id, source, "pod")  # same name → kept as a separate copy
    assert first.file_name == "POD signed.pdf" and second.file_name == "POD signed (2).pdf"
    assert db.document_path(first).read_bytes() == b"%PDF-1.4 test"
    assert db.documents_folder().name == "tms_documents"
    assert db.document_counts() == {load_id: 2}
    db.update_document_kind(second.id, "bol")
    assert [d.kind for d in db.list_documents(load_id)] == ["pod", "bol"]
    db.delete_document(first.id)
    assert not db.document_path(first).exists()
    db.delete_load(load_id)  # deleting the load removes its files too
    assert db.list_documents() == [] and not (db.documents_folder() / f"load_{load_id}").exists()


def test_backup_copy_includes_documents(db, tmp_path):
    load_id = db.add_load(Load(load_number="1"))
    source = tmp_path / "bol.pdf"
    source.write_bytes(b"bol")
    doc = db.add_document(load_id, source, "bol")
    target = db.backup_to(tmp_path / "backup" / "copy.db")
    restored = Database(target)
    copy_doc = restored.list_documents(load_id)[0]
    assert restored.document_path(copy_doc).read_bytes() == b"bol"  # the copy works on its own
    assert copy_doc.stored_as == doc.stored_as
    restored.close()


def test_document_validation(db, tmp_path):
    load_id = db.add_load(Load())
    with pytest.raises(ValidationError):
        db.add_document(load_id, tmp_path / "missing.pdf")
    real = tmp_path / "a.pdf"
    real.write_text("x")
    with pytest.raises(ValidationError):
        db.add_document(load_id, real, "photo")
    with pytest.raises(ValidationError):
        db.add_document(9999, real)


def test_guess_document_kind():
    from truck_tms.ui.documents import guess_kind

    assert guess_kind("Rate Confirmation 5501.pdf") == "rate_con"
    assert guess_kind("5501_BOL.pdf") == "bol"
    assert guess_kind("signed-pod.jpg") == "pod"
    assert guess_kind("Invoice 77.pdf") == "invoice"
    assert guess_kind("lumper receipt.png") == "receipt"
    assert guess_kind("IMG_2034.jpg") == "other"


def test_load_dialog_keeps_files_until_the_load_is_saved(app, db, tmp_path):
    from truck_tms.ui.loads import LoadDialog

    rc = tmp_path / "rate con.pdf"
    rc.write_text("rc")
    dialog = LoadDialog(db, None)
    dialog.documents.add_files([rc])
    assert dialog.documents.count() == 1 and db.list_documents() == []  # waiting for the load id
    dialog.load_number.setText("880")
    dialog.save()
    docs = db.list_documents(dialog.saved_id)
    assert [(d.file_name, d.kind) for d in docs] == [("rate con.pdf", "rate_con")]
    again = LoadDialog(db, db.get_load(dialog.saved_id))
    assert again.documents.count() == 1


@pytest.mark.parametrize("language", ["en", "tr"])
def test_load_dialog_rows_do_not_overlap(app, db, language):
    """Regression: wrapping hint texts made Qt squeeze the form so 'Notes' slid over the documents box."""
    from truck_tms.i18n import set_language
    from truck_tms.ui.dialog_kit import Section
    from truck_tms.ui.loads import LoadDialog

    set_language(language)
    dialog = LoadDialog(db, None)
    dialog.show()
    QTest.qWait(50)

    def bottom(w):
        return w.mapTo(dialog, w.rect().bottomLeft()).y()

    def top(w):
        return w.mapTo(dialog, w.rect().topLeft()).y()

    assert bottom(dialog.notes) < top(dialog.documents_card)
    cards = dialog.findChildren(Section)
    assert len(cards) == 5
    for card in cards:  # every field sits inside its own card
        for child in card.findChildren(QWidget):
            if child.isVisible() and child.parentWidget() is card:
                assert top(child) >= top(card) and bottom(child) <= bottom(card) + 1, child
    dialog.close()
    set_language("en")


def test_statement_export_with_documents(app, tmp_path):
    from truck_tms.statement import compute_statement
    from truck_tms.ui.export import write_statement_files

    db = Database(tmp_path / "demo.db")
    seed_demo_data(db)
    statement = [s for s in db.list_statements() if s.truck_id == 1][0]
    summary = compute_statement(db, statement)
    pod = tmp_path / "pod.pdf"
    pod.write_bytes(b"%PDF pod")
    db.add_document(summary.loads[0].id, pod, "pod")
    files = write_statement_files([summary], "csv", tmp_path / "out", "week", db.get_settings(),
                                  db=db, include_documents=True)
    copied = [f for f in files if f.parent.name == "week_documents"]
    assert len(copied) == 1 and "POD" in copied[0].name and copied[0].read_bytes() == b"%PDF pod"
    db.close()


# ----------------------------------------------------------------- charts
def test_trends(tmp_path):
    from truck_tms.ui.dashboard import compute_trends

    db = Database(tmp_path / "t.db")
    db.add_load(Load(broker="A", rate=1000, loaded_miles=400, delivery_date="2026-03-04"))  # week of 03-02
    db.add_load(Load(broker="B", rate=3000, loaded_miles=1000, delivery_date="2026-03-11"))
    db.add_load(Load(broker="A", rate=500, delivery_date="2026-03-12", status="cancelled"))  # not counted
    trends = compute_trends(db, weeks=3, today=date(2026, 3, 12))
    assert trends.weeks == ["2026-02-23", "2026-03-02", "2026-03-09"]
    assert trends.gross == [0, 1000, 3000]
    assert trends.rate_per_mile == [0, 2.5, 3]
    assert trends.top_brokers == [("B", 3000), ("A", 1000)]
    db.close()


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_charts_animate_and_paint(app, theme):
    from truck_tms.ui.charts import BarChart, LineChart, RankChart
    from truck_tms.ui.theme import apply_theme

    apply_theme(theme)
    for chart, labels, values in (
        (BarChart(), ["a", "b", "c"], [10, 0, 30]),
        (LineChart(), ["a", "b", "c"], [2.5, 0, 3.1]),
        (RankChart(), ["Acme", "Blue"], [500, 200]),
    ):
        chart.resize(320, 200)
        chart.set_data(labels, values)
        assert chart.progress == 0.0
        assert wait_until(lambda c=chart: c.progress == 1.0)
        assert not chart.grab().isNull()
        chart.set_data([], [], animate=False)
        assert not chart.has_data() and not chart.grab().isNull()  # "no data" text
    apply_theme("light")


def test_overview_shows_charts(app, tmp_path):
    from truck_tms.ui.dashboard import OverviewTab

    db = Database(tmp_path / "demo.db")
    seed_demo_data(db)
    page = OverviewTab(db)
    assert page.gross_chart.values[-2] > 0 and len(page.gross_chart.values) == 8
    assert len(page.broker_chart.labels) == 5
    assert max(page.rpm_chart.values) > 2
    page.deleteLater()
    db.close()
