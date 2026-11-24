"""Load board: one column per status; drag a card to another column to change the load's status."""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QScrollArea,
    QStyle,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)

from ..i18n import t
from .theme import token
from .widgets import STATUS_TONES

BOARD_STATUSES = ("planned", "dispatched", "in_transit", "delivered", "invoiced", "paid")
PAID_LIMIT = 40  # the "paid" column only shows the most recent loads, so big files stay fast
ID_ROLE = Qt.ItemDataRole.UserRole
CARD_ROLE = Qt.ItemDataRole.UserRole + 2
CARD_HEIGHT = 96


class CardDelegate(QStyledItemDelegate):
    """Draws a load as a card: number and gross on top, route, truck and driver, profit at the bottom."""

    def sizeHint(self, option, index):  # noqa: N802 (Qt API)
        return QSize(option.rect.width(), CARD_HEIGHT)

    def paint(self, painter: QPainter, option, index) -> None:
        card = index.data(CARD_ROLE)
        if not card:
            return
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(option.rect).adjusted(2, 3, -2, -3)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        path = QPainterPath()
        path.addRoundedRect(rect, 10, 10)
        painter.fillPath(path, QColor(token("card")))
        border = QColor(token("accent") if selected or hovered else token("border"))
        painter.setPen(QPen(border, 2 if selected else 1))
        painter.drawPath(path)
        # status stripe on the left edge
        painter.setClipPath(path)
        painter.fillRect(QRectF(rect.left(), rect.top(), 4, rect.height()), QColor(token(f"{card['tone']}_fg")))
        painter.setClipping(False)

        base = QFont(option.font)
        bold = QFont(base)
        bold.setBold(True)
        small = QFont(base)
        small.setPointSizeF(max(7.5, base.pointSizeF() - 1))
        left, right, width = rect.left() + 14, rect.right() - 10, rect.width() - 24

        def text(font, color, y, value, align=Qt.AlignmentFlag.AlignLeft):
            painter.setFont(font)
            painter.setPen(QColor(token(color)))
            elided = QFontMetrics(font).elidedText(value, Qt.TextElideMode.ElideRight, int(width))
            painter.drawText(QRectF(left, y, width, 20), align | Qt.AlignmentFlag.AlignVCenter, elided)

        top = rect.top() + 8
        text(bold, "text", top, card["number"])
        painter.setFont(bold)
        painter.setPen(QColor(token("text")))
        painter.drawText(QRectF(left, top, right - left, 20),
                         Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, card["gross"])
        text(base, "text", top + 21, card["route"])
        text(small, "muted", top + 41, card["who"])
        if card["profit"]:
            painter.setFont(small)
            painter.setPen(QColor(token(f"{card['profit_tone']}_fg")))
            painter.drawText(QRectF(left, top + 59, right - left, 18),
                             Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, card["profit"])
        text(small, "muted", top + 59, card["date"])
        painter.restore()


class CardList(QListWidget):
    """A column's cards; accepts cards dragged from the other columns."""

    dropped = Signal(int)  # load id

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("CardList")
        self.setItemDelegate(CardDelegate(self))
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(False)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setMouseTracking(True)
        self.setUniformItemSizes(True)

    def _from_other_column(self, event) -> bool:
        return isinstance(event.source(), CardList) and event.source() is not self

    def dragEnterEvent(self, event) -> None:  # noqa: N802 (Qt API)
        if self._from_other_column(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:  # noqa: N802 (Qt API)
        self.dragEnterEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802 (Qt API)
        source = event.source()
        if not self._from_other_column(event) or source.currentItem() is None:
            event.ignore()
            return
        load_id = source.currentItem().data(ID_ROLE)
        # the board rebuilds every column; nothing must be removed from the source list by Qt itself
        event.setDropAction(Qt.DropAction.IgnoreAction)
        event.accept()
        QTimer.singleShot(0, lambda: self.dropped.emit(load_id))


class BoardColumn(QFrame):
    def __init__(self, status: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("BoardColumn")
        self.status = status
        dot = QLabel("●")
        dot.setStyleSheet(f"color: {token(STATUS_TONES.get(status, 'neutral') + '_fg')};")
        title = QLabel(t("status." + status))
        title.setProperty("role", "section")
        self.count = QLabel("0")
        self.count.setProperty("role", "colcount")
        self.total = QLabel()
        self.total.setProperty("role", "kpisub")
        head = QHBoxLayout()
        head.setSpacing(6)
        head.addWidget(dot)
        head.addWidget(title)
        head.addWidget(self.count)
        head.addStretch(1)
        self.list = CardList()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 6)
        layout.setSpacing(2)
        layout.addLayout(head)
        layout.addWidget(self.total)
        layout.addWidget(self.list, 1)
        self.setMinimumWidth(230)


class LoadBoard(QWidget):
    """``moved(load_id, status)`` fires when a card is dropped on another column;
    ``card_clicked`` / ``card_opened`` on a click / double click."""

    moved = Signal(int, str)
    card_clicked = Signal(int)
    card_opened = Signal(int)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.columns: dict[str, BoardColumn] = {}
        row = QHBoxLayout()
        row.setSpacing(10)
        row.setContentsMargins(0, 0, 0, 0)
        holder = QWidget()
        holder.setLayout(row)
        for status in BOARD_STATUSES:
            column = BoardColumn(status)
            column.list.dropped.connect(lambda load_id, s=status: self.moved.emit(load_id, s))
            column.list.itemClicked.connect(lambda item: self.card_clicked.emit(item.data(ID_ROLE)))
            column.list.itemDoubleClicked.connect(lambda item: self.card_opened.emit(item.data(ID_ROLE)))
            self.columns[status] = column
            row.addWidget(column, 1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(holder)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll)

    def set_cards(self, cards: dict[str, list[dict]], totals: dict[str, str]) -> None:
        """``cards[status]`` = card dicts (see CardDelegate) with an ``id``; ``totals[status]`` = gross text."""
        for status, column in self.columns.items():
            items = cards.get(status, [])
            column.list.clear()
            for card in items[:PAID_LIMIT] if status == "paid" else items:
                item = QListWidgetItem()
                item.setData(ID_ROLE, card["id"])
                item.setData(CARD_ROLE, card)
                item.setSizeHint(QSize(200, CARD_HEIGHT))
                column.list.addItem(item)
            column.count.setText(str(len(items)))
            column.total.setText(totals.get(status, ""))

    def select(self, load_id: int | None) -> None:
        for column in self.columns.values():
            for i in range(column.list.count()):
                item = column.list.item(i)
                item.setSelected(item.data(ID_ROLE) == load_id)
