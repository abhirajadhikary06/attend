#!/usr/bin/env python3
"""
attend – AI-Powered Real-Time Facial Recognition Attendance System
Fully offline, CPU-only Windows desktop application.
"""

import sys
import os

# Ensure project root is on path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from app.utils.logging_setup import setup_logging
from app.ui.main_window import MainWindow


def main():
    setup_logging()
    # High-DPI support
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("attend")
    app.setOrganizationName("HIT")
    app.setStyle("Fusion")

    # Dark-ish palette can be set here if desired
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
