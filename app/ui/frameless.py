"""
Frameless window wrapper with a minimalist custom title bar and
native-feeling move and resize (uses the window system's own routines).
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QEvent
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
)

from app.ui.icons import icon, icon_pixmap
from app.ui.theme import TEXT, TEXT_DIM, ACCENT_HOVER


class TitleBar(QWidget):
    def __init__(self, window: "FramelessWindow", title: str):
        super().__init__(window)
        self.setObjectName("TitleBar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(40)
        self._win = window

        h = QHBoxLayout(self)
        h.setContentsMargins(14, 0, 0, 0)
        h.setSpacing(0)

        mark = QLabel()
        mark.setPixmap(icon_pixmap("scan-face", ACCENT_HOVER, 18, 2.0))
        self.title = QLabel(title)
        self.title.setObjectName("TitleText")
        h.addWidget(mark)
        h.addSpacing(8)
        h.addWidget(self.title)
        h.addStretch()

        self.btn_min = self._chrome_button("minus")
        self.btn_max = self._chrome_button("square")
        self.btn_close = self._chrome_button("x")
        self.btn_close.setObjectName("CloseBtn")
        self.btn_min.clicked.connect(window.showMinimized)
        self.btn_max.clicked.connect(window.toggle_maximize)
        self.btn_close.clicked.connect(window.close)
        for b in (self.btn_min, self.btn_max, self.btn_close):
            h.addWidget(b)

    @staticmethod
    def _chrome_button(icon_name: str) -> QPushButton:
        b = QPushButton()
        b.setProperty("chrome", True)
        b.setIcon(icon(icon_name, TEXT_DIM, 14))
        b.setCursor(Qt.ArrowCursor)
        b.setFocusPolicy(Qt.NoFocus)
        return b

    def set_maximized(self, maximized: bool):
        self.btn_max.setIcon(icon("copy" if maximized else "square", TEXT_DIM, 14))

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            handle = self._win.windowHandle()
            if handle:
                handle.startSystemMove()
        super().mousePressEvent(e)

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._win.toggle_maximize()


class FramelessWindow(QMainWindow):
    GRIP = 6

    def __init__(self, title: str):
        super().__init__()
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setWindowTitle(title)

        self._central = QWidget()
        self._central.setObjectName("Central")
        self._central.setAttribute(Qt.WA_StyledBackground, True)
        self._central.setMouseTracking(True)
        self._central.installEventFilter(self)
        self.setCentralWidget(self._central)

        self._outer = QVBoxLayout(self._central)
        self._outer.setContentsMargins(self.GRIP, self.GRIP, self.GRIP, self.GRIP)
        self._outer.setSpacing(0)

        self.frame = QFrame()
        self.frame.setObjectName("WindowFrame")
        fl = QVBoxLayout(self.frame)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setSpacing(0)

        self.title_bar = TitleBar(self, title)
        fl.addWidget(self.title_bar)
        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(0)
        fl.addWidget(self.body, 1)
        self._outer.addWidget(self.frame)

    def toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def changeEvent(self, e):
        if e.type() == QEvent.WindowStateChange:
            maxed = self.isMaximized()
            m = 0 if maxed else self.GRIP
            self._outer.setContentsMargins(m, m, m, m)
            self.title_bar.set_maximized(maxed)
        super().changeEvent(e)

    # -- edge resize -----------------------------------------------------------
    def _edges_at(self, pos):
        if self.isMaximized():
            return None
        g = self.GRIP
        w, h = self._central.width(), self._central.height()
        parts = []
        if pos.x() < g:
            parts.append(Qt.LeftEdge)
        if pos.x() > w - g:
            parts.append(Qt.RightEdge)
        if pos.y() < g:
            parts.append(Qt.TopEdge)
        if pos.y() > h - g:
            parts.append(Qt.BottomEdge)
        if not parts:
            return None
        edges = parts[0]
        for p in parts[1:]:
            edges = edges | p
        return edges

    @staticmethod
    def _cursor_for(edges):
        horiz = edges in (Qt.LeftEdge, Qt.RightEdge)
        vert = edges in (Qt.TopEdge, Qt.BottomEdge)
        if horiz:
            return Qt.SizeHorCursor
        if vert:
            return Qt.SizeVerCursor
        if edges in (Qt.LeftEdge | Qt.TopEdge, Qt.RightEdge | Qt.BottomEdge):
            return Qt.SizeFDiagCursor
        return Qt.SizeBDiagCursor

    def eventFilter(self, obj, ev):
        if obj is self._central:
            t = ev.type()
            if t == QEvent.MouseMove:
                edges = self._edges_at(ev.position().toPoint())
                if edges is None:
                    self._central.unsetCursor()
                else:
                    self._central.setCursor(self._cursor_for(edges))
            elif t == QEvent.MouseButtonPress and ev.button() == Qt.LeftButton:
                edges = self._edges_at(ev.position().toPoint())
                if edges is not None and self.windowHandle():
                    self.windowHandle().startSystemResize(edges)
                    return True
        return super().eventFilter(obj, ev)
