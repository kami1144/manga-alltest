"""
Scene panel for displaying parsed scenes.
Left panel with QListWidget showing parsed scenes, import buttons, scene count.
"""

import logging
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QColor
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QListWidget,
    QListWidgetItem,
    QLabel,
    QFrame,
)

logger = logging.getLogger(__name__)


class SceneListItem(QListWidgetItem):
    """Custom list item for a scene."""

    def __init__(self, scene_data: Dict[str, Any], page_num: int):
        super().__init__()
        self.scene_data = scene_data
        self.page_num = page_num

        # Set display text
        description = scene_data.get('description', 'Untitled Scene')
        dialogue_count = scene_data.get('dialogue_count', 0)
        self.setText(f"Page {page_num}: {description[:30]}")

        # Set tooltip
        tooltip = f"Scene: {description}\nDialogue: {dialogue_count}"
        self.setToolTip(tooltip)


class ScenePanel(QWidget):
    """Left panel showing scene list and controls."""

    # Signals
    importScriptClicked = pyqtSignal()
    importImagesClicked = pyqtSignal()
    sceneSelected = pyqtSignal(str)  # scene_id
    generateLayoutClicked = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._script_data: Optional[Dict[str, Any]] = None
        self._images: List[Dict[str, Any]] = []
        self._current_scene_id: Optional[str] = None

        self._setup_ui()
        logger.info("ScenePanel initialized")

    def _setup_ui(self) -> None:
        """Set up the UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        # Header
        header = QLabel("场景列表")
        header_font = QFont()
        header_font.setPointSize(11)
        header_font.setBold(True)
        header.setFont(header_font)
        layout.addWidget(header)

        # Import buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(5)

        self._import_script_btn = QPushButton("导入剧本")
        self._import_script_btn.setMaximumHeight(28)
        self._import_script_btn.clicked.connect(self.importScriptClicked.emit)
        btn_layout.addWidget(self._import_script_btn)

        self._import_images_btn = QPushButton("导入图片")
        self._import_images_btn.setMaximumHeight(28)
        self._import_images_btn.clicked.connect(self.importImagesClicked.emit)
        btn_layout.addWidget(self._import_images_btn)

        layout.addLayout(btn_layout)

        # Scene list
        self._scene_list = QListWidget()
        self._scene_list.setFrameShape(QFrame.Shape.NoFrame)
        self._scene_list.setAlternatingRowColors(True)
        self._scene_list.itemClicked.connect(self._on_scene_clicked)
        layout.addWidget(self._scene_list)

        # Status/count label
        self._status_label = QLabel("场景: 0 | 图片: 0")
        self._status_label.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(self._status_label)

        # Auto Layout button
        self._auto_layout_btn = QPushButton("自动排版")
        self._auto_layout_btn.setMaximumHeight(30)
        self._auto_layout_btn.clicked.connect(self.generateLayoutClicked.emit)
        layout.addWidget(self._auto_layout_btn)

    def _on_scene_clicked(self, item: SceneListItem) -> None:
        """Handle scene selection."""
        if isinstance(item, SceneListItem):
            self._current_scene_id = item.scene_data.get('scene_id')
            self.sceneSelected.emit(self._current_scene_id)

    def set_script_data(self, script_data: Dict[str, Any]) -> None:
        """Populate scene list from script data."""
        self._script_data = script_data
        self._scene_list.clear()

        if not script_data:
            return

        pages = script_data.get('pages', [])
        for page in pages:
            page_num = page.get('page_num', 0)
            scenes = page.get('scenes', [])
            for scene in scenes:
                item = SceneListItem(scene, page_num)
                self._scene_list.addItem(item)

        self._update_status()
        logger.info(f"Loaded {self._scene_list.count()} scenes")

    def set_images(self, images: List[Dict[str, Any]]) -> None:
        """Set loaded images count."""
        self._images = images
        self._update_status()

    def get_current_scene(self) -> Optional[Dict[str, Any]]:
        """Get currently selected scene data."""
        if not self._current_scene_id or not self._script_data:
            return None

        for page in self._script_data.get('pages', []):
            for scene in page.get('scenes', []):
                if scene.get('scene_id') == self._current_scene_id:
                    return scene
        return None

    def _update_status(self) -> None:
        """Update status label."""
        scene_count = self._scene_list.count()
        image_count = len(self._images)
        self._status_label.setText(f"Scenes: {scene_count} | Images: {image_count}")

    def get_scene_count(self) -> int:
        """Get total scene count."""
        return self._scene_list.count()

    def get_image_count(self) -> int:
        """Get loaded image count."""
        return len(self._images)
