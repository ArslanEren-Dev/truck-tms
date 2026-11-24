"""Building blocks shared by every dialog: a header band with an icon, and section cards.

    dialog = QDialog()
    page = DialogPage(dialog, "truck", "New Truck", "Enter a plate, a unit number, or both.")
    form = page.section("Identity", "truck")       # → QFormLayout inside a rounded card
    form.addRow("Plate", QLineEdit())
    page.finish(buttons)                            # header, sections (in columns) and buttons
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .theme import icon, token


class DialogHeader(QWidget):
    """Colored icon chip + title + subtitle, separated from the content by a thin line."""

    def __init__(self, icon_name: str, title: str, subtitle: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("DialogHeader")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        chip = QLabel()
        chip.setObjectName("DialogChip")
        chip.setFixedSize(44, 44)
        chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        chip.setPixmap(icon(icon_name, token("accent")).pixmap(24, 24))
        self.title = QLabel(title)
        self.title.setProperty("role", "dialogtitle")
        self.subtitle = QLabel(subtitle)
        self.subtitle.setProperty("role", "dialogsub")
        self.subtitle.setVisible(bool(subtitle))
        text = QVBoxLayout()
        text.setSpacing(1)
        text.addWidget(self.title)
        text.addWidget(self.subtitle)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(22, 16, 22, 14)
        layout.setSpacing(14)
        layout.addWidget(chip)
        layout.addLayout(text, 1)

    def set_subtitle(self, text: str) -> None:
        self.subtitle.setText(text)
        self.subtitle.setVisible(bool(text))


def with_header(dialog: QDialog, icon_name: str, title: str, subtitle: str = "") -> QVBoxLayout:
    """For dialogs without form sections (lists, previews): put the header band on top and return
    the layout to fill with the dialog's own content."""
    dialog.setWindowTitle(title)
    outer = QVBoxLayout(dialog)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)
    header = DialogHeader(icon_name, title, subtitle)
    outer.addWidget(header)
    content = QVBoxLayout()
    content.setContentsMargins(20, 14, 20, 16)
    content.setSpacing(10)
    outer.addLayout(content, 1)
    dialog.header = header
    return content


class Section(QFrame):
    """A rounded card with a small heading; ``form`` is a ready QFormLayout for its fields."""

    def __init__(self, title: str, icon_name: str | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Section")
        heading = QHBoxLayout()
        heading.setSpacing(8)
        if icon_name:
            mark = QLabel()
            mark.setPixmap(icon(icon_name, token("accent")).pixmap(16, 16))
            heading.addWidget(mark)
        label = QLabel(title.upper())
        label.setProperty("role", "sectiontitle")
        heading.addWidget(label)
        heading.addStretch(1)
        self.form = QFormLayout()
        self.form.setHorizontalSpacing(14)
        self.form.setVerticalSpacing(9)
        self.form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
        self.form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(16, 12, 16, 14)
        self.body.setSpacing(10)
        self.body.addLayout(heading)
        self.body.addLayout(self.form)


class DialogPage:
    """Lays a dialog out as: header band / section cards in a grid / button row."""

    def __init__(self, dialog: QDialog, icon_name: str, title: str, subtitle: str = ""):
        self.dialog = dialog
        dialog.setWindowTitle(title)
        self.header = DialogHeader(icon_name, title, subtitle)
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(14)
        self.grid.setVerticalSpacing(14)
        self.sections: list[Section] = []

    def section(self, title: str, icon_name: str | None = None, row: int | None = None, column: int = 0,
                row_span: int = 1, column_span: int = 1) -> QFormLayout:
        """Add a section card at (row, column) — by default one under the other — and return its form."""
        card = Section(title, icon_name)
        card.body.addStretch(1)  # keep the fields at the top when the card next to it is taller
        if row is None:
            row = len(self.sections)
        self.grid.addWidget(card, row, column, row_span, column_span)
        self.sections.append(card)
        return card.form

    def add_widget(self, widget: QWidget, row: int, column: int = 0, row_span: int = 1, column_span: int = 1) -> None:
        self.grid.addWidget(widget, row, column, row_span, column_span)

    def finish(self, buttons: QWidget, extra_left: QWidget | None = None) -> QVBoxLayout:
        """Header on top, the cards in a scroll area (for small screens), the buttons at the bottom."""
        self.body = QWidget()
        self.body.setObjectName("DialogBody")
        content = QVBoxLayout(self.body)
        content.setContentsMargins(20, 16, 20, 10)
        content.addLayout(self.grid)
        content.addStretch(1)
        # Qt can under-estimate the height of forms with wrapping texts and squeeze rows on top of each
        # other; pin the body to the height its parts really ask for (the scroll area handles the rest).
        self.body.setMinimumHeight(content.sizeHint().height())
        scroll = QScrollArea()
        scroll.setObjectName("DialogScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(self.body)
        self.scroll = scroll

        footer_widget = QWidget()
        footer_widget.setObjectName("DialogFooter")
        footer = QHBoxLayout(footer_widget)
        footer.setContentsMargins(20, 10, 20, 14)
        if extra_left is not None:
            footer.addWidget(extra_left)
        footer.addStretch(1)
        footer.addWidget(buttons)
        layout = QVBoxLayout(self.dialog)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.header)
        layout.addWidget(scroll, 1)
        layout.addWidget(footer_widget)

        # open at the size the content wants, but never taller than the screen
        width = max(self.dialog.minimumWidth(), self.body.sizeHint().width() + 24)
        height = self.header.sizeHint().height() + self.body.minimumHeight() + footer_widget.sizeHint().height() + 4
        screen = self.dialog.screen() or QGuiApplication.primaryScreen()
        if screen is not None:
            height = min(height, screen.availableGeometry().height() - 70)
        self.dialog.resize(width, height)
        return layout
