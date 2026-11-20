"""Sidebar navigation with a sliding selection highlight, page header and animated page changes.

``NavTabs`` offers the parts of the ``QTabWidget`` API the app uses (addTab, count, widget,
tabText, indexOf, currentIndex, currentWidget, setCurrentIndex, currentChanged), so the
rest of the code does not care that the tabs became a sidebar.
"""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QEvent, QPropertyAnimation, QRect, QSize, Qt, Signal
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import __version__
from .theme import asset_path, nav_icon, slide_in


def svg_pixmap(path, size: int, ratio: float = 1.0) -> QPixmap:
    """Render an SVG sharply at the screen's pixel density."""
    pix = QPixmap(int(size * ratio), int(size * ratio))
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    QSvgRenderer(str(path)).render(painter)
    painter.end()
    pix.setDevicePixelRatio(ratio)
    return pix


class NavTabs(QWidget):
    currentChanged = Signal(int)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._titles: list[str] = []
        self._subtitles: list[str] = []
        self._buttons: list[QPushButton] = []
        self._current = -1

        # ----- sidebar
        self.sidebar = QFrame()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setFixedWidth(224)
        side = QVBoxLayout(self.sidebar)
        side.setContentsMargins(12, 16, 12, 12)
        side.setSpacing(2)

        brand = QHBoxLayout()
        brand.setContentsMargins(6, 0, 0, 14)
        logo = QLabel()
        logo.setFixedSize(32, 32)
        logo.setPixmap(svg_pixmap(asset_path("logo.svg"), 32, self.devicePixelRatioF()))
        name = QLabel("Truck TMS")
        name.setObjectName("Brand")
        brand.addWidget(logo)
        brand.addWidget(name, 1)
        side.addLayout(brand)

        # the highlight sits behind the buttons and slides to the selected one
        self.indicator = QFrame(self.sidebar)
        self.indicator.setObjectName("NavIndicator")
        self.indicator.hide()
        self._indicator_anim = QPropertyAnimation(self.indicator, b"geometry", self)
        self._indicator_anim.setDuration(260)
        self._indicator_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.nav_layout = QVBoxLayout()
        self.nav_layout.setSpacing(2)
        side.addLayout(self.nav_layout)
        side.addStretch(1)

        self.footer = QVBoxLayout()
        self.footer.setSpacing(4)
        side.addLayout(self.footer)
        version = QLabel(f"v{__version__}")
        version.setObjectName("Version")
        side.addWidget(version)

        # ----- page area: header + stacked pages
        self.title = QLabel()
        self.title.setProperty("role", "pagetitle")
        self.subtitle = QLabel()
        self.subtitle.setProperty("role", "pagesub")
        header = QWidget()
        header.setObjectName("PageHeader")
        head = QVBoxLayout(header)
        head.setContentsMargins(24, 18, 24, 6)
        head.setSpacing(2)
        head.addWidget(self.title)
        head.addWidget(self.subtitle)

        self.stack = QStackedWidget()
        content = QVBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(0)
        content.addWidget(header)
        page_box = QVBoxLayout()
        page_box.setContentsMargins(16, 6, 16, 12)
        page_box.addWidget(self.stack)
        content.addLayout(page_box, 1)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self.sidebar)
        root.addLayout(content, 1)

        self.sidebar.installEventFilter(self)

    # ------------------------------------------------------------ QTabWidget API
    def addTab(self, widget: QWidget, text: str, icon_name: str | None = None,  # noqa: N802
               subtitle: str = "") -> int:
        index = self.stack.addWidget(widget)
        self._titles.append(text)
        self._subtitles.append(subtitle)
        button = QPushButton(text)
        button.setObjectName("NavButton")
        button.setCheckable(True)
        button.setProperty("noLift", True)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        if icon_name:
            button.setIcon(nav_icon(icon_name))
            button.setIconSize(QSize(18, 18))
        button.clicked.connect(lambda _=False, i=index: self.setCurrentIndex(i))
        self._buttons.append(button)
        self.nav_layout.addWidget(button)
        if self._current < 0:
            self.setCurrentIndex(0)
        return index

    def add_footer_button(self, button: QPushButton) -> None:
        button.setObjectName("NavButton")
        button.setProperty("noLift", True)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.footer.addWidget(button)

    def count(self) -> int:
        return self.stack.count()

    def widget(self, index: int) -> QWidget | None:
        return self.stack.widget(index)

    def tabText(self, index: int) -> str:  # noqa: N802
        return self._titles[index]

    def indexOf(self, widget: QWidget) -> int:  # noqa: N802
        return self.stack.indexOf(widget)

    def currentIndex(self) -> int:  # noqa: N802
        return self._current

    def currentWidget(self) -> QWidget | None:  # noqa: N802
        return self.stack.currentWidget()

    def setCurrentIndex(self, index: int) -> None:  # noqa: N802
        if not 0 <= index < self.count():
            return
        changed = index != self._current
        self._current = index
        self.stack.setCurrentIndex(index)
        for i, button in enumerate(self._buttons):
            button.setChecked(i == index)
        self.title.setText(self._titles[index])
        self.subtitle.setText(self._subtitles[index])
        self.subtitle.setVisible(bool(self._subtitles[index]))
        self._move_indicator(animate=self.isVisible())
        if changed:
            self.currentChanged.emit(index)
            if self.isVisible():
                slide_in(self.stack.currentWidget())

    # ---------------------------------------------------------------- indicator
    def _target_rect(self) -> QRect | None:
        if not 0 <= self._current < len(self._buttons):
            return None
        button = self._buttons[self._current]
        top_left = button.mapTo(self.sidebar, button.rect().topLeft())
        return QRect(top_left, button.size())

    def _move_indicator(self, animate: bool) -> None:
        rect = self._target_rect()
        if rect is None or rect.height() <= 0:
            return
        self.indicator.show()
        self.indicator.lower()
        if animate and self.indicator.geometry().height() > 0:
            self._indicator_anim.stop()
            self._indicator_anim.setStartValue(self.indicator.geometry())
            self._indicator_anim.setEndValue(rect)
            self._indicator_anim.start()
        else:
            self.indicator.setGeometry(rect)

    def eventFilter(self, obj, event):  # noqa: N802 (Qt API)
        if obj is self.sidebar and event.type() in (QEvent.Type.Resize, QEvent.Type.Show, QEvent.Type.LayoutRequest):
            self._move_indicator(animate=False)
        return False
