"""
Lightweight multi-face tracker based on IoU + embedding distance.
Keeps track IDs stable across frames so we can apply cooldown and
avoid re-processing the same person repeatedly.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import time
import numpy as np


@dataclass
class Track:
    track_id: int
    bbox: List[int]                 # [x1, y1, x2, y2]
    embedding: Optional[np.ndarray] = None
    student_pk: Optional[int] = None
    student_id: Optional[str] = None
    last_score: float = 0.0
    hits: int = 1
    age: int = 0
    time_since_update: int = 0
    last_seen: float = field(default_factory=time.time)
    attendance_marked: bool = False
    last_mark_attempt: float = 0.0


class SimpleTracker:
    def __init__(
        self,
        max_age: int = 30,          # frames
        min_hits: int = 2,
        iou_threshold: float = 0.3,
        emb_threshold: float = 0.35,
    ):
        self.max_age = max_age
        self.min_hits = min_hits
        self.iou_threshold = iou_threshold
        self.emb_threshold = emb_threshold
        self.tracks: Dict[int, Track] = {}
        self._next_id = 1

    @staticmethod
    def _iou(a: List[int], b: List[int]) -> float:
        x1 = max(a[0], b[0])
        y1 = max(a[1], b[1])
        x2 = min(a[2], b[2])
        y2 = min(a[3], b[3])
        inter = max(0, x2 - x1) * max(0, y2 - y1)
        if inter == 0:
            return 0.0
        area_a = (a[2] - a[0]) * (a[3] - a[1])
        area_b = (b[2] - b[0]) * (b[3] - b[1])
        return inter / (area_a + area_b - inter + 1e-6)

    def update(self, detections: List[dict]) -> List[Track]:
        """
        detections: list of {"bbox": [...], "embedding": np.ndarray, ...}
        Returns list of active tracks.
        """
        # Age existing tracks
        for t in self.tracks.values():
            t.age += 1
            t.time_since_update += 1

        if not detections:
            # Remove old tracks
            self._remove_stale()
            return list(self.tracks.values())

        # Match detections to existing tracks
        matched_det = set()
        matched_trk = set()

        # Greedy matching by IoU then embedding
        track_list = list(self.tracks.values())
        for i, det in enumerate(detections):
            best_iou = 0.0
            best_trk = None
            for trk in track_list:
                if trk.track_id in matched_trk:
                    continue
                iou = self._iou(det["bbox"], trk.bbox)
                if iou > best_iou and iou >= self.iou_threshold:
                    best_iou = iou
                    best_trk = trk

            if best_trk is not None:
                # Update track
                best_trk.bbox = det["bbox"]
                if det.get("embedding") is not None:
                    best_trk.embedding = det["embedding"]
                best_trk.hits += 1
                best_trk.time_since_update = 0
                best_trk.last_seen = time.time()
                matched_det.add(i)
                matched_trk.add(best_trk.track_id)

        # Create new tracks for unmatched detections
        for i, det in enumerate(detections):
            if i in matched_det:
                continue
            tid = self._next_id
            self._next_id += 1
            self.tracks[tid] = Track(
                track_id=tid,
                bbox=det["bbox"],
                embedding=det.get("embedding"),
            )

        self._remove_stale()
        return list(self.tracks.values())

    def _remove_stale(self):
        to_del = [
            tid for tid, t in self.tracks.items()
            if t.time_since_update > self.max_age
        ]
        for tid in to_del:
            del self.tracks[tid]

    def get_primary_track(self, frame_shape: Tuple[int, int]) -> Optional[Track]:
        """
        Select the most likely 'front' person using a simple proximity score:
        larger face area + closer to horizontal centre + more recent + higher hits.
        """
        if not self.tracks:
            return None

        h, w = frame_shape[:2]
        cx = w / 2.0
        best_score = -1e9
        best = None

        for t in self.tracks.values():
            if t.hits < self.min_hits:
                continue
            x1, y1, x2, y2 = t.bbox
            area = (x2 - x1) * (y2 - y1)
            face_cx = (x1 + x2) / 2.0
            centre_dist = abs(face_cx - cx) / w
            # Prefer larger faces near the centre that are recently updated
            score = (area / (w * h)) * 2.0 - centre_dist * 0.8 - (t.time_since_update * 0.05)
            if score > best_score:
                best_score = score
                best = t
        return best
