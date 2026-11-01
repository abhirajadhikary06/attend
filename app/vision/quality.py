"""
Face quality assessment: size, blur, pose (if available).
"""

from __future__ import annotations
from typing import Tuple
import cv2
import numpy as np

from app.core.config import config


def is_face_large_enough(bbox: list, min_size: int = None) -> bool:
    min_size = min_size or config.recognition.min_face_size
    x1, y1, x2, y2 = bbox
    return (x2 - x1) >= min_size and (y2 - y1) >= min_size


def blur_score(face_bgr: np.ndarray) -> float:
    """Laplacian variance – higher is sharper."""
    if face_bgr is None or face_bgr.size == 0:
        return 0.0
    gray = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def is_sharp_enough(face_bgr: np.ndarray, threshold: float = None) -> bool:
    threshold = threshold or config.recognition.blur_threshold
    return blur_score(face_bgr) >= threshold


def overall_quality(
    bbox: list,
    face_img: np.ndarray = None,
    pose: Tuple[float, float, float] = None,  # yaw, pitch, roll
) -> Tuple[bool, str]:
    """
    Returns (is_good, reason).
    """
    if not is_face_large_enough(bbox):
        return False, "Face too small"

    if face_img is not None and not is_sharp_enough(face_img):
        return False, "Face too blurry"

    if pose is not None:
        yaw, pitch, _ = pose
        if abs(yaw) > config.recognition.max_yaw:
            return False, "Face yaw too large"
        if abs(pitch) > config.recognition.max_pitch:
            return False, "Face pitch too large"

    return True, "OK"
