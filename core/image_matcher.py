"""
Image Matcher — Scene-to-Image assignment with saliency-aware cropping.

Responsibilities:
1. Match images to scenes (LLM semantic matching with keyword fallback)
2. Pre-compute salient regions (face/focal point) for each image
3. Assign images to panels based on scene importance (from narrative pacing)
4. Return image_ref + salient_region per panel for canvas rendering

Usage:
    matcher = ImageMatcher(images, scenes)
    assignments = matcher.match()   # [{panel_id, image_ref, salient_region, importance}, ...]
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image

from core.image_composer import find_salient_region
from core.image_analyzer import ImageAnalyzer, ImageAnalysis

logger = logging.getLogger(__name__)

# Shot type compatibility matrix
# Which shot types are compatible with which for manga panel matching
SHOT_COMPATIBILITY = {
    # Exact matches (score 1.0)
    'close_up': {'close_up': 1.0},
    'medium_shot': {'medium_shot': 1.0, 'two_shot': 0.7, 'over_shoulder': 0.6},
    'wide_shot': {'wide_shot': 1.0, 'aerial': 0.7},
    'two_shot': {'two_shot': 1.0, 'medium_shot': 0.7},
    'POV': {'POV': 1.0, 'close_up': 0.5},
    'over_shoulder': {'over_shoulder': 1.0, 'medium_shot': 0.6},
    'insert': {'insert': 1.0, 'close_up': 0.7},
    'tilted': {'tilted': 1.0},
    'aerial': {'aerial': 1.0, 'wide_shot': 0.7},
}

# Emotional tone compatibility matrix
# Which tones are compatible with which
TONE_COMPATIBILITY = {
    # Tono principal
    'intense': {'intense': 1.0, 'surprised': 0.9, 'joyful': 0.9, 'happy': 0.7, 'tense': 0.6, 'angry': 0.6, 'calm': 0.3},
    'calm': {'calm': 1.0, 'romantic': 0.7, 'comedic': 0.5, 'happy': 0.4, 'intimate': 0.5},
    'romantic': {'romantic': 1.0, 'intimate': 0.9, 'calm': 0.7, 'mysterious': 0.4, 'happy': 0.5, 'surprised': 0.4},
    'comedic': {'comedic': 1.0, 'happy': 0.8, 'calm': 0.5, 'surprised': 0.5},
    'mysterious': {'mysterious': 1.0, 'tense': 0.7, 'romantic': 0.4, 'melancholy': 0.5},
    'surprised': {'surprised': 1.0, 'intense': 0.7, 'tense': 0.6, 'romantic': 0.4},
    'tense': {'tense': 1.0, 'intense': 0.8, 'surprised': 0.6, 'mysterious': 0.5, 'sad': 0.4},
    'sad': {'sad': 1.0, 'melancholy': 0.9, 'tense': 0.5, 'calm': 0.3, 'mysterious': 0.4},
    'happy': {'happy': 1.0, 'comedic': 0.8, 'romantic': 0.6, 'calm': 0.4, 'joyful': 0.9},
    'melancholy': {'melancholy': 1.0, 'sad': 0.9, 'mysterious': 0.5, 'tense': 0.4, 'calm': 0.3},
    # Tonos adicionales
    'intimate': {'intimate': 1.0, 'romantic': 0.9, 'calm': 0.6, 'mysterious': 0.4},
    'joyful': {'joyful': 1.0, 'happy': 0.9, 'comedic': 0.6, 'romantic': 0.5, 'calm': 0.3},
    'angry': {'angry': 1.0, 'intense': 0.9, 'tense': 0.6, 'surprised': 0.4},
    'fear': {'fear': 1.0, 'tense': 0.7, 'mysterious': 0.6, 'intense': 0.5, 'sad': 0.3},
    'energetic': {'energetic': 1.0, 'happy': 0.8, 'comedic': 0.6, 'joyful': 0.7, 'intense': 0.6},
}

# Scene type compatibility
SCENE_TYPE_COMPATIBILITY = {
    'indoor': {'indoor': 1.0},
    'outdoor': {'outdoor': 1.0, 'landscape': 0.8},
    'close_up': {'close_up': 1.0},
    'medium_shot': {'medium_shot': 1.0},
    'wide_shot': {'wide_shot': 1.0},
    'portrait': {'portrait': 1.0},
    'landscape': {'landscape': 1.0, 'outdoor': 0.7},
    'unknown': {'unknown': 0.5},  # Can't judge unknown, give neutral score
}


class MatchResult:
    """Detailed result of scene-image matching with precision scoring."""
    def __init__(
        self,
        scene_id: str,
        image_ref: str,
        overall_score: float,
        shot_score: float,
        tone_score: float,
        scene_score: float,
        object_score: float,
        reasoning: str,
    ):
        self.scene_id = scene_id
        self.image_ref = image_ref
        self.overall_score = overall_score
        self.shot_score = shot_score
        self.tone_score = tone_score
        self.scene_score = scene_score
        self.object_score = object_score
        self.reasoning = reasoning
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'scene_id': self.scene_id,
            'image_ref': self.image_ref,
            'overall_score': round(self.overall_score, 3),
            'shot_score': round(self.shot_score, 3),
            'tone_score': round(self.tone_score, 3),
            'scene_score': round(self.scene_score, 3),
            'object_score': round(self.object_score, 3),
            'reasoning': self.reasoning,
        }

class ImageMatcher:
    """
    Matches uploaded images to manga scenes and panels.
    Assigns importance based on scene pacing (climax=high, tension=medium, calm=low).
    """

    # Keywords for rule-based fallback matching
    SCENE_KEYWORDS = {
        'face': ['顔', 'face', 'portrait', '表情', '目', '口'],
        'action': ['アクション', 'action', '動き', 'motion', '跳', '飛'],
        'background': ['背景', 'background', '風景', '景色', '街', '部屋'],
        'emotion': ['感情', 'emotion', '泣', '笑', '怒', '悲'],
        'romantic': ['ロマンチック', 'romantic', 'キス', '抱き', '甘い'],
        'dialogue': ['会話', 'dialogue', '会話中', '話して', '言って'],
    }

    def __init__(
        self,
        images: List[Dict[str, Any]],
        script_data: Dict[str, Any],
        layout_data: Dict[str, Any],
        llm_client: Optional[Any] = None,
    ):
        """
        Args:
            images: List of image dicts from image_processor (each has pil_image, path, etc.)
            script_data: Script data with scene descriptions
            layout_data: Layout data with scene → panel mapping
            llm_client: Optional LLM client for semantic matching
        """
        self._images = images
        self._script_data = script_data
        self._layout_data = layout_data
        self._llm = llm_client

        # Pre-compute salient regions for all images (cached)
        self._saliency_cache: Dict[str, Tuple[int, int, int, int]] = {}

    # ────────────────────────────────────────────────────────────────
    # Main entry point
    # ────────────────────────────────────────────────────────────────

    def match(self) -> List[Dict[str, Any]]:
        """
        Assign images to panels across all pages.

        Returns:
            List of assignments: [{panel_id, image_ref, salient_region, importance, match_score}, ...]
        """
        if not self._images:
            logger.warning("ImageMatcher: no images provided, skipping matching")
            return []

        # Pre-compute saliency for all images
        self._precompute_saliency()

        assignments = []
        pages = self._layout_data.get('pages', [])

        for page in pages:
            page_assignments = self._match_page(page)
            assignments.extend(page_assignments)

        logger.info(f"ImageMatcher: assigned {len(assignments)} panels to images")
        return assignments

    # ────────────────────────────────────────────────────────────────
    # Per-page matching
    # ────────────────────────────────────────────────────────────────

    def _match_page(self, page: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Match images to panels on a single page."""
        panels = page.get('panels', [])
        if not panels:
            return []

        # Build scene → panels mapping
        scene_panels: Dict[str, List[Dict]] = {}
        for panel in panels:
            scene = panel.get('scene', {})
            scene_id = scene.get('scene_id', '')
            if scene_id:
                scene_panels.setdefault(scene_id, []).append(panel)

        # Collect scene descriptions for LLM matching
        scene_descs = []
        for scene_id, scene_panels_list in scene_panels.items():
            scene_data = self._get_scene_data(scene_id)
            if scene_data:
                scene_descs.append({
                    'scene_id': scene_id,
                    'description': scene_data.get('description', '')[:200],
                    'shot_type': scene_data.get('shot_type', 'unknown'),
                    'emotional_tone': scene_data.get('emotional_tone', 'unknown'),
                    'pacing': scene_data.get('pacing', 'medium'),
                    'dialogue_preview': self._get_dialogue_preview(scene_data),
                    'panel_ids': [p.get('id') for p in scene_panels_list],
                })

        # Try LLM matching first, fallback to rules
        if self._llm and self._llm.is_available():
            logger.info(f"ImageMatcher: LLM available=True (provider check passed)")
            panel_assignments = self._llm_match_scenes(scene_descs)
        else:
            llm_state = f"llm={'present' if self._llm else 'None'}, available={'N/A' if not self._llm else self._llm.is_available()}"
            logger.info(f"ImageMatcher: LLM skipped ({llm_state}), using rule-based")
            panel_assignments = self._rule_match_scenes(scene_descs)
        for pa in panel_assignments:
            image_ref = pa.get('image_ref', '')
            pa['salient_region'] = self._saliency_cache.get(image_ref, (0, 0, 0, 0))
            pa['importance'] = self._derive_importance(pa.get('scene_id', ''))

        return panel_assignments

    # ────────────────────────────────────────────────────────────────
    # LLM-based semantic matching
    # ────────────────────────────────────────────────────────────────

    def _llm_match_scenes(
        self,
        scene_descs: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Use LLM to decide semantic scene-image matching, 
        then compute PRECISE scores using _compute_match_score.
        
        This ensures:
        1. LLM provides semantic understanding of which image fits which scene
        2. We compute exact accuracy scores (not LLM's self-reported confidence)
        """
        try:
            # First: analyze all images with Capability 2
            image_analyses = self._analyze_all_images()
            
            # Second: use LLM to decide which image for which scene
            image_summaries = self._summarize_images_with_analyses(image_analyses)
            prompt = self._build_matching_prompt(scene_descs, image_summaries)
            logger.info(f"ImageMatcher: LLM deciding scene-image assignments...")
            response = self._llm.complete(prompt)
            logger.info(f"ImageMatcher: LLM response: {str(response)[:200] if response else 'None'}")

            # Parse LLM's assignment decisions
            raw_assignments = self._parse_llm_assignments(response, scene_descs)
            if not raw_assignments:
                logger.warning("ImageMatcher: LLM didn't return valid assignments, using rule-based")
                return self._rule_match_scenes(scene_descs)
            
            # Third: compute precise scores for each assignment
            # Build scene_id → scene data map
            scene_map = {s['scene_id']: s for s in scene_descs}
            # Build image_ref → analysis map
            analysis_map = {a.image_ref: a for a in image_analyses}
            
            results = []
            for assignment in raw_assignments:
                scene_id = assignment.get('scene_id', '')
                image_ref = assignment.get('image_ref', '')
                
                scene = scene_map.get(scene_id, {})
                analysis = analysis_map.get(image_ref)
                
                if scene and analysis:
                    # Compute precise match score
                    match_result = self._compute_match_score(scene, analysis, image_ref)
                    results.append({
                        'panel_id': assignment.get('panel_id', ''),
                        'scene_id': scene_id,
                        'image_ref': image_ref,
                        'match_score': match_result.overall_score,
                        'shot_score': match_result.shot_score,
                        'tone_score': match_result.tone_score,
                        'scene_score': match_result.scene_score,
                        'object_score': match_result.object_score,
                        'reasoning': match_result.reasoning,
                    })
                else:
                    # Fallback for missing data
                    results.append({
                        'panel_id': assignment.get('panel_id', ''),
                        'scene_id': scene_id,
                        'image_ref': image_ref,
                        'match_score': 0.0,
                        'shot_score': 0.0,
                        'tone_score': 0.0,
                        'scene_score': 0.0,
                        'object_score': 0.0,
                        'reasoning': 'missing scene or image data',
                    })
            
            logger.info(f"ImageMatcher: computed precise scores for {len(results)} assignments")
            return results
            
        except Exception as e:
            logger.warning(f"ImageMatcher: LLM matching failed ({e}), falling back to rules")
            return self._rule_match_scenes(scene_descs)

    def _analyze_all_images(self) -> List[ImageAnalysis]:
        """Analyze all images once and cache results."""
        analyzer = ImageAnalyzer()
        analyses = []
        for img in self._images:
            path = img.get('path', '')
            if path:
                analysis = analyzer.analyze(path)
                analyses.append(analysis)
        return analyses

    def _summarize_images_with_analyses(self, analyses: List[ImageAnalysis]) -> List[Dict[str, str]]:
        """Build image summaries from pre-computed analyses."""
        summaries = []
        for img, analysis in zip(self._images, analyses):
            objects_str = ', '.join(analysis.objects[:5]) if analysis.objects else 'unknown'
            tone_str = ', '.join(analysis.emotional_tone) if analysis.emotional_tone else 'neutral'
            desc = (
                f"[{img.get('filename', 'unknown')}] "
                f"Objects: {objects_str}. "
                f"Shot: {analysis.shot_type}. "
                f"Tone: {tone_str}. "
                f"Characters: {analysis.character_count}. "
                f"{analysis.raw_description[:80] if analysis.raw_description else ''}"
            )
            summaries.append({
                'image_ref': img.get('path', ''),
                'description': desc,
            })
        return summaries

    def _summarize_images_for_matching(self) -> List[Dict[str, str]]:
        """Get a rich description of each image using LLM analysis (Capability 2)."""
        summaries = []
        analyzer = ImageAnalyzer()
        
        # Use LLM-based image analysis if available, otherwise fallback to filename
        for img in self._images:
            pil_img = img.get('pil_image')
            if not pil_img:
                continue
            
            path = img.get('path', '')
            
            # Try LLM-based analysis (Capability 2)
            if analyzer.is_available():
                try:
                    analysis = analyzer.analyze(path)
                    # Build rich description from analysis
                    objects_str = ', '.join(analysis.objects[:5]) if analysis.objects else 'unknown'
                    tone_str = ', '.join(analysis.emotional_tone) if analysis.emotional_tone else 'neutral'
                    desc = (
                        f"[{img.get('filename', 'unknown')}] "
                        f"Objects: {objects_str}. "
                        f"Shot: {analysis.shot_type}. "
                        f"Tone: {tone_str}. "
                        f"Characters: {analysis.character_count}. "
                        f"Expression: {analysis.face_expression}. "
                        f"{analysis.raw_description[:100] if analysis.raw_description else ''}"
                    )
                except Exception as e:
                    logger.warning(f"Image analysis failed for {path}: {e}")
                    desc = f"[{img.get('filename', 'unknown')}] {img.get('width', 0)}x{img.get('height', 0)} image"
            else:
                # Fallback: basic file info
                desc = f"[{img.get('filename', 'unknown')}] {img.get('width', 0)}x{img.get('height', 0)} image"
            
            summaries.append({
                'image_ref': path,
                'description': desc,
            })
        return summaries

    def _build_matching_prompt(
        self,
        scene_descs: List[Dict[str, Any]],
        image_summaries: List[Dict[str, str]],
    ) -> str:
        scenes_text = "\n".join(
            f"Scene {s['scene_id']}: {s['description']} | "
            f"shot: {s.get('shot_type', 'unknown')}, "
            f"tone: {s.get('emotional_tone', 'unknown')}, "
            f"pacing: {s.get('pacing', 'medium')} | "
            f"dialogue: {s.get('dialogue_preview', '')}"
            for s in scene_descs
        )
        images_text = "\n".join(
            f"- {img['image_ref']}: {img['description']}"
            for img in image_summaries
        )
        return (
            "You are a manga artist matching scenes to reference images.\n\n"
            f"Scenes to match:\n{scenes_text}\n\n"
            f"Available images:\n{images_text}\n\n"
            "For each scene, pick the best matching image (by scene description and emotional tone).\n"
            "Output JSON only: [{\"scene_id\":\"s1\",\"image_ref\":\"path/to/img.jpg\",\"match_score\":0.9},...]\n"
            "Score 0.0-1.0 for confidence. Unmatched scenes get score 0."
        )

    def _parse_llm_assignments(
        self,
        response: Optional[str],
        scene_descs: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Parse LLM JSON response into panel assignments."""
        import json, re
        
        # Guard: response must be a valid non-empty string
        if not response or not isinstance(response, str):
            logger.warning("LLM response is empty or None, falling back to rule-based")
            return []
        
        try:
            # Try to extract JSON array from response
            # Handle cases where LLM wraps JSON in code blocks or extra text
            json_str = response.strip()
            
            # Try direct JSON parse first
            try:
                data = json.loads(json_str)
            except json.JSONDecodeError:
                # Find JSON array in the response
                match = re.search(r'\[.*\]', json_str, re.DOTALL)
                if not match:
                    logger.warning(f"No JSON array found in LLM response: {response[:200]}")
                    return []
                json_str = match.group()
                try:
                    data = json.loads(json_str)
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse JSON from LLM response: {e}, raw: {json_str[:200]}")
                    return []
            
            # Ensure data is a list
            if isinstance(data, dict):
                data = [data]
            if not isinstance(data, list):
                logger.warning(f"Unexpected JSON type: {type(data)}")
                return []
            
            # Map scene_id → panel_ids
            scene_panel_map = {s['scene_id']: s['panel_ids'] for s in scene_descs}
            result = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                scene_id = item.get('scene_id', '')
                image_ref = item.get('image_ref', '')
                score = item.get('match_score', 0)
                if not scene_id:
                    continue
                for panel_id in scene_panel_map.get(scene_id, []):
                    result.append({
                        'panel_id': panel_id,
                        'scene_id': scene_id,
                        'image_ref': image_ref,
                        'match_score': score,
                    })
            
            if result:
                logger.info(f"Successfully parsed {len(result)} assignments from LLM response")
            return result
            
        except Exception as e:
            logger.warning(f"Failed to parse LLM assignments: {e}")
        return []

    # ────────────────────────────────────────────────────────────────
    # Rule-based fallback matching
    # ────────────────────────────────────────────────────────────────

    def _rule_match_scenes(
        self,
        scene_descs: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Rule-based scene→image matching:
        1. Keyword extraction from scene description + dialogue
        2. Score each image against keywords
        3. Assign best-match image to each scene's panels
        4. Distribute remaining images to remaining panels
        """
        if not self._images:
            return []

        # Build keyword profiles for each image from filename
        image_profiles = []
        for img in self._images:
            fname = (img.get('filename', '') or '').lower()
            # Extract keywords from filename (split on _, -, spaces)
            tokens = set(re.split(r'[_\-\s\.\-]', fname))
            tokens = {t for t in tokens if len(t) >= 2}
            image_profiles.append({
                'image_ref': img.get('path', ''),
                'tokens': tokens,
                'filename': fname,
            })

        assignments = []
        used_images = set()

        for scene in scene_descs:
            scene_id = scene['scene_id']
            text = f"{scene['description']} {scene['dialogue_preview']}".lower()

            # Extract matching tokens
            best_img = None
            best_score = -1

            for profile in image_profiles:
                if profile['image_ref'] in used_images:
                    continue
                score = len(profile['tokens'] & self._extract_keywords(text))
                if score > best_score:
                    best_score = score
                    best_img = profile['image_ref']

            # Fallback: use first unused image
            if best_img is None:
                for profile in image_profiles:
                    if profile['image_ref'] not in used_images:
                        best_img = profile['image_ref']
                        break

            if best_img:
                used_images.add(best_img)

            for panel_id in scene.get('panel_ids', []):
                assignments.append({
                    'panel_id': panel_id,
                    'scene_id': scene_id,
                    'image_ref': best_img or '',
                    'match_score': best_score / max(len(self._extract_keywords(text)), 1),
                })

        logger.info(f"ImageMatcher: rule-based matched {len(assignments)} panels")
        return assignments

    def _extract_keywords(self, text: str) -> set:
        """Extract meaningful keywords from scene text."""
        import re
        # Remove punctuation, split into tokens
        tokens = re.findall(r'\w{2,}', text.lower())
        # Filter stopwords
        stopwords = {'the', 'and', 'for', 'with', 'から', 'は', 'が', 'の', 'に', 'を', 'で', 'て', 'し', 'れ', 'さ', 'い', 'あ', 'こ', 'そ', 'ん'}
        return {t for t in tokens if t not in stopwords and len(t) >= 2}

    # ────────────────────────────────────────────────────────────────
    # Helpers
    # ────────────────────────────────────────────────────────────────

    def _precompute_saliency(self) -> None:
        """Pre-compute salient region for all images (run once, cache results)."""
        for img in self._images:
            pil_img = img.get('pil_image')
            if not pil_img:
                continue
            try:
                region = find_salient_region(pil_img)
                self._saliency_cache[img['path']] = region
                logger.debug(f"Saliency for {img.get('filename')}: {region}")
            except Exception as e:
                logger.warning(f"Saliency detection failed for {img.get('filename')}: {e}")
                self._saliency_cache[img['path']] = (0, 0, pil_img.width, pil_img.height)

    def _get_scene_data(self, scene_id: str) -> Optional[Dict[str, Any]]:
        """Find scene data from script_data by scene_id."""
        for page in self._script_data.get('pages', []):
            for scene in page.get('scenes', []):
                if scene.get('scene_id') == scene_id:
                    return scene
        return None

    def _get_dialogue_preview(self, scene_data: Dict[str, Any]) -> str:
        """Get a short preview of dialogue in a scene."""
        lines = scene_data.get('dialogue_lines', [])
        preview = ' '.join(l.get('text', '')[:30] for l in lines[:2])
        return preview

    def _derive_importance(self, scene_id: str) -> str:
        """
        Derive image importance from scene pacing.
        climax → high, tension → medium, calm/transition → low
        """
        scene_data = self._get_scene_data(scene_id)
        if not scene_data:
            return 'medium'
        pacing = scene_data.get('pacing', 'transition')
        if pacing == 'climax':
            return 'high'
        elif pacing == 'tension':
            return 'medium'
        else:
            return 'low'  # calm, transition

    def _compute_match_score(
        self,
        scene: Dict[str, Any],
        image_analysis: ImageAnalysis,
        image_path: str,
    ) -> MatchResult:
        """
        Compute PRECISE matching score by comparing scene requirements with image analysis.

        This is the core matching logic that must be accurate.
        It compares:
        1. Shot type (from storyboard) vs shot type (from image analysis)
        2. Emotional tone (from storyboard) vs emotional tone (from image analysis)
        3. Scene type compatibility
        4. Object/keyword overlap

        Returns MatchResult with detailed breakdown.
        """
        scene_id = scene.get('scene_id', '')
        scene_shot = scene.get('shot_type', 'unknown')
        scene_tone = scene.get('emotional_tone', 'unknown')
        scene_desc = scene.get('description', '').lower()
        scene_dialogue = scene.get('dialogue_preview', '').lower()

        img_shot = image_analysis.shot_type
        img_tones = image_analysis.emotional_tone
        img_objects = [o.lower() for o in image_analysis.objects]
        img_desc = image_analysis.raw_description.lower()

        # 1. Shot type matching (weight: 40%)
        shot_score = self._score_shot_compatibility(scene_shot, img_shot)

        # 2. Emotional tone matching (weight: 35%)
        tone_score = self._score_tone_compatibility(scene_tone, img_tones, image_analysis.face_expression)

        # 3. Scene type matching (weight: 15%)
        scene_score = self._score_scene_type_compatibility(scene_desc, image_analysis.scene_type)

        # 4. Object/content matching (weight: 10%)
        object_score = self._score_object_match(scene_desc, scene_dialogue, img_objects, img_desc)

        # Weighted overall score (调整权重: tone主导, shot辅助)
        overall = (
            shot_score * 0.20 +   # 降低: shot类型匹配重要性
            tone_score * 0.50 +   # 提高: emotional tone是核心
            scene_score * 0.15 +  # 保持: 场景类型
            object_score * 0.15   # 提高: 物体/内容匹配
        )

        # Build reasoning
        reasoning_parts = []
        if shot_score >= 0.8:
            reasoning_parts.append(f"shot: {scene_shot}→{img_shot} ✓")
        elif shot_score >= 0.5:
            reasoning_parts.append(f"shot: {scene_shot}→{img_shot} ~")
        else:
            reasoning_parts.append(f"shot: {scene_shot}→{img_shot} ✗")
        
        if tone_score >= 0.8:
            reasoning_parts.append(f"tone: {scene_tone} matches {img_tones} ✓")
        elif tone_score >= 0.5:
            reasoning_parts.append(f"tone: {scene_tone} partial {img_tones}")
        else:
            reasoning_parts.append(f"tone: {scene_tone} vs {img_tones} ✗")
        
        reasoning_parts.append(f"overall={overall:.2f}")
        reasoning = ", ".join(reasoning_parts)

        return MatchResult(
            scene_id=scene_id,
            image_ref=image_path,
            overall_score=overall,
            shot_score=shot_score,
            tone_score=tone_score,
            scene_score=scene_score,
            object_score=object_score,
            reasoning=reasoning,
        )

    def _score_shot_compatibility(self, scene_shot: str, img_shot: str) -> float:
        """Score shot type compatibility 0.0-1.0"""
        if scene_shot == 'unknown' or img_shot == 'unknown':
            return 0.5  # Can't judge unknown
        
        # Exact match
        if scene_shot == img_shot:
            return 1.0
        
        # Check compatibility matrix
        compat = SHOT_COMPATIBILITY.get(scene_shot, {})
        return compat.get(img_shot, 0.3)

    def _score_tone_compatibility(self, scene_tone: str, img_tones: List[str], face_expression: str = 'unknown') -> float:
        """Score emotional tone compatibility 0.0-1.0
        
        Also considers face_expression as a secondary tone indicator.
        """
        if scene_tone == 'unknown' or not img_tones:
            return 0.5
        
        # If scene has no specific tone, be lenient
        if scene_tone in ('unknown', 'neutral'):
            return 0.5
        
        # Check if any of the image tones match
        compat = TONE_COMPATIBILITY.get(scene_tone, {})
        best_score = 0.0
        for img_tone in img_tones:
            score = compat.get(img_tone, 0.2)
            if score > best_score:
                best_score = score
        
        # Also consider face_expression as secondary indicator
        if face_expression and face_expression not in ('unknown', 'neutral'):
            expr_score = compat.get(face_expression, 0.2)
            # Take the better of the two
            if expr_score > best_score:
                best_score = expr_score
        
        return best_score

    def _score_scene_type_compatibility(self, scene_desc: str, img_scene_type: str) -> float:
        """Score scene type compatibility 0.0-1.0"""
        if img_scene_type == 'unknown':
            return 0.5
        
        # Check for scene type keywords in description
        # English keywords
        indoor_keywords_en = ['indoor', 'inside', 'room', 'interior', 'coffee shop', 'cafe', 'restaurant', 'office', 'classroom', 'house', 'home', 'apartment', 'bedroom', 'kitchen', 'bathroom', 'living room', 'restaurant', 'bar', 'kitchen']
        outdoor_keywords_en = ['outdoor', 'outside', 'beach', 'ocean', 'sea', 'street', 'park', 'city', 'sky', 'sun', 'sunset', 'sunrise', 'mountain', 'river', 'forest', 'garden', 'outdoor', 'outside', 'road', 'highway']
        # Chinese keywords
        indoor_keywords_zh = ['室内', '部屋', '家', '教室', '会社', '咖啡馆', '餐厅', '辦公室', '厨房', '厨房做饭']
        outdoor_keywords_zh = ['海', '外', '街', '道', '公園', '空', '山', '室外', '沙滩', '河边', '室外']
        
        has_indoor = any(kw in scene_desc for kw in indoor_keywords_en + indoor_keywords_zh)
        has_outdoor = any(kw in scene_desc for kw in outdoor_keywords_en + outdoor_keywords_zh)
        
        # Indoor vs outdoor CONFLICT penalty
        if has_indoor and img_scene_type in ('outdoor', 'landscape', 'wide_shot'):
            return 0.1  # Indoor scene but outdoor image = severe penalty
        if has_outdoor and img_scene_type in ('indoor', 'portrait', 'close_up'):
            return 0.1  # Outdoor scene but indoor image = severe penalty
        
        if has_indoor and img_scene_type in ('indoor', 'portrait'):
            return 1.0
        if has_outdoor and img_scene_type in ('outdoor', 'landscape', 'wide_shot'):
            return 1.0
        
        # Check scene type compatibility matrix
        compat = SCENE_TYPE_COMPATIBILITY.get(img_scene_type, {})
        
        # Simple heuristic based on description
        if has_outdoor:
            return compat.get('outdoor', 0.5)
        elif has_indoor:
            return compat.get('indoor', 0.5)
        
        return 0.5

    def _score_object_match(
        self,
        scene_desc: str,
        scene_dialogue: str,
        img_objects: List[str],
        img_desc: str,
    ) -> float:
        """Score object/content match 0.0-1.0 based on keyword overlap"""
        if not img_objects:
            return 0.3
        
        # Extract meaningful keywords from scene description
        scene_text = f"{scene_desc} {scene_dialogue}".lower()
        
        # Key objects that should appear in image for this scene
        scene_objects = self._extract_scene_objects(scene_text)
        
        if not scene_objects:
            return 0.5  # No specific objects required
        
        # Build img_text from objects + description (both English and Chinese content)
        img_text = " ".join(img_objects).lower() + " " + img_desc.lower()
        
        # Count how many scene objects are found in image
        matches = 0
        for obj in scene_objects:
            if obj in img_text:
                matches += 1
            else:
                # Try translations for common Chinese→English terms
                translation = self._translate_keyword(obj)
                if translation:
                    # Check if ANY word in the translation matches
                    trans_words = translation.split()
                    if any(w in img_text for w in trans_words):
                        matches += 1
        
        return matches / len(scene_objects) if scene_objects else 0.5
    
    def _translate_keyword(self, kw: str) -> Optional[str]:
        """Translate common Chinese keywords to English for matching"""
        translations = {
            # People
            '男': 'boy man person people male',
            '女': 'girl woman person people female',
            '孩子': 'child kid boy girl',
            '子供': 'child kid boy girl',
            '少年': 'boy teen male',
            '少女': 'girl teen female',
            '中年': 'middle-aged adult man woman',
            '老人': 'elderly old man woman',
            '顔': 'face person',
            '目': 'eye eyes',
            '手': 'hand hands',
            # Places
            '海': 'ocean sea beach water waves',
            '河边': 'river bank waterfront',
            '沙滩': 'beach sand',
            '空': 'sky',
            '太陽': 'sun sunny sunlight',
            '月': 'moon',
            '山': 'mountain',
            '川': 'river water',
            '街': 'street city urban',
            '道': 'road street path',
            '教室': 'classroom room school indoor',
            '咖啡馆': 'coffee shop cafe interior indoor',
            'カフェ': 'cafe coffee shop',
            '家': 'house home building',
            '部屋': 'room indoor',
            '厨房': 'kitchen indoor cooking',
            '餐厅': 'restaurant dining indoor',
            '車': 'car vehicle',
            '電車': 'train',
            # Objects
            '排球': 'volleyball ball',
            'ボール': 'ball',
            '篮球': 'basketball ball',
            '足球': 'soccer ball football',
            '咖啡': 'coffee cup mug drink',
            # Emotions
            '笑': 'smile smiling happy laugh',
            '泣': 'cry crying sad tears',
            '怒': 'angry fury rage',
            '惊': 'surprised shock',
        }
        return translations.get(kw)

    def _extract_scene_objects(self, text: str) -> List[str]:
        """Extract key object/character keywords from scene description"""
        # Common manga/comic object keywords
        keywords = [
            # People
            '男', '女', '孩子', '子供', '少年', '少女', '中年', '老人',
            'boy', 'girl', 'man', 'woman', 'child', 'kid', 'adult', 'middle-aged', 'elderly',
            # Face/body
            '顔', '目', '手', 'face', 'eyes', 'hands',
            # Nature/outdoor
            '海', '波', '沙滩', '空', '太陽', '月', '山', '川', '街', '道', '河边', '公園',
            'sea', 'wave', 'beach', 'sky', 'sun', 'moon', 'mountain', 'river', 'street', 'road', 'park',
            # Indoor places
            '教室', '家', '部屋', '咖啡馆', 'カフェ', '厨房', '餐厅', '車', '電車',
            'classroom', 'house', 'room', 'cafe', 'coffee shop', 'kitchen', 'restaurant', 'car', 'train',
            # Objects
            '排球', 'ボール', '篮球', '足球', 'ball', 'volleyball', 'basketball', 'soccer',
            '咖啡', 'cup', 'mug', 'coffee',
            # Emotions
            '笑', '泣', '怒', '惊', 'happy', 'sad', 'angry', 'surprised', 'chatting', 'laughing',
        ]
        
        found = []
        for kw in keywords:
            if kw in text:
                found.append(kw)
        
        return found
