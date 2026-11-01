"""
Main application window – dashboard + live camera + navigation.
"""

from __future__ import annotations
import logging
import threading
import calendar
from datetime import datetime, date, timedelta
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QImage, QPixmap, QFont, QColor
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QStackedWidget, QFrame, QStatusBar, QMessageBox,
    QTextEdit, QFormLayout, QLineEdit,
    QSpinBox, QFileDialog, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QScrollArea, QGridLayout,
    QSizePolicy, QSplitter,
)

import cv2
import numpy as np

from app.core.config import config, save_config
from app.core.database import (
    init_db, get_all_students, log_action,
    cleanup_old_attendance, cleanup_expired_unknowns,
    get_sessions_with_counts, get_attendance_for_session_detailed,
    get_all_unknowns,
)
from app.vision.pipeline import FacePipeline, RecognitionResult
from app.services.attendance_service import AttendanceService
from app.services.enrollment import EnrollmentService
from app.utils.camera import Camera

logger = logging.getLogger(__name__)

# ── shared style tokens ───────────────────────────────────────────────────────
_BG      = "#1e1e2e"
_SURFACE = "#181825"
_TEXT    = "#cdd6f4"
_ACCENT  = "#89b4fa"
_GREEN   = "#a6e3a1"
_RED     = "#f38ba8"
_YELLOW  = "#f9e2af"
_MUTED   = "#6c7086"


def _label(text: str, color: str = _TEXT, bold: bool = False, size: int = 13) -> QLabel:
    lbl = QLabel(text)
    weight = "bold" if bold else "normal"
    lbl.setStyleSheet(f"color:{color}; font-size:{size}px; font-weight:{weight};")
    return lbl


def _btn(text: str, accent: bool = False) -> QPushButton:
    b = QPushButton(text)
    if accent:
        b.setStyleSheet(
            f"QPushButton{{background:{_ACCENT}; color:{_BG}; border:none; border-radius:6px;"
            f"padding:8px 18px; font-weight:bold; font-size:13px;}}"
            f"QPushButton:hover{{background:#7aa2f7;}}"
            f"QPushButton:pressed{{background:#6a8fd8;}}"
        )
    else:
        b.setStyleSheet(
            f"QPushButton{{background:#313244; color:{_TEXT}; border:none; border-radius:6px;"
            f"padding:8px 18px; font-size:13px;}}"
            f"QPushButton:hover{{background:#45475a;}}"
        )
    return b


# ── camera widget ─────────────────────────────────────────────────────────────
class CameraWidget(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(640, 480)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet(f"background:{_SURFACE}; color:{_MUTED}; border-radius:8px;")
        self.setText("Camera starting…")
        self._pixmap = None

    def update_frame(self, frame_bgr: np.ndarray, result: RecognitionResult = None):
        if frame_bgr is None:
            return
        display = frame_bgr.copy()
        if result and result.bbox:
            x1, y1, x2, y2 = result.bbox
            color = (0, 200, 0)
            if result.status == "unknown":
                color = (60, 60, 220)
            elif result.status in ("already_marked", "cooldown"):
                color = (0, 180, 255)
            elif result.status == "low_quality":
                color = (0, 140, 255)
            cv2.rectangle(display, (x1, y1), (x2, y2), color, 2)
            label = result.message
            if result.student_id:
                label = f"{result.student_id} | {result.message}"
            cv2.putText(display, label, (x1, max(20, y1 - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2, cv2.LINE_AA)
        rgb = cv2.cvtColor(display, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qimg = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
        self._pixmap = QPixmap.fromImage(qimg)
        self.setPixmap(self._pixmap.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def resizeEvent(self, event):
        if self._pixmap:
            self.setPixmap(self._pixmap.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        super().resizeEvent(event)


# ── attendance register page ──────────────────────────────────────────────────
class AttendanceRegisterPage(QWidget):
    """
    Left panel: month calendar showing session tiles per day.
    Right panel: session list for the selected day → click → student table.
    """

    NAV_IDX = 6   # stack index assigned in MainWindow

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_month = date.today().replace(day=1)
        self._selected_date: date | None = None
        self._sessions_data: list[dict] = []   # full 31-day cache
        self._build()

    # ── build ─────────────────────────────────────────────────────────────────
    def _build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        # ---- LEFT: calendar ------------------------------------------------
        left = QFrame()
        left.setFixedWidth(420)
        left.setStyleSheet(f"QFrame{{background:{_SURFACE}; border-radius:10px;}}")
        lv = QVBoxLayout(left)
        lv.setContentsMargins(16, 16, 16, 16)
        lv.setSpacing(8)

        # month nav header
        hdr = QHBoxLayout()
        self.btn_prev = _btn("◀")
        self.btn_prev.setFixedWidth(36)
        self.btn_next = _btn("▶")
        self.btn_next.setFixedWidth(36)
        self.lbl_month = _label("", color=_ACCENT, bold=True, size=15)
        self.lbl_month.setAlignment(Qt.AlignCenter)
        hdr.addWidget(self.btn_prev)
        hdr.addWidget(self.lbl_month, stretch=1)
        hdr.addWidget(self.btn_next)
        lv.addLayout(hdr)

        # day-of-week header row
        dow_row = QHBoxLayout()
        for d in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"):
            lbl = _label(d, color=_MUTED, size=11)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setFixedWidth(52)
            dow_row.addWidget(lbl)
        lv.addLayout(dow_row)

        # calendar grid (6 rows × 7 cols)
        self.cal_grid = QGridLayout()
        self.cal_grid.setSpacing(4)
        self._day_btns: dict[date, QPushButton] = {}
        for r in range(6):
            for c in range(7):
                b = QPushButton()
                b.setFixedSize(52, 52)
                b.setCheckable(True)
                b.setStyleSheet(self._day_style(False, False))
                self.cal_grid.addWidget(b, r, c)
        lv.addLayout(self.cal_grid)
        lv.addStretch()

        root.addWidget(left)

        # ---- RIGHT: session + student table --------------------------------
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(8)

        # session list header
        sess_hdr = QHBoxLayout()
        self.lbl_day_title = _label("Select a day", color=_ACCENT, bold=True, size=14)
        refresh_btn = _btn("↻ Refresh")
        refresh_btn.clicked.connect(self.refresh)
        sess_hdr.addWidget(self.lbl_day_title, stretch=1)
        sess_hdr.addWidget(refresh_btn)
        rv.addLayout(sess_hdr)

        # session cards (scroll area)
        sess_scroll = QScrollArea()
        sess_scroll.setWidgetResizable(True)
        sess_scroll.setFixedHeight(160)
        sess_scroll.setStyleSheet("QScrollArea{border:none; background:transparent;}")
        self.sess_container = QWidget()
        self.sess_layout = QHBoxLayout(self.sess_container)
        self.sess_layout.setContentsMargins(0, 0, 0, 0)
        self.sess_layout.setSpacing(8)
        self.sess_layout.addStretch()
        sess_scroll.setWidget(self.sess_container)
        rv.addWidget(sess_scroll)

        # student attendance table
        self.lbl_session_title = _label("", color=_MUTED, size=12)
        rv.addWidget(self.lbl_session_title)

        self.att_table = QTableWidget(0, 6)
        self.att_table.setHorizontalHeaderLabels(
            ["Student ID", "Name", "Department", "Semester", "Time", "Method"])
        self.att_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.att_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.att_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.att_table.setStyleSheet(
            f"QTableWidget{{background:{_SURFACE}; color:{_TEXT}; gridline-color:#313244;"
            f"border-radius:6px; font-size:13px;}}"
            f"QHeaderView::section{{background:#313244; color:{_ACCENT}; padding:6px; border:none;}}"
            f"QTableWidget::item:selected{{background:#313244;}}"
        )
        rv.addWidget(self.att_table, stretch=1)

        root.addWidget(right, stretch=1)

        # signals
        self.btn_prev.clicked.connect(self._prev_month)
        self.btn_next.clicked.connect(self._next_month)

    # ── helpers ───────────────────────────────────────────────────────────────
    @staticmethod
    def _day_style(has_data: bool, checked: bool, today: bool = False) -> str:
        if checked:
            bg, fg = _ACCENT, _BG
        elif has_data:
            bg, fg = "#1e3a5f", _GREEN
        elif today:
            bg, fg = "#2a2a3e", _YELLOW
        else:
            bg, fg = "#313244", _TEXT
        return (
            f"QPushButton{{background:{bg}; color:{fg}; border:none; border-radius:6px;"
            f"font-size:12px; font-weight:{'bold' if has_data or checked else 'normal'};}}"
            f"QPushButton:hover{{background:#45475a;}}"
            f"QPushButton:checked{{background:{_ACCENT}; color:{_BG}; font-weight:bold;}}"
        )

    def _session_card_style(self, selected: bool) -> str:
        bg = _ACCENT if selected else "#313244"
        fg = _BG if selected else _TEXT
        return (
            f"QPushButton{{background:{bg}; color:{fg}; border:none; border-radius:8px;"
            f"padding:10px 14px; font-size:12px; min-width:140px; text-align:left;}}"
            f"QPushButton:hover{{background:{'#7aa2f7' if selected else '#45475a'};}}"
        )

    # ── public API ────────────────────────────────────────────────────────────
    def refresh(self):
        """Reload data from DB and repaint."""
        days_in_month = calendar.monthrange(
            self._current_month.year, self._current_month.month)[1]
        self._sessions_data = get_sessions_with_counts(days=days_in_month + 5)
        self._paint_calendar()
        if self._selected_date:
            self._show_sessions_for_date(self._selected_date)

    # ── calendar painting ─────────────────────────────────────────────────────
    def _paint_calendar(self):
        m = self._current_month
        self.lbl_month.setText(m.strftime("%B  %Y"))

        # calendar.monthcalendar returns weeks as lists of [Mon..Sun], 0 = no day
        cal_weeks = calendar.monthcalendar(m.year, m.month)
        today_d   = date.today()

        dates_with_data: set[date] = {
            s["session_date"] for s in self._sessions_data if s["count"] > 0
        }
        dates_with_session: set[date] = {
            s["session_date"] for s in self._sessions_data
        }

        self._day_btns.clear()

        for row_idx in range(6):
            for col_idx in range(7):
                b = self.cal_grid.itemAtPosition(row_idx, col_idx).widget()
                b.blockSignals(True)

                if row_idx < len(cal_weeks):
                    day_num = cal_weeks[row_idx][col_idx]
                else:
                    day_num = 0

                if day_num == 0:
                    b.setText("")
                    b.setEnabled(False)
                    b.setChecked(False)
                    b.setStyleSheet("QPushButton{background:transparent; border:none;}")
                else:
                    d = date(m.year, m.month, day_num)
                    has_data  = d in dates_with_data
                    is_today  = d == today_d
                    is_checked = d == self._selected_date
                    b.setText(str(day_num))
                    b.setEnabled(True)
                    b.setChecked(is_checked)
                    b.setStyleSheet(self._day_style(has_data, is_checked, is_today))
                    self._day_btns[d] = b
                    # reconnect (disconnect first to avoid stacking)
                    try:
                        b.clicked.disconnect()
                    except RuntimeError:
                        pass
                    b.clicked.connect(lambda _, dd=d: self._on_day_clicked(dd))

                b.blockSignals(False)

    def _prev_month(self):
        m = self._current_month
        first = date(m.year, m.month, 1) - timedelta(days=1)
        self._current_month = first.replace(day=1)
        self.refresh()

    def _next_month(self):
        m = self._current_month
        last = date(m.year, m.month, calendar.monthrange(m.year, m.month)[1])
        self._current_month = (last + timedelta(days=1)).replace(day=1)
        self.refresh()

    def _on_day_clicked(self, d: date):
        # Uncheck previous
        if self._selected_date and self._selected_date in self._day_btns:
            prev_btn = self._day_btns[self._selected_date]
            prev_btn.setChecked(False)
            dates_with_data = {s["session_date"] for s in self._sessions_data if s["count"] > 0}
            prev_btn.setStyleSheet(self._day_style(
                self._selected_date in dates_with_data, False,
                self._selected_date == date.today()))
        self._selected_date = d
        if d in self._day_btns:
            self._day_btns[d].setChecked(True)
            dates_with_data = {s["session_date"] for s in self._sessions_data if s["count"] > 0}
            self._day_btns[d].setStyleSheet(self._day_style(d in dates_with_data, True, d == date.today()))
        self._show_sessions_for_date(d)

    # ── session cards ─────────────────────────────────────────────────────────
    def _show_sessions_for_date(self, d: date):
        self.lbl_day_title.setText(d.strftime("%A, %d %B %Y"))
        day_sessions = [s for s in self._sessions_data if s["session_date"] == d]

        # clear old cards
        while self.sess_layout.count() > 1:
            item = self.sess_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not day_sessions:
            no_lbl = _label("No sessions recorded for this day", color=_MUTED, size=12)
            self.sess_layout.insertWidget(0, no_lbl)
            self.att_table.setRowCount(0)
            self.lbl_session_title.setText("")
            return

        for i, s in enumerate(day_sessions):
            start = s["start_time"].strftime("%H:%M") if s["start_time"] else "—"
            end   = s["end_time"].strftime("%H:%M")   if s["end_time"]   else "—"
            card  = QPushButton(
                f"Session {s['session_number']}\n"
                f"{start} – {end}\n"
                f"{s['count']} present"
            )
            card.setStyleSheet(self._session_card_style(i == 0))
            card.clicked.connect(
                lambda _, ss=s, cc=card: self._on_session_card(ss, cc))
            self.sess_layout.insertWidget(i, card)

        # auto-select first
        if day_sessions:
            self._load_session_table(day_sessions[0])

    def _on_session_card(self, sess_data: dict, card: QPushButton):
        # reset all cards
        for i in range(self.sess_layout.count() - 1):
            w = self.sess_layout.itemAt(i).widget()
            if w:
                w.setStyleSheet(self._session_card_style(False))
        card.setStyleSheet(self._session_card_style(True))
        self._load_session_table(sess_data)

    def _load_session_table(self, sess_data: dict):
        start = sess_data["start_time"].strftime("%H:%M") if sess_data["start_time"] else "—"
        end   = sess_data["end_time"].strftime("%H:%M")   if sess_data["end_time"]   else "—"
        self.lbl_session_title.setText(
            f"Session {sess_data['session_number']}  ·  {start} – {end}  ·  "
            f"{sess_data['count']} student(s) present")

        rows = get_attendance_for_session_detailed(sess_data["session_pk"])
        self.att_table.setRowCount(len(rows))
        for row_idx, r in enumerate(rows):
            t = r["marked_at"].strftime("%H:%M:%S") if r["marked_at"] else "—"
            conf = f"{r['confidence']:.2f}" if r["confidence"] else "—"
            method_display = r["method"].capitalize()
            items = [r["student_id"], r["name"], r["department"],
                     r["semester"], t, method_display]
            for col, val in enumerate(items):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignCenter)
                self.att_table.setItem(row_idx, col, item)
            # colour-code method
            method_item = self.att_table.item(row_idx, 5)
            if r["method"] == "facial":
                method_item.setForeground(QColor(_GREEN))
            else:
                method_item.setForeground(QColor(_YELLOW))


# ── unknown faces gallery ─────────────────────────────────────────────────────
class UnknownGalleryPage(QWidget):
    THUMB_SIZE = 120

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()

    def _build(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 16, 16, 16)
        v.setSpacing(10)

        hdr = QHBoxLayout()
        hdr.addWidget(_label("Unknown Faces", color=_ACCENT, bold=True, size=16))
        hdr.addStretch()
        self.lbl_count = _label("0 faces", color=_MUTED, size=12)
        hdr.addWidget(self.lbl_count)
        refresh_btn = _btn("↻ Refresh")
        refresh_btn.clicked.connect(self.refresh)
        hdr.addWidget(refresh_btn)
        v.addLayout(hdr)

        v.addWidget(_label(
            "Faces seen by the camera that did not match any enrolled student. "
            "Saved at most once every 30 seconds per continuous sighting.",
            color=_MUTED, size=11))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{border:none; background:transparent;}")
        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout(self.grid_widget)
        self.grid_layout.setSpacing(10)
        self.grid_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        scroll.setWidget(self.grid_widget)
        v.addWidget(scroll, stretch=1)

        self.empty_lbl = _label(
            "No unknown faces captured yet.\n"
            "Unknown faces are saved automatically when a face cannot be recognised.",
            color=_MUTED, size=13)
        self.empty_lbl.setAlignment(Qt.AlignCenter)
        v.addWidget(self.empty_lbl)

    def refresh(self):
        # clear grid
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        unknowns = get_all_unknowns(limit=200)
        self.lbl_count.setText(f"{len(unknowns)} face(s)")
        self.empty_lbl.setVisible(len(unknowns) == 0)

        cols = max(1, 800 // (self.THUMB_SIZE + 12))
        for i, u in enumerate(unknowns):
            card = self._make_card(u)
            self.grid_layout.addWidget(card, i // cols, i % cols)

    def _make_card(self, u) -> QFrame:
        card = QFrame()
        card.setFixedSize(self.THUMB_SIZE + 16, self.THUMB_SIZE + 56)
        card.setStyleSheet(
            f"QFrame{{background:#313244; border-radius:8px;}}"
            f"QFrame:hover{{background:#45475a;}}"
        )
        cv = QVBoxLayout(card)
        cv.setContentsMargins(8, 8, 8, 8)
        cv.setSpacing(4)

        # thumbnail
        thumb_lbl = QLabel()
        thumb_lbl.setFixedSize(self.THUMB_SIZE, self.THUMB_SIZE)
        thumb_lbl.setAlignment(Qt.AlignCenter)
        thumb_lbl.setStyleSheet(f"background:{_SURFACE}; border-radius:4px;")

        pixmap = self._load_thumb(u.image_path)
        if pixmap:
            thumb_lbl.setPixmap(
                pixmap.scaled(self.THUMB_SIZE, self.THUMB_SIZE,
                              Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            thumb_lbl.setText("?")
            thumb_lbl.setStyleSheet(
                f"background:{_SURFACE}; color:{_MUTED}; border-radius:4px; font-size:28px;")
        cv.addWidget(thumb_lbl)

        # time label
        ts = u.last_seen.strftime("%d %b  %H:%M") if u.last_seen else "—"
        tl = _label(ts, color=_MUTED, size=10)
        tl.setAlignment(Qt.AlignCenter)
        cv.addWidget(tl)

        return card

    @staticmethod
    def _load_thumb(path: str | None) -> QPixmap | None:
        if not path:
            return None
        p = Path(path)
        if not p.exists():
            return None
        img = cv2.imread(str(p))
        if img is None:
            return None
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qimg = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
        return QPixmap.fromImage(qimg)


# ── main window ───────────────────────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("attend – Facial Recognition Attendance")
        self.resize(1280, 800)

        init_db()
        self.pipeline = FacePipeline()
        self.attendance_svc = AttendanceService()
        self.camera = Camera()
        self.enrollment_svc = None

        self._build_ui()
        self._connect_signals()
        QTimer.singleShot(300, self._startup)

    # ── build UI ──────────────────────────────────────────────────────────────
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        central.setStyleSheet(f"background:{_BG};")
        root = QHBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # ---- nav sidebar ----
        nav = QFrame()
        nav.setFixedWidth(200)
        nav.setStyleSheet(f"""
            QFrame {{ background:{_BG}; border-radius:10px; }}
            QPushButton {{
                text-align:left; padding:12px 16px; border:none;
                color:{_TEXT}; font-size:14px; border-radius:6px;
            }}
            QPushButton:hover {{ background:#313244; }}
            QPushButton:checked {{ background:{_ACCENT}; color:{_BG}; font-weight:bold; }}
        """)
        nv = QVBoxLayout(nav)
        nv.setContentsMargins(8, 16, 8, 16)
        nv.setSpacing(4)

        title = QLabel("attend")
        title.setStyleSheet(f"color:{_ACCENT}; font-size:20px; font-weight:bold; padding:8px;")
        nv.addWidget(title)

        self.btn_live     = QPushButton("  Live Attendance")
        self.btn_enroll   = QPushButton("  Enrollment")
        self.btn_students = QPushButton("  Students")
        self.btn_manual   = QPushButton("  Manual Mark")
        self.btn_register = QPushButton("  Attendance Register")
        self.btn_unknown  = QPushButton("  Unknown Faces")
        self.btn_settings = QPushButton("  Settings")

        self._nav_btns = [
            self.btn_live, self.btn_enroll, self.btn_students,
            self.btn_manual, self.btn_register, self.btn_unknown, self.btn_settings,
        ]
        for b in self._nav_btns:
            b.setCheckable(True)
            nv.addWidget(b)
        nv.addStretch()
        root.addWidget(nav)

        # ---- content stack ----
        self.stack = QStackedWidget()
        self.stack.setStyleSheet(f"background:{_SURFACE}; border-radius:10px;")
        root.addWidget(self.stack, stretch=1)

        # Page 0 – Live
        self.stack.addWidget(self._build_live_page())
        # Page 1 – Enrollment
        self.stack.addWidget(self._build_enroll_page())
        # Page 2 – Students
        self.stack.addWidget(self._build_students_page())
        # Page 3 – Manual
        self.stack.addWidget(self._build_manual_page())
        # Page 4 – Attendance Register
        self.att_register = AttendanceRegisterPage()
        self.stack.addWidget(self.att_register)
        # Page 5 – Unknown Faces
        self.unknown_gallery = UnknownGalleryPage()
        self.stack.addWidget(self.unknown_gallery)
        # Page 6 – Settings
        self.stack.addWidget(self._build_settings_page())

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.setStyleSheet(f"background:{_BG}; color:{_MUTED};")

        self.btn_live.setChecked(True)
        self.stack.setCurrentIndex(0)

    def _build_live_page(self) -> QWidget:
        page = QWidget()
        lv = QVBoxLayout(page)
        lv.setContentsMargins(12, 12, 12, 12)
        self.camera_widget = CameraWidget()
        lv.addWidget(self.camera_widget, stretch=1)

        info = QHBoxLayout()
        self.lbl_session = _label("Session: —")
        self.lbl_status  = _label("Status: Starting…")
        self.lbl_latency = _label("Latency: —")
        for l in (self.lbl_session, self.lbl_status, self.lbl_latency):
            l.setStyleSheet(f"color:{_TEXT}; font-size:13px; padding:4px 10px;")
            info.addWidget(l)
        info.addStretch()
        lv.addLayout(info)

        self.activity_log = QTextEdit()
        self.activity_log.setReadOnly(True)
        self.activity_log.setMaximumHeight(130)
        self.activity_log.setStyleSheet(
            f"background:{_SURFACE}; color:{_GREEN}; font-family:Consolas; font-size:12px; border-radius:6px;")
        lv.addWidget(self.activity_log)
        return page

    def _build_enroll_page(self) -> QWidget:
        page = QWidget()
        el = QVBoxLayout(page)
        el.setContentsMargins(24, 24, 24, 24)
        el.addWidget(_label("Enrollment", color=_ACCENT, bold=True, size=16))
        form = QFormLayout()
        form.setSpacing(10)
        self.en_student_id = QLineEdit()
        self.en_name       = QLineEdit()
        self.en_reg        = QLineEdit()
        self.en_dept       = QLineEdit()
        self.en_sem        = QLineEdit()
        for w in (self.en_student_id, self.en_name, self.en_reg, self.en_dept, self.en_sem):
            w.setStyleSheet(f"background:#313244; color:{_TEXT}; border:none; border-radius:6px; padding:7px; font-size:13px;")
        form.addRow("Student ID *", self.en_student_id)
        form.addRow("Name *",       self.en_name)
        form.addRow("Registration", self.en_reg)
        form.addRow("Department",   self.en_dept)
        form.addRow("Semester",     self.en_sem)
        el.addLayout(form)
        br = QHBoxLayout()
        self.btn_choose_photo = _btn("Choose Photo…")
        self.btn_enroll_one   = _btn("Enroll Student", accent=True)
        self.btn_bulk         = _btn("Bulk Enroll from Folder…")
        br.addWidget(self.btn_choose_photo)
        br.addWidget(self.btn_enroll_one)
        br.addWidget(self.btn_bulk)
        el.addLayout(br)
        self.enroll_log = QTextEdit()
        self.enroll_log.setReadOnly(True)
        self.enroll_log.setStyleSheet(
            f"background:{_SURFACE}; color:{_TEXT}; font-size:12px; border-radius:6px;")
        el.addWidget(self.enroll_log)
        self._enroll_photo_path = None
        return page

    def _build_students_page(self) -> QWidget:
        page = QWidget()
        sl = QVBoxLayout(page)
        sl.setContentsMargins(16, 16, 16, 16)
        sl.addWidget(_label("Students", color=_ACCENT, bold=True, size=16))
        self.students_table = QTableWidget(0, 5)
        self.students_table.setHorizontalHeaderLabels(
            ["Student ID", "Name", "Department", "Semester", "Enrolled"])
        self.students_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.students_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.students_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.students_table.setStyleSheet(
            f"QTableWidget{{background:{_SURFACE}; color:{_TEXT}; gridline-color:#313244; border-radius:6px; font-size:13px;}}"
            f"QHeaderView::section{{background:#313244; color:{_ACCENT}; padding:6px; border:none;}}"
            f"QTableWidget::item:selected{{background:#313244;}}"
        )
        sl.addWidget(self.students_table, stretch=1)
        rb = _btn("↻ Refresh")
        rb.clicked.connect(self._load_students)
        sl.addWidget(rb)
        return page

    def _build_manual_page(self) -> QWidget:
        page = QWidget()
        ml = QVBoxLayout(page)
        ml.setContentsMargins(24, 24, 24, 24)
        ml.addWidget(_label("Manual Attendance Mark", color=_ACCENT, bold=True, size=16))
        mf = QFormLayout()
        mf.setSpacing(10)
        self.man_student_id = QLineEdit()
        self.man_reason     = QLineEdit("Manual override by admin")
        for w in (self.man_student_id, self.man_reason):
            w.setStyleSheet(f"background:#313244; color:{_TEXT}; border:none; border-radius:6px; padding:7px; font-size:13px;")
        mf.addRow("Student ID", self.man_student_id)
        mf.addRow("Reason",     self.man_reason)
        ml.addLayout(mf)
        self.btn_manual_mark = _btn("Mark Attendance", accent=True)
        ml.addWidget(self.btn_manual_mark)
        self.manual_log = QTextEdit()
        self.manual_log.setReadOnly(True)
        self.manual_log.setStyleSheet(
            f"background:{_SURFACE}; color:{_TEXT}; font-size:12px; border-radius:6px;")
        ml.addWidget(self.manual_log)
        return page

    def _build_settings_page(self) -> QWidget:
        page = QWidget()
        sv = QVBoxLayout(page)
        sv.setContentsMargins(24, 24, 24, 24)
        sv.addWidget(_label("Settings", color=_ACCENT, bold=True, size=16))
        st = QFormLayout()
        st.setSpacing(10)
        self.cfg_match_th = QSpinBox()
        self.cfg_match_th.setRange(20, 80)
        self.cfg_match_th.setValue(int(config.recognition.match_threshold * 100))
        self.cfg_match_th.setStyleSheet(f"background:#313244; color:{_TEXT}; border:none; border-radius:6px; padding:6px;")
        self.cfg_s1_start = QLineEdit(config.sessions.session1_start)
        self.cfg_s1_end   = QLineEdit(config.sessions.session1_end)
        self.cfg_s2_start = QLineEdit(config.sessions.session2_start)
        self.cfg_s2_end   = QLineEdit(config.sessions.session2_end)
        for w in (self.cfg_s1_start, self.cfg_s1_end, self.cfg_s2_start, self.cfg_s2_end):
            w.setStyleSheet(f"background:#313244; color:{_TEXT}; border:none; border-radius:6px; padding:7px; font-size:13px;")
        st.addRow("Match threshold (×100)", self.cfg_match_th)
        st.addRow("Session 1 start (HH:MM)", self.cfg_s1_start)
        st.addRow("Session 1 end",           self.cfg_s1_end)
        st.addRow("Session 2 start",         self.cfg_s2_start)
        st.addRow("Session 2 end",           self.cfg_s2_end)
        sv.addLayout(st)
        save_btn = _btn("Save Settings", accent=True)
        save_btn.clicked.connect(self._save_settings)
        sv.addWidget(save_btn)
        sv.addStretch()
        return page

    # ── signals ───────────────────────────────────────────────────────────────
    def _connect_signals(self):
        self.btn_live.clicked.connect(lambda: self._nav(0))
        self.btn_enroll.clicked.connect(lambda: self._nav(1))
        self.btn_students.clicked.connect(lambda: self._nav(2))
        self.btn_manual.clicked.connect(lambda: self._nav(3))
        self.btn_register.clicked.connect(lambda: self._nav(4))
        self.btn_unknown.clicked.connect(lambda: self._nav(5))
        self.btn_settings.clicked.connect(lambda: self._nav(6))

        self.btn_choose_photo.clicked.connect(self._choose_photo)
        self.btn_enroll_one.clicked.connect(self._enroll_one)
        self.btn_bulk.clicked.connect(self._bulk_enroll)
        self.btn_manual_mark.clicked.connect(self._manual_mark)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._on_frame)
        self.timer.setInterval(66)

        self._latest_result: RecognitionResult | None = None
        self._frame_lock = threading.Lock()
        self._pipeline_busy = False

    def _nav(self, idx: int):
        for i, b in enumerate(self._nav_btns):
            b.setChecked(i == idx)
        self.stack.setCurrentIndex(idx)

        if idx == 0:
            if self.camera.is_healthy() and not self.timer.isActive():
                self.timer.start()
                self.lbl_status.setText("Status: Live tracking active")
                self.lbl_status.setStyleSheet(f"color:{_GREEN};")
        else:
            if self.timer.isActive():
                self.timer.stop()

        if idx == 2:
            self._load_students()
        elif idx == 4:
            self.att_register.refresh()
        elif idx == 5:
            self.unknown_gallery.refresh()

    # ── startup ───────────────────────────────────────────────────────────────
    def _startup(self):
        self.status_bar.showMessage("Initializing face recognition models…")
        try:
            ra = cleanup_old_attendance(retention_days=30)
            ru = cleanup_expired_unknowns()
            if ra or ru:
                logger.info("Cleanup: %d attendance, %d unknowns removed", ra, ru)
        except Exception:
            logger.exception("Startup cleanup failed")

        ok = self.pipeline.initialize()
        if not ok:
            QMessageBox.critical(self, "Model Error",
                "Failed to load InsightFace models.\n"
                "Make sure insightface and onnxruntime are installed.")
            self.status_bar.showMessage("Model load failed")
            return

        self.enrollment_svc = EnrollmentService(self.pipeline.recognizer)
        self.pipeline.on_result  = self._on_recognition_result
        self.pipeline.on_unknown = self.attendance_svc.handle_unknown

        if not self.camera.open():
            QMessageBox.warning(self, "Camera",
                "Could not open webcam. Check camera index in settings.")
            self.status_bar.showMessage("Camera unavailable")
        else:
            if self.stack.currentIndex() == 0:
                self.timer.start()
            self.status_bar.showMessage("Ready – camera running")

        self._update_session_label()

    # ── frame loop ────────────────────────────────────────────────────────────
    def _update_session_label(self):
        sess = self.attendance_svc.get_active_session()
        if sess:
            self.lbl_session.setText(f"Session: {sess.session_code} (ACTIVE)")
            self.lbl_session.setStyleSheet(f"color:{_GREEN}; font-weight:bold; font-size:13px; padding:4px 10px;")
        else:
            self.lbl_session.setText("Session: None active")
            self.lbl_session.setStyleSheet(f"color:{_RED}; font-size:13px; padding:4px 10px;")

    def _on_frame(self):
        ok, frame = self.camera.read()
        if not ok or frame is None:
            return
        with self._frame_lock:
            result = self._latest_result
        self.camera_widget.update_frame(frame, result)
        if result and result.latency_ms > 0:
            self.lbl_latency.setText(f"Latency: {result.latency_ms:.0f} ms")
        if not self._pipeline_busy:
            self._pipeline_busy = True
            threading.Thread(
                target=self._process_frame_bg, args=(frame.copy(),), daemon=True
            ).start()

    def _process_frame_bg(self, frame: np.ndarray):
        try:
            result = self.pipeline.process_frame(frame)
            with self._frame_lock:
                self._latest_result = result
            if result.status == "candidate" and result.student_pk is not None:
                self.pipeline.mark_track_as_attended(result.track_id)
                QTimer.singleShot(0, lambda r=result: self._handle_candidate(r))
        except Exception:
            logger.exception("Pipeline error in background thread")
        finally:
            self._pipeline_busy = False

    def _handle_candidate(self, result: RecognitionResult):
        success, msg = self.attendance_svc.try_mark_facial(
            result.student_pk, result.student_id, result.confidence, result.track_id)
        if success:
            self._log_activity(f"✓ {result.student_id} – {msg} ({result.confidence:.2f})")
            self.lbl_status.setText(f"Status: {msg}")
            self.lbl_status.setStyleSheet(f"color:{_GREEN}; font-weight:bold; font-size:13px; padding:4px 10px;")
        else:
            self._log_activity(f"• {result.student_id} – {msg}")
            self.lbl_status.setText(f"Status: {msg}")
            self.lbl_status.setStyleSheet(f"color:{_ACCENT}; font-size:13px; padding:4px 10px;")
        self._update_session_label()

    def _on_recognition_result(self, result: RecognitionResult):
        pass

    def _log_activity(self, text: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.activity_log.append(f"[{ts}] {text}")

    # ── enrollment ────────────────────────────────────────────────────────────
    def _choose_photo(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select student photo", "", "Images (*.jpg *.jpeg *.png *.bmp)")
        if path:
            self._enroll_photo_path = path
            self.enroll_log.append(f"Selected: {path}")

    def _enroll_one(self):
        if not self.enrollment_svc:
            self.enroll_log.append("Recognizer not ready"); return
        sid  = self.en_student_id.text().strip()
        name = self.en_name.text().strip()
        if not sid or not name or not self._enroll_photo_path:
            self.enroll_log.append("Student ID, Name and Photo are required"); return
        ok, msg = self.enrollment_svc.enroll_from_image(
            self._enroll_photo_path, sid, name,
            registration_no=self.en_reg.text().strip() or None,
            department=self.en_dept.text().strip() or None,
            semester=self.en_sem.text().strip() or None,
        )
        self.enroll_log.append(msg)
        if ok:
            n = self.pipeline.rebuild_index()
            self.enroll_log.append(f"FAISS index rebuilt ({n} students)")

    def _bulk_enroll(self):
        folder = QFileDialog.getExistingDirectory(self, "Select folder with student photos")
        if not folder or not self.enrollment_svc:
            return
        for fname, ok, msg in self.enrollment_svc.bulk_enroll_from_folder(folder):
            self.enroll_log.append(f"{fname}: {msg}")
        n = self.pipeline.rebuild_index()
        self.enroll_log.append(f"Done. Index size: {n}")

    # ── students ──────────────────────────────────────────────────────────────
    def _load_students(self):
        students = get_all_students()
        self.students_table.setRowCount(len(students))
        for row, s in enumerate(students):
            enrolled = s.enrolled_at.strftime("%Y-%m-%d") if s.enrolled_at else ""
            for col, val in enumerate([
                s.student_id, s.name, s.department or "",
                s.semester or "", enrolled
            ]):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignCenter)
                self.students_table.setItem(row, col, item)

    # ── manual ────────────────────────────────────────────────────────────────
    def _manual_mark(self):
        sid    = self.man_student_id.text().strip()
        reason = self.man_reason.text().strip() or "Manual override"
        if not sid:
            return
        ok, msg = self.attendance_svc.mark_manual(sid, reason=reason)
        self.manual_log.append(msg)
        self._log_activity(f"MANUAL: {sid} – {msg}")

    # ── settings ──────────────────────────────────────────────────────────────
    def _save_settings(self):
        config.recognition.match_threshold = self.cfg_match_th.value() / 100.0
        config.sessions.session1_start = self.cfg_s1_start.text().strip()
        config.sessions.session1_end   = self.cfg_s1_end.text().strip()
        config.sessions.session2_start = self.cfg_s2_start.text().strip()
        config.sessions.session2_end   = self.cfg_s2_end.text().strip()
        save_config(config)
        QMessageBox.information(self, "Settings", "Settings saved.")
        self._update_session_label()

    # ── close ─────────────────────────────────────────────────────────────────
    def closeEvent(self, event):
        self.timer.stop()
        self.camera.release()
        log_action("application_closed")
        super().closeEvent(event)
