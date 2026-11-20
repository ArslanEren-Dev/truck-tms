"""Main window: tabs, File / Help menus and a status bar that shows where data is saved."""

from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path
from collections.abc import Callable

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QKeySequence
from PySide6.QtWidgets import QFileDialog, QLabel, QMainWindow, QPushButton

from .. import PROJECT_URL, WEBSITE_URL, __version__
from ..database import Database, ValidationError, backups_folder
from ..i18n import set_language, t
from ..updates import Release, check_due, is_newer
from .compliance_tab import ComplianceTab
from .dashboard import OverviewTab
from .drivers import DriversTab
from .expenses import ExpensesTab
from .ifta_tab import IftaTab
from .invoices import InvoicesTab
from .loads import LoadsTab
from .maintenance import MaintenanceTab
from .nav import NavTabs
from .reports import ReportsTab
from .settings import SettingsTab
from .statements import StatementsTab
from .theme import apply_qt_language, apply_theme, icon, nav_icon
from .toast import show_toast
from .trucks import TrucksTab
from .update_check import UpdateChecker
from .widgets import confirm_action, show_error, show_info

DB_FILTER_KEY = "file.filter"


class MainWindow(QMainWindow):
    """``on_file_changed(path)`` is called when the user opens or creates another data file,
    so the app can reopen it next time."""

    def __init__(self, db: Database, on_file_changed: Callable[[str], None] | None = None,
                 check_updates: bool = False):
        super().__init__()
        self.setObjectName("MainWindow")  # toasts look for this window
        self.db = db
        self.on_file_changed = on_file_changed
        self._last_changes = db.change_count
        self.release: Release | None = None  # a newer version found on GitHub
        self._manual_check = False
        self.updates = UpdateChecker(self)
        self.updates.finished.connect(self._update_checked)
        self.resize(1360, 800)
        self.saved_timer = QTimer(self)
        self.saved_timer.setInterval(700)
        self.saved_timer.timeout.connect(self._check_saved)
        self.saved_timer.start()
        self.build()
        settings = db.get_settings()
        if (check_updates and settings["check_updates"] == "1" and check_due(settings.get("update_checked"))
                and not os.environ.get("TRUCK_TMS_NO_UPDATE_CHECK")):
            QTimer.singleShot(2500, self.updates.start)  # after the window is up

    # ------------------------------------------------------------------ build
    def build(self, select_index: int = 0) -> None:
        """(Re)create menus, tabs and status bar; used at start-up and after language/theme changes."""
        settings = self.db.get_settings()
        set_language(settings["language"])
        apply_qt_language(settings["language"])
        apply_theme(settings["theme"])
        self.setWindowTitle(f"{t('app.title')} — {Path(self.db.path).name}")
        self._build_menus()

        self.tabs = NavTabs()
        self.overview = OverviewTab(self.db)
        self.overview.action_requested.connect(self.quick_action)
        pages = [
            (self.overview, "tab.overview", "grid"),
            (TrucksTab(self.db), "tab.trucks", "truck"),
            (DriversTab(self.db), "tab.drivers", "user"),
            (LoadsTab(self.db), "tab.loads", "layers"),
            (InvoicesTab(self.db), "tab.invoices", "receipt"),
            (StatementsTab(self.db), "tab.statements", "file"),
            (MaintenanceTab(self.db), "tab.maintenance", "wrench"),
            (ExpensesTab(self.db), "tab.expenses", "wallet"),
            (ComplianceTab(self.db), "tab.compliance", "shield"),
            (IftaTab(self.db), "tab.ifta", "map"),
            (ReportsTab(self.db), "tab.reports", "chart"),
        ]
        settings_tab = SettingsTab(self.db)
        # defer the rebuild: the settings tab emitting the signal is destroyed by it
        settings_tab.appearance_changed.connect(
            lambda: QTimer.singleShot(0, lambda: self.build(self.tabs.count() - 1))
        )
        pages.append((settings_tab, "tab.settings", "sliders"))
        for page, key, icon_name in pages:
            self.tabs.addTab(page, t(key), icon_name, t("page." + key.split(".")[1]))

        self.update_btn = QPushButton(t("nav.update"))
        self.update_btn.setIcon(nav_icon("bell"))
        self.update_btn.clicked.connect(self.open_release)
        self.tabs.add_footer_button(self.update_btn)
        self.update_btn.setVisible(self.release is not None)
        dark = settings["theme"] == "dark"
        self.theme_btn = QPushButton(t("nav.light_mode" if dark else "nav.dark_mode"))
        self.theme_btn.setIcon(nav_icon("sun" if dark else "moon"))
        self.theme_btn.clicked.connect(self.toggle_theme)
        self.tabs.add_footer_button(self.theme_btn)

        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.setCentralWidget(self.tabs)  # deletes the previous page widget
        self.tabs.setCurrentIndex(select_index)
        self._build_status_bar()

    # ---------------------------------------------------------- quick actions
    def page_index(self, page_type) -> int:
        for i in range(self.tabs.count()):
            if isinstance(self.tabs.widget(i), page_type):
                return i
        return -1

    def quick_action(self, action: str) -> None:
        """Buttons on the overview page: jump to the right page and open its "new" dialog."""
        target = {"new_load": LoadsTab, "new_truck": TrucksTab, "new_driver": DriversTab,
                  "new_statement": StatementsTab, "new_invoice": InvoicesTab,
                  "compliance": ComplianceTab}[action]
        if action == "compliance":  # a reminder was clicked: just show the list
            self.tabs.setCurrentIndex(self.page_index(target))
            return
        index = self.page_index(target)
        self.tabs.setCurrentIndex(index)
        self.tabs.widget(index)._open(None)

    def import_loads(self) -> None:
        index = self.page_index(LoadsTab)
        self.tabs.setCurrentIndex(index)
        self.tabs.widget(index).import_loads()

    def toggle_theme(self) -> None:
        new_theme = "light" if self.db.get_settings()["theme"] == "dark" else "dark"
        self.db.set_setting("theme", new_theme)
        current = self.tabs.currentIndex()
        QTimer.singleShot(0, lambda: self.build(current))

    def _build_menus(self) -> None:
        bar = self.menuBar()
        bar.clear()
        file_menu = bar.addMenu(t("menu.file"))
        self._action(file_menu, t("menu.new"), self.new_file, QKeySequence.StandardKey.New, "file")
        self._action(file_menu, t("menu.open"), self.open_file, QKeySequence.StandardKey.Open, "folder")
        self._action(file_menu, t("menu.save"), self.save_now, QKeySequence.StandardKey.Save, "save")
        self._action(file_menu, t("menu.backup"), self.save_backup, QKeySequence("Ctrl+Shift+S"), "export")
        file_menu.addSeparator()
        self._action(file_menu, t("menu.import"), self.import_loads, QKeySequence("Ctrl+I"), "upload")
        file_menu.addSeparator()
        self._action(file_menu, t("menu.folder"), self.open_data_folder, None, "folder")
        file_menu.addSeparator()
        self._action(file_menu, t("menu.exit"), self.close, QKeySequence.StandardKey.Quit, "close")
        help_menu = bar.addMenu(t("menu.help"))
        self._action(help_menu, t("menu.website"), lambda: self.open_url(WEBSITE_URL), None, "file")
        self._action(help_menu, t("menu.github"), lambda: self.open_url(PROJECT_URL), None, "folder")
        self._action(help_menu, t("menu.report_issue"), lambda: self.open_url(PROJECT_URL + "/issues"), None, "edit")
        help_menu.addSeparator()
        self._action(help_menu, t("menu.check_updates"), self.check_for_updates, None, "bell")
        self._action(help_menu, t("menu.about"), self.show_about)

    def _action(self, menu, text, slot, shortcut=None, icon_name=None) -> QAction:
        action = QAction(text, self)
        if icon_name:
            action.setIcon(icon(icon_name))
        if shortcut is not None:
            action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(slot)
        menu.addAction(action)
        return action

    def _build_status_bar(self) -> None:
        status = self.statusBar()
        for child in status.findChildren(QLabel):
            status.removeWidget(child)
            child.deleteLater()
        self.file_label = QLabel(t("status.file", path=self.db.path))
        self.file_label.setToolTip(self.db.path)
        self.saved_label = QLabel("✓ " + t("status.autosave"))
        status.addWidget(self.file_label, 1)
        status.addPermanentWidget(self.saved_label)

    # ------------------------------------------------------------ autosave view
    def _check_saved(self) -> None:
        """Every change is written to the data file immediately; show when that last happened."""
        try:
            changes = self.db.change_count
        except Exception:  # database closed while switching files
            return
        if changes != self._last_changes:
            self._last_changes = changes
            self.saved_label.setText("✓ " + t("status.saved_at", time=datetime.now().strftime("%H:%M:%S")))

    def _on_tab_changed(self, index: int) -> None:
        # other pages may have changed the data (e.g. a new truck) — reload; NavTabs slides the page in
        widget = self.tabs.widget(index)
        if hasattr(widget, "refresh"):
            widget.refresh()

    # ------------------------------------------------------------------ files
    def switch_database(self, path: str) -> bool:
        """Open another data file (creating it if needed) and rebuild the window."""
        try:
            new_db = Database(path)
        except (ValidationError, OSError) as exc:
            show_error(self, exc if isinstance(exc, ValidationError) else "file.not_valid")
            return False
        old = self.db
        self.db = new_db
        self._last_changes = new_db.change_count
        old.close()
        self.build()
        if self.on_file_changed:
            self.on_file_changed(str(Path(path).resolve()))
        return True

    def _start_folder(self) -> str:
        return str(Path(self.db.path).resolve().parent) if self.db.path != ":memory:" else str(Path.home())

    def new_file(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, t("menu.new"), str(Path(self._start_folder()) / "tms.db"),
                                              t(DB_FILTER_KEY))
        if path:
            if not path.lower().endswith((".db", ".sqlite")):
                path += ".db"
            if self.switch_database(path):
                show_toast(t("toast.file_created", name=Path(path).name))

    def open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, t("menu.open"), self._start_folder(), t(DB_FILTER_KEY))
        if path:
            self.switch_database(path)

    def save_now(self) -> None:
        """Ctrl+S: everything is already saved; flush to disk anyway and confirm it in the status bar."""
        self.db.conn.commit()
        self.saved_label.setText("✓ " + t("status.saved_at", time=datetime.now().strftime("%H:%M:%S")))
        show_toast(t("status.saved_now"))

    def save_backup(self) -> None:
        name = f"{Path(self.db.path).stem}_backup_{date.today().isoformat()}.db"
        path, _ = QFileDialog.getSaveFileName(self, t("menu.backup"), str(Path(self._start_folder()) / name),
                                              t(DB_FILTER_KEY))
        if not path:
            return
        try:
            self.db.backup_to(path)
        except ValidationError as exc:
            show_error(self, exc)
            return
        folder = str(Path(path).parent)
        show_toast(t("toast.backup_saved", name=Path(path).name), "success",
                   (t("export.open_folder"), lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(folder))), 5000)

    def open_data_folder(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(self._start_folder()))

    @staticmethod
    def open_url(url: str) -> None:
        QDesktopServices.openUrl(QUrl(url))

    # ---------------------------------------------------------------- updates
    def check_for_updates(self) -> None:
        """Help → Check for updates: same check, but always says what it found."""
        self._manual_check = True
        self.updates.start()

    def _update_checked(self, release: Release | None) -> None:
        manual, self._manual_check = self._manual_check, False
        if release is not None:
            self.db.set_setting("update_checked", date.today().isoformat())
        if release is not None and is_newer(release.version):
            self.release = release
            self.update_btn.setVisible(True)
            show_toast(t("update.available", version=release.version), "info",
                       (t("update.download"), self.open_release), 10000)
            if manual:
                self.open_release_question()
        elif manual:
            show_info(self, t("update.latest", version=__version__) if release else t("update.failed"))

    def open_release_question(self) -> None:
        if self.release and confirm_action(self, t("update.question", version=self.release.version,
                                                    current=__version__), t("update.download")):
            self.open_release()

    def open_release(self) -> None:
        if self.release:
            self.open_url(self.release.url)

    def show_about(self) -> None:
        backups = str(backups_folder(self.db.path)) if self.db.path != ":memory:" else "—"
        show_info(self, t("about.text", version=__version__, path=self.db.path, backups=backups, url=PROJECT_URL))
