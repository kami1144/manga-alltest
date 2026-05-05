"""
Storyboard Generator — Convert script text to complete storyboard parameters.

This module implements "Capability 1: Script → Storyboard" for MangaAutoLayout.
It takes raw script text and generates complete storyboard parameters including:
- shot_type (camera shot selection)
- emotional_tone (scene mood)
- pacing (narrative rhythm)
- panel_count (number of panels)
- importance (scene priority)
- composition_notes (layout guidance)

Uses LLM for intelligent analysis with rule-based fallback.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional

from utils.llm_client import get_client, LLMClient

logger = logging.getLogger(__name__)

# --- Output schema ---
SHOT_TYPES = {
    'close_up', 'medium_shot', 'wide_shot', 'two_shot', 'POV',
    'over_shoulder', 'insert', 'tilted', 'aerial'
}

EMOTIONAL_TONES = {
    'intense', 'calm', 'romantic', 'comedic', 'mysterious',
    'surprised', 'tense', 'sad', 'melancholy'
}

PACING_VALUES = {'fast', 'slow', 'medium'}

IMPORTANCE_LEVELS = {'high', 'medium', 'low'}

# --- LLM Prompt Template ---
STORYBOARD_PROMPT = """You are a professional manga storyboard artist.

Convert the following manga script into detailed storyboard parameters.

Script:
{script_text}

Respond ONLY with a valid JSON array of scene objects:
[
  {{
    "scene_id": "s1",
    "description": "brief scene description",
    "shot_type": "close_up|medium_shot|wide_shot|two_shot|POV|over_shoulder|insert|tilted|aerial",
    "emotional_tone": "intense|calm|romantic|comedic|mysterious|surprised|tense|sad|melancholy",
    "pacing": "fast|slow|medium",
    "panel_count": 1-6,
    "importance": "high|medium|low",
    "composition_notes": "layout composition guidance"
  }}
]

Guidelines—use context to decide:
• ROMANTIC SCENES (告白/接吻/拥抱/脸红心跳/温柔氛围): tone=romantic, pacing=slow, shot=two_shot or medium_shot
  - Even if actions like "握住手" appear, it's emotional setup, NOT action
  - Look for: 告白, 表白, 接吻, 拥抱, 脸红, 心动, 温柔, 轻声, 夕陽, 海灘
• ACTION SCENES (突然冲出/战斗/危机/快速躲避): tone=intense, pacing=fast, shot=wide_shot→close_up
  - Look for: 杀手, 冲出, 战斗, 危机, 逃跑, 被打, 反击, 快速
• QUIET DIALOGUE (日常对话/教室/说明): tone=calm, pacing=medium, shot=medium_shot
  - Look for: 老师说, 解释, 说明, 日常, 回答
• COMEDY (吐槽/尴尬/误会): tone=comedic, pacing=medium
  - Look for: 搞笑, 笨蛋, 蠢, 尴尬, 吐槽, 误会
• SAD/MELANCHOLY (悲伤/忧郁/孤独): tone=sad or melancholy, pacing=slow
  - Look for: 忧郁, 悲伤, 泣, 哭, 孤独, 一人, 黙々, 静か, 物的, 思考
• KEY DISTINCTION: "握住手" in romantic context = romantic, not intense!
  The scene mood determines tone, not individual action words alone."""

# --- Rule-based keyword dictionaries ---
SHOT_KEYWORDS = {
    'close_up': ['特写', '脸部', '面部', '表情', '眼神', '嘴唇', '脸'],
    'wide_shot': ['远景', '全景', '全场', '天空', '背景', '街道', '天台', '校园', '室内'],
    'aerial': ['俯视', '鸟瞰', '上方', '从上空', '空中'],
    'POV': ['视角', '看着', '望着', '映入眼帘', '第一人称'],
    'tilted': ['斜角', '动感', '对角线', '倾斜'],
    'two_shot': ['两人', '二人', '双人', '并排', '并肩'],
    'insert': ['插入', '细节', '特写'],
    'over_shoulder': ['过肩', '背后'],
}

TONE_KEYWORDS = {
    'intense': ['紧张', '激烈', '高潮', '冲击', '暴力', '兴奋', '战斗', '危机', '冲出', '杀手', '逃跑', '反击'],
    'romantic': ['告白', '表白', '接吻', '拥抱', '爱抚', '脸红', '心跳', '心动', '浪漫', '温柔', '轻声', '夕阳', '海滩', '海风', '手'],
    'comedic': ['搞笑', '尴尬', '误会', '吐槽', '笨蛋', '蠢', '吐槽'],
    'mysterious': ['悬疑', '神秘', '未知', '黑暗中', '阴谋'],
    'surprised': ['惊讶', '震惊', '意外', '吃惊', '吓', '！'],
    'tense': ['紧张', '不安', '危险', '害怕', '恐惧', '担心'],
    'calm': ['平静', '日常', '对话', '说明', '回忆', '思考', '老师', '学生', '解释'],
    'sad': ['悲伤', '忧郁', '忧', '泣', '哭', '难过', '伤心', '寂', '孤独', '一人', '切ない'],
    'melancholy': ['憂鬱', '沈黙', '静か', '物的', 'Thoughts', '一人', '黙々'],
}

PACING_KEYWORDS = {
    'fast': ['突然', '瞬间', '立刻', '快速', '转眼', '冲出', '迅速', '快速'],
    'slow': ['慢慢', '渐渐', '此时', '安静', '沉默', '缓慢', '轻声', '温柔'],
}

ACTION_KEYWORDS = {
    'high': ['突然', '握住', '拥抱', '接吻', '告白', '表白', '战斗', '逃跑', '危机', '冲出'],
    'medium': ['转身', '走去', '坐下', '站起', '拿出', '打开'],
    'low': ['对话', '说明', '回忆', '思考', '讲述'],
}


class StoryboardGenerator:
    """
    Generate storyboard parameters from script text.

    Main entry point for Script → Storyboard capability.
    Falls back to rule-based analysis when LLM unavailable.
    """

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self._llm = llm_client
        self._cache: Dict[str, Any] = {}

    def generate(
        self,
        script_text: str,
        force_llm: bool = False,
    ) -> Dict[str, Any]:
        """
        Generate storyboard from script text.

        Args:
            script_text: Raw script text in format:
                场景1
                场景描述
                角色：对白
                （动作描述）

            force_llm: Force LLM call even if cached

        Returns:
            Dict with "scenes" key containing list of scene parameters:
            {{
                "scenes": [
                    {{
                        "scene_id": "s1",
                        "description": "...",
                        "shot_type": "medium_shot",
                        "emotional_tone": "romantic",
                        "pacing": "slow",
                        "panel_count": 2,
                        "importance": "high",
                        "composition_notes": "..."
                    }}
                ]
            }}
        """
        if not script_text or not script_text.strip():
            logger.warning("Empty script text, returning default")
            return self._default_result()

        # Parse script into raw scenes
        raw_scenes = self._parse_script_text(script_text)
        if not raw_scenes:
            logger.warning("Failed to parse script, returning default")
            return self._default_result()

        # Use LLM if available
        if self._is_llm_available() and not force_llm:
            llm_result = self._llm_generate(raw_scenes)
            if llm_result:
                logger.info(f"LLM generated {len(llm_result['scenes'])} scenes")
                return llm_result

        # Fallback to rule-based
        result = self._rule_based_generate(raw_scenes)
        logger.info(f"Rule-based generated {len(result['scenes'])} scenes")
        return result

    def _is_llm_available(self) -> bool:
        """Check if LLM client is available."""
        if self._llm is not None:
            return self._llm.is_available()
        client = get_client()
        return client.is_available()

    def _get_llm(self) -> LLMClient:
        """Get or create LLM client."""
        if self._llm is not None:
            return self._llm
        return get_client()

    def _parse_script_text(self, script_text: str) -> List[Dict[str, Any]]:
        """
        Parse script text into raw scene dicts.

        Expected format:
            场景1
            场景位置，时间
            角色1：对白
            角色2：对白
            （动作描述）
        """
        lines = script_text.strip().split('\n')
        scenes: List[Dict[str, Any]] = []
        current_scene: Optional[Dict[str, Any]] = None

        scene_pattern = re.compile(r'^(?:场景|Scene|第|Page)\s*(\d+)')
        dialogue_pattern = re.compile(r'^([^：:]+)[:：](.+)$')
        action_pattern = re.compile(r'^（(.+)）|^\[(.+)\]$')

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # New scene marker
            if scene_pattern.match(line):
                if current_scene:
                    scenes.append(current_scene)
                # Extract scene description (everything after number)
                desc = scene_pattern.sub('', line).strip()
                current_scene = {
                    'scene_id': f"s{len(scenes) + 1}",
                    'description': desc or line,
                    'dialogue_lines': [],
                    'actions': [],
                }
                continue

            # Dialogue
            dlg_match = dialogue_pattern.match(line)
            if dlg_match and current_scene:
                current_scene['dialogue_lines'].append({
                    'character': dlg_match.group(1).strip(),
                    'text': dlg_match.group(2).strip(),
                })
                continue

            # Action in parentheses
            act_match = action_pattern.match(line)
            if act_match and current_scene:
                action_text = act_match.group(1) or act_match.group(2)
                current_scene['actions'].append(action_text.strip())
                # Merge action into description
                if current_scene['description']:
                    current_scene['description'] += f" ({action_text.strip()})"
                else:
                    current_scene['description'] = action_text.strip()
                continue

            # Plain text = scene description or continuation
            if current_scene:
                if current_scene['description']:
                    current_scene['description'] += f" {line}"
                else:
                    current_scene['description'] = line

        # Finalize last scene
        if current_scene:
            scenes.append(current_scene)

        # Ensure at least one scene
        if not scenes:
            scenes.append({
                'scene_id': 's1',
                'description': script_text[:100],
                'dialogue_lines': [],
                'actions': [],
            })

        return scenes

    def _llm_generate(
        self,
        raw_scenes: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """Use LLM to generate storyboard parameters."""
        llm = self._get_llm()

        # Build script text for LLM
        script_text = self._build_script_text(raw_scenes)

        response = llm.chat(
            STORYBOARD_PROMPT.format(script_text=script_text),
            max_tokens=1024,
            temperature=0.3,
        )

        if not response:
            return None

        try:
            # Extract JSON from response
            json_start = response.find('[')
            if json_start < 0:
                json_start = response.find('{')

            if json_start < 0:
                logger.warning("No JSON found in LLM response")
                return None

            # Find the matching bracket
            if response[json_start] == '[':
                json_end = response.rfind(']') + 1
            else:
                json_end = response.rfind('}') + 1
                json_start = response.find('{')

            json_str = response[json_start:json_end]
            data = json.loads(json_str)

            # Ensure it's a list
            if isinstance(data, dict):
                data = [data]
            elif not isinstance(data, list):
                logger.warning(f"Unexpected JSON type: {type(data)}")
                return None

            # Validate and normalize each scene
            scenes = []
            for i, s in enumerate(data):
                scene = self._normalize_scene(s, raw_scenes[i] if i < len(raw_scenes) else {})
                scenes.append(scene)

            return {'scenes': scenes}

        except (json.JSONDecodeError, KeyError, IndexError) as e:
            logger.warning(f"Failed to parse LLM response: {e}")
            return None

    def _build_script_text(self, raw_scenes: List[Dict[str, Any]]) -> str:
        """Build readable script text for LLM."""
        lines = []
        for i, scene in enumerate(raw_scenes):
            lines.append(f"\nScene {i+1}")
            lines.append(scene.get('description', ''))
            for dlg in scene.get('dialogue_lines', []):
                char = dlg.get('character', 'Character')
                text = dlg.get('text', '')
                lines.append(f"  {char}: {text}")
            for act in scene.get('actions', []):
                lines.append(f"  ({act})")
        return '\n'.join(lines)

    def _normalize_scene(
        self,
        scene_data: Dict[str, Any],
        raw_scene: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Normalize and validate scene parameters."""
        # Extract scene_id
        scene_id = scene_data.get('scene_id', raw_scene.get('scene_id', 's1'))

        # Description (use raw if not provided)
        description = scene_data.get('description', '')
        if not description:
            description = raw_scene.get('description', '')

        # Shot type (validate against known types)
        shot = scene_data.get('shot_type', 'medium_shot')
        if shot not in SHOT_TYPES:
            shot = self._rule_shot_type(raw_scene.get('description', ''))

        # Emotional tone
        tone = scene_data.get('emotional_tone', 'calm')
        if tone not in EMOTIONAL_TONES:
            tone = 'calm'

        # Pacing
        pacing = scene_data.get('pacing', 'medium')
        if pacing not in PACING_VALUES:
            pacing = 'medium'

        # Panel count (1-6)
        panel_count = scene_data.get('panel_count', 2)
        try:
            panel_count = max(1, min(6, int(panel_count)))
        except (ValueError, TypeError):
            panel_count = 2

        # Importance
        importance = scene_data.get('importance', 'medium')
        if importance not in IMPORTANCE_LEVELS:
            importance = 'medium'

        # Composition notes
        notes = scene_data.get('composition_notes', '')

        return {
            'scene_id': scene_id,
            'description': description,
            'shot_type': shot,
            'emotional_tone': tone,
            'pacing': pacing,
            'panel_count': panel_count,
            'importance': importance,
            'composition_notes': notes,
        }

    def _rule_based_generate(
        self,
        raw_scenes: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Rule-based storyboard generation."""
        scenes = []
        for i, raw in enumerate(raw_scenes):
            desc = raw.get('description', '')
            dialogue_lines = raw.get('dialogue_lines', [])
            actions = raw.get('actions', [])
            dlg_count = len(dialogue_lines)

            # Determine shot type
            shot = self._rule_shot_type(desc)

            # Determine emotional tone
            tone = self._rule_emotional_tone(desc, dialogue_lines, actions)

            # Determine pacing
            pacing = self._rule_pacing(desc, dlg_count)

            # Determine panel count
            panel_count = self._rule_panel_count(tone, pacing, dlg_count)

            # Determine importance
            importance = self._rule_importance(desc, actions)

            # Generate composition notes
            notes = self._rule_composition_notes(shot, tone, importance)

            scenes.append({
                'scene_id': raw.get('scene_id', f"s{i + 1}"),
                'description': desc,
                'shot_type': shot,
                'emotional_tone': tone,
                'pacing': pacing,
                'panel_count': panel_count,
                'importance': importance,
                'composition_notes': notes,
            })

        return {'scenes': scenes}

    def _rule_shot_type(self, description: str) -> str:
        """Determine shot type from description."""
        desc_lower = description.lower()

        # Check for romantic context FIRST (overrides generic location keywords)
        romantic_markers = ['告白', '表白', '接吻', '拥抱', '握住', '脸红', '心动', '轻声']
        if any(m in desc_lower for m in romantic_markers):
            return 'two_shot'

        for shot, keywords in SHOT_KEYWORDS.items():
            if any(kw in desc_lower for kw in keywords):
                return shot

        return 'medium_shot'

    def _rule_emotional_tone(
        self,
        description: str,
        dialogue_lines: List[Dict[str, Any]],
        actions: List[str],
    ) -> str:
        """Determine emotional tone."""
        # Count keyword matches
        desc_lower = description.lower()
        dlg_text = ' '.join(d.get('text', '') for d in dialogue_lines).lower()
        act_text = ' '.join(actions).lower()
        combined = f"{desc_lower} {dlg_text} {act_text}"

        scores = {tone: 0 for tone in EMOTIONAL_TONES}

        for tone, keywords in TONE_KEYWORDS.items():
            for kw in keywords:
                if kw in combined:
                    scores[tone] += 1

        # Romantic context detection: 告白/表白/接吻/拥抱/脸红/心动/温柔
        # NOTE: "握住" in romantic context (告白/天台场景) = romantic, not intense
        romantic_context_markers = ['告白', '表白', '接吻', '拥抱', '脸红', '心动', '温柔', '轻声', '夕阳', '海滩', '海风', '握住', '拉住']
        has_romantic_context = any(m in combined for m in romantic_context_markers)

        # Action-like emotional words that are actually romantic in context
        emotional_actions = ['握住', '拉', '抱', '靠近']
        for act in emotional_actions:
            if act in combined:
                if has_romantic_context:
                    scores['romantic'] += 2
                else:
                    scores['intense'] += 1

        # Explicit romantic markers
        if '拥抱' in combined or '接吻' in combined:
            scores['romantic'] += 3
        if '告白' in combined or '表白' in combined:
            scores['romantic'] += 3
        if '脸红' in combined or '心动' in combined:
            scores['romantic'] += 2

        # Explicit intense markers (only if NOT in romantic context)
        intense_markers = ['战斗', '杀手', '冲出', '危机', '逃跑']
        for marker in intense_markers:
            if marker in combined:
                if has_romantic_context:
                    # Don't let action words override romantic in romantic scenes
                    pass
                else:
                    scores['intense'] += 2

        # Return highest scoring tone
        winner = max(scores, key=scores.get)
        if scores[winner] == 0:
            return 'calm'
        return winner

    def _rule_pacing(self, description: str, dialogue_count: int) -> str:
        """Determine pacing."""
        desc_lower = description.lower()

        # Check romantic context first - romantic scenes are slow even with "突然"
        romantic_markers = ['告白', '表白', '接吻', '拥抱', '脸红', '心动', '温柔', '轻声', '夕阳', '海滩', '握住']
        if any(m in desc_lower for m in romantic_markers):
            return 'slow'

        # Check action context (overrides romantic markers above if no romantic context)
        action_markers = ['冲出', '杀手', '战斗', '危机', '逃跑', '迅速', '快速']
        if any(m in desc_lower for m in action_markers):
            return 'fast'

        for pacing, keywords in PACING_KEYWORDS.items():
            if any(kw in desc_lower for kw in keywords):
                return pacing

        if dialogue_count > 4:
            return 'medium'
        elif dialogue_count <= 1:
            return 'slow'
        return 'medium'

    def _rule_panel_count(
        self,
        tone: str,
        pacing: str,
        dialogue_count: int,
    ) -> int:
        """Determine panel count."""
        if tone == 'intense' and dialogue_count <= 2:
            return 1
        if tone == 'tense' and pacing == 'fast':
            return 1
        # Romantic scenes with dialogue get more panels for buildup
        if tone == 'romantic' and dialogue_count >= 1:
            return 2

        if dialogue_count > 5:
            return 4
        elif dialogue_count >= 3:
            return 3
        elif dialogue_count >= 1:
            return 2
        return 1

    def _rule_importance(self, description: str, actions: List[str]) -> str:
        """Determine scene importance."""
        desc_lower = description.lower()
        act_text = ' '.join(actions).lower()
        combined = f"{desc_lower} {act_text}"

        # High importance markers
        high_markers = ['突然', '告白', '表白', '接吻', '拥抱', '战斗', '危机', '决定']
        for marker in high_markers:
            if marker in combined:
                return 'high'

        # Medium importance
        medium_markers = ['转身', '拿出', '打开', '走去', '坐下']
        for marker in medium_markers:
            if marker in combined:
                return 'medium'

        return 'medium'

    def _rule_composition_notes(
        self,
        shot_type: str,
        tone: str,
        importance: str,
    ) -> str:
        """Generate composition notes."""
        notes = []

        if shot_type == 'close_up':
            notes.append("人物居中")
        elif shot_type == 'wide_shot':
            notes.append("背景完整")
        elif shot_type == 'two_shot':
            notes.append("双人构图")

        if tone == 'romantic':
            notes.append("对话泡放下方")
        elif tone == 'intense':
            notes.append("动作感")

        if importance == 'high':
            notes.append("重点渲染")

        return "，".join(notes) if notes else ""

    def _default_result(self) -> Dict[str, Any]:
        """Return default result for empty/error cases."""
        return {
            'scenes': [{
                'scene_id': 's1',
                'description': '默认场景',
                'shot_type': 'medium_shot',
                'emotional_tone': 'calm',
                'pacing': 'medium',
                'panel_count': 2,
                'importance': 'medium',
                'composition_notes': '',
            }]
        }


# --- Convenience functions ---

def generate_storyboard(script_text: str) -> Dict[str, Any]:
    """
    Convenience function to generate storyboard from script text.

    Args:
        script_text: Raw script text

    Returns:
        Dict with "scenes" key
    """
    generator = StoryboardGenerator()
    return generator.generate(script_text)


# --- Test entry point ---

if __name__ == '__main__':
    import sys

    logging.basicConfig(level=logging.INFO)

    # Sample script
    sample_script = """场景1
天台，傍晚
男主：今天有话想跟你说...
女主：什么话？
（男主突然握住女主的手）"""

    # Use command line argument if provided
    if len(sys.argv) > 1:
        with open(sys.argv[1], 'r', encoding='utf-8') as f:
            sample_script = f.read()

    print(f"Input script:\n{sample_script}\n")
    print("-" * 40)

    result = generate_storyboard(sample_script)
    print(json.dumps(result, ensure_ascii=False, indent=2))