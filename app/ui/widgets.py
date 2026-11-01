"""Shared building blocks: buttons, labels, cards, headers and the camera view."""

from __future__ import annotations

import cv2
import numpy as np
from PySide6.QtCore import Qt, QRectF, QSize
from PySide6.QtGui import (
    QColor, QFont, QFontMetrics, QImage, QPainter, QPainterPath, QPen,
)
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app.ui.icons import icon, icon_pixmap
from app.ui.theme import ACCENT, AMBER, BG, BORDER, GREEN, MUTED, RED, SURFACE, TEXT, TEXT_DIM


def repolish(w: QWidget):
    w.style().unpolish(w)
    w.style().polish(w)


def make_label(text: str = "", role: str | None = None) -> QLabel:
    lbl = QLabel(text)
    if role:
        lbl.setProperty("role", role)
    return lbl


def set_tone(lbl: QLabel, tone: str | None):
    lbl.setProperty("tone", tone or "")
    repolish(lbl)


def make_button(text: str, variant: str | None = None, icon_name: str | None = None) -> QPushButton:
    b = QPushButton(text)
    b.setCursor(Qt.PointingHandCursor)
    if variant:
        b.setProperty("variant", variant)
    if icon_name:
        color = BG if variant == "primary" else ("#ffffff" if variant == "accent" else TEXT_DIM)
        b.setIcon(icon(icon_name, color, 16))
        b.setIconSize(QSize(16, 16))
    return b


class Card(QFrame):
    def __init__(self, parent=None, margins=(20, 20, 20, 20), spacing=12):
        super().__init__(parent)
        self.setObjectName("Card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(*margins)
        self.body.setSpacing(spacing)


class PageHeader(QWidget):
    def __init__(self, title: str, subtitle: str = "", parent=None):
        super().__init__(parent)
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        text = QVBoxLayout()
        text.setSpacing(2)
        text.addWidget(make_label(title, "h1"))
        if subtitle:
            text.addWidget(make_label(subtitle, "dim"))
        h.addLayout(text, 1)
        self.actions = QHBoxLayout()
        self.actions.setSpacing(8)
        h.addLayout(self.actions)


def kv_row(key: str, value: QLabel) -> QWidget:
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(0, 0, 0, 0)
    h.addWidget(make_label(key, "muted"))
    h.addStretch()
    value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    h.addWidget(value)
    return w


_STATUS_COLORS = {
    "unknown": RED,
    "already_marked": ACCENT,
    "cooldown": AMBER,
    "low_quality": AMBER,
}


class CameraView(QWidget):
    """Paints the frame and rounded detection boxes with a name pill."""

    RADIUS = 14

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(420, 420)
        self._image: QImage | None = None
        self._buf: np.ndarray | None = None
        self._result = None
        self._placeholder = "Waiting for camera"

    def set_placeholder(self, text: str):
        self._placeholder = text
        self._image = None
        self.update()

    def set_result(self, result):
        self._result = result

    def set_frame(self, frame_bgr: np.ndarray, result=None):
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        self._buf = np.ascontiguousarray(rgb)
        h, w, _ = self._buf.shape
        self._image = QImage(self._buf.data, w, h, 3 * w, QImage.Format_RGB888)
        if result is not None:
            self._result = result
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform | QPainter.TextAntialiasing)
        outer = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        clip = QPainterPath()
        clip.addRoundedRect(outer, self.RADIUS, self.RADIUS)
        p.setClipPath(clip)
        p.fillPath(clip, QColor(SURFACE))

        if self._image is None:
            pm = icon_pixmap("camera", MUTED, 36, 2.0)
            p.drawPixmap(int(outer.center().x() - 18), int(outer.center().y() - 34), pm)
            p.setPen(QColor(MUTED))
            p.drawText(QRectF(outer.left(), outer.center().y() + 8, outer.width(), 24),
                       Qt.AlignHCenter | Qt.AlignTop, self._placeholder)
        else:
            iw = self._image.width()
            diameter = min(self.width(), self.height()) - 36
            target = QRectF((self.width() - diameter) / 2, (self.height() - diameter) / 2,
                            diameter, diameter)
            circle = QPainterPath()
            circle.addEllipse(target)
            p.save()
            p.setClipPath(circle)
            p.drawImage(target, self._image)
            self._draw_detection(p, target, iw)
            p.restore()
            p.setPen(QPen(QColor(ACCENT), 2))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(target)

        p.setClipping(False)
        p.setPen(QPen(QColor(BORDER), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(outer, self.RADIUS, self.RADIUS)

    def _draw_detection(self, p: QPainter, target: QRectF, frame_w: int):
        r = self._result
        if not r or not getattr(r, "bbox", None):
            return
        x1, y1, x2, y2 = r.bbox
        s = target.width() / frame_w
        box = QRectF(target.x() + x1 * s, target.y() + y1 * s, (x2 - x1) * s, (y2 - y1) * s)
        color = QColor(_STATUS_COLORS.get(r.status, GREEN))

        fill = QColor(color)
        fill.setAlpha(22)
        p.setPen(QPen(color, 2))
        p.setBrush(fill)
        p.drawRoundedRect(box, 12, 12)

        text = r.message or ""
        if r.status == "already_marked" and getattr(r, "student_id", None):
            text = f"{r.student_id}   Already Recognized"
        elif getattr(r, "student_id", None):
            text = f"{r.student_id}   {text}"
        font = QFont(self.font())
        font.setPixelSize(12)
        font.setWeight(QFont.DemiBold)
        fm = QFontMetrics(font)
        pw, ph = fm.horizontalAdvance(text) + 20, 24
        py = box.top() - ph - 6
        if py < target.top() + 4:
            py = box.top() + 6
        pill = QRectF(box.left(), py, pw, ph)
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        p.drawRoundedRect(pill, ph / 2, ph / 2)
        p.setFont(font)
        p.setPen(QColor(BG))
        p.drawText(pill, Qt.AlignCenter, text)
