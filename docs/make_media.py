"""Regenerate the screenshots and the promo banner used by README.md and docs/index.html.

Usage (from the project folder, with the app installed):  python docs/make_media.py

Everything is rendered off-screen from the demo data, at 2x resolution for sharp images.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_SCALE_FACTOR", "2")
if os.name == "nt":
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

from PySide6.QtCore import QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import (  # noqa: E402
    QColor,
    QFont,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtSvg import QSvgRenderer  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

DOCS = Path(__file__).resolve().parent
SHOTS = DOCS / "screenshots"
PNG_MAX_COMPRESSION = 0  # Qt: PNG quality 0 = strongest (still lossless) compression


def settle(ms: int = 350) -> None:
    QTest.qWait(ms)  # let tab fade-ins and layouts finish


def full_size(dialog) -> None:
    """The off-screen 'monitor' is small, so dialogs open shortened (they scroll on small screens).
    For screenshots, give them their full height."""
    page = getattr(dialog, "page", None)
    if page is not None and hasattr(page, "body"):
        height = page.header.sizeHint().height() + page.body.minimumHeight() + 80
        dialog.resize(max(dialog.width(), dialog.minimumWidth()), height)


def screenshots() -> dict[str, Path]:
    from truck_tms.database import Database
    from truck_tms.demo import seed_demo_data
    from truck_tms.ui.export import STATEMENT_FORMATS, ExportDialog
    from truck_tms.ui.main_window import MainWindow
    from truck_tms.ui.splash import SplashScreen
    from truck_tms.ui.statements import StatementDialog

    SHOTS.mkdir(parents=True, exist_ok=True)
    for old in SHOTS.glob("*.png"):
        old.unlink()
    out: dict[str, Path] = {}

    def save(widget, name: str) -> None:
        path = SHOTS / f"{name}.png"
        widget.grab().save(str(path), "PNG", PNG_MAX_COMPRESSION)
        out[name] = path

    from truck_tms.i18n import t

    db = Database(":memory:")
    seed_demo_data(db)
    db.set_setting("company_name", "Eagle Dispatch LLC")
    window = MainWindow(db)
    window.resize(1360, 700)
    window.show()

    def tidy_status_bar() -> None:  # show a realistic path instead of ":memory:"
        window.file_label.setText(t("status.file", path=r"C:\Users\you\.truck_tms\tms.db"))
        window.setWindowTitle("Truck TMS — tms.db")

    tidy_status_bar()
    window.resize(1360, 1060)  # tall enough for the cards, the charts and the recent loads
    window.overview.refresh()  # start the count-up / chart animations, then wait for them to finish
    settle(1300)
    save(window, "overview")
    window.resize(1360, 700)
    for index, name in ((1, "trucks"), (2, "drivers"), (3, "loads"), (4, "statements"), (5, "maintenance")):
        window.tabs.setCurrentIndex(index)
        settle()
        save(window, name)

    first_week = [s for s in db.list_statements() if s.truck_id == 1][0]
    dialog = StatementDialog(db, first_week)
    full_size(dialog)
    dialog.show()
    dialog.preview.setFocus()  # no highlighted text in the date field
    settle(150)
    save(dialog, "statement")
    dialog.resize(1100, 760)
    settle(100)
    path = DOCS / "statement_summary.png"  # only used to build the banner
    dialog.preview.grab().save(str(path), "PNG", PNG_MAX_COMPRESSION)
    out["_summary"] = path
    dialog.close()

    export = ExportDialog(db, None, "Export Statement", STATEMENT_FORMATS, "statement_101_week",
                          [("one", "This statement only"), ("week", "All statements of the week")])
    export.folder.setText(r"C:\Users\you\Documents\Truck TMS")
    full_size(export)
    export.show()
    settle(100)
    save(export, "export")
    export.close()

    import tempfile

    from truck_tms.importer import write_template
    from truck_tms.ui.import_dialog import ImportDialog
    from truck_tms.ui.loads import LoadDialog

    work = Path(tempfile.mkdtemp(prefix="truck_tms_media_"))
    importer = ImportDialog(db)
    importer.load_file(write_template(work / "my_loads.csv"))
    importer.resize(1000, 760)
    importer.show()
    settle(150)
    save(importer, "import")
    importer.close()

    load = next(x for x in db.list_loads() if x.load_number == "#4410055")
    for name in ("Rate Confirmation 4410055.pdf", "BOL 4410055.pdf", "POD signed 4410055.jpg"):
        (work / name).write_bytes(b"%PDF-1.4 sample")
        db.add_document(load.id, work / name, __import__("truck_tms.ui.documents", fromlist=["guess_kind"])
                        .guess_kind(name))
    editor = LoadDialog(db, load)
    full_size(editor)
    editor.show()
    settle(150)
    save(editor, "load_documents")
    editor.close()

    splash = SplashScreen()
    splash.progress = 0.55
    save(splash, "splash")

    db.set_setting("language", "tr")  # Turkish version of the hero image for the TR web page
    window.build(0)
    dialog = StatementDialog(db, first_week)
    full_size(dialog)
    dialog.show()
    dialog.preview.setFocus()
    settle(150)
    save(dialog, "statement_tr")
    dialog.close()

    db.set_setting("theme", "dark")
    window.build(0)
    tidy_status_bar()
    window.overview.refresh()
    settle(1200)
    save(window, "dark_tr")
    window.close()
    db.close()
    return out


# ------------------------------------------------------------------------ banner
def _draw_truck(p: QPainter, x: float, y: float, scale: float) -> None:
    p.save()
    p.translate(x, y)
    p.scale(scale, scale)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0, 0, 0, 70))
    p.drawRoundedRect(QRectF(2, 31, 66, 6), 3, 3)
    p.setBrush(QColor("#FFFFFF"))
    p.drawRoundedRect(QRectF(0, 0, 42, 26), 3, 3)
    cab = QPainterPath(QPointF(45, 6))
    for pt in ((57, 6), (68, 16), (68, 26), (45, 26)):
        cab.lineTo(*pt)
    cab.closeSubpath()
    p.drawPath(cab)
    p.setBrush(QColor("#7FB2F0"))
    win = QPainterPath(QPointF(49, 9))
    for pt in ((56, 9), (63, 16), (49, 16)):
        win.lineTo(*pt)
    win.closeSubpath()
    p.drawPath(win)
    p.setBrush(QColor("#F5A623"))
    p.drawRect(QRectF(66, 20, 3, 3))
    font = QFont("Segoe UI", 8)
    font.setBold(True)
    p.setFont(font)
    p.setPen(QColor("#1E63C6"))
    p.drawText(QRectF(0, 0, 42, 26), Qt.AlignmentFlag.AlignCenter, "TMS")
    for wx in (10, 30, 58):
        p.setPen(QPen(QColor("#FFFFFF"), 2))
        p.setBrush(QColor("#0B1F3F"))
        p.drawEllipse(QPointF(wx, 29), 6, 6)
    p.restore()


def banner(screenshot: Path, target: Path, width: int = 1280, height: int = 640) -> None:
    img = QImage(width, height, QImage.Format.Format_ARGB32)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

    grad = QLinearGradient(0, 0, width, height)
    grad.setColorAt(0, QColor("#1E63C6"))
    grad.setColorAt(1, QColor("#081733"))
    p.fillRect(img.rect(), grad)

    # soft hills + road with the truck (same look as the start-up animation)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(255, 255, 255, 12))
    hills = QPainterPath(QPointF(0, 520))
    hills.cubicTo(QPointF(260, 420), QPointF(470, 520), QPointF(720, 460))
    hills.cubicTo(QPointF(960, 400), QPointF(1120, 470), QPointF(width, 430))
    hills.lineTo(width, height)
    hills.lineTo(0, height)
    hills.closeSubpath()
    p.drawPath(hills)
    road = QPainterPath(QPointF(-20, 600))
    road.cubicTo(QPointF(220, 600), QPointF(300, 540), QPointF(520, 548))
    road.cubicTo(QPointF(740, 556), QPointF(820, 610), QPointF(1300, 590))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QColor(255, 255, 255, 40), 46, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
    p.drawPath(road)
    p.setPen(QPen(QColor("#1C2733"), 38, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
    p.drawPath(road)
    dash = QPen(QColor("#F5A623"), 4, Qt.PenStyle.CustomDashLine)
    dash.setDashPattern([5, 5])
    p.setPen(dash)
    p.drawPath(road)
    pos = road.pointAtPercent(0.3)
    p.save()
    p.translate(pos)
    p.rotate(-road.angleAtPercent(0.3))
    _draw_truck(p, -50, -46, 1.45)
    p.restore()

    # app screenshot in a Windows-style window frame, bleeding off the right edge
    shot = QPixmap(str(screenshot))
    shot.setDevicePixelRatio(1)
    frame_w = 500
    source_h = shot.height() * 0.97
    frame_h = int(source_h * frame_w / shot.width())
    frame = QRectF(700, 64, frame_w, frame_h + 34)
    for i in range(16, 0, -1):  # soft shadow
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 7))
        p.drawRoundedRect(frame.adjusted(-i, -i + 12, i, i + 12), 14 + i, 14 + i)
    clip = QPainterPath()
    clip.addRoundedRect(frame, 12, 12)
    p.setClipPath(clip)
    p.fillRect(frame, QColor("#FFFFFF"))
    p.fillRect(QRectF(frame.x(), frame.y(), frame_w, 34), QColor("#F3F6FA"))
    QSvgRenderer(str(DOCS / "logo.svg")).render(p, QRectF(frame.x() + 12, frame.y() + 8, 18, 18))
    title_font = QFont("Segoe UI", 10)
    p.setFont(title_font)
    p.setPen(QColor("#1B2430"))
    p.drawText(QPointF(frame.x() + 38, frame.y() + 22), "Truck TMS — Weekly Statement")
    p.setPen(QPen(QColor("#6B7685"), 1.4))
    right = frame.x() + frame_w
    for k, kind in enumerate(("min", "max", "close")):  # Windows caption buttons
        cx = right - 26 - (2 - k) * 40
        if kind == "min":
            p.drawLine(QPointF(cx - 5, frame.y() + 17), QPointF(cx + 5, frame.y() + 17))
        elif kind == "max":
            p.drawRect(QRectF(cx - 5, frame.y() + 12, 10, 10))
        else:
            p.drawLine(QPointF(cx - 5, frame.y() + 12), QPointF(cx + 5, frame.y() + 22))
            p.drawLine(QPointF(cx + 5, frame.y() + 12), QPointF(cx - 5, frame.y() + 22))
    p.drawPixmap(QRectF(frame.x(), frame.y() + 34, frame_w, frame_h), shot,
                 QRectF(0, 0, shot.width(), source_h))
    p.setClipping(False)

    # logo + text
    QSvgRenderer(str(DOCS / "logo.svg")).render(p, QRectF(72, 88, 104, 104))
    p.setPen(QColor("#FFFFFF"))
    font = QFont("Segoe UI", 50)
    font.setWeight(QFont.Weight.Black)
    p.setFont(font)
    p.drawText(QPointF(192, 166), "Truck TMS")
    font = QFont("Segoe UI", 21)
    font.setWeight(QFont.Weight.DemiBold)
    p.setFont(font)
    p.drawText(QPointF(72, 250), "Open-source TMS for small trucking fleets")
    font = QFont("Segoe UI", 15)
    p.setFont(font)
    p.setPen(QColor(255, 255, 255, 200))
    p.drawText(QPointF(72, 300), "Trucks · Drivers · Loads · Weekly statements · Maintenance")
    p.setPen(QColor(255, 255, 255, 150))
    p.drawText(QPointF(72, 334), "Küçük filolar için açık kaynaklı TMS")

    # feature chips
    font = QFont("Segoe UI", 13)
    font.setWeight(QFont.Weight.DemiBold)
    p.setFont(font)
    x = 72.0
    for text, accent in (("Free & open source", False), ("English · Türkçe", False), ("Windows .exe", True)):
        w = p.fontMetrics().horizontalAdvance(text) + 32
        rect = QRectF(x, 380, w, 40)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#F5A623") if accent else QColor(255, 255, 255, 34))
        p.drawRoundedRect(rect, 20, 20)
        p.setPen(QColor("#1B1B1B") if accent else QColor("#FFFFFF"))
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
        x += w + 12
    p.end()
    img.save(str(target), "PNG", PNG_MAX_COMPRESSION)


def main() -> int:
    global _app  # keep a reference so Python does not delete the application object
    _app = QApplication.instance() or QApplication(sys.argv[:1])
    shots = screenshots()
    summary = shots.pop("_summary")
    banner(summary, DOCS / "banner.png")
    summary.unlink()
    for path in sorted(list(shots.values()) + [DOCS / "banner.png"]):
        img = QImage(str(path))
        print(f"{path.relative_to(DOCS.parent)}  {img.width()}x{img.height()}")
    for widget in QApplication.topLevelWidgets():  # clean shutdown
        widget.close()
        widget.deleteLater()
    QApplication.sendPostedEvents(None, 0)
    QApplication.processEvents()
    return 0


if __name__ == "__main__":
    sys.exit(main())
