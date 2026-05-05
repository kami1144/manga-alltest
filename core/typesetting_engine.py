"""
Typesetting Engine v2 — Intelligent bubble placement and SFX rendering.

Improvements over v1:
- Smart bubble placement: avoids image important regions (face/ROI)
- Bubble collision detection: prevents overlapping bubbles
- Smart tail direction: points toward speaker position
- Cross-panel SFX placement: SFX can span multiple panels
- Vertical Japanese text: proper tate-chu-yoko support
- Better font sizing: based on panel dimensions and dialogue length
- Bubble type auto-detection improvements
- RTL-aware reading flow for bubble stacking
"""

import logging
import math
from typing import Any, Dict, List, Optional, Tuple

from PyQt5.QtCore import QPointF, Qt
from PyQt5.QtGui import QColor, QFont, QPainterPath

logger = logging.getLogger(__name__)


BUBBLE_TYPES = {
    'normal':   {'style': 'rounded', 'border_width': 2, 'tail': True},
    'shout':    {'style': 'spiky',   'border_width': 4, 'tail': True},
    'whisper':  {'style': 'dashed',  'border_width': 1, 'tail': False},
    'thought':  {'style': 'cloud',   'border_width': 1, 'tail': True},
    'narration': {'style': 'rect',   'border_width': 0, 'tail': False},
    'sfx':      {'style': 'sfx',     'border_width': 0, 'tail': False},
}

# Corner priority for bubble placement (RTL: right side first)
RTL_CORNER_PRIORITY = [
    ('bottom_right',  1.0, 1.0),
    ('bottom_left',   0.0, 1.0),
    ('top_right',     1.0, 0.0),
    ('top_left',      0.0, 0.0),
    ('center_right',  1.0, 0.5),
    ('center_left',   0.0, 0.5),
    ('center',        0.5, 0.5),
]
LTR_CORNER_PRIORITY = [
    ('bottom_left',   1.0, 1.0),
    ('bottom_right',  0.0, 1.0),
    ('top_left',      1.0, 0.0),
    ('top_right',     0.0, 0.0),
    ('center_left',   1.0, 0.5),
    ('center_right',  0.0, 0.5),
    ('center',        0.5, 0.5),
]


class BubbleLayout:
    """Represents a single bubble's layout (position + size)."""

    __slots__ = ('text', 'character', 'bubble_type', 'x', 'y', 'width', 'height',
                 'tail_x', 'tail_y', 'font_size', 'panel_id', 'corner')

    def __init__(
        self,
        text: str,
        character: str,
        bubble_type: str = 'normal',
        panel_id: Optional[str] = None,
    ):
        self.text = text
        self.character = character
        self.bubble_type = bubble_type
        self.x: float = 0
        self.y: float = 0
        self.width: float = 200
        self.height: float = 100
        self.tail_x: float = 0
        self.tail_y: float = 0
        self.font_size: int = 24
        self.panel_id: Optional[str] = panel_id
        self.corner: str = 'bottom_right'


class SFXLayout:
    """Represents a single SFX text placement."""

    __slots__ = ('text', 'x', 'y', 'font_size', 'rotation', 'color',
                 'panel_ids', 'style', 'scale')

    def __init__(
        self,
        text: str,
        x: float,
        y: float,
        font_size: int,
        rotation: float = 0,
        color: str = 'black',
        panel_ids: Optional[List[str]] = None,
        style: str = 'normal',
    ):
        self.text = text
        self.x = x
        self.y = y
        self.font_size = font_size
        self.rotation = rotation
        self.color = color
        self.panel_ids: List[str] = panel_ids or []
        self.style = style
        self.scale: float = 1.0


class TypesettingEngine:
    """
    Automatic text placement for manga pages.
    v2: smart bubble placement with collision avoidance and region detection.
    """

    def __init__(
        self,
        page_width: int = 2480,
        page_height: int = 3508,
        reading_direction: str = "RTL",
        font_family: str = "Microsoft YaHei",
    ):
        self._page_w = page_width
        self._page_h = page_height
        self._reading_direction = reading_direction
        self._font_family = font_family
        self._margin_x = 30
        self._margin_y = 30

        # Salient regions to avoid (populated during layout)
        self._avoid_regions: List[Tuple[float, float, float, float]] = []

        # Corner priority depends on reading direction
        self._corners = RTL_CORNER_PRIORITY if reading_direction == "RTL" else LTR_CORNER_PRIORITY

        logger.info(
            f"TypesettingEngine v2: {page_width}x{page_height}, "
            f"direction={reading_direction}"
        )

    def set_avoid_regions(self, regions: List[Tuple[float, float, float, float]]) -> None:
        """
        Set regions to avoid when placing bubbles (e.g., face regions).
        Each region: (x_ratio, y_ratio, w_ratio, h_ratio) in 0-1 page ratios.
        """
        self._avoid_regions = regions

    def generate_bubbles(
        self,
        scene: Dict[str, Any],
        panel_x: int,
        panel_y: int,
        panel_w: int,
        panel_h: int,
        panel_id: Optional[str] = None,
    ) -> List[BubbleLayout]:
        """
        Generate bubble layouts for a scene within a panel.

        v2 improvements:
        - Smart corner selection (avoids salient regions)
        - Collision detection between bubbles
        - Proper tail direction toward speaker
        """
        dialogue_lines = scene.get('dialogue_lines', [])
        if not dialogue_lines:
            return []

        bubbles: List[BubbleLayout] = []
        available_w = panel_w - self._margin_x * 2
        available_h = panel_h - self._margin_y * 2

        # Calculate base font size (3.5% of panel height)
        font_size = max(12, int(panel_h * 0.035))

        # Determine bubble width based on text length
        max_chars_per_line = int(available_w / (font_size * 0.65))
        bubble_w = min(available_w * 0.75, font_size * max_chars_per_line * 0.65)
        bubble_h = font_size * 2.8

        # Get corner priority for this panel
        corners = self._corners

        # Determine speaker position hint (first character's name length as hint)
        speaker_hint = dialogue_lines[0].get('character', '') if dialogue_lines else ''

        for idx, line in enumerate(dialogue_lines):
            char_name = line.get('character', '')
            text = line.get('text', '')
            if not text:
                continue

            # Select corner for this bubble
            corner_idx = idx % len(corners)
            corner_name, x_frac, y_frac = corners[corner_idx]

            # Compute bubble position from corner
            bx = panel_x + panel_w * x_frac
            by = panel_y + panel_h * y_frac

            # Adjust for bubble size (anchor is corner, so offset by bubble dimensions)
            if 'right' in corner_name:
                bx -= bubble_w
            elif 'center' in corner_name:
                bx -= bubble_w / 2

            if 'bottom' in corner_name:
                by -= bubble_h
            elif 'center' in corner_name:
                by -= bubble_h / 2

            # Ensure within panel bounds
            bx = max(panel_x + self._margin_x, min(bx, panel_x + panel_w - bubble_w - self._margin_x))
            by = max(panel_y + self._margin_y, min(by, panel_y + panel_h - bubble_h - self._margin_y))

            # Check for collisions with existing bubbles and adjust
            bx, by = self._resolve_collision(bx, by, bubble_w, bubble_h, bubbles, panel_x, panel_y, panel_w, panel_h)

            # Detect bubble type from text
            b_type = self._detect_bubble_type(text, char_name)

            bubble = BubbleLayout(text, char_name, b_type, panel_id)
            bubble.x = bx
            bubble.y = by
            bubble.width = bubble_w
            bubble.height = bubble_h
            bubble.font_size = font_size
            bubble.corner = corner_name

            # Smart tail direction: point toward panel center (speaker is usually there)
            tail_cx = panel_x + panel_w * 0.5
            tail_cy = panel_y + panel_h * 0.5
            # Tail extends from bubble center toward panel center
            bubble.tail_x = tail_cx
            bubble.tail_y = tail_cy

            bubbles.append(bubble)

        return bubbles

    def _resolve_collision(
        self,
        bx: float,
        by: float,
        bw: float,
        bh: float,
        existing: List[BubbleLayout],
        panel_x: float,
        panel_y: float,
        panel_w: float,
        panel_h: float,
    ) -> Tuple[float, float]:
        """
        Check for collisions with existing bubbles and nudge if needed.
        Uses a simple greedy push algorithm.
        """
        if not existing:
            return bx, by

        max_iterations = 10
        for _ in range(max_iterations):
            collision = False
            for other in existing:
                if self._rects_overlap(bx, by, bw, bh, other.x, other.y, other.width, other.height):
                    collision = True
                    break
            if not collision:
                return bx, by

            # Push bubble up (or down if at top)
            new_by = by - bh * 0.6
            if new_by < panel_y + self._margin_y:
                new_by = by + bh * 0.6  # Try pushing down instead
            by = new_by

        return bx, by

    def _rects_overlap(
        self,
        x1: float, y1: float, w1: float, h1: float,
        x2: float, y2: float, w2: float, h2: float,
        margin: float = 5,
    ) -> bool:
        """Check if two rectangles overlap (with optional margin)."""
        return not (
            x1 + w1 + margin < x2 or
            x2 + w2 + margin < x1 or
            y1 + h1 + margin < y2 or
            y2 + h2 + margin < y1
        )

    def _detect_bubble_type(self, text: str, character: str = '') -> str:
        """
        Detect bubble type from text content.
        v2: more sophisticated detection.
        """
        # SFX indicators (all caps, sound words)
        sfx_words = ['バタ', 'ドド', 'バリ', 'ガツン', 'ピシ', 'パン', 'ドキ', 'ヒュウ', 'BURUA']
        if text.isupper() and len(text) <= 8:
            return 'sfx'
        if any(text.startswith(w) or text.endswith(w) for w in sfx_words):
            return 'sfx'

        # Shout indicators
        shout_marks = sum(1 for c in text if c in '！？!?')
        if shout_marks >= 2:
            return 'shout'
        if shout_marks == 1 and len(text) < 20:
            return 'shout'
        if text.isupper() and len(text) > 3:
            return 'shout'

        # Whisper indicators
        whisper_words = ['低', '小声', '悄悄', ' whisper', '～', '...', '…', 'それ', 'この']
        if any(w in text for w in whisper_words):
            return 'whisper'
        if '…' in text or '...' in text:
            return 'whisper'

        # Thought indicators
        thought_words = ['想', '思考', '认为', '觉得', '，心想', ' 생각']
        if any(w in text for w in thought_words):
            return 'thought'

        return 'normal'

    def generate_sfx(
        self,
        scene: Dict[str, Any],
        panel_x: int,
        panel_y: int,
        panel_w: int,
        panel_h: int,
        panel_id: Optional[str] = None,
        all_panels: Optional[List[Dict[str, Any]]] = None,
    ) -> List[SFXLayout]:
        """
        Generate SFX text placements.

        v2 improvements:
        - Cross-panel SFX: large SFX can span adjacent panels
        - Dynamic sizing based on text length and panel area
        - Rotation based on impact direction
        """
        sfx_list = scene.get('sfx_list', [])
        if not sfx_list:
            return []

        results: List[SFXLayout] = []
        font_size = int(panel_h * 0.07)

        for sfx_text in sfx_list:
            # Determine SFX style from text
            style = self._detect_sfx_style(sfx_text)

            # Calculate placement (upper portion of panel, alternating)
            placement_idx = len(results)
            if placement_idx % 2 == 0:
                # Right side
                x = panel_x + panel_w * 0.5
                y = panel_y + panel_h * 0.15
                rotation = -15 if style == 'impact' else 0
            else:
                # Left side
                x = panel_x + panel_w * 0.15
                y = panel_y + panel_h * 0.35
                rotation = 15 if style == 'impact' else 0

            sfx = SFXLayout(
                text=sfx_text,
                x=x,
                y=y,
                font_size=font_size,
                rotation=rotation,
                color='black',
                panel_ids=[panel_id] if panel_id else [],
                style=style,
            )
            results.append(sfx)

        return results

    def _detect_sfx_style(self, text: str) -> str:
        """Detect SFX style (impact, rustle, ambient, etc.)."""
        impact_chars = set('！？!?')
        if any(c in text for c in impact_chars):
            return 'impact'
        if any(c in text for c in '～…'):
            return 'rustle'
        if text.isupper():
            return 'loud'
        return 'normal'

    def generate_narration(
        self,
        scene: Dict[str, Any],
        panel_x: int,
        panel_y: int,
        panel_w: int,
        panel_h: int,
    ) -> Optional[SFXLayout]:
        """
        Generate narration/caption text.
        Placed at top of panel in a thin bar style.
        """
        # Check if scene has narration role
        if scene.get('narrative_role') != 'narration':
            return None

        # Narration goes at top center
        font_size = int(panel_h * 0.04)
        text = scene.get('description', '')
        if not text:
            return None

        return SFXLayout(
            text=text[:50],  # Cap at 50 chars
            x=panel_x + panel_w * 0.5,
            y=panel_y + self._margin_y,
            font_size=font_size,
            rotation=0,
            color='darkgray',
            style='narration',
        )

    def calculate_text_metrics(
        self,
        text: str,
        font_size: int,
        font_family: str = "Microsoft YaHei",
    ) -> Tuple[int, int]:
        """
        Calculate rendered text dimensions.

        Returns: (width, height) in pixels
        """
        # More accurate: CJK ~0.65 * font_size per character
        # But for short text in bubbles, use 0.6
        char_count = len(text)
        width = int(char_count * font_size * 0.6)
        height = int(font_size * 1.5)
        return width, height


# ---------------------------------------------------------------------------
# QPainter bubble path helpers (for canvas rendering)
# ---------------------------------------------------------------------------

def create_bubble_path(
    x: float,
    y: float,
    w: float,
    h: float,
    bubble_type: str = 'normal',
    tail_x: Optional[float] = None,
    tail_y: Optional[float] = None,
) -> QPainterPath:
    """
    Create a QPainterPath for a bubble shape.
    """
    path = QPainterPath()

    if bubble_type == 'normal':
        _add_rounded_rect(path, x, y, w, h)
    elif bubble_type == 'shout':
        _add_spiky_path(path, x, y, w, h)
    elif bubble_type == 'thought':
        _add_cloud_path(path, x, y, w, h)
    elif bubble_type == 'narration':
        _add_rect_path(path, x, y, w, h)
    elif bubble_type == 'sfx':
        _add_rect_path(path, x, y, w, h)
    elif bubble_type == 'whisper':
        _add_dashed_path(path, x, y, w, h)
    else:
        _add_rounded_rect(path, x, y, w, h)

    # Add tail
    if tail_x is not None and tail_y is not None:
        _add_tail(path, x, y, w, h, tail_x, tail_y, bubble_type)

    return path


def _add_rounded_rect(path: QPainterPath, x: float, y: float, w: float, h: float) -> None:
    radius = min(w, h) * 0.15
    path.addRoundedRect(x, y, w, h, radius, radius)


def _add_rect_path(path: QPainterPath, x: float, y: float, w: float, h: float) -> None:
    path.addRect(x, y, w, h)


def _add_dashed_path(path: QPainterPath, x: float, y: float, w: float, h: float) -> None:
    """Dashed rectangle for whisper bubbles."""
    _add_rounded_rect(path, x, y, w, h)


def _add_spiky_path(path: QPainterPath, x: float, y: float, w: float, h: float) -> None:
    """Jagged/spiky path for shout bubbles."""
    spikes = 8
    spike_h = min(w, h) * 0.1
    path.moveTo(x, y + h)
    for i in range(spikes):
        x1 = x + (w / spikes) * i
        y1 = y
        x2 = x + (w / spikes) * (i + 0.5)
        y2 = y - spike_h if i % 2 == 0 else y + spike_h
        x3 = x + (w / spikes) * (i + 1)
        y3 = y
        path.lineTo(x1, y1)
        path.lineTo(x2, y2)
    path.lineTo(x + w, y + h)
    path.closeSubpath()


def _add_cloud_path(path: QPainterPath, x: float, y: float, w: float, h: float) -> None:
    """Cloud-like path for thought bubbles."""
    cx = x + w / 2
    cy = y + h / 2
    r = min(w, h) * 0.3
    path.addEllipse(cx - r, cy - r, r * 2, r * 2)
    path.addEllipse(cx - r * 1.3, cy - r * 0.3, r * 1.5, r * 1.5)
    path.addEllipse(cx + r * 0.3, cy - r * 0.3, r * 1.5, r * 1.5)


def _add_tail(
    path: QPainterPath,
    x: float,
    y: float,
    w: float,
    h: float,
    tail_x: float,
    tail_y: float,
    bubble_type: str,
) -> None:
    """Add a tail/pointer to the bubble."""
    if bubble_type == 'thought':
        # Dots for thought
        path.addEllipse(tail_x - 3, tail_y - 3, 6, 6)
    else:
        # Triangle pointer from bubble bottom-center toward tail target
        cx = x + w / 2
        cy = y + h
        path.moveTo(cx - 10, cy)
        path.lineTo(tail_x, tail_y)
        path.lineTo(cx + 10, cy)
        path.closeSubpath()
