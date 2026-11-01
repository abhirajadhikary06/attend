"""
Functional pages (QSS styled): live scanner, enrollment, students, manual mark,
attendance register, unknown faces and settings. Pages expose widgets and
data-loading helpers only; MainWindow owns the behaviour and threading.
"""

from __future__ import annotations

import calendar
import logging
from datetime import date, timedelta
from pathlib import Path

import cv2
from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QFormLayout, QFrame, QGridLayout, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea, QSpinBox,
    QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)

from app.core.config import config
from app.core.time_utils import today_ist, to_ist
from app.core.database import (
    delete_unknown, get_all_unknowns, get_attendance_for_session_detailed,
    get_sessions_with_counts, log_action,
)
from app.ui.icons import icon
from app.ui.theme import AMBER, GREEN, TEXT_DIM
from app.ui.widgets import (
    Card, CameraView, PageHeader, kv_row, make_button, make_label, repolish, set_tone,
)

logger = logging.getLogger(__name__)


def _page_layout(page: QWidget, margins=(32, 28, 32, 28), spacing=18) -> QVBoxLayout:
    v = QVBoxLayout(page)
    v.setContentsMargins(*margins)
    v.setSpacing(spacing)
    return v


def _make_table(headers: list[str]) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    t.horizontalHeader().setHighlightSections(False)
    t.verticalHeader().setVisible(False)
    t.setShowGrid(False)
    t.setAlternatingRowColors(True)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.setFocusPolicy(Qt.NoFocus)
    return t


def _cell(text: str) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setTextAlignment(Qt.AlignCenter)
    return item


# ------------------------------------------------------------------------------
class LivePage(QWidget):
    def __init__(self):
        super().__init__()
        v = _page_layout(self)
        v.addWidget(PageHeader("Live Scanner", "Center one face in the guide. Matching runs locally on this device."))

        row = QHBoxLayout()
        row.setSpacing(18)
        self.camera_view = CameraView()
        row.addWidget(self.camera_view, 1)

        side = QVBoxLayout()
        side.setSpacing(14)
        info = Card()
        info.setFixedWidth(300)
        info.body.addWidget(make_label("Status", "h2"))
        self.lbl_session = make_label("None active")
        self.lbl_status = make_label("Starting")
        self.lbl_latency = make_label("-")
        info.body.addWidget(kv_row("Session", self.lbl_session))
        info.body.addWidget(kv_row("State", self.lbl_status))
        info.body.addWidget(kv_row("Latency", self.lbl_latency))
        side.addWidget(info)

        log_card = Card()
        log_card.setFixedWidth(300)
        log_card.body.addWidget(make_label("Activity", "h2"))
        self.activity_log = QTextEdit()
        self.activity_log.setObjectName("Log")
        self.activity_log.setReadOnly(True)
        log_card.body.addWidget(self.activity_log, 1)
        side.addWidget(log_card, 1)
        row.addLayout(side)
        v.addLayout(row, 1)

    def set_session(self, code: str | None):
        if code:
            self.lbl_session.setText(code)
            set_tone(self.lbl_session, "good")
        else:
            self.lbl_session.setText("None active")
            set_tone(self.lbl_session, "bad")

    def set_status(self, text: str, tone: str | None = None):
        self.lbl_status.setText(text)
        set_tone(self.lbl_status, tone)


# ------------------------------------------------------------------------------
class EnrollPage(QWidget):
    def __init__(self):
        super().__init__()
        v = _page_layout(self)
        v.addWidget(PageHeader("Enrollment", "Add students from a single photo or a folder of photos."))

        row = QHBoxLayout()
        row.setSpacing(18)

        form_card = Card()
        form_card.setFixedWidth(460)
        form_card.body.addWidget(make_label("Student profile", "h2"))
        form_card.body.addWidget(make_label("Use a clear, front-facing photo for the best match quality.", "muted"))
        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignLeft)
        self.en_student_id = QLineEdit()
        self.en_name = QLineEdit()
        self.en_reg = QLineEdit()
        self.en_dept = QLineEdit()
        self.en_sem = QLineEdit()
        self.en_student_id.setPlaceholderText("Required")
        self.en_name.setPlaceholderText("Required")
        form.addRow(make_label("Student ID", "dim"), self.en_student_id)
        form.addRow(make_label("Name", "dim"), self.en_name)
        form.addRow(make_label("Registration", "dim"), self.en_reg)
        form.addRow(make_label("Department", "dim"), self.en_dept)
        form.addRow(make_label("Semester", "dim"), self.en_sem)
        form_card.body.addLayout(form)

        self.photo_preview = QLabel("No photo selected")
        self.photo_preview.setObjectName("PhotoPreview")
        self.photo_preview.setAlignment(Qt.AlignCenter)
        self.photo_preview.setFixedHeight(150)
        form_card.body.addWidget(self.photo_preview)

        buttons = QHBoxLayout()
        self.btn_choose_photo = make_button("Choose photo", icon_name="image")
        self.btn_enroll_one = make_button("Enroll student", "primary", "user-plus")
        buttons.addWidget(self.btn_choose_photo)
        buttons.addWidget(self.btn_enroll_one, 1)
        form_card.body.addLayout(buttons)
        self.btn_bulk = make_button("Bulk enroll from folder", icon_name="folder-open")
        form_card.body.addWidget(self.btn_bulk)
        form_card.body.addStretch()
        row.addWidget(form_card)

        log_card = Card()
        log_card.body.addWidget(make_label("Enrollment activity", "h2"))
        self.enroll_log = QTextEdit()
        self.enroll_log.setObjectName("Log")
        self.enroll_log.setReadOnly(True)
        self.enroll_log.setPlaceholderText("Choose a photo or folder to begin. Results and index updates will appear here.")
        log_card.body.addWidget(self.enroll_log, 1)
        row.addWidget(log_card, 1)
        v.addLayout(row, 1)

    def set_photo(self, path: str):
        pm = QPixmap(path)
        if pm.isNull():
            self.photo_preview.setText("Preview unavailable")
            return
        self.photo_preview.setPixmap(pm.scaled(QSize(300, 140), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def set_busy(self, busy: bool):
        for b in (self.btn_choose_photo, self.btn_enroll_one, self.btn_bulk):
            b.setEnabled(not busy)


# ------------------------------------------------------------------------------
class StudentsPage(QWidget):
    def __init__(self):
        super().__init__()
        v = _page_layout(self)
        header = PageHeader("Students", "Everyone enrolled in the recognition index.")
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search ID, name, or department")
        self.lbl_count = make_label("0 students", "muted")
        self.search.setFixedWidth(280)
        self.search.textChanged.connect(self._filter)
        self.btn_refresh = make_button("Refresh", icon_name="refresh-cw")
        header.actions.addWidget(self.lbl_count)
        header.actions.addWidget(self.search)
        header.actions.addWidget(self.btn_refresh)
        v.addWidget(header)
        self.table = _make_table(["Student ID", "Name", "Department", "Semester", "Enrolled"])
        v.addWidget(self.table, 1)

    def load(self, students):
        self.lbl_count.setText(f"{len(students)} students")
        self.table.setRowCount(len(students))
        for row, s in enumerate(students):
            enrolled = s.enrolled_at.strftime("%Y-%m-%d") if s.enrolled_at else ""
            for col, val in enumerate([s.student_id, s.name, s.department or "", s.semester or "", enrolled]):
                self.table.setItem(row, col, _cell(val))
        self._filter(self.search.text())

    def _filter(self, text: str):
        needle = text.strip().lower()
        for r in range(self.table.rowCount()):
            hay = " ".join((self.table.item(r, c).text() if self.table.item(r, c) else "") for c in range(3)).lower()
            self.table.setRowHidden(r, bool(needle) and needle not in hay)


# ------------------------------------------------------------------------------
class ManualPage(QWidget):
    def __init__(self):
        super().__init__()
        v = _page_layout(self)
        v.addWidget(PageHeader("Manual Mark", "Record attendance when the camera cannot."))

        card = Card()
        card.setFixedWidth(520)
        card.body.addWidget(make_label('Manual attendance', 'h2'))
        card.body.addWidget(make_label('Use this option when a student cannot be marked by face recognition. Add a clear reason for the audit trail.', 'muted'))
        form = QFormLayout()
        form.setSpacing(12)
        self.man_student_id = QLineEdit()
        self.man_student_id.setPlaceholderText("Student ID")
        self.man_reason = QLineEdit("Manual override by admin")
        form.addRow(make_label("Student ID", "dim"), self.man_student_id)
        form.addRow(make_label("Reason", "dim"), self.man_reason)
        card.body.addLayout(form)
        self.btn_manual_mark = make_button("Mark attendance", "primary", "clipboard-check")
        card.body.addWidget(self.btn_manual_mark)
        v.addWidget(card)

        log_card = Card()
        log_card.body.addWidget(make_label("Result", "h2"))
        self.manual_log = QTextEdit()
        self.manual_log.setObjectName("Log")
        self.manual_log.setReadOnly(True)
        self.manual_log.setPlaceholderText("Manual attendance results will appear here.")
        log_card.body.addWidget(self.manual_log, 1)
        v.addWidget(log_card, 1)


# ------------------------------------------------------------------------------
class SettingsPage(QWidget):
    def __init__(self):
        super().__init__()
        v = _page_layout(self)
        v.addWidget(PageHeader("Settings", "Adjust recognition behavior and daily attendance windows."))

        card = Card()
        card.setFixedWidth(580)
        card.body.addWidget(make_label("Recognition sensitivity", "h2"))
        card.body.addWidget(make_label("Higher match thresholds are stricter and may require a clearer face image.", "muted"))
        recognition_form = QFormLayout()
        recognition_form.setSpacing(12)
        self.cfg_match_th = QSpinBox()
        self.cfg_match_th.setRange(20, 80)
        self.cfg_match_th.setValue(int(config.recognition.match_threshold * 100))
        recognition_form.addRow(make_label("Match threshold (x100)", "dim"), self.cfg_match_th)
        card.body.addLayout(recognition_form)

        card.body.addWidget(make_label("Attendance schedule", "h2"))
        card.body.addWidget(make_label("Session hours are evaluated in India Standard Time (IST).", "muted"))
        schedule_form = QFormLayout()
        schedule_form.setSpacing(12)
        self.cfg_s1_start = QLineEdit(config.sessions.session1_start)
        self.cfg_s1_end = QLineEdit(config.sessions.session1_end)
        self.cfg_s2_start = QLineEdit(config.sessions.session2_start)
        self.cfg_s2_end = QLineEdit(config.sessions.session2_end)
        schedule_form.addRow(make_label("Session 1 start (HH:MM)", "dim"), self.cfg_s1_start)
        schedule_form.addRow(make_label("Session 1 end", "dim"), self.cfg_s1_end)
        schedule_form.addRow(make_label("Session 2 start", "dim"), self.cfg_s2_start)
        schedule_form.addRow(make_label("Session 2 end", "dim"), self.cfg_s2_end)
        card.body.addLayout(schedule_form)

        self.btn_save = make_button("Save settings", "primary", "save")
        card.body.addWidget(self.btn_save)
        v.addWidget(card)
        v.addStretch()
# ------------------------------------------------------------------------------
class RegisterPage(QWidget):
    """Month calendar on the left; sessions for the chosen day and their students on the right."""

    def __init__(self):
        super().__init__()
        self._current_month = today_ist().replace(day=1)
        self._selected: date | None = None
        self._sessions: list[dict] = []
        self._cell_dates: dict[tuple[int, int], date | None] = {}
        self._cells: dict[tuple[int, int], QPushButton] = {}
        self._card_group: QButtonGroup | None = None
        self._build()

    def _build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 28)
        root.setSpacing(18)

        left = Card()
        left.setFixedWidth(404)
        hdr = QHBoxLayout()
        self.btn_prev = make_button("", "ghost", "chevron-left")
        self.btn_next = make_button("", "ghost", "chevron-right")
        self.lbl_month = make_label("", "h2")
        self.lbl_month.setAlignment(Qt.AlignCenter)
        hdr.addWidget(self.btn_prev)
        hdr.addWidget(self.lbl_month, 1)
        hdr.addWidget(self.btn_next)
        left.body.addLayout(hdr)

        grid = QGridLayout()
        grid.setSpacing(6)
        for c, d in enumerate(("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")):
            lbl = make_label(d, "muted")
            lbl.setAlignment(Qt.AlignCenter)
            grid.addWidget(lbl, 0, c)
        for r in range(6):
            for c in range(7):
                b = QPushButton()
                b.setProperty("day", True)
                b.setFixedSize(46, 46)
                b.setCheckable(True)
                b.setCursor(Qt.PointingHandCursor)
                b.clicked.connect(lambda _=False, rc=(r, c): self._on_cell(rc))
                grid.addWidget(b, r + 1, c)
                self._cells[(r, c)] = b
        left.body.addLayout(grid)
        left.body.addStretch()
        root.addWidget(left)

        right = QVBoxLayout()
        right.setSpacing(12)
        head = QHBoxLayout()
        self.lbl_day_title = make_label("Select a day", "h1")
        self.btn_refresh = make_button("Refresh", icon_name="refresh-cw")
        self.btn_refresh.clicked.connect(self.refresh)
        head.addWidget(self.lbl_day_title, 1)
        head.addWidget(self.btn_refresh)
        right.addLayout(head)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedHeight(104)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.sess_container = QWidget()
        self.sess_layout = QHBoxLayout(self.sess_container)
        self.sess_layout.setContentsMargins(0, 0, 0, 0)
        self.sess_layout.setSpacing(10)
        self.sess_layout.addStretch()
        scroll.setWidget(self.sess_container)
        right.addWidget(scroll)

        self.lbl_session_title = make_label("", "muted")
        right.addWidget(self.lbl_session_title)
        self.att_table = _make_table(["Student ID", "Name", "Department", "Semester", "Time", "Method"])
        right.addWidget(self.att_table, 1)
        root.addLayout(right, 1)

        self.btn_prev.clicked.connect(self._prev_month)
        self.btn_next.clicked.connect(self._next_month)

    # -- data -------------------------------------------------------------------
    def refresh(self):
        today = today_ist()
        fetch_days = max((today - self._current_month).days + 1, 31)
        try:
            self._sessions = get_sessions_with_counts(days=fetch_days)
        except Exception:
            logger.exception("Could not load sessions")
            self._sessions = []
        if self._selected is None:
            self._selected = today
        self._paint_calendar()
        self._show_sessions(self._selected)

    def _paint_calendar(self):
        m = self._current_month
        self.lbl_month.setText(m.strftime("%B %Y"))
        weeks = calendar.monthcalendar(m.year, m.month)
        today = today_ist()
        with_data = {s["session_date"] for s in self._sessions if s["count"] > 0}
        for (r, c), b in self._cells.items():
            day = weeks[r][c] if r < len(weeks) else 0
            b.blockSignals(True)
            if day == 0:
                self._cell_dates[(r, c)] = None
                b.setText("")
                b.setEnabled(False)
                b.setChecked(False)
            else:
                d = date(m.year, m.month, day)
                self._cell_dates[(r, c)] = d
                b.setText(str(day))
                b.setEnabled(True)
                b.setChecked(d == self._selected)
                b.setProperty("hasData", d in with_data)
                b.setProperty("today", d == today)
            repolish(b)
            b.blockSignals(False)

    def _on_cell(self, rc):
        d = self._cell_dates.get(rc)
        if d is None:
            return
        self._selected = d
        self._paint_calendar()
        self._show_sessions(d)

    def _prev_month(self):
        first = self._current_month - timedelta(days=1)
        self._current_month = first.replace(day=1)
        self._selected = self._default_selection()
        self.refresh()

    def _next_month(self):
        last = date(self._current_month.year, self._current_month.month,
                    calendar.monthrange(self._current_month.year, self._current_month.month)[1])
        self._current_month = (last + timedelta(days=1)).replace(day=1)
        self._selected = self._default_selection()
        self.refresh()

    def _default_selection(self) -> date:
        t = today_ist()
        m = self._current_month
        return t if (t.year, t.month) == (m.year, m.month) else m

    # -- sessions ---------------------------------------------------------------
    def _show_sessions(self, d: date):
        self.lbl_day_title.setText(d.strftime("%A, %d %B %Y"))
        day_sessions = [s for s in self._sessions if s["session_date"] == d]

        while self.sess_layout.count() > 1:
            item = self.sess_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
                item.widget().deleteLater()

        if not day_sessions:
            self.sess_layout.insertWidget(0, make_label("No sessions were recorded on this day.", "muted"))
            self.att_table.setRowCount(0)
            self.lbl_session_title.setText("")
            return

        self._card_group = QButtonGroup(self)
        self._card_group.setExclusive(True)
        for i, s in enumerate(day_sessions):
            start = s["start_time"].strftime("%H:%M") if s["start_time"] else "-"
            end = s["end_time"].strftime("%H:%M") if s["end_time"] else "-"
            card = QPushButton(f"Session {s['session_number']}\n{start} to {end}\n{s['count']} present")
            card.setProperty("sessionCard", True)
            card.setCheckable(True)
            card.setCursor(Qt.PointingHandCursor)
            card.setChecked(i == 0)
            card.clicked.connect(lambda _=False, ss=s: self._load_session_table(ss))
            self._card_group.addButton(card)
            self.sess_layout.insertWidget(i, card)
        self._load_session_table(day_sessions[0])

    def _load_session_table(self, s: dict):
        try:
            rows = get_attendance_for_session_detailed(s["session_pk"])
        except Exception:
            logger.exception("Could not load attendance rows")
            rows = []
        start = s["start_time"].strftime("%H:%M") if s["start_time"] else "-"
        end = s["end_time"].strftime("%H:%M") if s["end_time"] else "-"
        self.lbl_session_title.setText(
            f"Session {s['session_number']}, {start} to {end}, {len(rows)} student(s) present")
        self.att_table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            t = to_ist(r["marked_at"]).strftime("%H:%M:%S") if r["marked_at"] else "-"
            vals = [r["student_id"], r["name"], r["department"], r["semester"], t, r["method"].capitalize()]
            for col, val in enumerate(vals):
                self.att_table.setItem(i, col, _cell(str(val) if val is not None else ""))
            self.att_table.item(i, 5).setForeground(QColor(GREEN if r["method"] == "facial" else AMBER))


# ------------------------------------------------------------------------------
class UnknownPage(QWidget):
    THUMB = 120

    def __init__(self):
        super().__init__()
        self._cols = 0
        v = _page_layout(self)
        header = PageHeader("Unknown Faces",
                            "Faces that matched no enrolled student, saved at most once every 30 seconds per sighting.")
        self.lbl_count = make_label("0 faces", "muted")
        self.btn_refresh = make_button("Refresh", icon_name="refresh-cw")
        self.btn_refresh.clicked.connect(self.refresh)
        header.actions.addWidget(self.lbl_count)
        header.actions.addWidget(self.btn_refresh)
        v.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.grid_widget = QWidget()
        self.grid = QGridLayout(self.grid_widget)
        self.grid.setSpacing(12)
        self.grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        scroll.setWidget(self.grid_widget)
        v.addWidget(scroll, 1)

        self.empty_lbl = make_label("No unknown faces yet.\nUnmatched people seen by the camera will appear here for review.", "dim")
        self.empty_lbl.setObjectName("EmptyState")
        self.empty_lbl.setWordWrap(True)
        self.empty_lbl.setAlignment(Qt.AlignCenter)
        self.empty_lbl.setMinimumHeight(180)
        v.addWidget(self.empty_lbl)

    def _column_count(self) -> int:
        return max(1, (max(self.width(), 700) - 64) // (self.THUMB + 36))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self._cols and self._column_count() != self._cols:
            QTimer.singleShot(0, self.refresh)

    def refresh(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        try:
            unknowns = get_all_unknowns(limit=200)
        except Exception:
            logger.exception("Could not load unknown faces")
            unknowns = []
        self.lbl_count.setText(f"{len(unknowns)} face(s)")
        self.empty_lbl.setVisible(not unknowns)
        self._cols = self._column_count()
        for i, u in enumerate(unknowns):
            self.grid.addWidget(self._make_card(u), i // self._cols, i % self._cols)

    def _make_card(self, u) -> QFrame:
        card = QFrame()
        card.setObjectName("UnknownCard")
        card.setFixedSize(self.THUMB + 24, self.THUMB + 84)
        v = QVBoxLayout(card)
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(6)

        thumb = QLabel()
        thumb.setObjectName("Thumb")
        thumb.setFixedSize(self.THUMB, self.THUMB)
        thumb.setAlignment(Qt.AlignCenter)
        pm = self._load_thumb(u.image_path)
        if pm:
            thumb.setPixmap(pm.scaled(self.THUMB, self.THUMB, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            thumb.setText("No image")
        v.addWidget(thumb)

        ts = u.last_seen.strftime("%d %b, %H:%M") if u.last_seen else "-"
        stamp = make_label(ts, "muted")
        stamp.setAlignment(Qt.AlignCenter)
        v.addWidget(stamp)

        btn = make_button("Delete", "danger", "trash-2")
        btn.setFixedHeight(28)
        btn.clicked.connect(lambda _=False, pk=u.id: self._delete(pk))
        v.addWidget(btn)
        return card

    def _delete(self, pk: int):
        reply = QMessageBox.question(
            self, "Delete unknown face", "Remove this record and its image?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        image_path = delete_unknown(pk)
        if image_path:
            try:
                Path(image_path).unlink(missing_ok=True)
            except Exception as exc:
                logger.warning("Could not delete image file %s: %s", image_path, exc)
        log_action("unknown_face_deleted", details=f"pk={pk}")
        self.refresh()

    @staticmethod
    def _load_thumb(path: str | None) -> QPixmap | None:
        if not path or not Path(path).exists():
            return None
        img = cv2.imread(str(path))
        if img is None:
            return None
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        return QPixmap.fromImage(QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888).copy())
