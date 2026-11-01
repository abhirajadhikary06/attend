"""
Webcam capture helper with basic health monitoring.
"""

from __future__ import annotations
import logging
import time
from typing import Optional, Tuple
import cv2
import numpy as np

from app.core.config import config

logger = logging.getLogger(__name__)


class Camera:
    def __init__(self, index: int = None):
        self.index = index if index is not None else config.camera_index
        self.cap: Optional[cv2.VideoCapture] = None
        self._last_frame_time = 0.0
        self._fps = 0.0

    def open(self) -> bool:
        self.release()
        self.cap = cv2.VideoCapture(self.index, cv2.CAP_DSHOW)  # CAP_DSHOW better on Windows
        if not self.cap.isOpened():
            # Fallback
            self.cap = cv2.VideoCapture(self.index)
        if not self.cap.isOpened():
            logger.error("Cannot open camera index %d", self.index)
            return False

        # Reasonable defaults for attendance
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.cap.set(cv2.CAP_PROP_FPS, 30)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # reduce latency
        logger.info("Camera %d opened", self.index)
        return True

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        if self.cap is None or not self.cap.isOpened():
            return False, None
        ok, frame = self.cap.read()
        now = time.time()
        if self._last_frame_time > 0:
            dt = now - self._last_frame_time
            if dt > 0:
                self._fps = 0.9 * self._fps + 0.1 * (1.0 / dt)
        self._last_frame_time = now
        return ok, frame

    @property
    def fps(self) -> float:
        return self._fps

    def is_healthy(self) -> bool:
        return self.cap is not None and self.cap.isOpened()

    def release(self):
        if self.cap is not None:
            self.cap.release()
            self.cap = None
