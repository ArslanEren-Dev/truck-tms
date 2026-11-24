"""Small painted widgets: a sparkline, a profit gauge, an animated check mark, a hero band,
and helpers for staggered entrances and row flashes."""

from __future__ import annotations

import math
from collections.abc import Callable

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, QSize, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QFrame, QGraphicsOpacityEffect, QTableWidget, QWidget

from .theme import token


def _animation(owner: QWidget, duration: int, on_value, curve=QEasingCurve.Type.OutCubic) -> QVariantAnimation:
    anim = QVariantAnimation(owner)
    anim.setDuration(duration)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(curve)
    anim.valueChanged.connect(on_value)
    return anim


class Sparkline(QWidget):
    """A tiny trend line with a soft fill, drawn from left to right when the values change."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.values: list[float] = []
        self.progress = 1.0
        self.setFixedHeight(30)
        self.setMinimumWidth(60)
        self.anim = _animation(self, 700, self._step)

    def _step(self, value: float) -> None:
        self.progress = float(value)
        self.update()

    def set_values(self, values: list[float], animate: bool = True) -> None:
        self.values = [float(v) for v in values]
        self.setVisible(len(self.values) >= 2 and any(self.values))
        if animate:
            self.anim.stop()
            self.anim.start()
        else:
            self.progress = 1.0
            self.update()

    def points(self) -> list[QPointF]:
        if len(self.values) < 2:
            return []
        low, high = min(self.values), max(self.values)
        span = (high - low) or 1.0
        w, h = self.width() - 4, self.height() - 6
        step = w / (len(self.values) - 1)
        return [QPointF(2 + i * step, 3 + h - (v - low) / span * h) for i, v in enumerate(self.values)]

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt API)
        pts = self.points()
        if not pts:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setClipRect(QRectF(0, 0, self.width() * self.progress + 1, self.height()))
        accent = QColor(token("accent"))
        line = QPainterPath(pts[0])
        for pt in pts[1:]:
            line.lineTo(pt)
        area = QPainterPath(line)
        area.lineTo(pts[-1].x(), self.height())
        area.lineTo(pts[0].x(), self.height())
        area.closeSubpath()
        grad = QLinearGradient(0, 0, 0, self.height())
        top = QColor(accent)
        top.setAlpha(70)
        bottom = QColor(accent)
        bottom.setAlpha(0)
        grad.setColorAt(0, top)
        grad.setColorAt(1, bottom)
        p.fillPath(area, grad)
        p.setPen(QPen(accent, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.drawPath(line)
        p.setBrush(accent)
        p.drawEllipse(pts[-1], 2.6, 2.6)
        p.end()


def margin_tone(margin: float | None) -> str:
    """Color of a profit margin: red when losing money, orange when thin, green when healthy."""
    if margin is None:
        return "neutral"
    if margin < 0:
        return "danger"
    return "warning" if margin < 15 else "success"


class ProfitGauge(QWidget):
    """A half-circle gauge of the profit margin (0–50 %), sweeping to its new value."""

    MAX = 50.0

    def __init__(self, parent: QWidget | None = None, size: int = 96):
        super().__init__(parent)
        self.margin: float | None = None
        self.shown = 0.0
        self._from = 0.0
        self.setFixedSize(QSize(size, int(size * 0.62)))
        self.anim = _animation(self, 520, self._step)

    def _step(self, value: float) -> None:
        target = self.margin or 0.0
        self.shown = self._from + (target - self._from) * float(value)
        self.update()

    def set_margin(self, margin: float | None, animate: bool = True) -> None:
        self.margin = margin
        self._from = self.shown
        if animate:
            self.anim.stop()
            self.anim.start()
        else:
            self.shown = margin or 0.0
            self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt API)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        pen_w = max(6.0, w / 11)
        rect = QRectF(pen_w / 2 + 1, pen_w / 2 + 1, w - pen_w - 2, w - pen_w - 2)
        p.setPen(QPen(QColor(token("surface2")), pen_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawArc(rect, 180 * 16, -180 * 16)
        share = max(0.0, min(1.0, self.shown / self.MAX))
        color = QColor(token(f"{margin_tone(self.margin)}_fg" if self.margin is not None else "muted"))
        if share > 0:
            p.setPen(QPen(color, pen_w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawArc(rect, 180 * 16, int(-180 * 16 * share))
        p.setPen(QColor(token("text")))
        font = p.font()
        font.setBold(True)
        font.setPointSizeF(max(8.0, w / 9))
        p.setFont(font)
        text = "—" if self.margin is None else f"{self.shown:.0f}%"
        p.drawText(QRectF(0, rect.center().y() - w * 0.22, w, w * 0.3), Qt.AlignmentFlag.AlignCenter, text)
        p.end()


class AnimatedCheck(QWidget):
    """A green circle whose check mark draws itself (used by "saved" toasts)."""

    def __init__(self, color: str = "#4ADE80", parent: QWidget | None = None):
        super().__init__(parent)
        self.color = QColor(color)
        self.progress = 0.0
        self.setFixedSize(20, 20)
        self.anim = _animation(self, 420, self._step)
        QTimer.singleShot(60, self.anim.start)

    def _step(self, value: float) -> None:
        self.progress = float(value)
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt API)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        ring = min(1.0, self.progress * 2)
        p.setPen(QPen(self.color, 2))
        p.drawArc(QRectF(1.5, 1.5, 17, 17), 90 * 16, int(-360 * 16 * ring))
        tick = max(0.0, self.progress * 2 - 1)
        if tick > 0:
            a, b, c = QPointF(5.5, 10.5), QPointF(8.8, 13.6), QPointF(14.5, 7.0)
            path = QPainterPath(a)
            first = min(1.0, tick * 2)
            path.lineTo(a + (b - a) * first)
            if tick > 0.5:
                path.lineTo(b + (c - b) * ((tick - 0.5) * 2))
            p.setPen(QPen(self.color, 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            p.drawPath(path)
        p.end()


class HeroBand(QFrame):
    """The gradient band at the top of the overview, with soft circles drifting slowly behind the text."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Hero")
        self.phase = 0.0
        self.timer = QTimer(self)
        self.timer.setInterval(80)  # slow drift: a few repaints a second are enough
        self.timer.timeout.connect(self._tick)

    def showEvent(self, event) -> None:  # noqa: N802 (Qt API)
        self.timer.start()
        super().showEvent(event)

    def hideEvent(self, event) -> None:  # noqa: N802 (Qt API)
        self.timer.stop()
        super().hideEvent(event)

    def _tick(self) -> None:
        self.phase = (self.phase + 0.004) % 1.0
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt API)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect())
        grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
        grad.setColorAt(0, QColor(token("accent")))
        grad.setColorAt(1, QColor(token("hero_end")))
        path = QPainterPath()
        path.addRoundedRect(rect, 16, 16)
        p.fillPath(path, grad)
        p.setClipPath(path)
        p.setPen(Qt.PenStyle.NoPen)
        angle = self.phase * 2 * math.pi
        for i, (x, y, r, alpha) in enumerate(((0.82, 0.1, 0.55, 26), (0.95, 0.95, 0.35, 20), (0.55, 1.1, 0.4, 14))):
            dx = math.sin(angle + i * 2.1) * 0.03
            dy = math.cos(angle + i * 1.7) * 0.05
            p.setBrush(QColor(255, 255, 255, alpha))
            radius = r * rect.height() * 1.4
            p.drawEllipse(QPointF((x + dx) * rect.width(), (y + dy) * rect.height()), radius, radius)
        p.end()
        super().paintEvent(event)


def stagger_in(widgets: list[QWidget], step_ms: int = 45, duration: int = 320) -> None:
    """Fade widgets in one after another (cards appearing when a page opens)."""
    for i, widget in enumerate(widgets):
        if widget.graphicsEffect() is not None:
            continue  # a hover shadow is running; leave this card alone
        effect = QGraphicsOpacityEffect(widget)
        effect.setOpacity(0.0)
        widget.setGraphicsEffect(effect)
        anim = _animation(widget, duration, effect.setOpacity)
        anim.finished.connect(lambda w=widget, e=effect: w.graphicsEffect() is e and w.setGraphicsEffect(None))
        widget._stagger_anim = anim
        QTimer.singleShot(i * step_ms, anim.start)


def flash_row(table: QTableWidget, row: int, tone: str, then: Callable[[], None], duration: int = 260) -> None:
    """Tint a table row (e.g. red before it disappears), then call ``then``."""
    items = [table.item(row, c) for c in range(table.columnCount())]
    items = [item for item in items if item is not None]
    base = QColor(token(f"{tone}_bg"))
    if not items or not table.isVisible():
        then()
        return

    def step(value: float) -> None:
        color = QColor(base)
        color.setAlpha(int(255 * min(1.0, float(value) * 1.6)))
        for item in items:
            item.setBackground(color)

    anim = _animation(table, duration, step, QEasingCurve.Type.InOutQuad)
    anim.finished.connect(then)
    table._flash_anim = anim
    anim.start()
