"""Small notifications that slide in at the bottom right of the main window and disappear by themselves."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QEasingCurve, QPoint, QTimer, QVariantAnimation, Qt
from PySide6.QtWidgets import QApplication, QFrame, QHBoxLayout, QLabel, QPushButton, QWidget

from .theme import icon

MARGIN = 22
GAP = 10
TONE_ICONS = {"success": ("check", "#4ADE80"), "info": ("alert", "#7DB0FF"), "danger": ("alert", "#FF8A80")}


def main_window() -> QWidget | None:
    """The visible main window (toasts always go there, even when a dialog asked for them)."""
    for widget in QApplication.topLevelWidgets():
        if widget.objectName() == "MainWindow" and widget.isVisible():
            return widget
    return None


class Toast(QFrame):
    def __init__(self, host: QWidget, text: str, tone: str = "success",
                 action: tuple[str, Callable[[], None]] | None = None, duration_ms: int = 2600):
        super().__init__(host)
        self.setObjectName("Toast")
        self.host = host
        icon_name, color = TONE_ICONS.get(tone, TONE_ICONS["info"])
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(10)
        mark = QLabel()
        mark.setPixmap(icon(icon_name, color).pixmap(18, 18))
        label = QLabel(text)
        label.setWordWrap(True)
        label.setMaximumWidth(380)
        layout.addWidget(mark, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(label, 1)
        if action:
            button = QPushButton(action[0])
            button.setProperty("noLift", True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(action[1])
            button.clicked.connect(self.dismiss)
            layout.addWidget(button)
        self.adjustSize()
        self._offset = 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._apply)
        self.setWindowOpacity(1.0)
        QTimer.singleShot(duration_ms, self.dismiss)

    # 0 = hidden below, 1 = fully shown
    def _apply(self, value: float) -> None:
        self._offset = float(value)
        self.reposition()

    def reposition(self) -> None:
        toasts = [w for w in self.host.findChildren(Toast) if not getattr(w, "_closing", False) or w is self]
        below = 0
        for other in toasts:
            if other is self:
                break
            below += other.height() + GAP
        bottom_bar = 0
        status = getattr(self.host, "statusBar", None)
        if callable(status) and status().isVisible():
            bottom_bar = status().height()
        x = self.host.width() - self.width() - MARGIN
        y_shown = self.host.height() - bottom_bar - MARGIN - self.height() - below
        y = int(y_shown + (1.0 - self._offset) * 40)
        self.move(QPoint(x, y))

    def popup(self) -> None:
        self.show()
        self.raise_()
        self._anim.setDuration(260)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()

    def dismiss(self) -> None:
        if getattr(self, "_closing", False):
            return
        self._closing = True
        self._anim.stop()
        self._anim.setDuration(200)
        self._anim.setStartValue(self._offset)
        self._anim.setEndValue(0.0)
        self._anim.finished.connect(self.deleteLater)
        self._anim.start()


def show_toast(text: str, tone: str = "success", action: tuple[str, Callable[[], None]] | None = None,
               duration_ms: int = 2600) -> Toast | None:
    """Show a toast on the main window. Returns None when there is no visible main window (e.g. in tests)."""
    host = main_window()
    if host is None:
        return None
    toast = Toast(host, text, tone, action, duration_ms)  # colours come from the stylesheet (#Toast)
    toast.popup()
    return toast
