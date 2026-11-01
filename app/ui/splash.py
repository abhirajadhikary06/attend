"""Minimal full-screen animated brand intro for attend."""

from __future__ import annotations

import math

from PySide6.QtCore import Qt, QTimer, QRectF, QPointF
from PySide6.QtGui import QColor, QFont, QPainter, QRadialGradient
from PySide6.QtWidgets import QApplication, QWidget

from app.ui.icons import icon_pixmap
from app.ui.theme import ACCENT, ACCENT_HOVER, BG, TEXT


class SplashScreen(QWidget):
    """A short logo-only intro shown before the dashboard."""

    def __init__(self):
        super().__init__(None, Qt.SplashScreen | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_OpaquePaintEvent)
        self.setFixedSize(1360, 860)
        screen = QApplication.primaryScreen()
        if screen:
            self.move(screen.availableGeometry().center() - self.rect().center())
        self._phase = 0.0
        self._logo = icon_pixmap("scan-face", ACCENT_HOVER, 72, 2.0)
        self._timer = QTimer(self)
        self._timer.setInterval(24)
        self._timer.timeout.connect(self._advance)
        self._timer.start()

    def _advance(self):
        self._phase = (self._phase + 0.035) % (2 * math.pi)
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(BG))

        center = QPointF(self.width() / 2, self.height() / 2 - 12)
        glow = QRadialGradient(center, min(self.width(), self.height()) * 0.42)
        halo = QColor(ACCENT)
        halo.setAlpha(30)
        glow.setColorAt(0, halo)
        glow.setColorAt(1, QColor(BG))
        p.fillRect(self.rect(), glow)

        pulse = 1.0 + 0.035 * math.sin(self._phase)
        side = int(86 * pulse)
        p.setOpacity(0.84 + 0.16 * math.sin(self._phase) ** 2)
        p.drawPixmap(int(center.x() - side / 2), int(center.y() - side / 2),
                     side, side, self._logo)
        p.setOpacity(1.0)

        p.setFont(QFont("Segoe UI", 42, QFont.DemiBold))
        p.setPen(QColor(TEXT))
        p.drawText(QRectF(0, center.y() + 112, self.width(), 64),
                   Qt.AlignHCenter | Qt.AlignTop, "attend")
        p.end()
