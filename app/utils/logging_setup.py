import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from app.core.config import LOG_DIR


def setup_logging(level=logging.INFO):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / "attend.log"

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(level)

    # Console
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    root.addHandler(ch)

    # File
    fh = RotatingFileHandler(log_file, maxBytes=5_000_000, backupCount=3, encoding="utf-8")
    fh.setFormatter(fmt)
    root.addHandler(fh)

    # Quiet some noisy libraries
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("insightface").setLevel(logging.WARNING)
