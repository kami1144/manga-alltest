"""
AI Layout Advisor - LLM-powered layout decision engine.

Role: Simulates a professional manga layout artist's decision-making.
For each scene, it asks the LLM for:
  - Panel count
  - Template selection
  - Emotional tone
  - Pacing
  - Composition notes
  - Suggested camera shot

Falls back to rule-based decisions when LLM is unavailable.
"""

import logging
from typing import Any, Dict, List, Optional

from utils.llm_client import get_client, LLMClient

logger = logging.getLogger(__name__)

# --- Prompting strategies ---

LAYOUT_PROMPT_TEMPLATE = """You are a professional manga panel layout artist.

Given the following manga scene, analyze it and provide layout advice.

Scene Description:
{scene_desc}

Dialogue ({count} lines):
{dialogue}

Available Templates (choose ONE):
- full_bleed: 1 panel, dramatic splash
- half_vertical: 2 panels, left/right split
- thirds: 3 panels, classic grid
- manga_classic: 3 panels, large left + 2 stacked right
- grid_4: 4 panels, 2x2 grid
- grid_6: 6 panels, 2x3 grid
- dynamic_diagonal: 3 panels, diagonal flow
- splash: 1 panel, full-page dramatic moment

Scene Analysis Guidelines:
- High intensity / action → fewer panels, large or dynamic layouts
- Low intensity / quiet → more panels, calm grid
- Romantic / intimate → medium, balanced
- Comedy → rapid cuts, small panels, varied sizes
- Suspense / horror → unusual compositions, bleeds
- Dialogue-heavy → split panels, smaller text areas

Respond ONLY with a JSON object:
{{"panel_count": <1-6>, "template": "<template_name>", "emotional_tone": "<tone>", "pacing": "<speed>", "shot": "<shot_type>", "notes": "<composition_notes>"}}
"""

# --- Emotional markers ---
INTENSE_TONES = ["紧张", "激烈", "高潮", "冲击", "暴力", "兴奋", "高潮", "插入", "抽插", "暴力的", "强烈的"]
ROMANTIC_TONES = ["亲密", "脸红", "浪漫", "心跳", "拥抱", "接吻", "爱抚", "抚摸"]
COMEDIC_TONES = ["搞笑", "尴尬", "搞笑", "误会", "吐槽"]
SUSPENSE_TONES = ["悬疑", "恐怖", "紧张", "未知", "危机", "危机"]
CALM_TONES = ["平静", "日常", "对话", "说明", "回忆"]

PANEL_COUNT_RULES = {
    'high': 1,      # 1-2 panels for climax/high impact
    'medium': 2,    # 2-3 panels for normal scenes
    'low': 3,       # 3-4 panels for slow/quiet
    'rapid': 4,     # 4+ for rapid pacing
}


class AILayoutAdvisor:
    """
    Wraps LLM decisions with rule-based fallback.
    Main entry point for layout intelligence.
    """

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        provider: Optional[Any] = None,
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        if llm_client is not None:
            self._llm = llm_client
        elif provider is not None or api_key is not None or api_url is not None or model is not None:
            from utils.llm_client import LLMProvider, LLMClient
            actual_provider = provider if provider is not None else LLMProvider.MINIMAX
            self._llm = LLMClient(provider=actual_provider, api_key=api_key, api_url=api_url, model=model)
        else:
            self._llm = get_client()
        self._cache: Dict[str, Dict[str, Any]] = {}  # scene_id → advice

    def advise_scene(
        self,
        scene: Dict[str, Any],
        page_context: Optional[Dict[str, Any]] = None,
        force_llm: bool = False,
    ) -> Dict[str, Any]:
        """
        Get layout advice for a single scene.

        Args:
            scene: Scene data dict from parser
            page_context: Optional page-level context (previous scenes, etc.)
            force_llm: Force LLM call even if cached

        Returns:
            Dict with keys: panel_count, template, emotional_tone,
                           pacing, shot, notes, source (llm/rule)
        """
        scene_id = scene.get('scene_id', '')
        description = scene.get('description', '')
        dialogue_lines = scene.get('dialogue_lines', [])
        dialogue_count = scene.get('dialogue_count', 0)

        # Check cache
        if scene_id in self._cache and not force_llm:
            logger.debug(f"Using cached advice for {scene_id}")
            return self._cache[scene_id]

        # Try LLM first
        if self._llm.is_available():
            advice = self._llm_analyze(scene, description, dialogue_lines, dialogue_count)
            if advice:
                advice['source'] = 'llm'
                self._cache[scene_id] = advice
                logger.info(f"LLM advice for {scene_id}: {advice['template']}")
                return advice

        # Fallback to rule-based
        advice = self._rule_based_analyze(scene, description, dialogue_lines, dialogue_count)
        advice['source'] = 'rule'
        self._cache[scene_id] = advice
        logger.debug(f"Rule-based advice for {scene_id}: {advice['template']}")
        return advice

    def _llm_analyze(
        self,
        scene: Dict[str, Any],
        description: str,
        dialogue_lines: List[Dict[str, Any]],
        dialogue_count: int,
    ) -> Optional[Dict[str, Any]]:
        """Call LLM for scene analysis."""
        dialogue_text = "\n".join(
            f"{d.get('character', 'Narrator')}: {d.get('text', '')}"
            for d in dialogue_lines
        )
        if not dialogue_text:
            dialogue_text = "(no dialogue)"

        prompt = LAYOUT_PROMPT_TEMPLATE.format(
            scene_desc=description,
            count=dialogue_count,
            dialogue=dialogue_text[:400],
        )

        response = self._llm.chat(prompt, max_tokens=256, temperature=0.3)
        if not response:
            return None

        try:
            import json
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            if json_start < 0:
                return None
            data = json.loads(response[json_start:json_end])

            # Validate
            if not data.get('template') or not data.get('panel_count'):
                return None

            return {
                'panel_count': int(data.get('panel_count', 2)),
                'template': str(data.get('template', 'manga_classic')),
                'emotional_tone': str(data.get('emotional_tone', 'normal')),
                'pacing': str(data.get('pacing', 'medium')),
                'shot': str(data.get('shot', 'medium_shot')),
                'notes': str(data.get('notes', '')),
            }
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            logger.warning(f"Failed to parse LLM layout response: {e}")
            return None

    def _rule_based_analyze(
        self,
        scene: Dict[str, Any],
        description: str,
        dialogue_lines: List[Dict[str, Any]],
        dialogue_count: int,
    ) -> Dict[str, Any]:
        """
        Rule-based fallback when LLM is unavailable.
        Uses keyword detection + dialogue density heuristics.
        """
        desc_lower = description.lower()

        # --- Detect emotional tone ---
        emotional_tone = self._detect_tone(desc_lower, dialogue_lines)
        pacing = self._detect_pacing(desc_lower, dialogue_count)
        shot = self._detect_shot(desc_lower, description)

        # --- Determine panel count ---
        if emotional_tone == 'intense':
            panel_count = 1
        elif emotional_tone == 'rapid':
            panel_count = 4
        elif pacing == 'fast':
            panel_count = 3
        elif dialogue_count > 5:
            panel_count = 3
        elif dialogue_count >= 3:
            panel_count = 2
        else:
            panel_count = 1

        # --- Select template ---
        template = self._select_template(panel_count, emotional_tone, pacing)

        return {
            'panel_count': panel_count,
            'template': template,
            'emotional_tone': emotional_tone,
            'pacing': pacing,
            'shot': shot,
            'notes': '',
        }

    def _detect_tone(
        self,
        desc_lower: str,
        dialogue_lines: List[Dict[str, Any]],
    ) -> str:
        """Detect emotional tone from description keywords."""
        counts = {'intense': 0, 'romantic': 0, 'comedic': 0, 'suspense': 0, 'calm': 0}

        for keyword in INTENSE_TONES:
            if keyword in desc_lower:
                counts['intense'] += 2
        for keyword in ROMANTIC_TONES:
            if keyword in desc_lower:
                counts['romantic'] += 2
        for keyword in COMEDIC_TONES:
            if keyword in desc_lower:
                counts['comedic'] += 1
        for keyword in SUSPENSE_TONES:
            if keyword in desc_lower:
                counts['suspense'] += 1
        for keyword in CALM_TONES:
            if keyword in desc_lower:
                counts['calm'] += 1

        # Dialogue content check
        dialogue_all = " ".join(
            d.get('text', '').lower() for d in dialogue_lines
        )
        for keyword in INTENSE_TONES:
            if keyword in dialogue_all:
                counts['intense'] += 1

        winner = max(counts, key=counts.get)
        if counts[winner] == 0:
            return 'calm'
        return winner

    def _detect_pacing(self, desc_lower: str, dialogue_count: int) -> str:
        """Detect narrative pacing."""
        rapid_words = ["突然", "瞬间", "立刻", "快速", "转眼", "刹那间"]
        slow_words = ["慢慢", "渐渐地", "此时", "安静地", "沉默"]

        for w in rapid_words:
            if w in desc_lower:
                return 'fast'
        for w in slow_words:
            if w in desc_lower:
                return 'slow'

        if dialogue_count > 4:
            return 'medium'
        elif dialogue_count <= 1:
            return 'slow'
        return 'medium'

    def _detect_shot(self, desc_lower: str, description: str) -> str:
        """Detect suggested camera shot type."""
        close_keywords = ["特写", "脸部", "面部", "表情", "眼神", "嘴唇", "巨乳", "性器", "肉体", "胸", "臀部", "肌肤"]
        wide_keywords = ["远景", "广阔", "天空", "背景", "全场", "天台", "街道"]
        pov_keywords = ["视角", "看着", "望着", "映入眼帘"]
        over_keywords = ["俯视", "从上", "上方", "鸟瞰"]

        for kw in close_keywords:
            if kw in desc_lower:
                return 'close_up'
        for kw in wide_keywords:
            if kw in desc_lower:
                return 'wide_shot'
        for kw in pov_keywords:
            if kw in desc_lower:
                return 'POV'
        for kw in over_keywords:
            if kw in desc_lower:
                return 'over_shoulder'

        return 'medium_shot'

    def _select_template(
        self,
        panel_count: int,
        emotional_tone: str,
        pacing: str,
    ) -> str:
        """Select layout template based on scene analysis."""
        if panel_count == 1:
            if emotional_tone == 'intense':
                return 'splash'
            return 'full_bleed'

        if panel_count == 2:
            return 'half_vertical'

        if panel_count >= 3:
            if emotional_tone == 'intense':
                return 'dynamic_diagonal'
            if emotional_tone == 'comedic':
                return 'grid_4'
            return 'manga_classic'

        return 'manga_classic'

    def advise_page(
        self,
        page: Dict[str, Any],
        images: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Get layout advice for all scenes in a page.
        Returns a list of advice dicts, one per scene.
        """
        scenes = page.get('scenes', [])
        advice_list = []

        for scene in scenes:
            scene_advice = self.advise_scene(scene, page_context={'page': page})
            advice_list.append(scene_advice)

        # Page-level optimization: redistribute panels to fill page
        advice_list = self._redistribute_panels(scenes, advice_list)

        return advice_list

    def _redistribute_panels(
        self,
        scenes: List[Dict[str, Any]],
        advice_list: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Redistribute panel counts across scenes on a page.
        Ensures total panel count is feasible for the page layout.
        """
        if not scenes:
            return advice_list

        scene_count = len(scenes)

        # If all scenes suggest 1 panel each, keep as-is
        total_suggested = sum(a['panel_count'] for a in advice_list)

        # Cap at reasonable maximum for manga page (6)
        if total_suggested > 6:
            excess = total_suggested - 6
            # Reduce from lower-priority scenes (calm/medium first)
            sorted_indices = sorted(
                range(len(advice_list)),
                key=lambda i: advice_list[i]['panel_count']
            )
            for idx in sorted_indices[:excess]:
                if advice_list[idx]['panel_count'] > 1:
                    advice_list[idx]['panel_count'] -= 1

        return advice_list

    def clear_cache(self) -> None:
        """Clear the advice cache."""
        self._cache.clear()
        logger.debug("Layout advice cache cleared")
