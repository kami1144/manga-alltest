"""
Main application window for MangaAutoLayout.
Central QMainWindow with menu, toolbar, and central widget layout.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import QAction
from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QMenuBar,
    QMenu,
    QToolBar,
    QStatusBar,
    QLabel,
    QFileDialog,
    QMessageBox,
)

from core.parser import parse_script
from core.layout_engine import generate_layout
from core.image_processor import load_image, load_images_from_folder
from core.ai_layout_advisor import AILayoutAdvisor
from core.image_composer import ImageComposer, get_composer
from core.refiner import LayoutRefiner
from core.narrative_pacing import NarrativePacingAnalyzer
from core.image_matcher import ImageMatcher
from utils.export import export_pdf, export_zip
from utils.llm_client import LLMProvider

from ui.scene_panel import ScenePanel
from ui.dialogue_panel import DialoguePanel
from ui.canvas import CanvasWidget as Canvas

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """
    Main application window for MangaAutoLayout.
    Manages layout, menus, toolbar, and coordinates between panels.
    """

    # Signals for inter-panel communication
    scriptLoaded = pyqtSignal(dict)
    imagesLoaded = pyqtSignal(list)
    layoutGenerated = pyqtSignal(dict)
    sceneSelected = pyqtSignal(str)
    exportCompleted = pyqtSignal(str)

    def __init__(self, settings: Dict[str, Any], parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._settings = settings
        self._script_data: Optional[Dict[str, Any]] = None
        self._images: List[Dict[str, Any]] = []
        self._layout_data: Optional[Dict[str, Any]] = None
        self._current_page: int = 1
        self._total_pages: int = 0
        self._current_scene_id: Optional[str] = None
        self._page_rhythms: List[str] = []  # Pacing analysis results for each page

        # Initialize AI modules
        # Read LLM config from settings
        llm_provider_name = self._settings.get('llm_provider', 'MiniMax')
        provider_map = {
            'MiniMax': LLMProvider.MINIMAX,
            'OpenAI (兼容)': LLMProvider.OPENAI,
            'Ollama (本地)': LLMProvider.OLLAMA,
        }
        llm_provider = provider_map.get(llm_provider_name, LLMProvider.MINIMAX)
        llm_api_key = self._settings.get('llm_api_key') or None
        llm_api_url = self._settings.get('llm_api_url') or None
        llm_model = self._settings.get('llm_model') or None

        self._ai_advisor = AILayoutAdvisor(
            provider=llm_provider,
            api_key=llm_api_key,
            api_url=llm_api_url,
            model=llm_model,
        )
        self._image_composer = get_composer()
        self._refiner = LayoutRefiner(
            gutter_width=settings.get('gutter_width', 12),
            bleed_margin=settings.get('bleed_margin', 3),
        )
        self._pacing_analyzer = NarrativePacingAnalyzer(vision_provider="none")

        self._setup_ui()
        self._setup_connections()
        logger.info("MainWindow initialized")

    def _setup_ui(self) -> None:
        """Set up the UI components."""
        # Window properties
        self.setWindowTitle("MangaAutoLayout - 漫画排版工具")
        self.setMinimumSize(1200, 800)

        # Apply high DPI scaling (for PyQt5 compatibility, handled in main.py)
# QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
# QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

        # Create central widget with horizontal layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)

        # Left panel: Scene panel
        self._scene_panel = ScenePanel()
        main_layout.addWidget(self._scene_panel, stretch=1)

        # Center: Canvas
        self._canvas = Canvas()
        main_layout.addWidget(self._canvas, stretch=3)

        # Right panel: Dialogue panel
        self._dialogue_panel = DialoguePanel()
        main_layout.addWidget(self._dialogue_panel, stretch=1)

        # Create menu bar
        self._create_menu_bar()

        # Create toolbar
        self._create_toolbar()

        # Create status bar
        self._create_status_bar()

    def _create_menu_bar(self) -> None:
        """Create the menu bar."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("文件")

        self._action_import_script = QAction("导入剧本", self)
        self._action_import_script.setShortcut(QKeySequence.StandardKey.Open)
        self._action_import_script.triggered.connect(self._on_import_script)
        file_menu.addAction(self._action_import_script)

        self._action_import_images = QAction("导入图片", self)
        self._action_import_images.setShortcut(QKeySequence("Ctrl+Shift+O"))
        self._action_import_images.triggered.connect(self._on_import_images)
        file_menu.addAction(self._action_import_images)

        file_menu.addSeparator()

        self._action_export_pdf = QAction("导出 PDF", self)
        self._action_export_pdf.setShortcut(QKeySequence("Ctrl+E"))
        self._action_export_pdf.triggered.connect(self._on_export_pdf)
        file_menu.addAction(self._action_export_pdf)

        self._action_export_zip = QAction("导出 ZIP", self)
        self._action_export_zip.setShortcut(QKeySequence("Ctrl+Shift+E"))
        self._action_export_zip.triggered.connect(self._on_export_zip)
        file_menu.addAction(self._action_export_zip)

        file_menu.addSeparator()

        self._action_exit = QAction("退出", self)
        self._action_exit.setShortcut(QKeySequence.StandardKey.Quit)
        self._action_exit.triggered.connect(self.close)
        file_menu.addAction(self._action_exit)

        # Edit menu
        edit_menu = menubar.addMenu("编辑")

        self._action_undo = QAction("撤销", self)
        self._action_undo.setShortcut(QKeySequence.StandardKey.Undo)
        edit_menu.addAction(self._action_undo)

        self._action_redo = QAction("重做", self)
        self._action_redo.setShortcut(QKeySequence.StandardKey.Redo)
        edit_menu.addAction(self._action_redo)

        edit_menu.addSeparator()

        self._action_settings = QAction("设置", self)
        self._action_settings.triggered.connect(self._on_settings)
        edit_menu.addAction(self._action_settings)

        # View menu
        view_menu = menubar.addMenu("视图")

        self._action_zoom_in = QAction("放大", self)
        self._action_zoom_in.setShortcut(QKeySequence.StandardKey.ZoomIn)
        self._action_zoom_in.triggered.connect(self._canvas.zoom_in)
        view_menu.addAction(self._action_zoom_in)

        self._action_zoom_out = QAction("缩小", self)
        self._action_zoom_out.setShortcut(QKeySequence.StandardKey.ZoomOut)
        self._action_zoom_out.triggered.connect(self._canvas.zoom_out)
        view_menu.addAction(self._action_zoom_out)

        self._action_fit = QAction("适应窗口", self)
        self._action_fit.setShortcut(QKeySequence("Ctrl+0"))
        self._action_fit.triggered.connect(self._canvas.fit_to_window)
        view_menu.addAction(self._action_fit)

        # Help menu
        help_menu = menubar.addMenu("帮助")

        self._action_about = QAction("关于", self)
        self._action_about.triggered.connect(self._on_about)
        help_menu.addAction(self._action_about)

    def _create_toolbar(self) -> None:
        # Toolbar
        toolbar = QToolBar("主工具栏")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        # Import Script button
        self._btn_toolbar_import_script = QAction("导入剧本", self)
        self._btn_toolbar_import_script.triggered.connect(self._on_import_script)
        toolbar.addAction(self._btn_toolbar_import_script)

        # Import Images button
        self._btn_toolbar_import_images = QAction("导入图片", self)
        self._btn_toolbar_import_images.triggered.connect(self._on_import_images)
        toolbar.addAction(self._btn_toolbar_import_images)

        toolbar.addSeparator()

        # Auto Layout button
        self._btn_toolbar_auto_layout = QAction("自动排版", self)
        self._btn_toolbar_auto_layout.triggered.connect(self._on_auto_layout)
        toolbar.addAction(self._btn_toolbar_auto_layout)

        toolbar.addSeparator()

        # Export PDF button
        self._btn_toolbar_export_pdf = QAction("导出 PDF", self)
        self._btn_toolbar_export_pdf.triggered.connect(self._on_export_pdf)
        toolbar.addAction(self._btn_toolbar_export_pdf)

        # Export ZIP button
        self._btn_toolbar_export_zip = QAction("导出 ZIP", self)
        self._btn_toolbar_export_zip.triggered.connect(self._on_export_zip)
        toolbar.addAction(self._btn_toolbar_export_zip)

        toolbar.addSeparator()

        # Zoom controls
        self._btn_toolbar_zoom_in = QAction("🔍+", self)
        self._btn_toolbar_zoom_in.setToolTip("放大 (Ctrl++)")
        self._btn_toolbar_zoom_in.triggered.connect(self._canvas.zoom_in)
        toolbar.addAction(self._btn_toolbar_zoom_in)

        self._btn_toolbar_zoom_out = QAction("🔍-", self)
        self._btn_toolbar_zoom_out.setToolTip("缩小 (Ctrl+-)")
        self._btn_toolbar_zoom_out.triggered.connect(self._canvas.zoom_out)
        toolbar.addAction(self._btn_toolbar_zoom_out)

        self._btn_toolbar_fit = QAction("适应", self)
        self._btn_toolbar_fit.setToolTip("适应窗口 (Ctrl+0)")
        self._btn_toolbar_fit.triggered.connect(self._canvas.fit_to_window)
        toolbar.addAction(self._btn_toolbar_fit)

        # Page navigation
        toolbar.addSeparator()

        self._btn_toolbar_prev_page = QAction("◀", self)
        self._btn_toolbar_prev_page.setToolTip("上一页")
        self._btn_toolbar_prev_page.triggered.connect(self._on_prev_page)
        toolbar.addAction(self._btn_toolbar_prev_page)

        self._btn_toolbar_next_page = QAction("▶", self)
        self._btn_toolbar_next_page.setToolTip("下一页")
        self._btn_toolbar_next_page.triggered.connect(self._on_next_page)
        toolbar.addAction(self._btn_toolbar_next_page)

    def _create_status_bar(self) -> None:
        """Create the status bar."""
        self._status_bar = self.statusBar()

        self._status_label = QLabel("场景: 0 | 图片: 0 | 页数: 0/0")
        self._status_bar.addWidget(self._status_label)

    def _setup_connections(self) -> None:
        """Set up signal/slot connections."""
        # Scene panel connections
        self._scene_panel.importScriptClicked.connect(self._on_import_script)
        self._scene_panel.importImagesClicked.connect(self._on_import_images)
        self._scene_panel.sceneSelected.connect(self._on_scene_selected)
        self._scene_panel.generateLayoutClicked.connect(self._on_auto_layout)

        # Dialogue panel connections
        self._dialogue_panel.bubbleAdded.connect(self._on_bubble_added)
        self._dialogue_panel.bubbleRemoved.connect(self._on_bubble_removed)
        self._dialogue_panel.bubbleUpdated.connect(self._on_bubble_updated)

    def _on_import_script(self) -> None:
        """Handle import script action."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "导入剧本",
            "",
            "剧本文件 (*.txt *.docx *.json);;所有文件 (*)"
        )

        if not path:
            return

        try:
            self._script_data = parse_script(path)
            self._scene_panel.set_script_data(self._script_data)
            self._update_status()
            logger.info(f"Loaded script from {path}")
        except Exception as e:
            QMessageBox.critical(
                self,
                "错误",
                f"导入剧本失败: {str(e)}"
            )
            logger.error(f"Failed to import script: {e}")

    def _on_import_images(self) -> None:
        """Handle import images action."""
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "导入图片",
            "",
            "图片文件 (*.png *.jpg *.jpeg *.webp *.heif *.heic);;所有文件 (*)"
        )

        if not paths:
            return

        try:
            from core.image_processor import load_image
            images = []
            for path in paths:
                try:
                    img_data = load_image(path)
                    images.append(img_data)
                except Exception as e:
                    logger.warning(f"Failed to load {path}: {e}")
                    continue

            if not images:
                raise ValueError("没有找到有效的图片文件")

            self._images = images
            self._scene_panel.set_images(images)
            self._update_status()
            logger.info(f"Loaded {len(images)} images")
        except Exception as e:
            QMessageBox.critical(
                self,
                "错误",
                f"导入图片失败: {str(e)}"
            )
            logger.error(f"Failed to import images: {e}")

    def _on_auto_layout(self) -> None:
        """Handle auto layout action - runs AI-powered Pipeline."""
        if not self._script_data:
            QMessageBox.warning(
                self,
                "警告",
                "请先导入剧本"
            )
            return

        reading_direction = self._settings.get("reading_direction", "RTL")

        try:
            # Step 1: Generate base layout (scene → panel mapping)
            self._layout_data = generate_layout(
                self._script_data,
                self._images,
                reading_direction
            )

            # Step 1b: Narrative pacing analysis (geometric rhythm detection)
            # This populates self._page_rhythms for re-layout
            self._analyze_narrative_pacing(reading_direction)

            # Step 1c: Re-generate layout with rhythm awareness
            # Pass page rhythms to template selection for rhythm-aware templates
            if hasattr(self, '_page_rhythms') and self._page_rhythms:
                self._layout_data = generate_layout(
                    self._script_data,
                    self._images,
                    reading_direction,
                    page_rhythms=self._page_rhythms
                )
                logger.info(f"[LAYOUT] Re-generated layout with rhythm awareness: {self._page_rhythms}")

            # Step 1d: Image-to-scene matching (saliency detection + assignment)
            if self._images:
                self._match_images_to_panels()

            # Step 2: AI Layout Advisor - get advice for each scene
            logger.info("Running AI layout analysis...")
            ai_enabled = self._ai_advisor._llm.is_available()
            if ai_enabled:
                QMessageBox.information(
                    self,
                    "AI 布局",
                    "正在使用 AI 辅助布局决策..."
                )

            # Apply AI advice to each panel's scene data
            for page in self._layout_data.get('pages', []):
                for panel in page.get('panels', []):
                    scene = panel.get('scene', {})
                    if scene:
                        advice = self._ai_advisor.advise_scene(scene)
                        scene['layout_advice'] = advice
                        logger.info(
                            f"Scene {scene.get('scene_id')}: "
                            f"template={advice.get('template')}, "
                            f"tone={advice.get('emotional_tone')}, "
                            f"shot={advice.get('shot')}, "
                            f"source={advice.get('source')}"
                        )

            # Step 3: Refine layout (gutter, bleed, reading flow)
            self._layout_data = self._refiner.refine_layout(
                self._layout_data,
                reading_direction
            )

            self._total_pages = len(self._layout_data.get('pages', []))
            self._current_page = 1

            # Step 4: Update canvas with enriched layout
            self._canvas.set_layout(self._layout_data, self._script_data)
            self._update_status()
            logger.info(f"Generated AI layout for {self._total_pages} pages")

            QMessageBox.information(
                self,
                "成功",
                f"排版完成！\n"
                f"总页数: {self._total_pages}\n"
                f"AI辅助: {'是' if ai_enabled else '否（使用规则引擎）'}"
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                "错误",
                f"生成排版失败: {str(e)}"
            )
            logger.error(f"Failed to generate layout: {e}")

    def _analyze_narrative_pacing(self, reading_direction: str) -> None:
        """Step 1b: Analyze narrative pacing for each page using geometric features."""
        self._page_rhythms = []
        try:
            prev_rhythm = None
            page_size = (self._settings.get('page_width', 2480),
                         self._settings.get('page_height', 3507))

            for page in self._layout_data.get('pages', []):
                page_index = page.get('page_index', 0)
                panels = page.get('panels', [])

                if not panels:
                    self._page_rhythms.append('transition')
                    continue

                # Convert ratio-based panel layout to bounds-based format for analyzer
                panel_layout = self._panels_to_bounds(panels, page_size)
                panel_layout['page_index'] = page_index

                # Analyze with geometric features (vision_provider="none" → rule-based)
                result = self._pacing_analyzer.analyze_page(
                    manga_page_image="",  # no image, use geometric only
                    panel_layout=panel_layout,
                    prev_rhythm=prev_rhythm
                )

                # Inject pacing into each panel's scene
                panel_pacings = {p.get('panel_id'): p for p in result.get('panel_pacings', [])}
                for panel in panels:
                    scene = panel.get('scene', {})
                    if scene:
                        pacing = panel_pacings.get(panel.get('id', ''), {})
                        scene['pacing'] = pacing.get('pacing', 'transition')
                        scene['pacing_emotion'] = pacing.get('emotion', 'neutral')
                        scene['pacing_indicators'] = pacing.get('visual_indicators', [])
                        scene['pacing_reason'] = pacing.get('reason', '')

                # Log per-page result
                overall = result.get('overall_rhythm', 'transition')
                self._page_rhythms.append(overall)
                rhythm_label = {'climax': '🔴高潮', 'tension': '🟡紧张', 'transition': '🟢过渡', 'calm': '🔵平静'}.get(overall, overall)
                logger.info(f"[PACING] page {page_index + 1}: {rhythm_label}")

                prev_rhythm = overall

        except Exception as e:
            logger.warning(f"Narrative pacing analysis failed (non-critical): {e}")

    def _panels_to_bounds(self, panels: list, page_size: tuple) -> dict:
        """Convert ratio-based panels to bounds-based format for NarrativePacingAnalyzer."""
        w, h = page_size
        result_panels = []
        for panel in panels:
            x_ratio = panel.get('x_ratio', 0)
            y_ratio = panel.get('y_ratio', 0)
            w_ratio = panel.get('w_ratio', 1)
            h_ratio = panel.get('h_ratio', 1)
            bounds = {
                'x': int(x_ratio * w),
                'y': int(y_ratio * h),
                'w': int(w_ratio * w),
                'h': int(h_ratio * h),
            }
            gaps = panel.get('gaps', {})
            result_panels.append({
                'panel_id': panel.get('id', ''),
                'bounds': bounds,
                'gaps': {
                    'left': gaps.get('left', 0),
                    'right': gaps.get('right', 0),
                    'top': gaps.get('top', 0),
                    'bottom': gaps.get('bottom', 0),
                },
                'border_style': panel.get('border_style', 'solid'),
                'splash': panel.get('splash', False),
                'overlay': panel.get('overlay', False),
            })
        return {'panels': result_panels, 'page_size': {'w': w, 'h': h}}

    def _match_images_to_panels(self) -> None:
        """Step 1c: Match uploaded images to panels using LLM or rules, pre-compute saliency."""
        try:
            matcher = ImageMatcher(
                images=self._images,
                script_data=self._script_data,
                layout_data=self._layout_data,
                llm_client=self._ai_advisor._llm,
            )
            assignments = matcher.match()

            # Build panel_id → assignment lookup
            assign_map = {a['panel_id']: a for a in assignments}

            # Inject image_ref + salient_region into each panel
            matched = 0
            for page in self._layout_data.get('pages', []):
                for panel in page.get('panels', []):
                    panel_id = panel.get('id', '')
                    if panel_id in assign_map:
                        a = assign_map[panel_id]
                        panel['image_ref'] = a.get('image_ref', '')
                        panel['salient_region'] = a.get('salient_region', (0, 0, 0, 0))
                        panel['importance'] = a.get('importance', 'medium')
                        matched += 1

            logger.info(f"[IMAGE MATCH] assigned images to {matched} panels")
        except Exception as e:
            logger.warning(f"Image matching failed (non-critical): {e}")

    def _on_export_pdf(self) -> None:
        """Handle export PDF action."""
        if not self._layout_data:
            QMessageBox.warning(
                self,
                "警告",
                "请先生成排版"
            )
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export PDF",
            "",
            "PDF Files (*.pdf)"
        )

        if not path:
            return

        try:
            page_size_name = self._settings.get("page_size", "A4")
            reading_direction = self._settings.get("reading_direction", "RTL")

            from utils.export import get_page_size
            page_size_mm = get_page_size(page_size_name)

            text_elements = {}  # Get from dialogue panel

            success = export_pdf(
                self._layout_data,
                self._images,
                text_elements,
                path,
                page_size_mm,
                reading_direction
            )

            if success:
                QMessageBox.information(
                    self,
                    "成功",
                    f"PDF 已导出至 {path}"
                )
                self.exportCompleted.emit(path)
            else:
                raise RuntimeError("Export failed")
        except Exception as e:
            QMessageBox.critical(
                self,
                "错误",
                f"导出 PDF 失败: {str(e)}"
            )
            logger.error(f"Failed to export PDF: {e}")

    def _on_export_zip(self) -> None:
        """Handle export ZIP action."""
        if not self._layout_data:
            QMessageBox.warning(
                self,
                "警告",
                "请先生成排版"
            )
            return

        directory = QFileDialog.getExistingDirectory(
            self,
            "Export ZIP",
            "",
            QFileDialog.Option.ShowDirsOnly
        )

        if not directory:
            return

        try:
            reading_direction = self._settings.get("reading_direction", "RTL")
            zip_format = self._settings.get("zip_format", "PNG")

            text_elements = {}  # Get from dialogue panel

            success = export_zip(
                self._layout_data,
                self._images,
                text_elements,
                directory,
                reading_direction,
                zip_format
            )

            if success:
                QMessageBox.information(
                    self,
                    "成功",
                    f"ZIP 已导出至 {directory}"
                )
                self.exportCompleted.emit(directory)
            else:
                raise RuntimeError("Export failed")
        except Exception as e:
            QMessageBox.critical(
                self,
                "错误",
                f"导出 ZIP 失败: {str(e)}"
            )
            logger.error(f"Failed to export ZIP: {e}")

    def _on_scene_selected(self, scene_id: str) -> None:
        """Handle scene selection."""
        self._current_scene_id = scene_id
        scene = self._scene_panel.get_current_scene()
        if scene:
            self._dialogue_panel.load_scene_dialogue(scene)
            self.sceneSelected.emit(scene_id)
            # Refresh canvas to redraw bubbles for the updated scene
            if self._layout_data:
                self._canvas.load_page(
                    self._current_page - 1,
                    self._layout_data,
                    self._script_data or {}
                )
            logger.info(f"Selected scene: {scene_id}")

    def _on_bubble_added(self, bubble_data: Dict[str, Any]) -> None:
        """Handle bubble added in dialogue panel — update script data and refresh canvas."""
        if not self._current_scene_id or not self._script_data:
            return
        # Find the current scene in script_data and update its dialogue_lines
        for page in self._script_data.get('pages', []):
            for scene in page.get('scenes', []):
                if scene.get('scene_id') == self._current_scene_id:
                    scene.setdefault('dialogue_lines', []).append({
                        'character': bubble_data.get('character', 'Unknown'),
                        'text': bubble_data.get('text', ''),
                    })
                    scene['dialogue_count'] = len(scene['dialogue_lines'])
                    break
        # Refresh canvas
        if self._layout_data:
            self._canvas.load_page(
                self._current_page - 1,
                self._layout_data,
                self._script_data or {}
            )

    def _on_bubble_removed(self, index: int) -> None:
        """Handle bubble removed — update script data and refresh canvas."""
        if not self._current_scene_id or not self._script_data:
            return
        for page in self._script_data.get('pages', []):
            for scene in page.get('scenes', []):
                if scene.get('scene_id') == self._current_scene_id:
                    lines = scene.get('dialogue_lines', [])
                    if 0 <= index < len(lines):
                        lines.pop(index)
                        scene['dialogue_count'] = len(lines)
                    break
        if self._layout_data:
            self._canvas.load_page(
                self._current_page - 1,
                self._layout_data,
                self._script_data or {}
            )

    def _on_bubble_updated(self, index: int, bubble_data: Dict[str, Any]) -> None:
        """Handle bubble updated — update script data and refresh canvas."""
        if not self._current_scene_id or not self._script_data:
            return
        for page in self._script_data.get('pages', []):
            for scene in page.get('scenes', []):
                if scene.get('scene_id') == self._current_scene_id:
                    lines = scene.get('dialogue_lines', [])
                    if 0 <= index < len(lines):
                        lines[index] = {
                            'character': bubble_data.get('character', 'Unknown'),
                            'text': bubble_data.get('text', ''),
                        }
                    break
        if self._layout_data:
            self._canvas.load_page(
                self._current_page - 1,
                self._layout_data,
                self._script_data or {}
            )

    def _on_prev_page(self) -> None:
        """Go to previous page."""
        if self._current_page > 1:
            self._current_page -= 1
            if self._layout_data:
                self._canvas.load_page(
                    self._current_page - 1,
                    self._layout_data,
                    self._script_data or {}
                )
            self._update_status()

    def _on_next_page(self) -> None:
        """Go to next page."""
        if self._layout_data and self._current_page < self._total_pages:
            self._current_page += 1
            self._canvas.load_page(
                self._current_page - 1,
                self._layout_data,
                self._script_data or {}
            )
            self._update_status()

    def _on_settings(self) -> None:
        """Handle settings action."""
        from ui.dialogs.settings_dialog import SettingsDialog
        dialog = SettingsDialog(self._settings, self)
        if dialog.exec():
            # Get updated settings from dialog (dialog has its own dict copy)
            self._settings.update(dialog.get_settings())
            # Reload LLM config after settings change
            llm_provider_name = self._settings.get('llm_provider', 'MiniMax')
            provider_map = {
                'MiniMax': LLMProvider.MINIMAX,
                'OpenAI (兼容)': LLMProvider.OPENAI,
                'Ollama (本地)': LLMProvider.OLLAMA,
            }
            llm_provider = provider_map.get(llm_provider_name, LLMProvider.MINIMAX)
            llm_api_key = self._settings.get('llm_api_key') or None
            llm_api_url = self._settings.get('llm_api_url') or None
            llm_model = self._settings.get('llm_model') or None

            self._ai_advisor = AILayoutAdvisor(
                provider=llm_provider,
                api_key=llm_api_key,
                api_url=llm_api_url,
                model=llm_model,
            )
            logger.info("LLM advisor reinitialized after settings change")

    def _on_about(self) -> None:
        """Handle about action."""
        QMessageBox.about(
            self,
            "关于 MangaAutoLayout",
            "MangaAutoLayout v1.0\n\n"
            "漫画/连环画自动排版工具\n\n"
            "功能：\n"
            "• 剧本解析\n"
            "• 自动排版\n"
            "• PDF/ZIP 导出\n"
            "• RTL 阅读方向支持"
        )

    def _update_status(self) -> None:
        """Update status bar."""
        scene_count = self._scene_panel.get_scene_count()
        image_count = self._scene_panel.get_image_count()
        self._status_label.setText(
            f"Scenes: {scene_count} | Images: {image_count} | "
            f"Page: {self._current_page}/{self._total_pages}"
        )