#!/usr/bin/env python3
"""
InteractiveNoiseReducer — Production-Grade Speech-Preserving Noise Reduction
Entry point: initializes logging, config, and launches the Qt application.
"""

import sys
import os
import logging
from pathlib import Path

# Ensure project root is on path
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QFontDatabase

from core.config_manager import ConfigManager
from ui.main_window import MainWindow
from ui.styles import apply_theme


def setup_logging(log_dir: Path) -> logging.Logger:
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "app.log"

    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)-8s %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    return logging.getLogger("InteractiveNoiseReducer")


def main():
    # High-DPI is handled automatically in Qt6 — no attribute needed
    app = QApplication(sys.argv)
    app.setApplicationName("InteractiveNoiseReducer")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("AudioEngineeringTools")

    log = setup_logging(ROOT / "logs")
    log.info("=== InteractiveNoiseReducer starting ===")

    config = ConfigManager(ROOT / "config.json")
    log.info(f"Config loaded — theme={config.get('theme', 'dark')}")

    apply_theme(app, config.get("theme", "dark"))

    window = MainWindow(config)
    window.show()

    log.info("Main window displayed — entering event loop")
    exit_code = app.exec()
    log.info(f"Application exited with code {exit_code}")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
