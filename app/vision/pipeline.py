"""
Main vision pipeline: frame → detections → tracking → primary face → recognition → decision.
"""

from __future__ import annotations
import logging
import time
from dataclasses import dataclass
from typing import Optional, Callable
import numpy as np

from app.core.config import config
from app.vision.recognizer import FaceRecognizer
from app.vision.tracker import SimpleTracker, Track
from app.vision.quality import overall_quality

logger = logging.getLogger(__name__)


@dataclass
class RecognitionResult:
    status: str                     # "marked", "already_marked", "unknown", "low_quality", "no_face"
    message: str
    student_id: Optional[str] = None
    student_pk: Optional[int] = None
    confidence: float = 0.0
    track_id: Optional[int] = None
    latency_ms: float = 0.0
    bbox: Optional[list] = None


class FacePipeline:
    def __init__(self):
        self.recognizer = FaceRecognizer()
        self.tracker = SimpleTracker()
        self._frame_count = 0
        self._last_result: Optional[RecognitionResult] = None
        self._last_unknown_save: float = 0.0

        # Set of student PKs whose attendance is confirmed in the current session.
        # This is the authoritative in-memory record — independent of tracker state.
        # Even if a track is dropped and recreated, this set prevents re-marking.
        self._marked_students: set = set()

        # Callbacks set by the UI / service layer
        self.on_result: Optional[Callable[[RecognitionResult], None]] = None
        self.on_unknown: Optional[Callable[[np.ndarray, np.ndarray], None]] = None

    def initialize(self) -> bool:
        ok = self.recognizer.initialize()
        if ok:
            # Always rebuild from DB to ensure any students enrolled in a
            # previous session are picked up. The disk index may be stale.
            n = self.recognizer.build_index()
            logger.info("Built index with %d students", n)
        return ok

    def process_frame(self, frame: np.ndarray) -> RecognitionResult:
        """
        Process a single BGR frame.
        Returns a RecognitionResult describing the decision for the primary face.
        """
        t0 = time.perf_counter()
        self._frame_count += 1

        # Optional frame skipping for performance
        if config.frame_skip > 1 and (self._frame_count % config.frame_skip) != 0:
            if self._last_result:
                return self._last_result
            return RecognitionResult(status="no_face", message="Skipped frame")

        # Detect all faces; ArcFace is deferred to the selected track when needed.
        detections = self.recognizer.detect_faces(frame)

        # Update tracker
        tracks = self.tracker.update(detections)

        primary = self.tracker.get_primary_track(frame.shape)
        if primary is None:
            result = RecognitionResult(status="no_face", message="No suitable face")
            self._last_result = result
            return result

        # Quality check
        x1, y1, x2, y2 = primary.bbox
        face_crop = frame[max(0, y1):y2, max(0, x1):x2]
        good, reason = overall_quality(primary.bbox, face_crop)
        if not good:
            result = RecognitionResult(
                status="low_quality",
                message=reason,
                track_id=primary.track_id,
                bbox=primary.bbox,
            )
            self._last_result = result
            return result

        # Cooldown / already processed
        now = time.time()
        if primary.attendance_marked:
            logger.debug("Track %d already marked (attendance_marked=True)", primary.track_id)
            result = RecognitionResult(
                status="already_marked",
                message="Attendance Already Marked",
                student_id=primary.student_id,
                student_pk=primary.student_pk,
                confidence=primary.last_score,
                track_id=primary.track_id,
                bbox=primary.bbox,
            )
            self._last_result = result
            return result

        # Check the authoritative marked-students set.
        # Catches the case where the track was dropped and recreated but the
        # student was already confirmed in the DB this session.
        if primary.student_pk is not None and primary.student_pk in self._marked_students:
            logger.debug("Track %d: student_pk %d in _marked_students, syncing", primary.track_id, primary.student_pk)
            primary.attendance_marked = True   # sync track state
            result = RecognitionResult(
                status="already_marked",
                message="Attendance Already Marked",
                student_id=primary.student_id,
                student_pk=primary.student_pk,
                confidence=primary.last_score,
                track_id=primary.track_id,
                bbox=primary.bbox,
            )
            self._last_result = result
            return result

        if (now - primary.last_mark_attempt) < config.recognition.recognition_cooldown_sec:
            result = RecognitionResult(
                status="cooldown",
                message="Please wait…",
                track_id=primary.track_id,
                bbox=primary.bbox,
            )
            self._last_result = result
            return result

        # Only embed the selected face when this track is due for recognition.
        # Detection and tracking continue every processed frame without repeating ArcFace.
        if primary.embedding is None:
            primary.embedding = self.recognizer.embed_detection(frame, primary.kps)
            if primary.embedding is None:
                primary.last_mark_attempt = now
                result = RecognitionResult(
                    status="no_face",
                    message="Could not extract face embedding",
                    track_id=primary.track_id,
                    bbox=primary.bbox,
                    latency_ms=(time.perf_counter() - t0) * 1000,
                )
                self._last_result = result
                return result

        student_pk, student_id, score = self.recognizer.search(primary.embedding)

        latency = (time.perf_counter() - t0) * 1000

        if student_pk is not None:
            primary.student_pk = student_pk
            primary.student_id = student_id
            primary.last_score = score
            primary.last_mark_attempt = now

            # Check authoritative set AFTER recognition — catches the case where
            # a new track just had recognition run for the first time but the
            # student was already marked in this session (track-drop race).
            if student_pk in self._marked_students:
                logger.debug("Post-FAISS: student_pk %d already in _marked_students", student_pk)
                primary.attendance_marked = True
                result = RecognitionResult(
                    status="already_marked",
                    message="Attendance Already Marked",
                    student_id=student_id,
                    student_pk=student_pk,
                    confidence=score,
                    track_id=primary.track_id,
                    latency_ms=latency,
                    bbox=primary.bbox,
                )
                self._last_result = result
                return result

            logger.debug("Emitting candidate for %s (track %d)", student_id, primary.track_id)

            result = RecognitionResult(
                status="candidate",
                message=f"Recognized {student_id}",
                student_id=student_id,
                student_pk=student_pk,
                confidence=score,
                track_id=primary.track_id,
                latency_ms=latency,
                bbox=primary.bbox,
            )
        else:
            result = RecognitionResult(
                status="unknown",
                message="Face Not Recognized",
                confidence=score,
                track_id=primary.track_id,
                latency_ms=latency,
                bbox=primary.bbox,
            )
            primary.last_mark_attempt = now
            # Save unknown face — throttled to at most once every 30 s per track
            if self.on_unknown and (now - self._last_unknown_save) >= 30.0:
                self._last_unknown_save = now
                if primary.embedding is not None:
                    x1, y1, x2, y2 = primary.bbox
                    face_crop = frame[max(0, y1):y2, max(0, x1):x2]
                    try:
                        self.on_unknown(primary.embedding.copy(), face_crop.copy())
                    except Exception:
                        logger.exception("on_unknown callback failed")

        if result.status == "unknown":
            primary.embedding = None  # Refresh the sample at the next allowed retry.

        self._last_result = result
        if self.on_result:
            try:
                self.on_result(result)
            except Exception:
                logger.exception("on_result callback failed")
        return result

    def mark_track_as_attended(self, track_id: int, student_pk: int = None):
        """
        Mark a track as attended after a confirmed DB write.
        Uses both track_id AND student_pk so any track for the same student
        is silenced, even if the track_id changed (track-drop race condition).
        """
        logger.info("mark_track_as_attended: track_id=%s student_pk=%s, _marked_students before=%s",
                    track_id, student_pk, self._marked_students)
        t = self.tracker.tracks.get(track_id)
        if t:
            t.attendance_marked = True

        if student_pk is not None:
            self._marked_students.add(student_pk)
            for trk in self.tracker.tracks.values():
                if trk.student_pk == student_pk:
                    trk.attendance_marked = True

        logger.info("mark_track_as_attended done: _marked_students=%s, track_ids=%s",
                    self._marked_students,
                    {tid: t.attendance_marked for tid, t in self.tracker.tracks.items()})

    def rebuild_index(self) -> int:
        """Rebuild FAISS index from DB. Resets unknown-track cooldowns so newly
        enrolled students are recognised on the very next pipeline cycle."""
        n = self.recognizer.build_index()
        self.tracker.reset_unknown_tracks()
        return n

    def notify_new_session(self):
        """Call when a new attendance session becomes active so in-frame students
        can be re-marked without restarting the app."""
        self._marked_students.clear()
        self.tracker.reset_for_new_session()
