"""
Settings dialog with tabs for General, Page Settings, and Export options.
"""

import logging
from typing import Any, Dict, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QTabWidget,
    QWidget,
    QLabel,
    QLineEdit,
    QComboBox,
    QSpinBox,
    QDoubleSpinBox,
    QCheckBox,
    QGroupBox,
    QFormLayout,
    QDialogButtonBox,
    QPushButton,
)

logger = logging.getLogger(__name__)

PAGE_SIZE_OPTIONS = ['A4', 'B5', 'Japanese A5']
READING_DIRECTION_OPTIONS = ['RTL (从右到左)', 'LTR (从左到右)']
QUALITY_OPTIONS = ['72 DPI', '150 DPI', '300 DPI']
CROP_MODE_OPTIONS = ['fit (适应)', 'fill (填充)']


class SettingsDialog(QDialog):
    """Settings dialog with tabbed interface."""

    def __init__(self, settings: Dict[str, Any], parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._settings = settings.copy()
        self._setup_ui()
        self._load_settings()
        logger.info("SettingsDialog initialized")

    def _setup_ui(self) -> None:
        """Set up the UI components."""
        self.setWindowTitle("设置")
        self.setMinimumWidth(400)
        self.setMinimumHeight(350)

        layout = QVBoxLayout(self)

        # Tab widget
        self._tabs = QTabWidget()
        layout.addWidget(self._tabs)

        # General tab
        self._general_tab = self._create_general_tab()
        self._tabs.addTab(self._general_tab, "常规")

        # Page Settings tab
        self._page_tab = self._create_page_tab()
        self._tabs.addTab(self._page_tab, "页面设置")

        # Export tab
        self._export_tab = self._create_export_tab()
        self._tabs.addTab(self._export_tab, "导出")

        # AI Settings tab
        self._ai_tab = self._create_ai_tab()
        self._tabs.addTab(self._ai_tab, "AI 设置")

        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _create_general_tab(self) -> QWidget:
        """Create the General settings tab."""
        widget = QWidget()
        layout = QFormLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Reading direction
        self._reading_dir_combo = QComboBox()
        self._reading_dir_combo.addItems(READING_DIRECTION_OPTIONS)
        layout.addRow("阅读方向:", self._reading_dir_combo)

        # Gutter width
        self._gutter_spin = QSpinBox()
        self._gutter_spin.setRange(0, 50)
        self._gutter_spin.setSuffix(" px")
        layout.addRow("间距宽度:", self._gutter_spin)

        # Auto layout
        self._auto_layout_check = QCheckBox("启用自动排版")
        layout.addRow(self._auto_layout_check)

        return widget

    def _create_page_tab(self) -> QWidget:
        """Create the Page Settings tab."""
        widget = QWidget()
        layout = QFormLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Page size
        self._page_size_combo = QComboBox()
        self._page_size_combo.addItems(PAGE_SIZE_OPTIONS)
        layout.addRow("页面大小:", self._page_size_combo)

        # Bleed margin
        self._bleed_spin = QDoubleSpinBox()
        self._bleed_spin.setRange(0, 10)
        self._bleed_spin.setSuffix(" mm")
        self._bleed_spin.setDecimals(1)
        layout.addRow("出血宽度:", self._bleed_spin)

        # Crop mode
        self._crop_mode_combo = QComboBox()
        self._crop_mode_combo.addItems(CROP_MODE_OPTIONS)
        layout.addRow("图片裁剪模式:", self._crop_mode_combo)

        # Panel count preference
        self._panel_count_spin = QSpinBox()
        self._panel_count_spin.setRange(1, 6)
        layout.addRow("面板数量:", self._panel_count_spin)

        return widget

    def _create_export_tab(self) -> QWidget:
        """Create the Export settings tab."""
        widget = QWidget()
        layout = QFormLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # PDF quality
        self._pdf_quality_combo = QComboBox()
        self._pdf_quality_combo.addItems(QUALITY_OPTIONS)
        layout.addRow("PDF 质量:", self._pdf_quality_combo)

        # ZIP format
        self._zip_format_combo = QComboBox()
        self._zip_format_combo.addItems(['PNG', 'JPEG'])
        layout.addRow("ZIP 格式:", self._zip_format_combo)

        # Include dialogue JSON
        self._include_json_check = QCheckBox()
        self._include_json_check.setChecked(True)
        layout.addRow("包含 dialogue.json:", self._include_json_check)

        # SD API URL
        self._sd_api_url = QLineEdit()
        self._sd_api_url.setPlaceholderText("https://api.minimax.chat/v1/...")
        layout.addRow("SD API 地址:", self._sd_api_url)

        # SD settings
        sd_group = QGroupBox("Stable Diffusion 设置")
        sd_layout = QFormLayout(sd_group)

        self._sd_steps = QSpinBox()
        self._sd_steps.setRange(1, 100)
        sd_layout.addRow("步数:", self._sd_steps)

        self._sd_width = QSpinBox()
        self._sd_width.setRange(256, 2048)
        self._sd_width.setSingleStep(64)
        sd_layout.addRow("宽度:", self._sd_width)

        self._sd_height = QSpinBox()
        self._sd_height.setRange(256, 2048)
        self._sd_height.setSingleStep(64)
        sd_layout.addRow("高度:", self._sd_height)

        layout.addRow(sd_group)

        return widget

    def _create_ai_tab(self) -> QWidget:
        """Create the AI/LLM settings tab."""
        widget = QWidget()
        layout = QFormLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Provider
        self._llm_provider_combo = QComboBox()
        self._llm_provider_combo.addItems(['MiniMax', 'OpenAI (兼容)', 'Ollama (本地)'])
        layout.addRow("LLM Provider:", self._llm_provider_combo)

        # API Key
        self._llm_api_key = QLineEdit()
        self._llm_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._llm_api_key.setPlaceholderText("sk-...")
        layout.addRow("API Key:", self._llm_api_key)

        # API URL (optional, for custom endpoints)
        self._llm_api_url = QLineEdit()
        self._llm_api_url.setPlaceholderText("https://api.minimax.io/v1/chat/completions")
        layout.addRow("API URL (可选):", self._llm_api_url)

        # Model name
        self._llm_model = QLineEdit()
        self._llm_model.setPlaceholderText("MiniMax-M2")
        layout.addRow("Model:", self._llm_model)

        # Test button
        test_layout = QHBoxLayout()
        self._test_btn = QPushButton("测试连接")
        self._test_status = QLabel("")
        self._test_btn.clicked.connect(self._test_llm_connection)
        test_layout.addWidget(self._test_btn)
        test_layout.addWidget(self._test_status)
        layout.addRow(test_layout)

        # Status hint
        hint = QLabel("设置后会立即生效，无需重启程序")
        hint.setStyleSheet("color: gray; font-size: 11px;")
        layout.addRow(hint)

        return widget

    def _test_llm_connection(self) -> None:
        """Test LLM connection."""
        from utils.llm_client import LLMClient, LLMProvider
        provider_map = {
            'MiniMax': LLMProvider.MINIMAX,
            'OpenAI (兼容)': LLMProvider.OPENAI,
            'Ollama (本地)': LLMProvider.OLLAMA,
        }
        provider = provider_map.get(self._llm_provider_combo.currentText(), LLMProvider.MINIMAX)
        api_key = self._llm_api_key.text() or None
        api_url = self._llm_api_url.text() or None
        model = self._llm_model.text() or None

        try:
            client = LLMClient(provider=provider, api_key=api_key, api_url=api_url, model=model)
            if client.is_available():
                self._test_status.setText("连接成功")
                self._test_status.setStyleSheet("color: green;")
            else:
                self._test_status.setText("不可用（检查 API Key）")
                self._test_status.setStyleSheet("color: red;")
        except Exception as e:
            self._test_status.setText(f"错误: {e}")
            self._test_status.setStyleSheet("color: red;")

    def _load_settings(self) -> None:
        """Load settings into UI controls."""
        # General
        reading_dir = self._settings.get('reading_direction', 'RTL')
        # Support both old ('RTL') and new ('RTL (从右到左)') formats
        if reading_dir in READING_DIRECTION_OPTIONS:
            self._reading_dir_combo.setCurrentText(reading_dir)
        elif reading_dir == 'RTL':
            self._reading_dir_combo.setCurrentIndex(0)
        elif reading_dir == 'LTR':
            self._reading_dir_combo.setCurrentIndex(1)

        self._gutter_spin.setValue(self._settings.get('gutter_width', 12))
        self._auto_layout_check.setChecked(self._settings.get('auto_layout', True))

        # Page settings
        page_size = self._settings.get('page_size', 'A4')
        if page_size in PAGE_SIZE_OPTIONS:
            self._page_size_combo.setCurrentText(page_size)

        self._bleed_spin.setValue(self._settings.get('bleed_margin', 3))
        crop_mode = self._settings.get('crop_mode', 'fit')
        # Support both old ('fit') and new ('fit (适应)') formats
        if crop_mode in CROP_MODE_OPTIONS:
            self._crop_mode_combo.setCurrentText(crop_mode)
        elif crop_mode == 'fit':
            self._crop_mode_combo.setCurrentIndex(0)
        elif crop_mode == 'fill':
            self._crop_mode_combo.setCurrentIndex(1)

        self._panel_count_spin.setValue(self._settings.get('preferred_panels', 3))

        # Export
        pdf_quality = self._settings.get('pdf_quality', 300)
        quality_text = f"{pdf_quality} DPI"
        if quality_text in QUALITY_OPTIONS:
            self._pdf_quality_combo.setCurrentText(quality_text)

        zip_format = self._settings.get('zip_format', 'PNG')
        self._zip_format_combo.setCurrentText(zip_format)

        self._include_json_check.setChecked(self._settings.get('include_dialogue_json', True))

        self._sd_api_url.setText(self._settings.get('sd_api_url', ''))
        self._sd_steps.setValue(self._settings.get('sd_steps', 20))
        self._sd_width.setValue(self._settings.get('sd_width', 1024))
        self._sd_height.setValue(self._settings.get('sd_height', 1536))

        # AI / LLM
        self._llm_provider_combo.setCurrentText(self._settings.get('llm_provider', 'MiniMax'))
        self._llm_api_key.setText(self._settings.get('llm_api_key', ''))
        self._llm_api_url.setText(self._settings.get('llm_api_url', ''))
        self._llm_model.setText(self._settings.get('llm_model', 'MiniMax-M2'))

    def _on_accept(self) -> None:
        """Save settings and accept."""
        self._save_settings()
        self.accept()

    def _save_settings(self) -> None:
        """Save UI values back to settings dict."""
        # General
        reading_dir_raw = self._reading_dir_combo.currentText()
        # Save as plain 'RTL'/'LTR' for compatibility
        self._settings['reading_direction'] = 'RTL' if 'RTL' in reading_dir_raw else 'LTR'
        self._settings['gutter_width'] = self._gutter_spin.value()
        self._settings['auto_layout'] = self._auto_layout_check.isChecked()

        # Page settings
        self._settings['page_size'] = self._page_size_combo.currentText()

        self._settings['bleed_margin'] = self._bleed_spin.value()
        crop_mode_raw = self._crop_mode_combo.currentText()
        # Save as plain 'fit'/'fill' for compatibility
        self._settings['crop_mode'] = 'fit' if crop_mode_raw.startswith('fit') else 'fill'
        self._settings['preferred_panels'] = self._panel_count_spin.value()

        # Export
        quality_text = self._pdf_quality_combo.currentText()
        self._settings['pdf_quality'] = int(quality_text.split()[0])
        self._settings['zip_format'] = self._zip_format_combo.currentText()
        self._settings['include_dialogue_json'] = self._include_json_check.isChecked()

        # SD
        self._settings['sd_api_url'] = self._sd_api_url.text()
        self._settings['sd_steps'] = self._sd_steps.value()
        self._settings['sd_width'] = self._sd_width.value()
        self._settings['sd_height'] = self._sd_height.value()

        # LLM
        self._settings['llm_provider'] = self._llm_provider_combo.currentText()
        self._settings['llm_api_key'] = self._llm_api_key.text()
        self._settings['llm_api_url'] = self._llm_api_url.text()
        self._settings['llm_model'] = self._llm_model.text()

        logger.info("Settings saved from dialog")

    def get_settings(self) -> Dict[str, Any]:
        """Get the current settings."""
        return self._settings
