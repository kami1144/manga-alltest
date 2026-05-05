"""
Dialogue panel for editing dialogue bubbles.
Right panel with bubble type selector, text input, add/remove buttons.
"""

import logging
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QComboBox,
    QTextEdit,
    QListWidget,
    QListWidgetItem,
    QFrame,
    QScrollArea,
    QGroupBox,
    QSizePolicy,
)

logger = logging.getLogger(__name__)

# Bubble types supported
BUBBLE_TYPES = ['normal', 'shout', 'thought', 'whisper', 'sfx']


class DialogueBubbleListItem(QListWidgetItem):
    """Custom list item for a dialogue bubble."""

    def __init__(self, bubble_data: Dict[str, Any]):
        super().__init__()
        self.bubble_data = bubble_data

        character = bubble_data.get('character', 'Unknown')
        text = bubble_data.get('text', '')
        bubble_type = bubble_data.get('type', 'normal')

        self.setText(f"[{bubble_type}] {character}: {text[:20]}")
        self.setToolTip(f"{bubble_type} | {character}: {text}")


class DialoguePanel(QWidget):
    """Right panel for editing dialogue bubbles."""

    # Signals
    bubbleAdded = pyqtSignal(dict)  # bubble_data
    bubbleRemoved = pyqtSignal(int)  # index
    bubbleUpdated = pyqtSignal(int, dict)  # index, bubble_data
    bubbleTypeChanged = pyqtSignal(str)  # bubble_type

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._current_scene: Optional[Dict[str, Any]] = None
        self._bubble_list: List[Dict[str, Any]] = []

        self._setup_ui()
        logger.info("DialoguePanel initialized")

    def _setup_ui(self) -> None:
        """Set up the UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        # Header
        header = QLabel("对话框编辑")
        header_font = QFont()
        header_font.setPointSize(11)
        header_font.setBold(True)
        header.setFont(header_font)
        layout.addWidget(header)

        # Bubble type selector
        type_group = QGroupBox("气泡类型")
        type_layout = QVBoxLayout(type_group)
        type_layout.setContentsMargins(5, 5, 5, 5)

        self._bubble_type_combo = QComboBox()
        self._bubble_type_combo.addItems(BUBBLE_TYPES)
        self._bubble_type_combo.currentTextChanged.connect(self.bubbleTypeChanged.emit)
        type_layout.addWidget(self._bubble_type_combo)
        layout.addWidget(type_group)

        # Character input
        char_label = QLabel("角色:")
        layout.addWidget(char_label)

        self._character_input = QTextEdit()
        self._character_input.setMaximumHeight(30)
        self._character_input.setPlaceholderText("角色名称")
        layout.addWidget(self._character_input)

        # Dialogue text input
        text_label = QLabel("对话:")
        layout.addWidget(text_label)

        self._dialogue_input = QTextEdit()
        self._dialogue_input.setPlaceholderText("输入对话内容...")
        layout.addWidget(self._dialogue_input)

        # Add button
        self._add_btn = QPushButton("添加气泡")
        self._add_btn.setMaximumHeight(28)
        self._add_btn.clicked.connect(self._on_add_bubble)
        layout.addWidget(self._add_btn)

        # Bubble list
        list_label = QLabel("气泡列表:")
        layout.addWidget(list_label)

        self._bubble_list_widget = QListWidget()
        self._bubble_list_widget.setMaximumHeight(150)
        layout.addWidget(self._bubble_list_widget)

        # Remove button
        btn_layout = QHBoxLayout()
        self._remove_btn = QPushButton("删除")
        self._remove_btn.setMaximumHeight(28)
        self._remove_btn.clicked.connect(self._on_remove_bubble)
        btn_layout.addWidget(self._remove_btn)

        self._clear_btn = QPushButton("清空")
        self._clear_btn.setMaximumHeight(28)
        self._clear_btn.clicked.connect(self._on_clear_bubbles)
        btn_layout.addWidget(self._clear_btn)

        layout.addLayout(btn_layout)

        # Info section
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(spacer)

        info_group = QGroupBox("信息")
        info_layout = QVBoxLayout(info_group)
        info_layout.setContentsMargins(5, 5, 5, 5)

        self._info_label = QLabel("选择一个场景以编辑对话")
        self._info_label.setWordWrap(True)
        self._info_label.setStyleSheet("color: gray; font-size: 10px;")
        info_layout.addWidget(self._info_label)
        layout.addWidget(info_group)

    def _on_add_bubble(self) -> None:
        """Handle add bubble button click."""
        character = self._character_input.toPlainText().strip()
        text = self._dialogue_input.toPlainText().strip()

        if not text:
            logger.warning("Cannot add empty bubble")
            return

        bubble_data = {
            'type': self._bubble_type_combo.currentText(),
            'character': character or 'Unknown',
            'text': text,
        }

        self._bubble_list.append(bubble_data)
        item = DialogueBubbleListItem(bubble_data)
        self._bubble_list_widget.addItem(item)

        # Clear inputs
        self._character_input.clear()
        self._dialogue_input.clear()

        self.bubbleAdded.emit(bubble_data)
        logger.info(f"Added bubble: {bubble_data['type']}")

    def _on_remove_bubble(self) -> None:
        """Handle remove bubble button click."""
        current_row = self._bubble_list_widget.currentRow()
        if current_row >= 0:
            self._bubble_list_widget.takeItem(current_row)
            self._bubble_list.pop(current_row)
            self.bubbleRemoved.emit(current_row)
            logger.info(f"Removed bubble at index {current_row}")

    def _on_clear_bubbles(self) -> None:
        """Clear all bubbles."""
        self._bubble_list_widget.clear()
        self._bubble_list.clear()
        logger.info("Cleared all bubbles")

    def load_scene_dialogue(self, scene_data: Dict[str, Any]) -> None:
        """Load dialogue from a scene."""
        self._current_scene = scene_data
        self._bubble_list_widget.clear()
        self._bubble_list.clear()

        if not scene_data:
            self._info_label.setText("Select a scene to edit dialogue")
            return

        # Load existing dialogue lines
        dialogue_lines = scene_data.get('dialogue_lines', [])
        for line in dialogue_lines:
            bubble_data = {
                'type': 'normal',
                'character': line.get('character', 'Unknown'),
                'text': line.get('text', ''),
            }
            self._bubble_list.append(bubble_data)
            item = DialogueBubbleListItem(bubble_data)
            self._bubble_list_widget.addItem(item)

        scene_desc = scene_data.get('description', 'Untitled')
        count = len(dialogue_lines)
        self._info_label.setText(f"场景: {scene_desc[:40]}\n气泡数: {count}")
        logger.info(f"Loaded {count} dialogue bubbles from scene")

    def get_bubbles(self) -> List[Dict[str, Any]]:
        """Get all bubbles."""
        return self._bubble_list.copy()

    def set_bubble_list(self, bubbles: List[Dict[str, Any]]) -> None:
        """Set the bubble list."""
        self._bubble_list = bubbles.copy()
        self._bubble_list_widget.clear()
        for bubble in bubbles:
            item = DialogueBubbleListItem(bubble)
            self._bubble_list_widget.addItem(item)
