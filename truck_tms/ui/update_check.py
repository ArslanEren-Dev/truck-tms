"""Runs the GitHub release check in a background thread and reports back on the GUI thread."""

from __future__ import annotations

import contextlib
import threading
from collections.abc import Callable

from PySide6.QtCore import QObject, Signal

from ..updates import Release, fetch_latest


class UpdateChecker(QObject):
    """``finished(release_or_None)`` is emitted on the GUI thread when the check is done."""

    finished = Signal(object)

    def __init__(self, parent: QObject | None = None, fetch: Callable[[], Release | None] = fetch_latest):
        super().__init__(parent)
        self.fetch = fetch
        self.running = False

    def start(self) -> None:
        if self.running:
            return
        self.running = True
        threading.Thread(target=self._run, name="update-check", daemon=True).start()

    def _run(self) -> None:
        try:
            release = self.fetch()
        except Exception:  # never let a network oddity reach the user
            release = None
        self.running = False
        with contextlib.suppress(RuntimeError):  # the window was closed while GitHub was answering
            self.finished.emit(release)  # queued to the GUI thread
