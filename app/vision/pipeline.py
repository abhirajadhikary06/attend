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
        self._last_unknown_save: float = 0.0   # throttle unknown saves

        # Callbacks set by the UI / service layer
        self.on_result: Optional[Callable[[RecognitionResult], None]] = None
        self.on_unknown: Optional[Callable[[np.ndarray, np.ndarray], None]] = None  # (embedding, face_crop)

    def initialize(self) -> bool:
        ok = self.recognizer.initialize()
        if ok:
            # Try load existing index, otherwise build from DB
            if not self.recognizer.load_index():
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

        # Detect + embed
        detections = self.recognizer.detect_and_embed(frame)

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

        # Recognition
        if primary.embedding is None:
            result = RecognitionResult(status="no_face", message="No embedding")
            self._last_result = result
            return result

        student_pk, student_id, score = self.recognizer.search(primary.embedding)

        latency = (time.perf_counter() - t0) * 1000

        if student_pk is not None:
            primary.student_pk = student_pk
            primary.student_id = student_id
            primary.last_score = score
            primary.last_mark_attempt = now

            result = RecognitionResult(
                status="candidate",          # service layer will decide mark vs already
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

        self._last_result = result
        if self.on_result:
            try:
                self.on_result(result)
            except Exception:
                logger.exception("on_result callback failed")
        return result

    def mark_track_as_attended(self, track_id: int):
        t = self.tracker.tracks.get(track_id)
        if t:
            t.attendance_marked = True

    def rebuild_index(self) -> int:
        return self.recognizer.build_index()
