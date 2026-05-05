"""Core modules for manga-auto-layout."""

from core.parser import (
    parse_script,
    get_scene_count,
    get_total_dialogue_count,
    StoryAnalyzer,
)
from core.layout_engine import (
    generate_layout,
    load_template,
    get_all_templates,
    get_page_count,
    get_total_panel_count,
)
from core.image_processor import (
    load_images_from_folder,
    load_image,
    process_image,
    get_image_info,
)
from core.text_typesetter import (
    typeset_text,
    render_bubble,
    BUBBLE_CONFIGS,
)
from core.refiner import (
    refine_layout,
    check_overflow,
    scale_to_fit,
)

__all__ = [
    # parser
    "parse_script",
    "get_scene_count",
    "get_total_dialogue_count",
    "StoryAnalyzer",
    # layout_engine
    "generate_layout",
    "load_template",
    "get_all_templates",
    "get_page_count",
    "get_total_panel_count",
    # image_processor
    "load_images_from_folder",
    "load_image",
    "process_image",
    "get_image_info",
    # text_typesetter
    "typeset_text",
    "render_bubble",
    "BUBBLE_CONFIGS",
    # refiner
    "refine_layout",
    "check_overflow",
    "scale_to_fit",
]
