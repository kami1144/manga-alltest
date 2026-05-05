"""
Enhanced script parser for mangaAutoLayout v2.

Supports the workflow: Parse Script → Understand Story → Plan Pacing → Structure Output.

New capabilities over v1:
- Shot type detection (close_up / wide_shot / POV / etc.)
- Importance / impact markers (★ high, ☆ medium)
- Narrative role classification (climax / transition / calm / reveal)
- Image attachment syntax (#img: filename.jpg)
- StoryAnalyzer: LLM-powered page-level narrative rhythm analysis
- Page grouping: groups scenes into pages based on pacing strategy
"""

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from docx import Document

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# New enhanced script syntax
# ---------------------------------------------------------------------------
# ★ 场景名        = high importance scene (climax/high-impact)
# ☆ 场景名        = medium importance (normal dramatic)
# 无标记          = low importance (filler/transitional)
# @CU            = close-up shot
# @WS            = wide shot
# @POV           = first-person POV
# @OV            = over-shoulder
# @TILT          = tilted/dynamic
# @2S            = two-shot
# #img:xxx.jpg   = attach image to this scene
# 【climax】      = explicit narrative role override
# 【transition】  = transition scene
# 【reveal】      = reveal/reaction shot
# 【narration】   = pure narration (no dialogue)

SHOT_ABBREV = {
    '@CU':   'close_up',
    '@CU2':  'close_up_2',    # extreme close-up
    '@WS':   'wide_shot',
    '@WS2':  'very_wide',     # establishing shot
    '@POV':  'POV',
    '@OV':   'over_shoulder',
    '@TILT': 'tilted',
    '@2S':   'two_shot',
    '@INT':  'insert',         # insert/detail shot
    '@AERIAL': 'aerial',
    '@PANNING': 'panning',
}

NARRATIVE_ROLES = {'climax', 'transition', 'calm', 'reveal', 'narration', 'action', 'comedic'}
IMPORTANCE_LEVELS = {'high', 'medium', 'low'}

# ---------------------------------------------------------------------------
# StoryAnalyzer — LLM-powered narrative understanding
# ---------------------------------------------------------------------------

STORY_ANALYSIS_PROMPT = """You are a professional manga editor analyzing a story.

Given the following scenes from ONE page, analyze the narrative rhythm of this page.

Scenes on this page:
{scenes_text}

Respond ONLY with a valid JSON object:
{{"page_rhythm": "climax_dominant|balanced|calm_dominant", "dominant_emotion": "<emotion>", "urgency": 1-10, "page_type": "splash|crowded|standard|minimal", "reading_pace": "fast|medium|slow", "layout_strategy": "<one-sentence advice>"}}
"""


class StoryAnalyzer:
    """
    LLM-powered story understanding.
    Analyzes page-level narrative rhythm, emotional arc, and pacing.
    Falls back to rule-based analysis when LLM is unavailable.
    """

    def __init__(self, llm_client=None):
        self._llm = llm_client

    def analyze_page(self, page_scenes: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Analyze a single page's scenes and return page-level metadata.

        Returns:
            Dict with: page_rhythm, dominant_emotion, urgency (1-10),
                       page_type, reading_pace, layout_strategy
        """
        if len(page_scenes) == 0:
            return self._default_page_analysis()

        # Check if any scene has explicit markers
        has_explicit = any(
            s.get('importance') == 'high' or s.get('narrative_role') == 'climax'
            for s in page_scenes
        )

        # Build scenes text for LLM
        scenes_text = self._build_scenes_text(page_scenes)

        # Try LLM analysis
        if self._llm and self._llm.is_available():
            result = self._llm_analyze(scenes_text, page_scenes)
            if result:
                return result

        # Rule-based fallback
        return self._rule_based_page_analysis(page_scenes)

    def _llm_analyze(self, scenes_text: str, page_scenes: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Use LLM to analyze page rhythm."""
        try:
            from utils.llm_client import get_client
            if self._llm is None:
                self._llm = get_client()

            response = self._llm.chat(
                STORY_ANALYSIS_PROMPT.format(scenes_text=scenes_text),
                max_tokens=300,
                temperature=0.2,
            )
            if not response:
                return None

            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            if json_start < 0:
                return None

            data = json.loads(response[json_start:json_end])

            # Validate required keys
            required = ['page_rhythm', 'dominant_emotion', 'urgency', 'page_type', 'reading_pace', 'layout_strategy']
            if all(k in data for k in required):
                data['urgency'] = max(1, min(10, int(data['urgency'])))
                data['source'] = 'llm'
                logger.info(f"LLM page analysis: rhythm={data['page_rhythm']}, urgency={data['urgency']}")
                return data
            return None

        except Exception as e:
            logger.warning(f"LLM page analysis failed: {e}")
            return None

    def _rule_based_page_analysis(self, page_scenes: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Rule-based fallback when LLM unavailable."""
        total_dialogue = sum(s.get('dialogue_count', 0) for s in page_scenes)
        scene_count = len(page_scenes)

        # Detect high-impact markers
        has_high_importance = any(s.get('importance') == 'high' for s in page_scenes)
        has_climax = any(s.get('narrative_role') == 'climax' for s in page_scenes)
        has_action = any(s.get('narrative_role') == 'action' for s in page_scenes)

        # Determine rhythm
        if has_high_importance or has_climax or has_action:
            rhythm = 'climax_dominant'
            urgency = 8
        elif total_dialogue > 8:
            rhythm = 'balanced'
            urgency = 5
        elif total_dialogue < 3:
            rhythm = 'calm_dominant'
            urgency = 3
        else:
            rhythm = 'balanced'
            urgency = 5

        # Determine page type
        if scene_count == 1:
            page_type = 'splash'
        elif scene_count <= 3:
            page_type = 'standard'
        elif scene_count <= 5:
            page_type = 'crowded'
        else:
            page_type = 'crowded'

        # Determine pace
        if has_action or urgency >= 8:
            pace = 'fast'
        elif urgency <= 3:
            pace = 'slow'
        else:
            pace = 'medium'

        return {
            'page_rhythm': rhythm,
            'dominant_emotion': 'unknown',
            'urgency': urgency,
            'page_type': page_type,
            'reading_pace': pace,
            'layout_strategy': 'use larger panels for high-urgency pages' if urgency >= 7 else 'balanced grid for standard pacing',
            'source': 'rule',
        }

    def _build_scenes_text(self, scenes: List[Dict[str, Any]]) -> str:
        """Build readable scene text for LLM prompt."""
        lines = []
        for i, s in enumerate(scenes):
            desc = s.get('description', '')
            role = s.get('narrative_role', '')
            imp = s.get('importance', '')
            dialogues = s.get('dialogue_lines', [])
            role_tag = f" [{role}]" if role else ""
            imp_tag = f" [{imp} impact]" if imp else ""
            lines.append(f"Scene {i+1}{role_tag}{imp_tag}: {desc}")
            for d in dialogues:
                lines.append(f"  - {d.get('character', '')}: {d.get('text', '')}")
        return '\n'.join(lines)

    def _default_page_analysis(self) -> Dict[str, Any]:
        return {
            'page_rhythm': 'balanced',
            'dominant_emotion': 'unknown',
            'urgency': 5,
            'page_type': 'standard',
            'reading_pace': 'medium',
            'layout_strategy': 'standard grid layout',
            'source': 'rule',
        }


# ---------------------------------------------------------------------------
# Enhanced parser
# ---------------------------------------------------------------------------

def parse_script(
    file_path: str,
    use_llm_analysis: bool = True,
    llm_client=None,
) -> Dict[str, Any]:
    """
    Parse a manga script file into structured story data.

    Enhanced syntax:
        ★ 高潮场景          → importance=high, narrative_role=climax
        ☆ 场景名            → importance=medium
        @CU, @WS, @POV      → shot type
        #img:photo.jpg      → attached image
        【climax】           → explicit narrative role
        《SFX》              → sound effects

    Args:
        file_path: Path to script file (TXT or DOCX)
        use_llm_analysis: Use LLM for page-level rhythm analysis
        llm_client: Optional LLM client (uses global if not provided)

    Returns:
        Parsed story data with pages, scenes, and page-level analysis
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Script file not found: {file_path}")

    extension = path.suffix.lower()
    if extension == '.txt':
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
    elif extension == '.docx':
        doc = Document(path)
        content = '\n'.join(p.text for p in doc.paragraphs if p.text.strip())
    else:
        raise ValueError(f"Unsupported file format: {extension}")

    # Phase 1: syntactic parsing → raw pages + scenes
    raw_pages = _parse_content(content)

    # Phase 2: semantic enrichment (shot detection, importance, role)
    _enrich_scenes(raw_pages)

    # Phase 3: page-level narrative analysis
    analyzer = StoryAnalyzer(llm_client) if use_llm_analysis else None
    for page in raw_pages:
        if analyzer:
            page['narrative'] = analyzer.analyze_page(page['scenes'])
        else:
            page['narrative'] = StoryAnalyzer()._rule_based_page_analysis(page['scenes'])

    # Phase 4: assign page layout hints based on narrative analysis
    _assign_page_layout_hints(raw_pages)

    logger.info(
        f"Parsed {len(raw_pages)} pages, "
        f"{sum(len(p['scenes']) for p in raw_pages)} scenes"
    )
    return {'pages': raw_pages}


# ---------------------------------------------------------------------------
# Phase 1: syntactic parsing
# ---------------------------------------------------------------------------

# Compiled regexes (module-level for performance)
_SCENE_MARKERS = re.compile(
    r'^(?<!\w)(?:场景|Scene|第|Page)\s*(\d+)'
    r'|^第?\s*(\d+)\s*(?:页|page|P)'
    r'|^《(.+)》\s*$',  # standalone SFX line = scene separator
    re.IGNORECASE
)
_DIALOGUE = re.compile(r'^([^：:]+)[:：](.+)$')
_ACTION_FULLWIDTH = re.compile(r'^（(.+)）$')
_ACTION_SQUARE = re.compile(r'^\[(.+)\]$')
_SFX = re.compile(r'^《(.+?)》\s*$|^「(.+?)」\s*$')
_IMPORTANCE = re.compile(r'^[★☆]+')
_SHOT = re.compile(r'@(\w+)')
_IMG_REF = re.compile(r'#img:\s*(.+)')
_NARRATIVE_ROLE = re.compile(r'【(.+?)】')
_EXPLICIT_ROLE = re.compile(r'^(?:场景|Scene)\s*\d+\s*【(.+?)】')


def _parse_content(content: str) -> List[Dict[str, Any]]:
    """Phase 1: syntactic parsing into raw page/scene structure."""
    lines = content.split('\n')
    pages: List[Dict[str, Any]] = []
    current_page: Optional[Dict[str, Any]] = None
    current_scene: Optional[Dict[str, Any]] = None

    page_num = 0
    scene_id = 0

    def _finalize_scene():
        nonlocal current_page, current_scene, page_num
        if current_scene:
            if not current_page:
                page_num += 1
                current_page = {'page_num': page_num, 'scenes': []}
                pages.append(current_page)
            current_page['scenes'].append(current_scene)

    def _new_scene(description: str) -> Dict[str, Any]:
        nonlocal scene_id
        scene_id += 1
        return {
            'scene_id': f'scene_{scene_id}',
            'description': description,
            'dialogue_lines': [],
            'sfx_list': [],
            'importance': 'low',
            'narrative_role': '',
            'shot_type': '',
            'attached_images': [],
            'dialogue_count': 0,
            'dialogue_density': 'low',
        }

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue

        # --- New scene/page marker ---
        scene_match = _SCENE_MARKERS.match(line)
        if scene_match:
            _finalize_scene()
            # Extract description (everything after the number/marker)
            # "场景1 室内 白天" → description = "室内 白天"
            desc = line
            for g in scene_match.groups():
                if g:
                    desc = line[scene_match.end():].strip()
                    break
            if not desc:
                desc = line
            current_scene = _new_scene(desc)
            i += 1
            continue

        # --- Importance marker at line start (★ or ☆ before description) ---
        imp_match = _IMPORTANCE.match(line)
        if imp_match and current_scene is None:
            # Standalone importance line = new scene
            _finalize_scene()
            desc = _IMPORTANCE.sub('', line).strip()
            current_scene = _new_scene(desc)
            stars = imp_match.group()
            current_scene['importance'] = 'high' if '★' in stars else 'medium'
            i += 1
            continue

        # --- Shot type inline (e.g. "@CU 脸部特写") ---
        shot_match = _SHOT.search(line)
        if shot_match and current_scene is None:
            _finalize_scene()
            desc = _SHOT.sub('', line).strip()
            current_scene = _new_scene(desc)
            current_scene['shot_type'] = _normalize_shot(shot_match.group(1))
            i += 1
            continue

        # --- Image attachment anywhere in the line ---
        img_match = _IMG_REF.search(line)
        if img_match and current_scene:
            current_scene.setdefault('attached_images', []).append(img_match.group(1).strip())
            line = _IMG_REF.sub('', line).strip()

        # --- Narrative role inline 【climax】 ---
        role_match = _NARRATIVE_ROLE.search(line)
        if role_match and current_scene:
            role = role_match.group(1).strip().lower()
            if role in NARRATIVE_ROLES:
                current_scene['narrative_role'] = role
                if role == 'climax' and current_scene['importance'] == 'low':
                    current_scene['importance'] = 'high'
                if role == 'action':
                    current_scene['importance'] = 'high'
            line = _NARRATIVE_ROLE.sub('', line).strip()

        # --- Explicit role in scene marker ---
        explicit_role = _EXPLICIT_ROLE.match(line)
        if explicit_role:
            role = explicit_role.group(1).strip().lower()
            if role in NARRATIVE_ROLES and current_scene:
                current_scene['narrative_role'] = role

        # --- Dialogue ---
        dlg_match = _DIALOGUE.match(line)
        if dlg_match and current_scene:
            character = dlg_match.group(1).strip()
            dialogue = dlg_match.group(2).strip()
            current_scene['dialogue_lines'].append({
                'character': character,
                'text': dialogue,
            })
            current_scene['dialogue_count'] += 1
            i += 1
            continue

        # --- Action in parentheses ---
        is_action = False
        for pattern in (_ACTION_FULLWIDTH, _ACTION_SQUARE):
            m = pattern.match(line)
            if m:
                is_action = True
                if current_scene:
                    # Merge into description
                    action = m.group(1)
                    existing = current_scene['description']
                    current_scene['description'] = f"{existing} ({action})" if existing else action
                break
        if is_action:
            i += 1
            continue

        # --- SFX ---
        sfx_match = _SFX.match(line)
        if sfx_match and current_scene:
            sfx = sfx_match.group(1) or sfx_match.group(2)
            current_scene['sfx_list'].append(sfx.strip())
            i += 1
            continue

        # --- Plain paragraph = new scene (MVP fallback for narrative scripts) ---
        if current_scene:
            _finalize_scene()
        current_scene = _new_scene(line)
        i += 1

    _finalize_scene()

    # Ensure at least one page
    if not pages:
        pages.append({'page_num': 1, 'scenes': [_new_scene('Default scene')]})

    # Calculate dialogue density
    for page in pages:
        for scene in page['scenes']:
            scene['dialogue_density'] = _calculate_density(scene['dialogue_count'])

    return pages


# ---------------------------------------------------------------------------
# Phase 2: semantic enrichment
# ---------------------------------------------------------------------------

def _enrich_scenes(pages: List[Dict[str, Any]]) -> None:
    """
    Phase 2: detect shot types and importance from scene descriptions
    using keyword analysis (for scenes without explicit markers).
    """
    for page in pages:
        for scene in page['scenes']:
            # Auto-detect shot from description keywords
            if not scene.get('shot_type'):
                scene['shot_type'] = _detect_shot_from_text(scene.get('description', ''))

            # Auto-detect importance from narrative role
            if scene.get('narrative_role') in ('climax', 'action') and scene.get('importance') == 'low':
                scene['importance'] = 'high'


def _detect_shot_from_text(description: str) -> str:
    """Detect shot type from description text."""
    d = description.lower()
    if any(kw in d for kw in ['特写', 'close', '脸部', '脸', '表情', '眼神', '胸', '巨乳', '肉体', '肌肤']):
        return 'close_up'
    if any(kw in d for kw in ['远景', 'wide', '全景', '全场', '天空', '背景', '街道', '天台']):
        return 'wide_shot'
    if any(kw in d for kw in ['俯视', 'bird', '鸟瞰', '上方', '从上空']):
        return 'aerial'
    if any(kw in d for kw in ['视角', ' POV', 'first person', '第一视角', '看着', '望着']):
        return 'POV'
    if any(kw in d for kw in ['斜角', 'tilt', '动感', '对角线']):
        return 'tilted'
    if any(kw in d for kw in ['二人', 'two', '两人', '双人', '并排']):
        return 'two_shot'
    if any(kw in d for kw in ['插入', 'insert', '细节', '特制品']):
        return 'insert'
    if any(kw in d for kw in ['过肩', 'over']):
        return 'over_shoulder'
    return 'medium_shot'  # default


def _normalize_shot(abbrev: str) -> str:
    """Normalize shot abbreviation to canonical name."""
    return SHOT_ABBREV.get(f'@{abbrev.upper()}', abbrev.lower())


def _calculate_density(dialogue_count: int) -> str:
    if dialogue_count > 5:
        return 'high'
    elif dialogue_count >= 3:
        return 'medium'
    return 'low'


# ---------------------------------------------------------------------------
# Phase 4: page layout hints based on narrative analysis
# ---------------------------------------------------------------------------

def _assign_page_layout_hints(pages: List[Dict[str, Any]]) -> None:
    """
    Assign layout hints to each page based on narrative analysis.
    These hints guide the layout engine's template selection.
    """
    for page in pages:
        narrative = page.get('narrative', {})
        rhythm = narrative.get('page_rhythm', 'balanced')
        page_type = narrative.get('page_type', 'standard')
        urgency = narrative.get('urgency', 5)
        role = narrative.get('narrative', {}).get('page_rhythm', 'balanced')

        # Panel count hint based on urgency and page_type
        if page_type == 'splash':
            hint_panels = 1
        elif urgency >= 8 or rhythm == 'climax_dominant':
            hint_panels = min(3, len(page['scenes']))
        elif page_type == 'crowded':
            hint_panels = min(6, len(page['scenes']))
        elif rhythm == 'calm_dominant':
            hint_panels = min(4, len(page['scenes']))
        else:
            hint_panels = min(4, len(page['scenes']))

        # Bleed hint
        allow_bleed = urgency >= 7 or page_type == 'splash'

        # Grid hint
        if page_type in ('crowded', 'minimal') or rhythm == 'calm_dominant':
            prefer_grid = True
        else:
            prefer_grid = False

        page['layout_hints'] = {
            'suggested_panel_count': hint_panels,
            'allow_bleed': allow_bleed,
            'prefer_grid': prefer_grid,
            'urgency': urgency,
            'page_type': page_type,
        }


# ---------------------------------------------------------------------------
# Backward compatibility helpers
# ---------------------------------------------------------------------------

def get_scene_count(script_data: Dict[str, Any]) -> int:
    return sum(len(page['scenes']) for page in script_data['pages'])


def get_total_dialogue_count(script_data: Dict[str, Any]) -> int:
    total = 0
    for page in script_data['pages']:
        for scene in page['scenes']:
            total += scene.get('dialogue_count', 0)
    return total
