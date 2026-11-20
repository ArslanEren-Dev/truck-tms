"""Small animated charts drawn with QPainter.

The app draws its own charts instead of using the Qt Charts module, which is licensed under
the GPL and would not fit this MIT-licensed project.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QToolTip, QWidget

from ..i18n import t
from .theme import token

Formatter = Callable[[float], str]


class Chart(QWidget):
    """Common parts: data, grow-in animation, hover tracking, 'no data' text."""

    def __init__(self, fmt: Formatter = lambda v: f"{v:,.0f}", parent: QWidget | None = None):
        super().__init__(parent)
        self.fmt = fmt
        self.labels: list[str] = []
        self.values: list[float] = []
        self.progress = 1.0
        self.hover = -1
        self.setMinimumHeight(190)
        self.setMouseTracking(True)
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(900)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._step)

    def set_data(self, labels: list[str], values: list[float], animate: bool = True) -> None:
        self.labels, self.values = list(labels), [float(v or 0) for v in values]
        self.hover = -1
        if animate:
            self._anim.stop()
            self.progress = 0.0
            self._anim.start()
        else:
            self.progress = 1.0
        self.update()

    def _step(self, value: float) -> None:
        self.progress = float(value)
        self.update()

    def has_data(self) -> bool:
        return any(v > 0 for v in self.values)

    # ---- helpers for subclasses
    def plot_rect(self) -> QRectF:
        return QRectF(8, 12, self.width() - 16, self.height() - 40)

    def draw_empty(self, p: QPainter) -> None:
        p.setPen(QColor(token("muted")))
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, t("chart.no_data"))

    def small_font(self, bold: bool = False) -> QFont:
        font = QFont(self.font())
        font.setPointSizeF(max(7.5, font.pointSizeF() - 1.5))
        font.setBold(bold)
        return font

    def index_at(self, x: float) -> int:
        n = len(self.values)
        rect = self.plot_rect()
        if n == 0 or not rect.left() <= x <= rect.right():
            return -1
        return min(n - 1, int((x - rect.left()) / (rect.width() / n)))

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 (Qt API)
        index = self.index_at(event.position().x())
        if index != self.hover:
            self.hover = index
            self.update()
        if index >= 0:
            QToolTip.showText(event.globalPosition().toPoint(), f"{self.labels[index]}: {self.fmt(self.values[index])}",
                              self)

    def leaveEvent(self, _event) -> None:  # noqa: N802 (Qt API)
        self.hover = -1
        self.update()


class BarChart(Chart):
    """Vertical bars that grow from the bottom; the last (current) bar is highlighted."""

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt API)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.has_data():
            self.draw_empty(p)
            return
        rect = self.plot_rect()
        top = max(self.values) * 1.15
        p.setPen(QPen(QColor(token("border")), 1, Qt.PenStyle.DashLine))
        for i in range(1, 4):  # light grid
            y = rect.bottom() - rect.height() * i / 3
            p.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
        n = len(self.values)
        slot = rect.width() / n
        bar_w = min(38.0, slot * 0.58)
        accent, soft = QColor(token("accent")), QColor(token("accent"))
        soft.setAlpha(110)
        p.setFont(self.small_font())
        for i, value in enumerate(self.values):
            h = rect.height() * (value / top) * self.progress
            x = rect.left() + slot * i + (slot - bar_w) / 2
            bar = QRectF(x, rect.bottom() - h, bar_w, h)
            highlight = i == n - 1 or i == self.hover
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(accent if highlight else soft)
            path = QPainterPath()
            path.addRoundedRect(bar, min(6.0, bar_w / 3), min(6.0, bar_w / 3))
            p.drawPath(path)
            p.setPen(QColor(token("muted")))
            p.drawText(QRectF(rect.left() + slot * i, rect.bottom() + 4, slot, 18),
                       Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, self.labels[i])
            if highlight and self.progress > 0.95 and value > 0:
                p.setFont(self.small_font(bold=True))
                p.setPen(QColor(token("text")))
                p.drawText(QRectF(x - 30, bar.top() - 18, bar_w + 60, 16), Qt.AlignmentFlag.AlignCenter,
                           self.fmt(value))
                p.setFont(self.small_font())


class LineChart(Chart):
    """A line with a soft area underneath; it is drawn from left to right."""

    def point(self, i: int, top: float, bottom: float) -> QPointF:
        rect = self.plot_rect()
        slot = rect.width() / len(self.values)
        span = (top - bottom) or 1.0
        x = rect.left() + slot * i + slot / 2
        y = rect.bottom() - rect.height() * (self.values[i] - bottom) / span
        return QPointF(x, y)

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt API)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.has_data():
            self.draw_empty(p)
            return
        rect = self.plot_rect()
        shown = [v for v in self.values if v > 0]
        top, bottom = max(shown) * 1.15, min(shown) * 0.75
        p.setPen(QPen(QColor(token("border")), 1, Qt.PenStyle.DashLine))
        for i in range(1, 4):
            y = rect.bottom() - rect.height() * i / 3
            p.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
        points = [self.point(i, top, bottom) for i in range(len(self.values)) if self.values[i] > 0]
        indices = [i for i in range(len(self.values)) if self.values[i] > 0]
        clip = QRectF(rect.left(), 0, rect.width() * self.progress, self.height())
        p.save()
        p.setClipRect(clip)
        if len(points) > 1:
            area = QPainterPath(QPointF(points[0].x(), rect.bottom()))
            for pt in points:
                area.lineTo(pt)
            area.lineTo(QPointF(points[-1].x(), rect.bottom()))
            area.closeSubpath()
            grad = QLinearGradient(0, rect.top(), 0, rect.bottom())
            fill = QColor(token("accent"))
            fill.setAlpha(70)
            grad.setColorAt(0, fill)
            fill.setAlpha(0)
            grad.setColorAt(1, fill)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(grad)
            p.drawPath(area)
            line = QPainterPath(points[0])
            for pt in points[1:]:
                line.lineTo(pt)
            p.setPen(QPen(QColor(token("accent")), 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                          Qt.PenJoinStyle.RoundJoin))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(line)
        for i, pt in zip(indices, points):
            big = i == self.hover or i == indices[-1]
            p.setPen(QPen(QColor(token("card")), 2))
            p.setBrush(QColor(token("accent")))
            p.drawEllipse(pt, 5.5 if big else 3.5, 5.5 if big else 3.5)
        p.restore()
        p.setFont(self.small_font())
        slot = rect.width() / len(self.values)
        for i, label in enumerate(self.labels):
            p.setPen(QColor(token("muted")))
            p.drawText(QRectF(rect.left() + slot * i, rect.bottom() + 4, slot, 18),
                       Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, label)
        if self.progress > 0.95 and points:
            i = self.hover if self.hover in indices else indices[-1]
            pt = points[indices.index(i)]
            p.setFont(self.small_font(bold=True))
            p.setPen(QColor(token("text")))
            p.drawText(QRectF(pt.x() - 50, pt.y() - 24, 100, 16), Qt.AlignmentFlag.AlignCenter, self.fmt(self.values[i]))


class RankChart(Chart):
    """Horizontal bars, biggest first (e.g. top brokers)."""

    def plot_rect(self) -> QRectF:
        return QRectF(8, 8, self.width() - 16, self.height() - 16)

    def index_at(self, x: float) -> int:  # rows, not columns
        return -1

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 (Qt API)
        rect = self.plot_rect()
        n = len(self.values)
        if n == 0:
            return
        row = int((event.position().y() - rect.top()) / (rect.height() / max(n, 5)))
        index = row if 0 <= row < n else -1
        if index != self.hover:
            self.hover = index
            self.update()
        if index >= 0:
            QToolTip.showText(event.globalPosition().toPoint(), f"{self.labels[index]}: {self.fmt(self.values[index])}",
                              self)

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt API)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.has_data():
            self.draw_empty(p)
            return
        rect = self.plot_rect()
        n = len(self.values)
        row_h = rect.height() / max(n, 5)
        top = max(self.values)
        font = self.small_font()
        metrics = QFontMetrics(font)
        value_w = max(metrics.horizontalAdvance(self.fmt(v)) for v in self.values) + 8
        label_w = min(rect.width() * 0.38, max(metrics.horizontalAdvance(lbl) for lbl in self.labels) + 10)
        track_w = rect.width() - label_w - value_w
        p.setFont(font)
        for i, (label, value) in enumerate(zip(self.labels, self.values)):
            y = rect.top() + row_h * i
            bar_h = min(14.0, row_h * 0.5)
            cy = y + (row_h - bar_h) / 2
            p.setPen(QColor(token("text")))
            p.drawText(QRectF(rect.left(), y, label_w - 8, row_h), Qt.AlignmentFlag.AlignVCenter,
                       metrics.elidedText(label, Qt.TextElideMode.ElideRight, int(label_w - 8)))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(token("surface2")))
            p.drawRoundedRect(QRectF(rect.left() + label_w, cy, track_w, bar_h), bar_h / 2, bar_h / 2)
            color = QColor(token("accent"))
            if i != self.hover and i != 0:
                color.setAlpha(150)
            p.setBrush(color)
            w = max(bar_h, track_w * (value / top) * self.progress)
            p.drawRoundedRect(QRectF(rect.left() + label_w, cy, w, bar_h), bar_h / 2, bar_h / 2)
            p.setPen(QColor(token("muted")))
            p.drawText(QRectF(rect.right() - value_w, y, value_w, row_h),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, self.fmt(value))
