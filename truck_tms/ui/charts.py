"""Animated charts drawn with QPainter.

The app draws its own charts instead of using the Qt Charts module, which is licensed under
the GPL and would not fit this MIT-licensed project.

Every chart grows in when its data changes, follows the mouse with a smoothly moving highlight
and shows the value under the cursor in a small bubble drawn inside the chart.
"""

from __future__ import annotations

import math
from collections.abc import Callable

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from ..i18n import t
from .theme import token

Formatter = Callable[[float], str]


def compact(value: float) -> str:
    """Short axis label: 950 -> '950', 12_400 -> '12.4k', 3_200_000 -> '3.2M'."""
    sign = "-" if value < 0 else ""
    value = abs(value)
    for limit, suffix in ((1e6, "M"), (1e3, "k")):
        if value >= limit:
            text = f"{value / limit:.1f}".rstrip("0").rstrip(".")
            return f"{sign}{text}{suffix}"
    return f"{sign}{value:.0f}" if value >= 10 or value == 0 else f"{sign}{value:.1f}".rstrip("0").rstrip(".")


def nice_max(value: float) -> float:
    """Round the top of the scale up to 1, 2, 2.5 or 5 x 10^n so the grid lines get round numbers."""
    if value <= 0:
        return 1.0
    exp = 10 ** math.floor(math.log10(value))
    for step in (1, 2, 2.5, 5, 10):
        if value <= step * exp:
            return step * exp
    return 10 * exp


def series_colors() -> list[QColor]:
    return [QColor(c) for c in token("series").split(",")]


def ease_out(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return 1 - (1 - x) ** 3


class Chart(QWidget):
    """Common parts: data, grow-in animation, smooth hover tracking, value bubble, 'no data' text."""

    GRID_LINES = 4

    def __init__(self, fmt: Formatter = lambda v: f"{v:,.0f}", parent: QWidget | None = None):
        super().__init__(parent)
        self.fmt = fmt
        self.axis_fmt: Formatter = compact
        self.labels: list[str] = []
        self.values: list[float] = []
        self.progress = 1.0
        self.hover = -1
        self.hover_pos = -1.0   # eases towards ``hover`` so the highlight glides between items
        self.setMinimumHeight(190)
        self.setMouseTracking(True)
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(1000)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.Linear)  # each item eases on its own (staggered)
        self._anim.valueChanged.connect(self._step)
        self._hover_anim = QVariantAnimation(self)
        self._hover_anim.setDuration(180)
        self._hover_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._hover_anim.valueChanged.connect(self._hover_step)

    # ---- data
    def set_data(self, labels: list[str], values: list[float], animate: bool = True) -> None:
        self.labels, self.values = list(labels), [float(v or 0) for v in values]
        self.hover, self.hover_pos = -1, -1.0
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

    def _hover_step(self, value: float) -> None:
        self.hover_pos = float(value)
        self.update()

    def item_progress(self, i: int, n: int) -> float:
        """Grow-in of item ``i``: items start one after another and each eases out."""
        if n <= 1:
            return ease_out(self.progress)
        delay = 0.35 * i / (n - 1)
        return ease_out((self.progress - delay) / 0.65)

    def has_data(self) -> bool:
        return any(v > 0 for v in self.values)

    # ---- hover
    def set_hover(self, index: int) -> None:
        if index == self.hover:
            return
        self.hover = index
        self._hover_anim.stop()
        if index < 0:
            self.hover_pos = -1.0
            self.update()
            return
        if self.hover_pos < 0:
            self.hover_pos = float(index)
            self.update()
            return
        self._hover_anim.setStartValue(self.hover_pos)
        self._hover_anim.setEndValue(float(index))
        self._hover_anim.start()

    def index_at(self, pos: QPointF) -> int:
        n = len(self.values)
        rect = self.plot_rect()
        if n == 0 or not rect.left() <= pos.x() <= rect.right():
            return -1
        return min(n - 1, int((pos.x() - rect.left()) / (rect.width() / n)))

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 (Qt API)
        self.set_hover(self.index_at(event.position()))

    def leaveEvent(self, _event) -> None:  # noqa: N802 (Qt API)
        self.set_hover(-1)

    # ---- drawing helpers
    def plot_rect(self) -> QRectF:
        left = self.axis_width()
        return QRectF(left, 14, self.width() - left - 8, self.height() - 42)

    def axis_width(self) -> float:
        if not self.has_data():
            return 8.0
        metrics = QFontMetrics(self.small_font())
        top = nice_max(max(self.values) * 1.08)
        return 12.0 + max(metrics.horizontalAdvance(self.axis_fmt(top * i / self.GRID_LINES))
                          for i in range(self.GRID_LINES + 1))

    def draw_grid(self, p: QPainter, rect: QRectF, top: float, bottom: float = 0.0) -> None:
        p.setFont(self.small_font())
        for i in range(self.GRID_LINES + 1):
            y = rect.bottom() - rect.height() * i / self.GRID_LINES
            p.setPen(QPen(QColor(token("border")), 1, Qt.PenStyle.SolidLine if i == 0 else Qt.PenStyle.DotLine))
            p.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            p.setPen(QColor(token("muted")))
            value = bottom + (top - bottom) * i / self.GRID_LINES
            p.drawText(QRectF(0, y - 8, rect.left() - 8, 16),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, self.axis_fmt(value))

    def draw_labels(self, p: QPainter, rect: QRectF) -> None:
        n = len(self.labels)
        slot = rect.width() / max(n, 1)
        metrics = QFontMetrics(self.small_font())
        every = max(1, math.ceil((max((metrics.horizontalAdvance(lb) for lb in self.labels), default=0) + 8) / slot))
        p.setFont(self.small_font())
        for i, label in enumerate(self.labels):
            if i % every and i != n - 1:
                continue
            p.setPen(QColor(token("text") if i == self.hover else token("muted")))
            p.drawText(QRectF(rect.left() + slot * i - 10, rect.bottom() + 6, slot + 20, 18),
                       Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, label)

    def draw_bubble(self, p: QPainter, anchor: QPointF, title: str, value: str) -> None:
        """A rounded value bubble above ``anchor``, kept inside the widget."""
        title_font, value_font = self.small_font(), self.small_font(bold=True)
        value_font.setPointSizeF(value_font.pointSizeF() + 1.5)
        tm, vm = QFontMetrics(title_font), QFontMetrics(value_font)
        w = max(tm.horizontalAdvance(title), vm.horizontalAdvance(value)) + 22
        h = tm.height() + vm.height() + 12
        x = min(max(4.0, anchor.x() - w / 2), self.width() - w - 4)
        y = anchor.y() - h - 10
        if y < 2:
            y = anchor.y() + 14
        box = QRectF(x, y, w, h)
        p.save()
        p.setPen(Qt.PenStyle.NoPen)
        shadow = QColor(0, 0, 0, 40)
        p.setBrush(shadow)
        p.drawRoundedRect(box.translated(0, 2), 8, 8)
        p.setBrush(QColor(token("toast")))
        p.drawRoundedRect(box, 8, 8)
        p.setPen(QColor(token("toast_text")))
        p.setFont(title_font)
        muted = QColor(token("toast_text"))
        muted.setAlpha(170)
        p.setPen(muted)
        p.drawText(QRectF(box.left(), box.top() + 5, w, tm.height()), Qt.AlignmentFlag.AlignHCenter, title)
        p.setPen(QColor(token("toast_text")))
        p.setFont(value_font)
        p.drawText(QRectF(box.left(), box.top() + 5 + tm.height(), w, vm.height()), Qt.AlignmentFlag.AlignHCenter,
                   value)
        p.restore()

    def draw_empty(self, p: QPainter) -> None:
        p.setPen(QColor(token("muted")))
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, t("chart.no_data"))

    def small_font(self, bold: bool = False) -> QFont:
        font = QFont(self.font())
        font.setPointSizeF(max(7.5, font.pointSizeF() - 1.5))
        font.setBold(bold)
        return font

    def painter(self) -> QPainter:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        return p


class BarChart(Chart):
    """Vertical gradient bars that grow one after another; the current (last) bar is highlighted."""

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt API)
        p = self.painter()
        if not self.has_data():
            self.draw_empty(p)
            return
        rect = self.plot_rect()
        top = nice_max(max(self.values) * 1.08)
        self.draw_grid(p, rect, top)
        n = len(self.values)
        slot = rect.width() / n
        bar_w = min(34.0, slot * 0.56)
        if self.hover_pos >= 0:  # soft column behind the hovered bar, gliding between bars
            band = QColor(token("accent"))
            band.setAlpha(22)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(band)
            band_x = rect.left() + slot * self.hover_pos + 2
            p.drawRoundedRect(QRectF(band_x, rect.top(), slot - 4, rect.height()), 8, 8)
        accent, accent2 = QColor(token("accent")), QColor(token("accent2"))
        for i, value in enumerate(self.values):
            h = rect.height() * (value / top) * self.item_progress(i, n)
            if h <= 0:
                continue
            x = rect.left() + slot * i + (slot - bar_w) / 2
            bar = QRectF(x, rect.bottom() - h, bar_w, h)
            strong = i == self.hover or (self.hover < 0 and i == n - 1)
            grad = QLinearGradient(bar.topLeft(), bar.bottomLeft())
            top_color, bottom_color = QColor(accent2), QColor(accent)
            if not strong:
                top_color.setAlpha(120)
                bottom_color.setAlpha(150)
            grad.setColorAt(0, top_color)
            grad.setColorAt(1, bottom_color)
            radius = min(7.0, bar_w / 2.6, h / 2)
            path = QPainterPath()
            path.addRoundedRect(bar, radius, radius)
            square = QPainterPath()  # square off the bottom corners: bars stand on the axis
            square.addRect(QRectF(bar.left(), bar.bottom() - radius, bar.width(), radius))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(grad)
            p.drawPath(path.united(square))
        self.draw_labels(p, rect)
        index = self.hover if self.hover >= 0 else (n - 1 if self.progress >= 1 else -1)
        if index >= 0 and self.values[index] > 0:
            h = rect.height() * self.values[index] / top
            anchor = QPointF(rect.left() + slot * index + slot / 2, rect.bottom() - h)
            self.draw_bubble(p, anchor, self.labels[index], self.fmt(self.values[index]))


class LineChart(Chart):
    """A smooth line with a gradient area, drawn from left to right; a guide line follows the mouse."""

    def _points(self, rect: QRectF, top: float, bottom: float) -> list[tuple[int, QPointF]]:
        n = len(self.values)
        slot = rect.width() / n
        span = (top - bottom) or 1.0
        return [(i, QPointF(rect.left() + slot * i + slot / 2,
                            rect.bottom() - rect.height() * (v - bottom) / span))
                for i, v in enumerate(self.values) if v > 0]

    @staticmethod
    def smooth_path(points: list[QPointF]) -> QPainterPath:
        """Catmull-Rom spline through the points (as cubic Béziers), kept from overshooting."""
        path = QPainterPath(points[0])
        for k in range(len(points) - 1):
            p0 = points[k - 1] if k > 0 else points[k]
            p1, p2 = points[k], points[k + 1]
            p3 = points[k + 2] if k + 2 < len(points) else p2
            c1 = QPointF(p1.x() + (p2.x() - p0.x()) / 6, p1.y() + (p2.y() - p0.y()) / 6)
            c2 = QPointF(p2.x() - (p3.x() - p1.x()) / 6, p2.y() - (p3.y() - p1.y()) / 6)
            low, high = min(p1.y(), p2.y()), max(p1.y(), p2.y())
            c1.setY(min(max(c1.y(), low), high))
            c2.setY(min(max(c2.y(), low), high))
            path.cubicTo(c1, c2, p2)
        return path

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt API)
        p = self.painter()
        if not self.has_data():
            self.draw_empty(p)
            return
        rect = self.plot_rect()
        shown = [v for v in self.values if v > 0]
        top = nice_max(max(shown) * 1.08)
        low = min(shown)
        bottom = 0.0 if low < top * 0.5 else math.floor(low * 0.8 / (top / 10)) * (top / 10)
        self.draw_grid(p, rect, top, bottom)
        indexed = self._points(rect, top, bottom)
        points = [pt for _, pt in indexed]
        reveal = ease_out(self.progress)
        p.save()
        p.setClipRect(QRectF(0, 0, rect.left() + rect.width() * reveal + 6, self.height()))
        accent = QColor(token("accent"))
        if len(points) > 1:
            line = self.smooth_path(points)
            area = QPainterPath(line)
            area.lineTo(QPointF(points[-1].x(), rect.bottom()))
            area.lineTo(QPointF(points[0].x(), rect.bottom()))
            area.closeSubpath()
            grad = QLinearGradient(0, rect.top(), 0, rect.bottom())
            fill = QColor(accent)
            fill.setAlpha(90)
            grad.setColorAt(0, fill)
            fill.setAlpha(0)
            grad.setColorAt(1, fill)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(grad)
            p.drawPath(area)
            p.setPen(QPen(accent, 2.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(line)
        p.restore()
        # guide line at the (gliding) hover position
        if self.hover_pos >= 0:
            slot = rect.width() / len(self.values)
            x = rect.left() + slot * self.hover_pos + slot / 2
            guide = QColor(token("muted"))
            guide.setAlpha(140)
            p.setPen(QPen(guide, 1, Qt.PenStyle.DashLine))
            p.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
        last = indexed[-1][0] if indexed else -1
        for i, pt in indexed:
            if pt.x() > rect.left() + rect.width() * reveal + 6:
                continue
            big = i == self.hover or (self.hover < 0 and i == last)
            if big:
                halo = QColor(accent)
                halo.setAlpha(50)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(halo)
                p.drawEllipse(pt, 10, 10)
            p.setPen(QPen(QColor(token("card")), 2))
            p.setBrush(accent)
            p.drawEllipse(pt, 5.5 if big else 3.2, 5.5 if big else 3.2)
        self.draw_labels(p, rect)
        index = self.hover if self.hover >= 0 and self.values[self.hover] > 0 else (last if reveal >= 1 else -1)
        if index >= 0:
            pt = dict(indexed)[index]
            self.draw_bubble(p, pt, self.labels[index], self.fmt(self.values[index]))


class RankChart(Chart):
    """Horizontal bars, biggest first (e.g. top brokers)."""

    def plot_rect(self) -> QRectF:
        return QRectF(8, 8, self.width() - 16, self.height() - 16)

    def index_at(self, pos: QPointF) -> int:
        n = len(self.values)
        rect = self.plot_rect()
        if n == 0:
            return -1
        row = int((pos.y() - rect.top()) / (rect.height() / max(n, 5)))
        return row if 0 <= row < n else -1

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt API)
        p = self.painter()
        if not self.has_data():
            self.draw_empty(p)
            return
        rect = self.plot_rect()
        n = len(self.values)
        row_h = rect.height() / max(n, 5)
        top = max(self.values)
        font = self.small_font()
        metrics = QFontMetrics(font)
        value_w = max(metrics.horizontalAdvance(self.fmt(v)) for v in self.values) + 10
        label_w = min(rect.width() * 0.38, max(metrics.horizontalAdvance(lbl) for lbl in self.labels) + 12)
        track_w = rect.width() - label_w - value_w
        accent, accent2 = QColor(token("accent")), QColor(token("accent2"))
        for i, (label, value) in enumerate(zip(self.labels, self.values, strict=True)):
            y = rect.top() + row_h * i
            bar_h = min(14.0, row_h * 0.5)
            cy = y + (row_h - bar_h) / 2
            if i == self.hover:
                band = QColor(token("accent"))
                band.setAlpha(18)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(band)
                p.drawRoundedRect(QRectF(rect.left() - 4, y + 2, rect.width() + 8, row_h - 4), 8, 8)
            p.setFont(self.small_font(bold=i == self.hover))
            p.setPen(QColor(token("text")))
            p.drawText(QRectF(rect.left(), y, label_w - 8, row_h), Qt.AlignmentFlag.AlignVCenter,
                       metrics.elidedText(label, Qt.TextElideMode.ElideRight, int(label_w - 8)))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(token("surface2")))
            p.drawRoundedRect(QRectF(rect.left() + label_w, cy, track_w, bar_h), bar_h / 2, bar_h / 2)
            w = max(bar_h, track_w * (value / top) * self.item_progress(i, n))
            grad = QLinearGradient(rect.left() + label_w, 0, rect.left() + label_w + w, 0)
            start, end = QColor(accent), QColor(accent2)
            if i != self.hover and not (self.hover < 0 and i == 0):
                start.setAlpha(160)
                end.setAlpha(140)
            grad.setColorAt(0, start)
            grad.setColorAt(1, end)
            p.setBrush(grad)
            p.drawRoundedRect(QRectF(rect.left() + label_w, cy, w, bar_h), bar_h / 2, bar_h / 2)
            p.setFont(font)
            p.setPen(QColor(token("text") if i == self.hover else token("muted")))
            p.drawText(QRectF(rect.right() - value_w, y, value_w, row_h),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, self.fmt(value))


class DonutChart(Chart):
    """Ring split into coloured parts with a legend; the hovered part lifts out and its value shows
    in the middle. ``colors`` overrides the theme's series colours."""

    def __init__(self, fmt: Formatter = lambda v: f"{v:,.0f}", parent: QWidget | None = None):
        super().__init__(fmt, parent)
        self.colors: list[QColor] | None = None
        self.center_title = ""

    def _geometry(self) -> tuple[QRectF, QRectF]:
        size = min(self.height() - 16, self.width() * 0.5)
        ring = QRectF(12, (self.height() - size) / 2, size, size)
        legend = QRectF(ring.right() + 18, 8, self.width() - ring.right() - 26, self.height() - 16)
        return ring, legend

    def _color(self, i: int) -> QColor:
        palette = self.colors or series_colors()
        return QColor(palette[i % len(palette)])

    def index_at(self, pos: QPointF) -> int:
        ring, legend = self._geometry()
        total = sum(self.values)
        if not total:
            return -1
        if legend.contains(pos):
            row = int((pos.y() - self._legend_top(legend)) / self._legend_row())
            return row if 0 <= row < len(self.values) else -1
        center = ring.center()
        dx, dy = pos.x() - center.x(), pos.y() - center.y()
        radius = ring.width() / 2
        if not radius * 0.55 <= math.hypot(dx, dy) <= radius + 6:
            return -1
        angle = (90 - math.degrees(math.atan2(-dy, dx))) % 360  # clockwise from 12 o'clock
        acc = 0.0
        for i, v in enumerate(self.values):
            acc += 360 * v / total
            if angle <= acc:
                return i
        return -1

    def _two_line_legend(self) -> bool:
        """Name above value when there is room; otherwise one line per part (name … value)."""
        line = QFontMetrics(self.small_font()).height()
        return (line * 2 + 6) * len(self.values) <= self.height() - 16

    def _legend_row(self) -> float:
        line = QFontMetrics(self.small_font()).height()
        return line * 2 + 6 if self._two_line_legend() else line + 7

    def _legend_top(self, legend: QRectF) -> float:
        return legend.center().y() - self._legend_row() * len(self.values) / 2

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt API)
        p = self.painter()
        total = sum(self.values)
        if not total:
            self.draw_empty(p)
            return
        ring, legend = self._geometry()
        thickness = ring.width() * 0.17
        reveal = ease_out(self.progress)
        start = 90.0
        track = QColor(token("surface2"))
        p.setPen(QPen(track, thickness, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
        inner = ring.adjusted(thickness / 2 + 4, thickness / 2 + 4, -thickness / 2 - 4, -thickness / 2 - 4)
        p.drawArc(inner, 0, 360 * 16)
        for i, value in enumerate(self.values):
            span = -360.0 * value / total * reveal
            if not span:
                continue
            arc = inner
            if i == self.hover:  # lift the hovered part outwards
                mid = math.radians(start + span / 2)
                arc = inner.translated(5 * math.cos(mid), -5 * math.sin(mid))
            pen = QPen(self._color(i), thickness * (1.12 if i == self.hover else 1.0), Qt.PenStyle.SolidLine,
                       Qt.PenCapStyle.FlatCap)
            p.setPen(pen)
            gap = 1.2 if len([v for v in self.values if v]) > 1 else 0.0
            p.drawArc(arc, int((start - gap / 2) * 16), int((span + gap) * 16))
            start += span
        # centre text: hovered part, or the total
        index = self.hover
        title = self.labels[index] if index >= 0 else self.center_title
        value = self.values[index] if index >= 0 else total
        title_font, value_font = self.small_font(), self.small_font(bold=True)
        value_font.setPointSizeF(value_font.pointSizeF() + 3)
        center_box = inner.adjusted(thickness / 2, thickness / 2, -thickness / 2, -thickness / 2)
        p.setPen(QColor(token("muted")))
        p.setFont(title_font)
        tm = QFontMetrics(title_font)
        title_box = QRectF(center_box.left(), center_box.center().y() - tm.height() - 1, center_box.width(),
                           tm.height())
        p.drawText(title_box,
                   Qt.AlignmentFlag.AlignHCenter, tm.elidedText(title, Qt.TextElideMode.ElideRight,
                                                                int(center_box.width())))
        p.setPen(QColor(token("text")))
        p.setFont(value_font)
        vm = QFontMetrics(value_font)
        p.drawText(QRectF(center_box.left() - 10, center_box.center().y(), center_box.width() + 20, vm.height()),
                   Qt.AlignmentFlag.AlignHCenter, vm.elidedText(self.fmt(value), Qt.TextElideMode.ElideRight,
                                                                int(center_box.width() + 20)))
        # legend
        row_h = self._legend_row()
        y = self._legend_top(legend)
        font, bold = self.small_font(), self.small_font(bold=True)
        lm, bm = QFontMetrics(font), QFontMetrics(bold)
        two_lines = self._two_line_legend()
        for i, (label, value) in enumerate(zip(self.labels, self.values, strict=True)):
            row = QRectF(legend.left(), y + row_h * i, legend.width(), row_h)
            if i == self.hover:
                band = QColor(token("accent"))
                band.setAlpha(18)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(band)
                p.drawRoundedRect(row.adjusted(-6, 1, 0, -1), 7, 7)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(self._color(i))
            dot_top = row.top() + 6 if two_lines else row.center().y() - 5
            p.drawRoundedRect(QRectF(row.left(), dot_top, 10, 10), 3, 3)
            text_left, text_w = row.left() + 16, row.width() - 16
            if two_lines:
                share = f"  ·  {value / total:.0%}" if total else ""
                p.setFont(font)
                p.setPen(QColor(token("muted")))
                p.drawText(QRectF(text_left, row.top() + 2, text_w, lm.height()), Qt.AlignmentFlag.AlignLeft,
                           lm.elidedText(label, Qt.TextElideMode.ElideRight, int(text_w)))
                p.setFont(bold)
                p.setPen(QColor(token("text")))
                p.drawText(QRectF(text_left, row.top() + 2 + lm.height(), text_w, lm.height() + 2),
                           Qt.AlignmentFlag.AlignLeft, self.fmt(value) + share)
            else:
                amount = self.fmt(value)
                amount_w = bm.horizontalAdvance(amount) + 4
                p.setFont(bold)
                p.setPen(QColor(token("text") if value else token("muted")))
                p.drawText(QRectF(row.right() - amount_w, row.top(), amount_w, row_h),
                           Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, amount)
                p.setFont(font)
                p.setPen(QColor(token("muted")))
                p.drawText(QRectF(text_left, row.top(), text_w - amount_w - 8, row_h),
                           Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                           lm.elidedText(label, Qt.TextElideMode.ElideRight, int(text_w - amount_w - 8)))
