"""
Background workers. Nothing in this module touches widgets; results travel
back to the GUI thread through queued signals only.
"""

from __future__ import annotations

import itertools
import logging
import time

from PySide6.QtCore import QObject, QRunnable, QThread, Signal, Slot

logger = logging.getLogger(__name__)


class CameraThread(QThread):
    """Owns the capture device. Opens, polls and releases it off the GUI thread."""

    frame_ready = Signal(object)
    status_changed = Signal(bool, str)

    def __init__(self, camera, fps: int = 15, parent=None):
        super().__init__(parent)
        self._camera = camera
        self._interval = 1.0 / max(1, fps)
        self.paused = True

    def run(self):
        try:
            opened = self._camera.open()
        except Exception as exc:
            logger.exception("Camera open failed")
            self.status_changed.emit(False, str(exc))
            return
        if not opened:
            self.status_changed.emit(False, "Could not open webcam")
            return
        self.status_changed.emit(True, "Camera online")

        while not self.isInterruptionRequested():
            started = time.perf_counter()
            if self.paused:
                self.msleep(80)
                continue
            ok, frame = self._camera.read()
            if ok and frame is not None:
                self.frame_ready.emit(frame.copy())
            elif not self._camera.is_healthy():
                self.status_changed.emit(False, "Camera signal lost")
                self.msleep(500)
            remaining = self._interval - (time.perf_counter() - started)
            if remaining > 0:
                self.msleep(int(remaining * 1000))
        self._camera.release()


class InitThread(QThread):
    """Loads the recognition models without blocking the window."""

    finished_loading = Signal(bool)

    def __init__(self, pipeline, parent=None):
        super().__init__(parent)
        self._pipeline = pipeline

    def run(self):
        try:
            ok = bool(self._pipeline.initialize())
        except Exception:
            logger.exception("Pipeline initialisation failed")
            ok = False
        self.finished_loading.emit(ok)


class InferenceWorker(QObject):
    """Lives in its own QThread; detection, embedding and FAISS search run here."""

    result_ready = Signal(object)

    def __init__(self, pipeline):
        super().__init__()
        self._pipeline = pipeline

    @Slot(object)
    def process(self, frame):
        try:
            result = self._pipeline.process_frame(frame)
        except Exception:
            logger.exception("Pipeline error in inference worker")
            result = None
        self.result_ready.emit(result)


class _TaskSignals(QObject):
    done = Signal(int, object)
    failed = Signal(int, str)


class Task(QRunnable):
    """One-shot job for QThreadPool (enrollment, index rebuild, bulk import)."""

    _ids = itertools.count(1)

    def __init__(self, fn):
        super().__init__()
        self.setAutoDelete(False)
        self.tid = next(self._ids)
        self.fn = fn
        self.signals = _TaskSignals()

    def run(self):
        try:
            self.signals.done.emit(self.tid, self.fn())
        except Exception as exc:
            logger.exception("Background task failed")
            self.signals.failed.emit(self.tid, str(exc))
