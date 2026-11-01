"""
Dashboard bridge (Python -> QML), icon image provider and the QQuickWidget host.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from pathlib import Path

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtQuick import QQuickImageProvider
from PySide6.QtQuickWidgets import QQuickWidget

from app.core.database import get_all_students, get_all_unknowns, get_sessions_with_counts
from app.core.time_utils import now_ist, today_ist
from app.ui.icons import icon_pixmap
from app.ui.theme import BG, THEME_DICT

logger = logging.getLogger(__name__)
QML_DIR = Path(__file__).parent / "qml"


class IconProvider(QQuickImageProvider):
    """Serves image://icons/<name>/<hexcolor> to QML."""

    def __init__(self):
        super().__init__(QQuickImageProvider.Pixmap)

    def requestPixmap(self, id, size, requestedSize):
        name, _, hexcol = id.partition("/")
        side = requestedSize.width() if requestedSize.width() > 0 else 24
        pm = icon_pixmap(name, "#" + (hexcol or "a1a1aa"), side)
        return pm if not pm.isNull() else QPixmap(side, side)


class DashboardBridge(QObject):
    statsChanged = Signal()
    navigateRequested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._students = 0
        self._today = 0
        self._unknown = 0
        self._trend_values = [0] * 7
        self._trend_labels = [""] * 7
        self._session_label = "No active session"
        self._session_active = False
        self._camera_online = False
        self._camera_label = "Starting"
        self._models_ready = False
        self._db_ok = True
        self._activity: list[dict] = []

    # -- properties exposed to QML --------------------------------------------
    studentCount = Property(int, lambda s: s._students, notify=statsChanged)
    todayCount = Property(int, lambda s: s._today, notify=statsChanged)
    unknownCount = Property(int, lambda s: s._unknown, notify=statsChanged)
    trendValues = Property("QVariantList", lambda s: s._trend_values, notify=statsChanged)
    trendLabels = Property("QVariantList", lambda s: s._trend_labels, notify=statsChanged)
    sessionLabel = Property(str, lambda s: s._session_label, notify=statsChanged)
    sessionActive = Property(bool, lambda s: s._session_active, notify=statsChanged)
    cameraOnline = Property(bool, lambda s: s._camera_online, notify=statsChanged)
    cameraLabel = Property(str, lambda s: s._camera_label, notify=statsChanged)
    modelsReady = Property(bool, lambda s: s._models_ready, notify=statsChanged)
    dbOk = Property(bool, lambda s: s._db_ok, notify=statsChanged)
    activity = Property("QVariantList", lambda s: s._activity, notify=statsChanged)
    greeting = Property(str, lambda s: s._greeting(), notify=statsChanged)
    dateLabel = Property(str, lambda s: now_ist().strftime("%A, %d %B"), notify=statsChanged)

    @staticmethod
    def _greeting() -> str:
        h = now_ist().hour
        return "Good morning" if h < 12 else ("Good afternoon" if h < 18 else "Good evening")

    @Slot(str)
    def navigate(self, key: str):
        self.navigateRequested.emit(key)

    # -- python-side updates ----------------------------------------------------
    def refresh_stats(self):
        try:
            self._students = len(get_all_students())
            self._unknown = len(get_all_unknowns(limit=500))
            today = today_ist()
            per_day = {today - timedelta(days=i): 0 for i in range(6, -1, -1)}
            for s in get_sessions_with_counts(days=7):
                d = s["session_date"]
                if d in per_day:
                    per_day[d] += int(s["count"])
            self._trend_values = list(per_day.values())
            self._trend_labels = [d.strftime("%a") for d in per_day]
            self._today = per_day[today]
            self._db_ok = True
        except Exception:
            logger.exception("Dashboard stats refresh failed")
            self._db_ok = False
        self.statsChanged.emit()

    def set_session(self, code: str | None):
        self._session_active = bool(code)
        self._session_label = code if code else "No active session"
        self.statsChanged.emit()

    def set_camera(self, online: bool, label: str):
        self._camera_online = online
        self._camera_label = label
        self.statsChanged.emit()

    def set_models_ready(self, ready: bool):
        self._models_ready = ready
        self.statsChanged.emit()

    def push_activity(self, title: str, detail: str, kind: str = "info"):
        self._activity.insert(0, {
            "title": title, "detail": detail, "kind": kind,
            "time": now_ist().strftime("%H:%M"),
        })
        del self._activity[6:]
        self.statsChanged.emit()


class DashboardView(QQuickWidget):
    def __init__(self, bridge: DashboardBridge, parent=None):
        super().__init__(parent)
        self.setResizeMode(QQuickWidget.SizeRootObjectToView)
        self.setClearColor(QColor(BG))
        self._provider = IconProvider()          # keep a reference alive
        self.engine().addImageProvider("icons", self._provider)
        ctx = self.rootContext()
        ctx.setContextProperty("backend", bridge)
        ctx.setContextProperty("Theme", THEME_DICT)
        self.setSource(QUrl.fromLocalFile(str(QML_DIR / "Dashboard.qml")))
        if self.status() == QQuickWidget.Error:
            for err in self.errors():
                logger.error("QML: %s", err.toString())
