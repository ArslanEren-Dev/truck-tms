"""Start-up animation: a small truck drives along a winding road.

The road is the progress bar: when the truck reaches the end of the road,
loading is finished and the main window appears.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from .. import __version__
from ..i18n import t

WIDTH, HEIGHT = 620, 360


def road_path() -> QPainterPath:
    path = QPainterPath(QPointF(40, 262))
    path.cubicTo(QPointF(140, 262), QPointF(170, 196), QPointF(270, 206))
    path.cubicTo(QPointF(370, 216), QPointF(380, 292), QPointF(470, 280))
    path.cubicTo(QPointF(530, 272), QPointF(552, 232), QPointF(580, 226))
    return path


class SplashScreen(QWidget):
    finished = Signal()

    def __init__(self, duration_ms: int = 2400):
        super().__init__(None, Qt.WindowType.SplashScreen | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(WIDTH, HEIGHT)
        self.progress = 0.0
        self.path = road_path()
        self.anim = QVariantAnimation(self)
        self.anim.setDuration(duration_ms)
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.setEasingCurve(QEasingCurve.Type.InOutSine)
        self.anim.valueChanged.connect(self._step)
        self.anim.finished.connect(self.finished)
        screen = QGuiApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self.move(geo.center().x() - WIDTH // 2, geo.center().y() - HEIGHT // 2)

    def start(self) -> None:
        self.anim.start()

    def _step(self, value: float) -> None:
        self.progress = float(value)
        self.update()

    def status_text(self) -> str:
        p = self.progress
        if p >= 1.0:
            return t("splash.ready")
        if p < 0.35:
            return t("splash.opening")
        if p < 0.75:
            return t("splash.preparing")
        return t("splash.almost")

    # ----------------------------------------------------------------- painting
    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt API)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._background(p)
        self._title(p)
        self._road(p)
        self._truck(p)
        self._footer(p)
        p.end()

    def _background(self, p: QPainter) -> None:
        grad = QLinearGradient(0, 0, WIDTH, HEIGHT)
        grad.setColorAt(0, QColor("#1E63C6"))
        grad.setColorAt(1, QColor("#0B1F3F"))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(grad)
        p.drawRoundedRect(QRectF(0, 0, WIDTH, HEIGHT), 22, 22)
        # distant hills
        p.setBrush(QColor(255, 255, 255, 14))
        hills = QPainterPath(QPointF(0, 250))
        hills.cubicTo(QPointF(120, 170), QPointF(220, 230), QPointF(330, 190))
        hills.cubicTo(QPointF(430, 150), QPointF(520, 210), QPointF(WIDTH, 170))
        hills.lineTo(WIDTH, HEIGHT - 22)
        hills.lineTo(0, HEIGHT - 22)
        hills.closeSubpath()
        p.drawPath(hills)

    def _title(self, p: QPainter) -> None:
        p.setPen(QColor("#FFFFFF"))
        font = QFont("Segoe UI", 24)
        font.setBold(True)
        p.setFont(font)
        p.drawText(QPointF(36, 62), "Truck TMS")
        font = QFont("Segoe UI", 10)
        p.setFont(font)
        p.setPen(QColor(255, 255, 255, 190))
        p.drawText(QPointF(38, 88), f"{t('splash.subtitle')}  ·  v{__version__}")

    def _road(self, p: QPainter) -> None:
        p.setBrush(Qt.BrushStyle.NoBrush)
        # shoulder + asphalt
        p.setPen(QPen(QColor(255, 255, 255, 40), 38, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawPath(self.path)
        p.setPen(QPen(QColor("#24303D"), 30, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawPath(self.path)
        # dashed centre line still ahead of the truck
        dash = QPen(QColor(255, 255, 255, 120), 3, Qt.PenStyle.CustomDashLine, Qt.PenCapStyle.RoundCap)
        dash.setDashPattern([4, 5])
        p.setPen(dash)
        p.drawPath(self.path)
        # the part already driven glows orange
        if self.progress > 0:
            driven = QPainterPath(self.path.pointAtPercent(0))
            steps = max(2, int(120 * self.progress))
            for i in range(1, steps + 1):
                driven.lineTo(self.path.pointAtPercent(self.progress * i / steps))
            p.setPen(QPen(QColor("#F5A623"), 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawPath(driven)
        # finish flag
        end = self.path.pointAtPercent(1.0)
        p.setPen(QPen(QColor("#FFFFFF"), 3))
        p.drawLine(end, end + QPointF(0, -42))
        for row in range(3):
            for col in range(3):
                p.fillRect(QRectF(end.x() + col * 7, end.y() - 42 + row * 7, 7, 7),
                           QColor("#FFFFFF") if (row + col) % 2 == 0 else QColor("#111111"))

    def _truck(self, p: QPainter) -> None:
        t_ = min(max(self.progress, 0.0), 1.0)
        pos = self.path.pointAtPercent(t_)
        angle = self.path.angleAtPercent(t_)
        p.save()
        p.translate(pos)
        p.rotate(-angle)
        p.translate(-34, -30)  # truck is 68 x 34, sitting on the road centre line
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 60))
        p.drawRoundedRect(QRectF(2, 30, 66, 6), 3, 3)          # shadow
        p.setBrush(QColor("#FFFFFF"))
        p.drawRoundedRect(QRectF(0, 0, 42, 26), 3, 3)          # trailer
        cab = QPainterPath(QPointF(45, 6))
        cab.lineTo(57, 6)
        cab.lineTo(68, 16)
        cab.lineTo(68, 26)
        cab.lineTo(45, 26)
        cab.closeSubpath()
        p.drawPath(cab)                                          # cab
        p.setBrush(QColor("#7FB2F0"))
        window = QPainterPath(QPointF(49, 9))
        window.lineTo(56, 9)
        window.lineTo(63, 16)
        window.lineTo(49, 16)
        window.closeSubpath()
        p.drawPath(window)
        p.setBrush(QColor("#F5A623"))
        p.drawRect(QRectF(66, 20, 3, 3))                         # headlight
        p.setPen(QColor("#1E63C6"))
        font = QFont("Segoe UI", 8)
        font.setBold(True)
        p.setFont(font)
        p.drawText(QRectF(0, 0, 42, 26), Qt.AlignmentFlag.AlignCenter, "TMS")
        # wheels turn while driving
        spin = self.progress * 360 * 9
        for x in (10, 30, 58):
            p.save()
            p.translate(x, 29)
            p.setPen(QPen(QColor("#FFFFFF"), 2))
            p.setBrush(QColor("#0B1F3F"))
            p.drawEllipse(QPointF(0, 0), 6, 6)
            p.rotate(spin)
            p.drawLine(QPointF(-4, 0), QPointF(4, 0))
            p.restore()
        p.restore()

    def _footer(self, p: QPainter) -> None:
        p.setPen(QColor(255, 255, 255, 220))
        font = QFont("Segoe UI", 10)
        p.setFont(font)
        p.drawText(QPointF(36, HEIGHT - 30), self.status_text())
        font.setBold(True)
        p.setFont(font)
        p.drawText(QRectF(0, HEIGHT - 46, WIDTH - 36, 22),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                   t("fmt.percent", v=math.floor(self.progress * 100)))
