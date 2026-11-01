"""
Main window: frameless shell, sidebar navigation, QML dashboard and worker wiring.

Threading model
  - CameraThread     : capture loop (open, read, release)
  - InferenceWorker  : detection, embedding and FAISS search in its own QThread
  - InitThread       : model loading at startup
  - QThreadPool      : enrollment, bulk import and index rebuilds
  The GUI thread only paints frames, applies results and performs the short
  attendance write, exactly as the original implementation did.
"""

from __future__ import annotations

import logging

import cv2
import numpy as np
from datetime import datetime

from PySide6.QtCore import QSize, Qt, QThread, QThreadPool, QTimer, Signal, Slot
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton,
    QStackedWidget, QVBoxLayout,
)

from app.core.config import config, save_config, LOG_DIR
from app.core.time_utils import now_ist
from app.core.database import (
    cleanup_expired_unknowns, cleanup_old_attendance, get_all_students, init_db, log_action,
)
from app.services.attendance_service import AttendanceService
from app.services.enrollment import EnrollmentService
from app.ui.dashboard import DashboardBridge, DashboardView
from app.ui.frameless import FramelessWindow
from app.ui.icons import icon, icon_pixmap
from app.ui.pages import (
    EnrollPage, LivePage, ManualPage, RegisterPage, SettingsPage, StudentsPage, UnknownPage,
)
from app.ui.theme import ACCENT_HOVER, GREEN, RED, TEXT, TEXT_DIM
from app.ui.widgets import make_label, set_tone
from app.ui.workers import CameraThread, InferenceWorker, InitThread, Task
from app.utils.camera import Camera
from app.vision.pipeline import FacePipeline, RecognitionResult

logger = logging.getLogger(__name__)

NAV_ITEMS = [
    ("dashboard", "Dashboard", "layout-dashboard"),
    ("live", "Live Scanner", "scan-face"),
    ("enroll", "Enrollment", "user-plus"),
    ("students", "Students", "users"),
    ("manual", "Manual Mark", "clipboard-check"),
    ("register", "Attendance Register", "calendar"),
    ("unknown", "Unknown Faces", "user-x"),
]


class MainWindow(FramelessWindow):
    _infer_request = Signal(object)

    def __init__(self):
        super().__init__("attend")
        self.resize(1360, 860)
        self.setMinimumSize(1100, 700)

        init_db()
        self.pipeline = FacePipeline()
        self.attendance_svc = AttendanceService()
        self.camera = Camera()
        self.enrollment_svc: EnrollmentService | None = None
        self.bridge = DashboardBridge(self)

        self._latest_result: RecognitionResult | None = None
        self._busy = False
        self._models_ready = False
        self._circle_mask = None
        self._scan_active = False
        self._last_session_code: str | None = None
        self._enroll_photo_path: str | None = None
        self._tasks: dict[int, tuple[Task, object]] = {}
        self._pool = QThreadPool.globalInstance()

        self._build_ui()
        self.enroll_page.btn_enroll_one.setEnabled(False)
        self.enroll_page.btn_bulk.setEnabled(False)
        self.enroll_page.enroll_log.append(
            "Preparing the recognition model. Enrollment will be enabled when it is ready."
        )
        self._build_workers()
        self._wire()
        QTimer.singleShot(200, self._startup)

    # -- construction --------------------------------------------------------------
    def _build_ui(self):
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        side = QFrame()
        side.setObjectName("Sidebar")
        side.setFixedWidth(236)
        sv = QVBoxLayout(side)
        sv.setContentsMargins(12, 16, 12, 16)
        sv.setSpacing(2)

        brand = QHBoxLayout()
        brand.setContentsMargins(8, 0, 0, 10)
        mark = QLabel()
        mark.setPixmap(icon_pixmap("scan-face", ACCENT_HOVER, 22, 2.0))
        name = QLabel("attend")
        name.setObjectName("Brand")
        brand.addWidget(mark)
        brand.addSpacing(8)
        brand.addWidget(name)
        brand.addStretch()
        sv.addLayout(brand)
        sv.addWidget(make_label("Workspace", "muted"))

        self._nav_btns: dict[str, QPushButton] = {}
        for key, text, ico in NAV_ITEMS:
            sv.addWidget(self._nav_button(key, text, ico))
        sv.addStretch()
        sv.addWidget(self._nav_button("settings", "Settings", "settings"))
        row.addWidget(side)

        self.stack = QStackedWidget()
        self.stack.setObjectName("Stack")
        self.dashboard_view = DashboardView(self.bridge)
        self.live_page = LivePage()
        self.enroll_page = EnrollPage()
        self.students_page = StudentsPage()
        self.manual_page = ManualPage()
        self.register_page = RegisterPage()
        self.unknown_page = UnknownPage()
        self.settings_page = SettingsPage()
        self._pages = {
            "dashboard": self.dashboard_view, "live": self.live_page, "enroll": self.enroll_page,
            "students": self.students_page, "manual": self.manual_page,
            "register": self.register_page, "unknown": self.unknown_page,
            "settings": self.settings_page,
        }
        for page in self._pages.values():
            self.stack.addWidget(page)
        row.addWidget(self.stack, 1)
        self.body_layout.addLayout(row, 1)

        self._nav_btns["dashboard"].setChecked(True)
        self.live_page.set_session(None)
        self.live_page.camera_view.set_placeholder("Camera starting")

    def _nav_button(self, key: str, text: str, icon_name: str) -> QPushButton:
        b = QPushButton("  " + text)
        b.setProperty("nav", True)
        b.setCheckable(True)
        b.setCursor(Qt.PointingHandCursor)
        b.setIcon(icon(icon_name, TEXT_DIM, 18, on_color=TEXT))
        b.setIconSize(QSize(18, 18))
        b.clicked.connect(lambda _=False, k=key: self._nav(k))
        self._nav_btns[key] = b
        return b

    def _build_workers(self):
        self.camera_thread = CameraThread(self.camera, fps=15, parent=self)
        self.infer_thread = QThread(self)
        self.infer_worker = InferenceWorker(self.pipeline)
        self.infer_worker.moveToThread(self.infer_thread)
        self._infer_request.connect(self.infer_worker.process)
        self.infer_worker.result_ready.connect(self._on_result)
        self.camera_thread.frame_ready.connect(self._on_frame)
        self.camera_thread.status_changed.connect(self._on_camera_status)
        self._init_thread = InitThread(self.pipeline, self)
        self._init_thread.finished_loading.connect(self._on_models_ready)

    def _wire(self):
        self.bridge.navigateRequested.connect(self._nav)
        p = self.enroll_page
        p.btn_choose_photo.clicked.connect(self._choose_photo)
        p.btn_enroll_one.clicked.connect(self._enroll_one)
        p.btn_bulk.clicked.connect(self._bulk_enroll)
        self.manual_page.btn_manual_mark.clicked.connect(self._manual_mark)
        self.students_page.btn_refresh.clicked.connect(self._load_students)
        self.settings_page.btn_save.clicked.connect(self._save_settings)

        self.session_timer = QTimer(self)
        self.session_timer.setInterval(15000)
        self.session_timer.timeout.connect(self._update_session_label)
        self.session_timer.start()

    # -- navigation ----------------------------------------------------------------
    def _nav(self, key: str):
        if key not in self._pages:
            return
        for k, b in self._nav_btns.items():
            b.setChecked(k == key)
        self.stack.setCurrentWidget(self._pages[key])

        self._scan_active = key == "live"
        self.camera_thread.paused = not self._scan_active
        if self._scan_active and self.camera_thread.isRunning():
            self.live_page.set_status("Live tracking active", "good")

        if key == "dashboard":
            self.bridge.refresh_stats()
        elif key == "students":
            self._load_students()
        elif key == "register":
            self.register_page.refresh()
        elif key == "unknown":
            self.unknown_page.refresh()

    # -- startup -------------------------------------------------------------------
    def _startup(self):
        try:
            ra = cleanup_old_attendance(retention_days=30)
            ru = cleanup_expired_unknowns()
            if ra or ru:
                logger.info("Cleanup: %d attendance, %d unknowns removed", ra, ru)
        except Exception:
            logger.exception("Startup cleanup failed")
        self.bridge.refresh_stats()
        self._update_session_label()
        self._init_thread.start()
        self.camera_thread.start()

    @Slot(bool)
    def _on_models_ready(self, ok: bool):
        if not ok:
            QMessageBox.critical(
                self, "Model error",
                "Could not initialize InsightFace. On first launch, check internet access "
                "so the recognition model can download.\n\n"
                f"See the log for details: {LOG_DIR / 'attend.log'}")
            self.live_page.set_status("Models unavailable", "bad")
            return
        self._models_ready = True
        self.enrollment_svc = EnrollmentService(self.pipeline.recognizer)
        self.enroll_page.btn_enroll_one.setEnabled(True)
        self.enroll_page.btn_bulk.setEnabled(True)
        self.enroll_page.enroll_log.append("Recognizer ready. Enrollment is available.")
        self.pipeline.on_result = lambda r: None
        self.pipeline.on_unknown = self.attendance_svc.handle_unknown
        self.infer_thread.start()
        self.bridge.set_models_ready(True)
        self.bridge.push_activity("Models loaded", "Recognition is ready", "success")

    @Slot(bool, str)
    def _on_camera_status(self, ok: bool, msg: str):
        self.bridge.set_camera(ok, "Online" if ok else "Offline")
        if ok:
            self.live_page.camera_view.set_placeholder("Open Live Scanner to start")
        else:
            self.live_page.camera_view.set_placeholder(msg)
            self.live_page.set_status(msg, "bad")
            self.bridge.push_activity("Camera", msg, "warn")

    # -- frame loop ----------------------------------------------------------------
    @Slot(object)
    def _on_frame(self, frame):
        if not self._scan_active:
            return
        h, w = frame.shape[:2]
        side = max(1, int(min(h, w) * 0.82))
        x0, y0 = (w - side) // 2, (h - side) // 2
        frame = frame[y0:y0 + side, x0:x0 + side].copy()
        if self._circle_mask is None or self._circle_mask.shape != (side, side):
            mask = np.zeros((side, side), dtype=np.uint8)
            cv2.circle(mask, (side // 2, side // 2), side // 2 - 8, 255, -1)
            self._circle_mask = mask.astype(bool)
        frame[~self._circle_mask] = 0

        self.live_page.camera_view.set_frame(frame, self._latest_result)
        if self._models_ready and not self._busy:
            self._busy = True
            self._infer_request.emit(frame)

    @Slot(object)
    def _on_result(self, result):
        self._busy = False
        if result is None:
            return
        self._latest_result = result
        self.live_page.camera_view.set_result(result)
        if result.latency_ms > 0:
            self.live_page.lbl_latency.setText(f"{result.latency_ms:.0f} ms")
            target = config.recognition.target_latency_ms
            tone = "good" if result.latency_ms <= target else ("info" if result.latency_ms <= target * 2 else "bad")
            set_tone(self.live_page.lbl_latency, tone)
        if result.status == "candidate" and result.student_pk is not None:
            self._handle_candidate(result)

    def _handle_candidate(self, result: RecognitionResult):
        track = self.pipeline.tracker.tracks.get(result.track_id)
        if track and track.attendance_marked:
            return
        success, msg = self.attendance_svc.try_mark_facial(
            result.student_pk, result.student_id, result.confidence, result.track_id)
        # Silence the track either way so the database is not queried every frame.
        self.pipeline.mark_track_as_attended(result.track_id)
        if success:
            self._log_activity(f"{result.student_id}  {msg}  ({result.confidence:.2f})")
            self.live_page.set_status(msg, "good")
            self.bridge.push_activity(result.student_id, msg, "success")
            self.bridge.refresh_stats()
            if self.stack.currentWidget() is self.register_page:
                self.register_page.refresh()
        else:
            self._log_activity(f"{result.student_id}  {msg}")
            self.live_page.set_status(msg, "info")
        self._update_session_label()

    def _log_activity(self, text: str):
        self.live_page.activity_log.append(f"[{now_ist():%H:%M:%S}] {text}")

    def _update_session_label(self):
        sess = self.attendance_svc.get_active_session()
        code = sess.session_code if sess else None
        if code and self._last_session_code not in (None, code):
            self.pipeline.notify_new_session()
            logger.info("Session changed to %s, tracker reset", code)
        if code:
            self._last_session_code = code
        self.live_page.set_session(code)
        self.bridge.set_session(code)

    # -- background task helper ----------------------------------------------------
    def _run_task(self, fn, on_done):
        task = Task(fn)
        self._tasks[task.tid] = (task, on_done)
        task.signals.done.connect(self._task_done)
        task.signals.failed.connect(self._task_failed)
        self._pool.start(task)

    @Slot(int, object)
    def _task_done(self, tid: int, result):
        entry = self._tasks.pop(tid, None)
        if entry:
            entry[1](result)

    @Slot(int, str)
    def _task_failed(self, tid: int, error: str):
        self._tasks.pop(tid, None)
        self.enroll_page.set_busy(False)
        self.enroll_page.enroll_log.append(f"Error: {error}")

    # -- enrollment ----------------------------------------------------------------
    def _choose_photo(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select student photo", "", "Images (*.jpg *.jpeg *.png *.bmp)")
        if path:
            self._enroll_photo_path = path
            self.enroll_page.set_photo(path)
            self.enroll_page.enroll_log.append(f"Selected: {path}")

    def _enroll_one(self):
        p = self.enroll_page
        if not self.enrollment_svc:
            p.enroll_log.append("Recognizer is not ready yet.")
            return
        sid, name = p.en_student_id.text().strip(), p.en_name.text().strip()
        if not sid or not name or not self._enroll_photo_path:
            p.enroll_log.append("Student ID, name and a photo are required.")
            return
        path = self._enroll_photo_path
        extra = dict(
            registration_no=p.en_reg.text().strip() or None,
            department=p.en_dept.text().strip() or None,
            semester=p.en_sem.text().strip() or None,
        )
        p.set_busy(True)

        def job():
            ok, msg = self.enrollment_svc.enroll_from_image(path, sid, name, **extra)
            n = self.pipeline.rebuild_index() if ok else None
            return ok, msg, n

        def done(res):
            ok, msg, n = res
            p.set_busy(False)
            p.enroll_log.append(msg)
            if ok:
                p.enroll_log.append(f"Index rebuilt, {n} students active.")
                self.bridge.push_activity("Enrolled", f"{sid} ({n} in index)", "success")
                self.bridge.refresh_stats()

        self._run_task(job, done)

    def _bulk_enroll(self):
        p = self.enroll_page
        folder = QFileDialog.getExistingDirectory(self, "Select folder with student photos")
        if not folder or not self.enrollment_svc:
            return
        p.set_busy(True)
        p.enroll_log.append(f"Importing from {folder}")

        def job():
            results = list(self.enrollment_svc.bulk_enroll_from_folder(folder))
            return results, self.pipeline.rebuild_index()

        def done(res):
            results, n = res
            p.set_busy(False)
            for fname, _ok, msg in results:
                p.enroll_log.append(f"{fname}: {msg}")
            p.enroll_log.append(f"Bulk import finished. Index has {n} students.")
            self.bridge.push_activity("Bulk import", f"{len(results)} files processed", "info")
            self.bridge.refresh_stats()

        self._run_task(job, done)

    # -- students / manual / settings ------------------------------------------------
    def _load_students(self):
        try:
            self.students_page.load(get_all_students())
        except Exception:
            logger.exception("Could not load students")

    def _manual_mark(self):
        p = self.manual_page
        sid = p.man_student_id.text().strip()
        reason = p.man_reason.text().strip() or "Manual override"
        if not sid:
            p.manual_log.append("Enter a student ID first.")
            return
        ok, msg = self.attendance_svc.mark_manual(sid, reason=reason)
        color = GREEN if ok else RED
        label = "Marked" if ok else "Failed"
        p.manual_log.append(f'<span style="color:{color};">{label}: {msg}</span>')
        self._log_activity(f"MANUAL {sid}  {msg}")
        if ok:
            self.bridge.push_activity("Manual mark", sid, "success")
            self.bridge.refresh_stats()

    def _save_settings(self):
        s = self.settings_page
        config.recognition.match_threshold = s.cfg_match_th.value() / 100.0
        config.sessions.session1_start = s.cfg_s1_start.text().strip()
        config.sessions.session1_end = s.cfg_s1_end.text().strip()
        config.sessions.session2_start = s.cfg_s2_start.text().strip()
        config.sessions.session2_end = s.cfg_s2_end.text().strip()
        save_config(config)
        QMessageBox.information(self, "Settings", "Settings saved.")
        self._update_session_label()

    # -- shutdown --------------------------------------------------------------------
    def closeEvent(self, event):
        self.camera_thread.requestInterruption()
        self.camera_thread.wait(3000)
        self.infer_thread.quit()
        self.infer_thread.wait(3000)
        self._pool.waitForDone(2000)
        log_action("application_closed")
        super().closeEvent(event)
