"""
Canvas widget for rendering manga pages.
Uses PyQt6 QGraphicsView and QGraphicsScene.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

from PyQt5.QtCore import Qt, QRectF, QPointF, pyqtSignal
from PyQt5.QtGui import (
    QPen, QBrush, QColor, QPainter, QPixmap, QFont,
    QFontMetrics, QTransform, QPolygonF
)
from PyQt5.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsItem,
    QGraphicsRectItem, QGraphicsPixmapItem, QGraphicsTextItem,
    QGraphicsPolygonItem,
    QScrollBar, QWidget
)

logger = logging.getLogger(__name__)


class PanelItem(QGraphicsRectItem):
    """Graphics item for a manga panel."""

    def __init__(self, x: int, y: int, w: int, h: int, panel_data: Dict[str, Any]):
        super().__init__(x, y, w, h)
        self.panel_data = panel_data

        # Set appearance
        self.setPen(QPen(QColor(0, 0, 0), 2))
        self.setBrush(QBrush(QColor(255, 255, 255)))

        # Allow selection
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, True)

    def get_panel_id(self) -> str:
        """Get panel ID."""
        return self.panel_data.get('id', '')


class ImagePanelItem(QGraphicsRectItem):
    """Graphics item for panel with image."""

    def __init__(
        self,
        x: int,
        y: int,
        w: int,
        h: int,
        panel_data: Dict[str, Any],
        pixmap: Optional[QPixmap] = None
    ):
        super().__init__(x, y, w, h)
        self.panel_data = panel_data
        self._pixmap = pixmap

        # Set appearance
        self.setPen(QPen(QColor(0, 0, 0), 2))
        if pixmap and not pixmap.isNull():
            self.setBrush(QBrush(pixmap))
        else:
            self.setBrush(QBrush(QColor(240, 240, 240)))

        # Allow selection
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, True)

    def setPixmap(self, pixmap: QPixmap) -> None:
        """Set the panel image."""
        self._pixmap = pixmap
        if pixmap and not pixmap.isNull():
            self.setBrush(QBrush(pixmap))
        self.update()


class SlantedPanelItem(QGraphicsPolygonItem):
    """
    Graphics item for a manga panel with slanted (parallelogram) shape.
    Used for dynamic/tilted layouts that create diagonal visual flow.
    """

    def __init__(
        self,
        x: int,
        y: int,
        w: int,
        h: int,
        panel_data: Dict[str, Any],
        slant_angle: float = 15.0
    ):
        self.panel_data = panel_data
        self._slant_angle = slant_angle

        # Build parallelogram polygon
        # Clamp slant to avoid collapse
        dx = max(int(w * 0.08), min(int(w * 0.4), int(w * slant_angle / 100)))
        # Top edge: (x, y) to (x + w, y)
        # Right edge: (x + w, y) to (x + w - dx, y + h)
        # Bottom edge: (x + w - dx, y + h) to (x - dx, y + h)
        # Left edge: (x - dx, y + h) to (x, y)
        polygon_points = [
            QPointF(x, y),
            QPointF(x + w, y),
            QPointF(x + w - dx, y + h),
            QPointF(x - dx, y + h),
        ]
        super().__init__(polygon_points)

        self.setPen(QPen(QColor(0, 0, 0), 2))
        self.setBrush(QBrush(QColor(245, 245, 245)))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, True)

    def get_panel_id(self) -> str:
        """Get panel ID."""
        return self.panel_data.get('id', '')


class BleedPanelItem(QGraphicsRectItem):
    """
    Graphics item for a panel that bleeds to page edge.
    Drawn with thicker border to emphasize the 破格 effect.
    """

    def __init__(self, x: int, y: int, w: int, h: int, panel_data: Dict[str, Any]):
        super().__init__(x, y, w, h)
        self.panel_data = panel_data
        self.setPen(QPen(QColor(0, 0, 0), 4))  # thicker border for 破格
        self.setBrush(QBrush(QColor(240, 240, 240)))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, True)

    def get_panel_id(self) -> str:
        return self.panel_data.get('id', '')


class DialogueBubbleItem(QGraphicsRectItem):
    """Graphics item for dialogue bubble."""

    def __init__(self, x: int, y: int, w: int, h: int, bubble_data: Dict[str, Any]):
        super().__init__(x, y, w, h)
        self.bubble_data = bubble_data
        self.bubble_type = bubble_data.get('type', 'normal')

        # Set appearance based on type
        if self.bubble_type == 'whisper':
            self.setPen(QPen(QColor(150, 150, 150), 1, Qt.DashLine))
            self.setBrush(QBrush(QColor(255, 255, 255, 200)))
        else:
            self.setPen(QPen(QColor(0, 0, 0), 2))
            self.setBrush(QBrush(QColor(255, 255, 255)))

            if self.bubble_type == 'shout':
                self.setPen(QPen(QColor(0, 0, 0), 3))


class SFXTextItem(QGraphicsTextItem):
    """Graphics item for SFX text."""

    def __init__(self, x: int, y: int, text: str, style: str = 'normal'):
        super().__init__(text)
        self.setPos(x, y)

        # Set font and style
        font = QFont()
        if style == 'bold':
            font.setWeight(QFont.Weight.Bold)
            self.setFont(QFont(font.family(), 24, QFont.Weight.Bold))
        else:
            self.setFont(QFont(font.family(), 16))

        self.setDefaultTextColor(QColor(0, 0, 0))


class ReadingOrderItem(QGraphicsTextItem):
    """Graphics item for reading order number."""

    def __init__(self, x: int, y: int, order: int):
        super().__init__(str(order))
        self.setPos(x, y)

        font = QFont()
        font.setPointSize(10)
        font.setWeight(QFont.Weight.Bold)
        self.setFont(font)
        self.setDefaultTextColor(QColor(100, 100, 100))


class MangaCanvas(QGraphicsView):
    """Canvas for rendering manga page layout."""

    # Signals
    panelClicked = pyqtSignal(str)  # panel_id
    zoomChanged = pyqtSignal(float)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        # Set up scene
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)

        # State
        self._current_page = 0
        self._total_pages = 0
        self._layout_data: Optional[Dict[str, Any]] = None
        self._script_data: Optional[Dict[str, Any]] = None
        self._zoom = 1.0

        # Page dimensions (A4 at 300 DPI)
        self._page_width = 2480  # ~210mm at 300dpi
        self._page_height = 3508  # ~297mm at 300dpi

        # Image cache to avoid reloading the same image on every paint
        self._pixmap_cache: Dict[str, QPixmap] = {}

        # Set up view
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        # Optimized rendering: only repaint changed regions
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.BoundingRectViewportUpdate)
        self.setBackgroundBrush(QColor(180, 180, 180))
        self.setForegroundBrush(QBrush(QColor(180, 180, 180)))


        # Enable anti-aliasing (only for final output)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setRenderHint(QPainter.RenderHint.LosslessImageRendering)

        logger.info("Canvas initialized")

    def set_page_size(self, width: int, height: int) -> None:
        """Set page dimensions in pixels."""
        self._page_width = width
        self._page_height = height
        self._scene.setSceneRect(0, 0, width, height)
        self._pixmap_cache.clear()
        self.resetTransform()
        self.fitInView(self._scene.sceneRect(), Qt.KeepAspectRatio)

    def load_page(
        self,
        page_index: int,
        layout_data: Dict[str, Any],
        script_data: Dict[str, Any]
    ) -> None:
        """Load and render a page."""
        self._current_page = page_index
        self._layout_data = layout_data
        self._script_data = script_data

        pages = layout_data.get('pages', [])
        if page_index >= len(pages):
            logger.warning(f"Page index {page_index} out of range")
            return

        self._total_pages = len(pages)
        page = pages[page_index]

        # Clear scene efficiently
        self._scene.clear()

        # Draw page background
        self._draw_page_background()

        # Draw panels
        panels = page.get('panels', [])
        for panel in panels:
            self._draw_panel(panel)

        # Draw dialogue bubbles
        script_pages = script_data.get('pages', [])
        self._draw_dialogue_bubbles(script_pages, page_index, panels)

        # Draw reading order numbers
        self._draw_reading_order(panels)

        self._scene.update()
        logger.info(f"Loaded page {page_index + 1}/{self._total_pages}")

    def _draw_dialogue_bubbles(
        self,
        script_pages: List[Dict[str, Any]],
        page_index: int,
        panels: List[Dict[str, Any]]
    ) -> None:
        """Draw dialogue bubbles for all scenes on this page."""
        if page_index >= len(script_pages):
            return

        page_scenes = script_pages[page_index].get('scenes', [])
        if not page_scenes:
            return

        # Round-robin bubbles across panels
        active_panels = [p for p in panels if p.get('reading_order') is not None]
        if not active_panels:
            active_panels = panels

        bubble_idx = 0
        for scene in page_scenes:
            dialogue_lines = scene.get('dialogue_lines', [])
            for line in dialogue_lines:
                panel = active_panels[bubble_idx % len(active_panels)]
                self._draw_bubble_in_panel(panel, line)
                bubble_idx += 1

    def _draw_bubble_in_panel(
        self,
        panel: Dict[str, Any],
        dialogue_line: Dict[str, Any]
    ) -> None:
        """Draw a single dialogue bubble inside a panel."""
        x_ratio = panel.get('x_ratio', 0)
        y_ratio = panel.get('y_ratio', 0)
        w_ratio = panel.get('w_ratio', 1)
        h_ratio = panel.get('h_ratio', 1)

        px = int(x_ratio * self._page_width)
        py = int(y_ratio * self._page_height)
        pw = int(w_ratio * self._page_width)
        ph = int(h_ratio * self._page_height)

        # Position bubble in upper-left of panel
        margin = int(pw * 0.05)
        bx = px + margin
        by = py + margin
        bw = max(int(pw * 0.55), 80)
        bh = max(int(ph * 0.22), 40)

        # Bubble background
        bubble_rect = QGraphicsRectItem(bx, by, bw, bh)
        bubble_rect.setPen(QPen(QColor(0, 0, 0), 2))
        bubble_rect.setBrush(QBrush(QColor(255, 255, 255)))
        self._scene.addItem(bubble_rect)

        text = dialogue_line.get('text', '')
        if not text:
            return

        character = dialogue_line.get('character', '')
        font_size = max(9, min(14, int(bw / (len(text) * 0.8 + len(character) * 1.2))))

        # Character name
        name_item = QGraphicsTextItem(character, bubble_rect)
        name_item.setFont(QFont('Microsoft YaHei', font_size, QFont.Weight.Bold))
        name_item.setDefaultTextColor(QColor(0, 0, 0))
        name_item.setPos(bx + 5, by + 3)
        name_item.setTextWidth(bw - 10)

        # Dialogue text (truncated to fit)
        display_text = text if len(text) <= 35 else text[:33] + '…'
        text_item = QGraphicsTextItem(display_text, bubble_rect)
        text_item.setFont(QFont('Microsoft YaHei', font_size))
        text_item.setDefaultTextColor(QColor(30, 30, 30))
        text_item.setPos(bx + 5, by + font_size + 6)
        text_item.setTextWidth(bw - 10)
        text_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)

    def _draw_page_background(self) -> None:
        """Draw white page background."""
        bg = QGraphicsRectItem(0, 0, self._page_width, self._page_height)
        bg.setPen(QPen(Qt.NoPen))
        bg.setBrush(QBrush(QColor(255, 255, 255)))
        self._scene.addItem(bg)

    def _draw_panel(self, panel: Dict[str, Any]) -> None:
        """Draw a single panel with shape effects (slanted/bleed/rect)."""
        shape = panel.get('shape', 'rect')
        bleed_edge = panel.get('bleed_edge')
        slant_angle = panel.get('slant_angle', 0)
        x_ratio = panel.get('x_ratio', 0)
        y_ratio = panel.get('y_ratio', 0)
        w_ratio = panel.get('w_ratio', 1)
        h_ratio = panel.get('h_ratio', 1)

        x = int(x_ratio * self._page_width)
        y = int(y_ratio * self._page_height)
        w = int(w_ratio * self._page_width)
        h = int(h_ratio * self._page_height)
        w = max(w, 10)
        h = max(h, 10)

        # Try to load image (with cache)
        scaled_pixmap = None
        image_ref = panel.get('image_ref')
        if image_ref:
            # Check cache first
            cache_key = f"{image_ref}:{w}x{h}"
            if cache_key in self._pixmap_cache:
                scaled_pixmap = self._pixmap_cache[cache_key]
            else:
                try:
                    pixmap = QPixmap(image_ref)
                    if not pixmap.isNull():
                        scaled_pixmap = pixmap.scaled(
                            w, h,
                            Qt.IgnoreAspectRatio,
                            Qt.SmoothTransformation
                        )
                        # Cache the scaled result
                        if len(self._pixmap_cache) < 200:
                            self._pixmap_cache[cache_key] = scaled_pixmap
                except Exception as e:
                    logger.warning(f"Failed to load image {image_ref}: {e}")

        # --- Slanted panels (parallelogram) ---
        if shape == 'slanted':
            panel_item = SlantedPanelItem(x, y, w, h, panel, slant_angle)
            self._scene.addItem(panel_item)
            if scaled_pixmap and not scaled_pixmap.isNull():
                # Cannot clip pixmap to polygon in basic QGraphicsView
                # Draw image as separate item clipped by panel shape
                pass
            self._add_scene_description(panel, panel_item)
            return

        # --- Bleed panels ---
        if bleed_edge and bleed_edge != 'none':
            panel_item = BleedPanelItem(x, y, w, h, panel)
            self._scene.addItem(panel_item)
            self._add_scene_description(panel, panel_item)
            return

        # --- Standard panels (rect) ---
        if scaled_pixmap and not scaled_pixmap.isNull():
            panel_item = ImagePanelItem(x, y, w, h, panel, scaled_pixmap)
        else:
            panel_item = QGraphicsRectItem(x, y, w, h)
            panel_item.setPen(QPen(QColor(0, 0, 0), 2))
            panel_item.setBrush(QBrush(QColor(240, 240, 240)))
            panel_item.setData(0, panel.get('id', ''))
        panel_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self._scene.addItem(panel_item)
        self._add_scene_description(panel, panel_item)

    def _add_scene_description(
        self,
        panel: Dict[str, Any],
        parent_item: QGraphicsItem
    ) -> None:
        """Add scene description text at bottom of panel."""
        scene = panel.get('scene', {})
        description = scene.get('description', '')
        if not description:
            return

        x = int(panel.get('x_ratio', 0) * self._page_width)
        y = int(panel.get('y_ratio', 0) * self._page_height)
        w = int(panel.get('w_ratio', 1) * self._page_width)
        h = int(panel.get('h_ratio', 1) * self._page_height)

        display_text = description[:80] + ('...' if len(description) > 80 else '')
        text_item = QGraphicsTextItem(display_text, parent_item)
        text_item.setFont(QFont('Microsoft YaHei', max(8, int(h * 0.02))))
        text_item.setDefaultTextColor(QColor(255, 255, 255))
        text_item.setPos(x + 5, y + h - int(h * 0.05) - 20)
        text_item.setTextWidth(w - 10)
        text_item.setTextInteractionFlags(Qt.NoTextInteraction)
        y_ratio = panel.get('y_ratio', 0)
        w_ratio = panel.get('w_ratio', 1)
        h_ratio = panel.get('h_ratio', 1)
        x = int(x_ratio * self._page_width)
        y = int(y_ratio * self._page_height)
        w = int(w_ratio * self._page_width)
        h = int(h_ratio * self._page_height)

    def _draw_reading_order(self, panels: List[Dict[str, Any]]) -> None:
        """Draw reading order numbers."""
        for panel in panels:
            order = panel.get('reading_order')
            if order:
                x_ratio = panel.get('x_ratio', 0)
                y_ratio = panel.get('y_ratio', 0)
                x = int(x_ratio * self._page_width) + 5
                y = int(y_ratio * self._page_height) + 5
                order_item = ReadingOrderItem(x, y, order)
                self._scene.addItem(order_item)

    def set_current_page(self, index: int) -> None:
        """Navigate to a specific page."""
        if self._layout_data and 0 <= index < self._total_pages:
            pages = self._layout_data['pages']
            script_pages = self._script_data.get('pages', []) if self._script_data else []
            self.load_page(index, {'pages': pages}, {'pages': script_pages})

    def next_page(self) -> None:
        """Go to next page."""
        if self._current_page < self._total_pages - 1:
            self.set_current_page(self._current_page + 1)

    def prev_page(self) -> None:
        """Go to previous page."""
        if self._current_page > 0:
            self.set_current_page(self._current_page - 1)

    def zoom_in(self) -> None:
        """Zoom in."""
        self._zoom = min(3.0, self._zoom * 1.2)
        self.scale(1.2, 1.2)
        self.zoomChanged.emit(self._zoom)

    def zoom_out(self) -> None:
        """Zoom out."""
        self._zoom = max(0.3, self._zoom / 1.2)
        self.scale(1/1.2, 1/1.2)
        self.zoomChanged.emit(self._zoom)

    def fit_page(self) -> None:
        """Fit page in view."""
        self.resetTransform()
        rect = QRectF(0, 0, self._page_width, self._page_height)
        self.fitInView(rect, Qt.KeepAspectRatio)
        self._zoom = 1.0
        self.zoomChanged.emit(self._zoom)

    def fit_to_window(self) -> None:
        """Alias for fit_page."""
        self.fit_page()

    def set_layout(self, layout_data: Dict[str, Any], script_data: Optional[Dict[str, Any]] = None) -> None:
        """Set layout data and render first page."""
        self._layout_data = layout_data
        self._script_data = script_data
        pages = layout_data.get('pages', [])
        self._total_pages = len(pages)

        if pages:
            self.load_page(0, layout_data, script_data or {})
            self.fit_page()
        else:
            # No pages — show empty scene and auto-fit
            self._scene.clear()
            self._draw_page_background()
            self.fit_page()

    def get_current_page(self) -> int:
        """Get current page index."""
        return self._current_page

    def get_total_pages(self) -> int:
        """Get total page count."""
        return self._total_pages

    def mousePressEvent(self, event):
        """Handle mouse press for panel selection."""
        super().mousePressEvent(event)

        # Check if we clicked a panel
        items = self._scene.selectedItems()
        if items:
            for item in items:
                if isinstance(item, (PanelItem, ImagePanelItem)):
                    self.panelClicked.emit(item.get_panel_id())
                    break

    def keyPressEvent(self, event):
        """Handle keyboard navigation."""
        if event.key() == Qt.Key.Key_Right or event.key() == Qt.Key.Key_Down:
            self.next_page()
        elif event.key() == Qt.Key.Key_Left or event.key() == Qt.Key.Key_Up:
            self.prev_page()
        elif event.key() == Qt.Key.Key_Plus:
            self.zoom_in()
        elif event.key() == Qt.Key.Key_Minus:
            self.zoom_out()
        elif event.key() == Qt.Key.Key_F:
            self.fit_page()
        else:
            super().keyPressEvent(event)


# Alias for backwards compatibility
CanvasWidget = MangaCanvas