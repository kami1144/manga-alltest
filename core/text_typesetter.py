"""
Text typesetter for manga dialogue bubbles.
"""

import logging
import math
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)


# Bubble type configurations
BUBBLE_CONFIGS = {
    'normal': {
        'corner_radius': 15,
        'outline_width': 2,
    },
    'shout': {
        'jagged_edges': True,
        'points': 12,
        'outline_width': 3,
    },
    'thought': {
        'cloud_shape': True,
        'outline_width': 2,
    },
    'whisper': {
        'dotted_outline': True,
        'outline_width': 1,
    },
    'sfx': {
        'bold': True,
        'outline_width': 4,
    },
}

# Default minimum bubble size
MIN_BUBBLE_WIDTH = 80
MIN_BUBBLE_HEIGHT = 40


def typeset_text(
    dialogue_lines: List[Dict[str, Any]],
    panel_width: int,
    panel_height: int,
    bubble_type: str = 'normal',
    vertical: bool = False
) -> List[Dict[str, Any]]:
    """
    Generate text elements for dialogue.

    Args:
        dialogue_lines: List of dialogue dicts with 'character' and 'text'
        panel_width: Panel width in pixels
        panel_height: Panel height in pixels
        bubble_type: Type of bubble ('normal', 'shout', 'thought', 'whisper', 'sfx')
        vertical: Use vertical Japanese text layout

    Returns:
        List of text element dicts
    """
    if not dialogue_lines:
        return []

    elements: List[Dict[str, Any]] = []
    positions = _get_bubble_positions(len(dialogue_lines), panel_width, panel_height)

    for idx, (dialogue, position) in enumerate(zip(dialogue_lines, positions)):
        bubble_width = max(MIN_BUBBLE_WIDTH, position[2])
        bubble_height = max(MIN_BUBBLE_HEIGHT, position[3])

        element = {
            'type': bubble_type if idx == 0 else 'normal',
            'x': position[0],
            'y': position[1],
            'width': bubble_width,
            'height': bubble_height,
            'text': dialogue.get('text', ''),
            'character': dialogue.get('character', ''),
            'style': _get_bubble_style(bubble_type),
        }
        elements.append(element)

    logger.info(f"Typeset {len(elements)} dialogue elements")
    return elements


def _get_bubble_positions(
    count: int,
    panel_width: int,
    panel_height: int
) -> List[Tuple[int, int, int, int]]:
    """
    Get bubble positions in panel corners.
    Avoids center where main action usually is.
    """
    positions = []
    margin = 20
    bubble_w = min(150, panel_width // 2)
    bubble_h = min(60, panel_height // 4)

    # Corner positions (RTL friendly)
    corners = [
        (margin, margin),  # Top-left
        (panel_width - bubble_w - margin, margin),  # Top-right
        (margin, panel_height - bubble_h - margin),  # Bottom-left
        (panel_width - bubble_w - margin, panel_height - bubble_h - margin),  # Bottom-right
    ]

    for i in range(count):
        x, y = corners[i % len(corners)]
        positions.append((x, y, bubble_w, bubble_h))

    return positions


def _get_bubble_style(bubble_type: str) -> Dict[str, Any]:
    """Get bubble style configuration."""
    return BUBBLE_CONFIGS.get(bubble_type, BUBBLE_CONFIGS['normal'])


def render_bubble(
    img: Image.Image,
    element: Dict[str, Any],
    vertical: bool = False
) -> Image.Image:
    """
    Render a dialogue bubble onto an image.

    Args:
        img: Target image
        element: Text element dict
        vertical: Use vertical text

    Returns:
        Image with bubble rendered
    """
    draw = ImageDraw.Draw(img, 'RGBA')
    x = element['x']
    y = element['y']
    w = element['width']
    h = element['height']
    bubble_type = element.get('type', 'normal')

    # Get style
    style = BUBBLE_CONFIGS.get(bubble_type, BUBBLE_CONFIGS['normal'])

    # Draw bubble shape based on type
    if bubble_type == 'normal':
        _draw_normal_bubble(draw, x, y, w, h, style)
    elif bubble_type == 'shout':
        _draw_shout_bubble(draw, x, y, w, h, style)
    elif bubble_type == 'thought':
        _draw_thought_bubble(draw, x, y, w, h, style)
    elif bubble_type == 'whisper':
        _draw_whisper_bubble(draw, x, y, w, h, style)
    elif bubble_type == 'sfx':
        _draw_sfx_text(draw, x, y, w, h, element.get('text', ''))

    return img


def _draw_normal_bubble(
    draw: ImageDraw.Draw,
    x: int,
    y: int,
    w: int,
    h: int,
    style: Dict[str, Any]
) -> None:
    """Draw a normal rounded rectangle bubble."""
    radius = style.get('corner_radius', 15)
    outline = style.get('outline_width', 2)
    fill = (255, 255, 255, 230)  # White with slight transparency

    # Draw rounded rect
    draw.rounded_rectangle(
        [x, y, x + w, y + h],
        radius=radius,
        fill=fill,
        outline=(0, 0, 0, 255),
        width=outline
    )


def _draw_shout_bubble(
    draw: ImageDraw.Draw,
    x: int,
    y: int,
    w: int,
    h: int,
    style: Dict[str, Any]
) -> None:
    """Draw an explosion/jagged shout bubble."""
    points = style.get('points', 12)
    outline = style.get('outline_width', 3)

    # Create jagged polygon
    polygon = []
    for i in range(points):
        angle = 2 * math.pi * i / points
        radius_mod = 1.0 if i % 2 == 0 else 0.85
        px = x + w // 2 + (w // 2 - 5) * radius_mod * math.cos(angle)
        py = y + h // 2 + (h // 2 - 5) * radius_mod * math.sin(angle)
        polygon.append((px, py))

    draw.polygon(
        polygon,
        fill=(255, 255, 255, 230),
        outline=(0, 0, 0, 255),
        width=outline
    )


def _draw_thought_bubble(
    draw: ImageDraw.Draw,
    x: int,
    y: int,
    w: int,
    h: int,
    style: Dict[str, Any]
) -> None:
    """Draw a thought cloud bubble."""
    outline = style.get('outline_width', 2)

    # Draw overlapping circles for cloud effect
    fill = (255, 255, 255, 230)
    circles = [
        (x + w // 3, y + h // 2, w // 3),
        (x + 2 * w // 3, y + h // 2, w // 3),
        (x + w // 2, y + h // 3, w // 3),
        (x + w // 2, y + 2 * h // 3, w // 3),
    ]

    for cx, cy, cr in circles:
        draw.ellipse(
            [cx - cr, cy - cr, cx + cr, cy + cr],
            fill=fill,
            outline=(0, 0, 0, 255),
            width=outline
        )


def _draw_whisper_bubble(
    draw: ImageDraw.Draw,
    x: int,
    y: int,
    w: int,
    h: int,
    style: Dict[str, Any]
) -> None:
    """Draw a dotted whisper bubble."""
    radius = style.get('corner_radius', 15)
    outline = style.get('outline_width', 1)

    # Draw with dotted line (dashed)
    draw.rounded_rectangle(
        [x, y, x + w, y + h],
        radius=radius,
        fill=(255, 255, 255, 180),
        outline=(100, 100, 100, 200),
        width=outline
    )


def _draw_sfx_text(
    draw: ImageDraw.Draw,
    x: int,
    y: int,
    w: int,
    h: int,
    text: str
) -> None:
    """Draw stylized SFX text."""
    # SFX is typically bold and impactful
    # This is handled by text rendering, just draw a background marker area
    pass


def get_font_size(bubble_width: int, bubble_height: int) -> int:
    """Calculate appropriate font size for bubble."""
    min_dim = min(bubble_width, bubble_height)
    # Scale font with bubble size
    font_size = max(10, min_dim // 5)
    return font_size


def estimate_text_size(
    text: str,
    font_size: int
) -> Tuple[int, int]:
    """
    Estimate text dimensions.
    This is a rough estimate - actual rendering depends on font.
    """
    # Approximate: each character is about 0.6em wide
    char_width = font_size * 0.6
    lines = text.count('\n') + 1
    width = int(len(text) * char_width)
    height = int(lines * font_size * 1.2)

    return (width, height)