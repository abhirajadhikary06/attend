"""
Application configuration and path management.
All paths are relative to the project root or user data directory.
"""

from pathlib import Path
from dataclasses import dataclass, field
from typing import Tuple
import json
import os
import sys

# Keep writable runtime files out of the install directory in frozen builds.
# This lets the packaged app run without administrator/write access to its folder.
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if getattr(sys, "frozen", False):
    APP_DATA_ROOT = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Attend"
    DATA_DIR = APP_DATA_ROOT / "data"
    MODELS_DIR = APP_DATA_ROOT / "models"
else:
    APP_DATA_ROOT = PROJECT_ROOT
    DATA_DIR = APP_DATA_ROOT / "data"
    MODELS_DIR = APP_DATA_ROOT / "models"

FACES_DIR = DATA_DIR / "faces"
UNKNOWNS_DIR = DATA_DIR / "unknowns"
FAISS_DIR = DATA_DIR / "faiss_index"
DB_PATH = DATA_DIR / "attend.db"
CONFIG_PATH = DATA_DIR / "config.json"
LOG_DIR = DATA_DIR / "logs"

# Ensure directories exist
for d in [DATA_DIR, FACES_DIR, UNKNOWNS_DIR, FAISS_DIR, MODELS_DIR, LOG_DIR]:
    d.mkdir(parents=True, exist_ok=True)


@dataclass
class RecognitionConfig:
    # Similarity threshold (cosine similarity). Higher = stricter.
    # ArcFace typically works well around 0.35–0.45 for verification.
    match_threshold: float = 0.42
    unknown_threshold: float = 0.38          # slightly lower for unknown dedup
    min_face_size: int = 80                  # pixels (width or height)
    max_yaw: float = 35.0                    # degrees
    max_pitch: float = 25.0
    blur_threshold: float = 80.0             # Laplacian variance
    recognition_cooldown_sec: float = 8.0    # avoid re-marking same track quickly
    target_latency_ms: int = 300


@dataclass
class SessionConfig:
    # Two configurable sessions per day (24h format)
    session1_start: str = "09:00"
    session1_end: str = "13:00"
    session2_start: str = "14:00"
    session2_end: str = "18:00"
    timezone: str = "Asia/Kolkata"


@dataclass
class UnknownFaceConfig:
    retention_days: int = 7
    max_images_per_person: int = 1
    cleanup_interval_hours: int = 6


@dataclass
class AppConfig:
    recognition: RecognitionConfig = field(default_factory=RecognitionConfig)
    sessions: SessionConfig = field(default_factory=SessionConfig)
    unknown: UnknownFaceConfig = field(default_factory=UnknownFaceConfig)
    camera_index: int = 0
    frame_skip: int = 1                      # process every Nth frame
    max_display_fps: int = 15
    admin_password_hash: str = ""            # set on first run
    institution_name: str = "Haldia Institute of Technology"
    encryption_enabled: bool = True


def load_config() -> AppConfig:
    """Load config from JSON or return defaults."""
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            rec = RecognitionConfig(**data.get("recognition", {}))
            sess = SessionConfig(**data.get("sessions", {}))
            unk = UnknownFaceConfig(**data.get("unknown", {}))
            return AppConfig(
                recognition=rec,
                sessions=sess,
                unknown=unk,
                camera_index=data.get("camera_index", 0),
                frame_skip=data.get("frame_skip", 1),
                max_display_fps=data.get("max_display_fps", 15),
                admin_password_hash=data.get("admin_password_hash", ""),
                institution_name=data.get("institution_name", "Haldia Institute of Technology"),
                encryption_enabled=data.get("encryption_enabled", True),
            )
        except Exception:
            pass
    return AppConfig()


def save_config(cfg: AppConfig) -> None:
    data = {
        "recognition": {
            "match_threshold": cfg.recognition.match_threshold,
            "unknown_threshold": cfg.recognition.unknown_threshold,
            "min_face_size": cfg.recognition.min_face_size,
            "max_yaw": cfg.recognition.max_yaw,
            "max_pitch": cfg.recognition.max_pitch,
            "blur_threshold": cfg.recognition.blur_threshold,
            "recognition_cooldown_sec": cfg.recognition.recognition_cooldown_sec,
            "target_latency_ms": cfg.recognition.target_latency_ms,
        },
        "sessions": {
            "session1_start": cfg.sessions.session1_start,
            "session1_end": cfg.sessions.session1_end,
            "session2_start": cfg.sessions.session2_start,
            "session2_end": cfg.sessions.session2_end,
            "timezone": cfg.sessions.timezone,
        },
        "unknown": {
            "retention_days": cfg.unknown.retention_days,
            "max_images_per_person": cfg.unknown.max_images_per_person,
            "cleanup_interval_hours": cfg.unknown.cleanup_interval_hours,
        },
        "camera_index": cfg.camera_index,
        "frame_skip": cfg.frame_skip,
        "max_display_fps": cfg.max_display_fps,
        "admin_password_hash": cfg.admin_password_hash,
        "institution_name": cfg.institution_name,
        "encryption_enabled": cfg.encryption_enabled,
    }
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# Singleton-style access
config = load_config()
