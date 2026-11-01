"""
Business logic for marking attendance, session management and unknown faces.
"""

from __future__ import annotations
import logging
from datetime import datetime, date, time as dtime, timedelta
from typing import Optional, Tuple
from pathlib import Path
import cv2
import numpy as np

from app.core.config import config, UNKNOWNS_DIR
from app.core.database import (
    get_session, get_or_create_session, mark_attendance,
    add_or_update_unknown, log_action, get_student_by_id,
    AttendanceSessionDTO,
)
from app.core.models import Attendance, Student, AttendanceSession
from sqlalchemy import select, and_

logger = logging.getLogger(__name__)


class AttendanceService:
    def __init__(self):
        self.current_session: Optional[AttendanceSessionDTO] = None
        self._refresh_current_session()

    def _parse_time(self, hhmm: str) -> dtime:
        h, m = map(int, hhmm.split(":"))
        return dtime(h, m)

    def _refresh_current_session(self) -> None:
        """Determine which (if any) session is active right now."""
        now = datetime.now()
        today = now.date()
        t = now.time()

        s1_start = self._parse_time(config.sessions.session1_start)
        s1_end = self._parse_time(config.sessions.session1_end)
        s2_start = self._parse_time(config.sessions.session2_start)
        s2_end = self._parse_time(config.sessions.session2_end)

        session_num = None
        start_dt = end_dt = None

        if s1_start <= t <= s1_end:
            session_num = 1
            start_dt = datetime.combine(today, s1_start)
            end_dt = datetime.combine(today, s1_end)
        elif s2_start <= t <= s2_end:
            session_num = 2
            start_dt = datetime.combine(today, s2_start)
            end_dt = datetime.combine(today, s2_end)

        if session_num is None:
            self.current_session = None
            return

        self.current_session = get_or_create_session(today, session_num, start_dt, end_dt)

    def get_active_session(self) -> Optional[AttendanceSessionDTO]:
        self._refresh_current_session()
        return self.current_session

    def try_mark_facial(
        self,
        student_pk: int,
        student_id: str,
        confidence: float,
        track_id: int = None,
    ) -> Tuple[bool, str]:
        """
        Attempt to mark attendance for a recognized student in the current session.
        """
        session = self.get_active_session()
        if session is None:
            return False, "No active attendance session"

        success, msg = mark_attendance(
            student_pk=student_pk,
            session_pk=session.id,
            method="facial",
            confidence=confidence,
        )
        if success:
            log_action(
                "attendance_marked",
                details=f"student={student_id} session={session.session_code} conf={confidence:.3f}",
            )
        return success, msg

    def mark_manual(
        self,
        student_id: str,
        reason: str = "Manual override",
        admin: str = "admin",
    ) -> Tuple[bool, str]:
        student = get_student_by_id(student_id)
        if student is None:
            return False, f"Student {student_id} not found"

        session = self.get_active_session()
        if session is None:
            return False, "No active attendance session"

        success, msg = mark_attendance(
            student_pk=student.id,
            session_pk=session.id,
            method="manual",
            admin_note=reason,
            marked_by=admin,
        )
        if success:
            log_action(
                "manual_attendance",
                actor=admin,
                details=f"student={student_id} reason={reason}",
            )
        return success, msg

    def handle_unknown(
        self,
        embedding: np.ndarray,
        face_bgr: np.ndarray,
    ) -> None:
        """Save a representative image + embedding for an unknown face."""
        try:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            img_path = UNKNOWNS_DIR / f"unknown_{ts}.jpg"
            cv2.imwrite(str(img_path), face_bgr)
            add_or_update_unknown(
                embedding=embedding,
                image_path=str(img_path),
                retention_days=config.unknown.retention_days,
            )
            log_action("unknown_face_captured", details=str(img_path))
        except Exception:
            logger.exception("Failed to store unknown face")
