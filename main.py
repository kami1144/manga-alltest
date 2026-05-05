"""
MangaAutoLayout - Automatic manga/comic page layout application.
Entry point for PyQt6 desktop application.
"""

import os
os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
os.environ.setdefault("QT_USE_HIGH_DPI_PIXMAPS", "1")

import sys
import json
import logging
from pathlib import Path
from typing import Any, Dict

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication

# Configure logging - both console and file
LOG_DIR = Path.home() / ".manga_auto_layout" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

file_handler = logging.FileHandler(LOG_DIR / "run.log", encoding="utf-8")
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

error_handler = logging.FileHandler(LOG_DIR / "error.log", encoding="utf-8")
error_handler.setLevel(logging.ERROR)
error_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(), file_handler, error_handler]
)
logger = logging.getLogger(__name__)

# Default settings
DEFAULT_SETTINGS: Dict[str, Any] = {
    "sd_api_url": "https://api.minimax.chat/v1/text/chatcompletion_v2",
    "sd_steps": 20,
    "sd_width": 1024,
    "sd_height": 1536,
    "reading_direction": "RTL",
    "gutter_width": 12,
    "page_size": "A4",
    "bleed_margin": 3,
    "pdf_quality": 300,
    "zip_format": "PNG",
    "last_project_dir": "",
    "last_script_path": "",
    "last_images_dir": "",
}

DEFAULT_PAGE_SIZES: Dict[str, tuple] = {
    "A4": (210, 297),
    "B5": (182, 257),
    "Japanese A5": (148, 210),
}


def get_settings_path() -> Path:
    """Get the settings file path."""
    settings_dir = Path.home() / ".manga_auto_layout"
    return settings_dir / "settings.json"


def setup_directories() -> None:
    """Create necessary directories."""
    settings_dir = Path.home() / ".manga_auto_layout"
    settings_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Settings directory created: {settings_dir}")


def setup_environment() -> Dict[str, Any]:
    """Load or create settings."""
    settings_path = get_settings_path()
    if settings_path.exists():
        try:
            with open(settings_path, 'r', encoding='utf-8') as f:
                settings = json.load(f)
            logger.info("Settings loaded from file")
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to load settings: {e}, using defaults")
            settings = DEFAULT_SETTINGS.copy()
    else:
        settings = DEFAULT_SETTINGS.copy()
        save_settings(settings)
        logger.info("Created default settings")

    return settings


def save_settings(settings: Dict[str, Any]) -> None:
    """Save settings to file."""
    settings_path = get_settings_path()
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    with open(settings_path, 'w', encoding='utf-8') as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)
    logger.info("Settings saved")


def main() -> int:
    """Main entry point."""
    setup_directories()
    settings = setup_environment()

    # Create application
    app = QApplication(sys.argv)

    app.setApplicationName("MangaAutoLayout")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("MangaAutoLayout")

    # Import main window after app is created
    from ui.main_window import MainWindow

    logger.info("Starting MangaAutoLayout application")

    # Create and show main window
    window = MainWindow(settings)
    window.show()

    # Save settings on app exit
    app.aboutToQuit.connect(lambda: save_settings(settings))

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())