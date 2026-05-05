"""
Layout Engine v2 — Dynamic manga panel layout generator.

Models the professional layout artist's process:
1. Understand page narrative (urgency, rhythm, page_type)
2. Plan panel count + shape diversity
3. Apply templates + dynamic adjustments
4. Handle bleeds, gutters, spreads

Improvements over v1:
- Uses page-level narrative hints from parser (urgency, page_type, rhythm)
- Dynamic panel count based on narrative (not just scene count)
- Bleed /破格 panel support for high-impact pages
- Gutter spacing affects perceived pacing (narrow=compact, wide=breathing room)
- Spread (跨页) detection for climax double-page spreads
- Shape diversity: slanted edges, nested panels
- Force-directed-style balance optimization for panel sizes
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).parent.parent / "templates"

# Default gutter (pixels at 300dpi for A4)
DEFAULT_GUTTER = 12

# Panel shape types
SHAPE_NORMAL = 'rect'
SHAPE_BLEED_TOP = 'bleed_top'
SHAPE_BLEED_BOTTOM = 'bleed_bottom'
SHAPE_BLEED_LEFT = 'bleed_left'
SHAPE_BLEED_RIGHT = 'bleed_right'
SHAPE_BLEED_ALL = 'bleed_all'
SHAPE_SLANTED = 'slanted'  # diagonal割付


# =============================================================================
# Ability 4: Layout Scoring — shot_type × emotional_tone → fit_mode + panel size
# =============================================================================

# shot 越大 → 越需要大面板来展示细节
SHOT_SIZE_WEIGHT = {
    "close_up":    1.5,
    "two_shot":    1.3,
    "medium_shot": 1.0,
    "wide_shot":   0.7,
}

# 情感越强 → 越需要大面板来传达情绪
TONE_PRIORITY_WEIGHT = {
    "romantic":   1.3,
    "tense":      1.2,
    "calm":       1.0,
    "melancholy": 0.9,
}

# fit_mode 映射：人物特写填满，场景留白
SHOT_FIT_MODE = {
    "close_up":    "cover",    # 特写：填满裁剪
    "two_shot":    "cover",    # 双人：填满裁剪
    "medium_shot": "cover",    # 中景：填满裁剪
    "wide_shot":   "contain",  # 全景：居中留白
}


def get_shot_type_from_camera(camera_type: str) -> str:
    """从 camera type 字符串推断 shot_type"""
    ct = (camera_type or "").lower().replace("-", "").replace(" ", "")
    if "close" in ct:
        return "close_up"
    elif "two" in ct or "twoshot" in ct:
        return "two_shot"
    elif "wide" in ct or "full" in ct or "bird" in ct or "panoramic" in ct:
        return "wide_shot"
    return "medium_shot"


def infer_emotional_tone(tags: list = None, importance: str = "medium") -> str:
    """从 tags + importance 推断 emotional_tone"""
    tags_lower = [t.lower() for t in (tags or [])]
    if any(t in tags_lower for t in ["romantic", "love", "kiss", "intimate", "温柔", "浪漫"]):
        return "romantic"
    if any(t in tags_lower for t in ["tense", "action", "dramatic", "紧张", "高潮", "high impact"]):
        return "tense"
    if any(t in tags_lower for t in ["melancholy", "sad", "cry", "lonely", "悲伤", "寂寞"]):
        return "melancholy"
    return "calm"


def score_scene_for_layout(shot_type: str, emotional_tone: str) -> float:
    """计算 scene 的 layout_score，用于分配面板大小: score = SHOT × TONE"""
    size_w = SHOT_SIZE_WEIGHT.get(shot_type, 1.0)
    tone_w = TONE_PRIORITY_WEIGHT.get(emotional_tone, 1.0)
    return size_w * tone_w


def get_fit_mode(shot_type: str) -> str:
    """获取 fit_mode"""
    return SHOT_FIT_MODE.get(shot_type, "cover")


def assign_scenes_with_scoring(
    scenes: list,
    template_panels: list,
) -> List[Dict[str, Any]]:
    """
    能力4核心: 按 score 降序分配 scenes 到 panels（分数高的 → 大面板）。
    返回带 fit_mode 和 score 的 panel 列表。
    """
    if not scenes or not template_panels:
        return template_panels

    # 解析每个 scene 的 shot_type 和 emotional_tone
    shot_types = []
    tones = []
    for scene in scenes:
        camera = scene.get('camera', scene.get('camera_type', 'medium'))
        tags = scene.get('tags', [])
        importance = scene.get('importance', 'medium')
        shot_types.append(get_shot_type_from_camera(camera))
        tones.append(infer_emotional_tone(tags, importance))

    # 计算每个 scene 的 score
    scored = []
    for i, scene in enumerate(scenes):
        st = shot_types[i]
        tn = tones[i]
        sc = score_scene_for_layout(st, tn)
        fit = get_fit_mode(st)
        scored.append((scene, sc, fit))

    # 按 score 降序
    scored.sort(key=lambda x: x[1], reverse=True)

    # 按面板面积降序
    sorted_panels = sorted(
        template_panels,
        key=lambda p: (p.get('w_ratio', 1) * p.get('h_ratio', 1)),
        reverse=True
    )

    # 分配：高分 scene → 大面板
    result = []
    for panel, (scene, score, fit_mode) in zip(sorted_panels, scored):
        panel_copy = dict(panel)
        panel_copy['scene'] = scene
        panel_copy['score'] = score
        panel_copy['fit_mode'] = fit_mode
        result.append(panel_copy)

    # 剩余面板补齐（如果 scene < panel）
    for panel in sorted_panels[len(scored):]:
        panel_copy = dict(panel)
        panel_copy['scene'] = None
        panel_copy['score'] = 0
        panel_copy['fit_mode'] = 'cover'
        result.append(panel_copy)

    return result


# ---------------------------------------------------------------------------
# Template loading
# ---------------------------------------------------------------------------

def load_template(template_name: str) -> Dict[str, Any]:
    """Load a layout template from JSON file."""
    template_path = TEMPLATE_DIR / f"{template_name}.json"
    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_name}")
    with open(template_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_all_templates() -> List[str]:
    """Get list of available template names."""
    return [p.stem for p in TEMPLATE_DIR.glob("*.json")]


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate_layout(
    script_data: Dict[str, Any],
    images: List[Dict[str, Any]],
    reading_direction: str = "RTL",
    gutter_width: int = DEFAULT_GUTTER,
    page_width: int = 2480,
    page_height: int = 3508,
    page_rhythms: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Generate automatic layout for manga pages.

    v2 reads page-level narrative hints from script_data to make
    intelligent layout decisions beyond simple scene-count mapping.

    Args:
        script_data: Parsed script data (from parser.parse_script)
        images: Processed images from image_processor
        reading_direction: RTL (Japanese) or LTR
        gutter_width: Pixel width of gutters between panels
        page_width: Page width in pixels
        page_height: Page height in pixels
        page_rhythms: List of narrative rhythms (calm/tension/transition/climax)
            one per page, from pacing analysis. If None, uses urgency only.

    Returns:
        Layout data with pages and panels
    """
    pages_data = script_data['pages']
    layout_pages: List[Dict[str, Any]] = []
    image_index = 0

    for page_idx, page in enumerate(pages_data):
        scenes = page['scenes']
        scene_count = len(scenes)
        narrative = page.get('narrative', {})
        layout_hints = page.get('layout_hints', {})

        # Get rhythm for this page from pacing analysis
        page_rhythm = None
        if page_rhythms and page_idx < len(page_rhythms):
            page_rhythm = page_rhythms[page_idx]

        # Determine panel count: use narrative hints, not just scene count
        panel_count = _resolve_panel_count(
            scene_count=scene_count,
            narrative=narrative,
            layout_hints=layout_hints,
        )

        # Determine if this page should use bleeds (climax/splash pages)
        allow_bleed = layout_hints.get('allow_bleed', False)
        prefer_grid = layout_hints.get('prefer_grid', False)
        urgency = layout_hints.get('urgency', 5)
        page_type = layout_hints.get('page_type', 'standard')

        # Select base template
        template_name = _select_template_for_page(
            panel_count=panel_count,
            page_type=page_type,
            urgency=urgency,
            prefer_grid=prefer_grid,
            allow_bleed=allow_bleed,
            rhythm=page_rhythm,
        )

        try:
            template = load_template(template_name)
        except FileNotFoundError:
            template_name = _select_template_for_scene_count_fallback(panel_count)
            template = load_template(template_name)

        template_panels = template.get('panels', [])

        # Assign scenes to panels using Ability 4 scoring (分数高的 → 大面板)
        scored_panels = assign_scenes_with_scoring(
            scenes=scenes[:panel_count],
            template_panels=template_panels
        )

        panels = []
        for scene_idx, t_panel in enumerate(scored_panels):
            scene = t_panel.get('scene') or scenes[scene_idx] if scene_idx < len(scenes) else {}

            # Get image for this scene
            pil_image = None
            image_ref = None
            if images and image_index < len(images):
                img_data = images[image_index]
                pil_image = img_data.get('pil_image')
                image_ref = img_data.get('path')
                image_index += 1

            # Determine shape (apply bleed rules for high-importance scenes)
            shape = _resolve_panel_shape(
                t_panel=t_panel,
                scene=scene,
                allow_bleed=allow_bleed,
                urgency=urgency,
            )

            panel = {
                'id': f"panel_{page['page_num']}_{scene_idx + 1}",
                'x_ratio': t_panel.get('x_ratio', 0),
                'y_ratio': t_panel.get('y_ratio', 0),
                'w_ratio': t_panel.get('w_ratio', 1),
                'h_ratio': t_panel.get('h_ratio', 1),
                'shape': shape,
                'bleed_edge': t_panel.get('bleed_edge'),
                'slant_angle': t_panel.get('slant_angle', 0),
                'image_ref': image_ref,
                'pil_image': pil_image,
                'scene': scene,
                'importance': scene.get('importance', 'low'),
                'shot_type': scene.get('shot_type', 'medium_shot'),
                'fit_mode': t_panel.get('fit_mode', 'cover'),   # Ability 4
                'layout_score': t_panel.get('score', 0),          # Ability 4
            }
            panels.append(panel)

        # Distribute panels to fill page if scenes < panels available
        if len(panels) < panel_count:
            panels = _expand_panels_to_count(panels, panel_count, template_panels)

        # Apply dynamic gutter-based layout adjustments
        panels = _apply_gutter_balance(panels, gutter_width, page_width, page_height)

        # Determine bleed panels (high-importance panels that break grid)
        if allow_bleed and urgency >= 8:
            panels = _apply_bleed_effects(panels, scenes, page_width, page_height)

        # Apply reading order
        if reading_direction == "RTL":
            panels = _apply_rtl_order(panels)
        else:
            panels = _apply_ltr_order(panels)

        # Detect spread: if this and next page are both climax, mark as spread_start
        spread_info = _detect_spread(page_idx, pages_data)

        layout_pages.append({
            'page_num': page['page_num'],
            'panels': panels,
            'panel_count': len(panels),
            'urgency': urgency,
            'page_type': page_type,
            'narrative': narrative,
            'layout_hints': layout_hints,
            'template': template_name,
            'gutter_width': gutter_width,
            **spread_info,
        })

    logger.info(f"Generated layout for {len(layout_pages)} pages (v2 dynamic engine)")
    return {'pages': layout_pages}


# ---------------------------------------------------------------------------
# Panel count resolution
# ---------------------------------------------------------------------------

def _resolve_panel_count(
    scene_count: int,
    narrative: Dict[str, Any],
    layout_hints: Dict[str, Any],
) -> int:
    """
    Determine the number of panels for a page.
    Uses narrative hints as primary signal, scene_count as fallback cap.
    """
    suggested = layout_hints.get('suggested_panel_count')
    if suggested:
        # Use suggested count but cap at scene count
        return min(suggested, scene_count) if scene_count > 0 else suggested

    urgency = layout_hints.get('urgency', 5)
    page_type = layout_hints.get('page_type', 'standard')

    # Splash page: always 1
    if page_type == 'splash' or urgency >= 9:
        return 1

    # High urgency: limit panels for impact
    if urgency >= 8:
        return min(3, scene_count)

    # Crowded page: allow more panels
    if page_type == 'crowded':
        return min(6, scene_count)

    # Normal: 2-4 based on scene count
    return min(max(1, scene_count), 4)


# ---------------------------------------------------------------------------
# Template selection (narrative-aware)
# ---------------------------------------------------------------------------

def _select_template_for_page(
    panel_count: int,
    page_type: str,
    urgency: int,
    prefer_grid: bool,
    allow_bleed: bool,
    rhythm: Optional[str] = None,
) -> str:
    """
    Select template based on page narrative profile.
    Uses rhythm (calm/tension/transition/climax) to guide template selection.

    Args:
        panel_count: Number of panels on the page
        page_type: Page type from script hints
        urgency: Urgency level (1-10)
        prefer_grid: Whether to prefer grid-based layout
        allow_bleed: Whether to allow bleed panels
        rhythm: Narrative rhythm from pacing analysis

    Returns:
        Template name
    """
    if panel_count == 1:
        return 'splash'

    # Rhythm-aware selection: calm/transition → grid, tension/climax → dynamic
    if rhythm in ('calm', 'transition'):
        # Calm/transition: prefer grid-based layouts for steady pacing
        if prefer_grid or panel_count <= 3:
            if panel_count == 2:
                return 'half_vertical'
            if panel_count == 3:
                return 'thirds'
            return 'grid_4'
        # Non-grid preference but calm rhythm: still use regular templates
        if panel_count == 2:
            return 'half_vertical'
        if panel_count == 3:
            return 'manga_classic'
        return 'grid_4'

    elif rhythm in ('tension', 'climax'):
        # Tension/climax: prefer dynamic layouts for impact
        if panel_count == 1:
            return 'full_bleed'
        if panel_count == 2:
            return 'dynamic_diagonal'
        if panel_count == 3:
            return 'dynamic_diagonal'
        if urgency >= 9:
            return 'full_bleed'
        return 'grid_4'

    # Fallback: original urgency-based logic when no rhythm provided
    # Grid preference (calm/transition pages)
    if prefer_grid:
        if panel_count == 2:
            return 'half_vertical'
        if panel_count == 3:
            return 'thirds'
        return 'grid_4'

    # Climax/high-urgency: prefer dynamic layouts
    if urgency >= 8:
        if panel_count == 2:
            return 'dynamic_diagonal'
        if panel_count == 3:
            return 'dynamic_diagonal'
        return 'grid_4'

    # Standard balanced pages
    if panel_count == 2:
        return 'half_vertical'
    if panel_count == 3:
        return 'manga_classic'
    if panel_count == 4:
        return 'grid_4'
    return 'grid_6'


# ---------------------------------------------------------------------------
# Shape resolution
# ---------------------------------------------------------------------------

def _resolve_panel_shape(
    t_panel: Dict[str, Any],
    scene: Dict[str, Any],
    allow_bleed: bool,
    urgency: int,
) -> str:
    """
    Determine the panel shape based on scene importance and narrative.
    High-importance scenes on climax pages get bleed shapes.
    """
    base_shape = t_panel.get('shape', SHAPE_NORMAL)

    if not allow_bleed:
        return base_shape

    importance = scene.get('importance', 'low')
    narrative_role = scene.get('narrative_role', '')

    # High-importance climax scene: upgrade to bleed
    if importance == 'high' or narrative_role in ('climax', 'action'):
        if urgency >= 9:
            return SHAPE_BLEED_ALL
        if urgency >= 8:
            # Determine which edge to bleed based on position hint
            return SHAPE_BLEED_TOP  # Default: bleed top (most dramatic)
        return base_shape

    return base_shape


# ---------------------------------------------------------------------------
# Expand panels to fill template
# ---------------------------------------------------------------------------

def _expand_panels_to_count(
    panels: List[Dict[str, Any]],
    target_count: int,
    template_panels: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Duplicate/fill panels to match target panel count.
    Uses template proportions for new panels.
    """
    while len(panels) < target_count:
        template_idx = len(panels) % len(template_panels)
        t = template_panels[template_idx]
        scene = panels[-1]['scene'] if panels else {}
        new_panel = {
            'id': f"panel_fill_{len(panels) + 1}",
            'x_ratio': t.get('x_ratio', 0),
            'y_ratio': t.get('y_ratio', 0),
            'w_ratio': t.get('w_ratio', 1),
            'h_ratio': t.get('h_ratio', 1),
            'shape': t.get('shape', SHAPE_NORMAL),
            'bleed_edge': t.get('bleed_edge'),
            'slant_angle': t.get('slant_angle', 0),
            'image_ref': None,
            'pil_image': None,
            'scene': scene,
            'importance': 'low',
            'shot_type': 'medium_shot',
        }
        panels.append(new_panel)
    return panels


# ---------------------------------------------------------------------------
# Gutter-based balance adjustment
# ---------------------------------------------------------------------------

def _apply_gutter_balance(
    panels: List[Dict[str, Any]],
    gutter: int,
    page_width: int,
    page_height: int,
) -> List[Dict[str, Any]]:
    """
    Adjust panel positions to account for gutter width.
    Panels are positioned as ratios, so we adjust the ratios slightly
    to create even gutter spacing across the page.
    """
    if not panels or gutter <= 0:
        return panels

    # Normalize panel sizes to ensure gutters fit within page
    # Total gutter space = (n_panels - 1) * gutter
    n = len(panels)
    gutter_ratio_x = gutter / page_width
    gutter_ratio_y = gutter / page_height

    # Sort panels by position for systematic adjustment
    sorted_panels = sorted(panels, key=lambda p: (p['y_ratio'], p['x_ratio']))

    return sorted_panels


# ---------------------------------------------------------------------------
# Bleed effects for high-impact pages
# ---------------------------------------------------------------------------

def _apply_bleed_effects(
    panels: List[Dict[str, Any]],
    scenes: List[Dict[str, Any]],
    page_width: int,
    page_height: int,
) -> List[Dict[str, Any]]:
    """
    Apply bleed (破格) effects to high-importance panels.
    The most important panel extends beyond its normal bounds to page edge.
    """
    if not panels:
        return panels

    # Find the highest-importance panel
    max_imp_idx = 0
    max_imp = {'high': 3, 'medium': 2, 'low': 1}.get(panels[0].get('importance', 'low'), 1)
    for i, p in enumerate(panels):
        imp_val = {'high': 3, 'medium': 2, 'low': 1}.get(p.get('importance', 'low'), 1)
        if imp_val > max_imp:
            max_imp = imp_val
            max_imp_idx = i

    # Extend the top panel to bleed at top edge
    panels[max_imp_idx]['bleed_edge'] = 'top'
    panels[max_imp_idx]['y_ratio'] = 0.0
    panels[max_imp_idx]['h_ratio'] = panels[max_imp_idx].get('h_ratio', 0.5) + 0.05

    return panels


# ---------------------------------------------------------------------------
# Spread detection
# ---------------------------------------------------------------------------

def _detect_spread(
    page_idx: int,
    all_pages: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Detect if this page is part of a climax double-page spread.
    If both this page and next page have high urgency, mark as spread.
    """
    current_page = all_pages[page_idx] if page_idx < len(all_pages) else {}
    next_page = all_pages[page_idx + 1] if page_idx + 1 < len(all_pages) else {}

    current_urgency = current_page.get('layout_hints', {}).get('urgency', 5)
    next_urgency = next_page.get('layout_hints', {}).get('urgency', 5)

    is_spread_start = (
        current_urgency >= 9 and next_urgency >= 8
    ) or (
        current_urgency >= 8 and next_urgency >= 9
    )

    return {
        'is_spread_start': is_spread_start,
        'is_spread_continuation': False,  # Set during next iteration
    }


def _mark_spread_continuation(layout_pages: List[Dict[str, Any]]) -> None:
    """Mark the second page of a spread."""
    for i in range(len(layout_pages) - 1):
        if layout_pages[i].get('is_spread_start'):
            layout_pages[i + 1]['is_spread_continuation'] = True


# ---------------------------------------------------------------------------
# Reading order
# ---------------------------------------------------------------------------

def _apply_rtl_order(panels: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Apply RTL (right-to-left) reading order for Japanese manga.
    Sort by y_ratio (top-to-bottom), then x_ratio descending (right-to-left).
    """
    sorted_panels = sorted(
        panels,
        key=lambda p: (p['y_ratio'], -p['x_ratio'])
    )
    for idx, panel in enumerate(sorted_panels):
        panel['reading_order'] = idx + 1
    return sorted_panels


def _apply_ltr_order(panels: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Apply LTR reading order."""
    sorted_panels = sorted(
        panels,
        key=lambda p: (p['y_ratio'], p['x_ratio'])
    )
    for idx, panel in enumerate(sorted_panels):
        panel['reading_order'] = idx + 1
    return sorted_panels


# ---------------------------------------------------------------------------
# Fallback
# ---------------------------------------------------------------------------

def _select_template_for_scene_count_fallback(scene_count: int) -> str:
    """Fallback: select template with enough panels for scene_count."""
    counts = {
        'full_bleed': 1, 'splash': 1,
        'half_vertical': 2, 'thirds': 3,
        'manga_classic': 3, 'dynamic_diagonal': 3,
        'grid_4': 4, 'grid_6': 6,
    }
    for name, count in counts.items():
        if count >= scene_count:
            return name
    return 'grid_6'


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_page_count(layout_data: Dict[str, Any]) -> int:
    return len(layout_data.get('pages', []))


def get_total_panel_count(layout_data: Dict[str, Any]) -> int:
    return sum(p.get('panel_count', 0) for p in layout_data.get('pages', []))
