"""Entry point: ``python -m truck_tms [--db PATH] [--demo] [--no-splash]`` or ``truck-tms``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="truck-tms", description="Truck TMS desktop app")
    parser.add_argument("--db", help="data file to open (default: the last file used, or ~/.truck_tms/tms.db)")
    parser.add_argument("--demo", action="store_true",
                        help="add sample trucks, drivers, loads and statements if the data file is empty")
    parser.add_argument("--no-splash", action="store_true", help="skip the start-up animation")
    parser.add_argument("--self-test", metavar="FOLDER",
                        help="check that this build works: build every screen, export files to FOLDER, then exit")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test(Path(args.self_test))

    from PySide6.QtCore import QEasingCurve, QSettings, QVariantAnimation
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication, QMessageBox

    # absolute imports so this file also works as the PyInstaller entry script
    from truck_tms.database import Database, ValidationError, auto_backup, default_db_path
    from truck_tms.demo import seed_demo_data
    from truck_tms.i18n import set_language, t
    from truck_tms.ui.main_window import MainWindow
    from truck_tms.ui.splash import SplashScreen
    from truck_tms.ui.theme import apply_qt_language, asset_path

    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("Truck TMS")
    app.setOrganizationName("TruckTMS")
    app.setStyle("Fusion")
    icon = asset_path("truck_tms.ico")
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))

    # which data file? --db, else the last one used, else the default
    prefs = QSettings("TruckTMS", "TruckTMS")
    remembered = prefs.value("last_db", "", str)
    if args.db:
        path = args.db
    elif remembered and Path(remembered).is_file():
        path = remembered
    else:
        path = str(default_db_path())

    try:
        auto_backup(path)
        db = Database(path)
    except (ValidationError, OSError) as exc:
        key = exc.key if isinstance(exc, ValidationError) else "file.not_valid"
        QMessageBox.critical(None, "Truck TMS", f"{t(key)}\n\n{path}")
        return 1
    if args.demo:
        seed_demo_data(db)
    if not args.db:
        prefs.setValue("last_db", str(Path(path).resolve()))
    language = db.get_settings()["language"]
    set_language(language)
    apply_qt_language(language)

    def remember(new_path: str) -> None:
        prefs.setValue("last_db", new_path)

    splash = None if args.no_splash else SplashScreen()
    if splash:
        splash.show()
        app.processEvents()
    window = MainWindow(db, on_file_changed=remember, check_updates=True)

    def show_window() -> None:
        window.setWindowOpacity(0.0)
        window.show()
        fade = QVariantAnimation(window)
        fade.setDuration(260)
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        fade.valueChanged.connect(window.setWindowOpacity)
        fade.start()
        if splash:
            splash.close()

    if splash:
        splash.finished.connect(show_window)
        splash.start()
    else:
        window.show()
    code = app.exec()
    window.db.close()
    return code


def self_test(folder: Path) -> int:
    """Smoke test for a packaged build (e.g. the .exe): no user interaction needed.

    Writes ``self_test.log`` into ``folder``; exit code 0 means everything worked.
    """
    import time
    import traceback

    from PySide6.QtWidgets import QApplication

    from truck_tms.database import Database
    from truck_tms.demo import seed_demo_data
    from truck_tms.i18n import t
    from truck_tms.report import build_truck_report
    from truck_tms.statement import compute_statement
    from truck_tms.ui.export import write_report_files, write_statement_files
    from truck_tms.ui.main_window import MainWindow
    from truck_tms.ui.splash import SplashScreen
    from truck_tms.ui.theme import icon

    folder.mkdir(parents=True, exist_ok=True)
    log = []
    try:
        app = QApplication.instance() or QApplication(sys.argv[:1])
        db = Database(folder / "self_test.db")
        seed_demo_data(db)
        for language in ("en", "tr"):
            for theme in ("light", "dark"):
                db.set_setting("language", language)
                db.set_setting("theme", theme)
                window = MainWindow(db)
                window.show()
                for i in list(range(window.tabs.count())) + [0]:
                    window.tabs.setCurrentIndex(i)
                    app.processEvents()
                deadline = time.monotonic() + 0.5  # let the tab fade-in finish before the screenshot
                while time.monotonic() < deadline:
                    app.processEvents()
                window.grab().save(str(folder / f"screen_{language}_{theme}.png"))
                log.append(f"ok  screens {language}/{theme}: {window.tabs.tabText(0)}")
                window.close()
                window.deleteLater()
        log.append(f"ok  Qt translation: {t('btn.yes')} / svg icon: {not icon('plus').isNull()}")
        splash = SplashScreen()
        splash.progress = 0.5
        log.append(f"ok  splash paints: {not splash.grab().isNull()}")
        summaries = [compute_statement(db, s) for s in db.list_statements()]
        files = write_statement_files(summaries[:1], "all", folder, "statement", db.get_settings())
        files += write_report_files(build_truck_report(db, 1, "2000-01-01", "2100-01-01"), "pdf_csv",
                                    folder, "truck_report", db.get_settings())
        for f in files:
            assert f.stat().st_size > 500, f
        log.append("ok  exported: " + ", ".join(f.name for f in files))
        db.backup_to(folder / "backup_copy.db")
        log.append("ok  backup copy")
        db.close()
        code = 0
    except Exception:
        log.append("FAILED\n" + traceback.format_exc())
        code = 1
    (folder / "self_test.log").write_text("\n".join(log) + "\n", encoding="utf-8")
    return code


if __name__ == "__main__":
    sys.exit(main())
