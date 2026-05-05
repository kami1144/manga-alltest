"""
Image Analyzer — LLM-powered image content analysis for manga panel matching.

Responsibilities:
1. Analyze image content (objects, characters, scene type, emotional tone)
2. Extract visual features useful for matching to manga scenes
3. Support batch analysis for efficiency

Usage:
    analyzer = ImageAnalyzer()
    result = analyzer.analyze("path/to/image.jpg")
    # Returns: {objects, scene_type, emotional_tone, characters, composition, quality_score}

    # Batch analyze
    results = analyzer.analyze_batch(["img1.jpg", "img2.png"])
"""

import json
import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# mmx CLI path
MMX_CLI = os.path.expanduser("~/.npm-global/bin/mmx")

# Supported image formats
SUPPORTED_FORMATS = {'.jpg', '.jpeg', '.png', '.webp'}


@dataclass
class ImageAnalysis:
    """Structured result of image analysis."""
    # Visual content
    objects: List[str] = field(default_factory=list)  # ["face", "person", "background"]
    scene_type: str = "unknown"  # indoor, outdoor, close_up, wide_shot, etc.
    composition: str = "unknown"  # centered, rule_of_thirds, diagonal, etc.
    
    # Emotional/content attributes
    emotional_tone: List[str] = field(default_factory=list)  # ["romantic", "intense", "calm"]
    color_mood: str = "unknown"  # warm, cool, dark, bright, muted
    
    # Character info
    character_count: int = 0
    has_face: bool = False
    face_expression: str = "unknown"  # happy, sad, surprised, neutral
    
    # Technical
    shot_type: str = "unknown"  # close_up, medium_shot, wide_shot, two_shot, etc.
    aspect_ratio: str = "unknown"  # portrait, landscape, square
    image_ref: str = ""
    
    # Raw description
    raw_description: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'objects': self.objects,
            'scene_type': self.scene_type,
            'composition': self.composition,
            'emotional_tone': self.emotional_tone,
            'color_mood': self.color_mood,
            'character_count': self.character_count,
            'has_face': self.has_face,
            'face_expression': self.face_expression,
            'shot_type': self.shot_type,
            'aspect_ratio': self.aspect_ratio,
            'image_ref': self.image_ref,
            'raw_description': self.raw_description,
        }


class ImageAnalyzer:
    """
    Analyze images using MiniMax VLM via mmx CLI.
    
    Provides structured content analysis useful for manga panel matching:
    - Object detection
    - Scene classification
    - Emotional tone detection
    - Composition analysis
    - Character/face detection
    """

    def __init__(self):
        self._mmx_available = os.path.isfile(MMX_CLI)
        if not self._mmx_available:
            logger.warning("mmx CLI not found, image analysis will use fallback")

    def is_available(self) -> bool:
        """Check if mmx vision is available."""
        return self._mmx_available

    def analyze(self, image_path: str) -> ImageAnalysis:
        """
        Analyze a single image.
        
        Args:
            image_path: Path to image file
            
        Returns:
            ImageAnalysis with structured results
        """
        if not os.path.exists(image_path):
            logger.error(f"Image not found: {image_path}")
            return ImageAnalysis(image_ref=image_path)
        
        if not self._mmx_available:
            return self._fallback_analysis(image_path)
        
        try:
            return self._mmx_analyze(image_path)
        except Exception as e:
            logger.warning(f"mmx analysis failed ({e}), using fallback")
            return self._fallback_analysis(image_path)

    def analyze_batch(self, image_paths: List[str]) -> List[ImageAnalysis]:
        """
        Analyze multiple images.
        
        Args:
            image_paths: List of image file paths
            
        Returns:
            List of ImageAnalysis results (same order as input)
        """
        results = []
        for path in image_paths:
            result = self.analyze(path)
            results.append(result)
        return results

    def _mmx_analyze(self, image_path: str) -> ImageAnalysis:
        """Use mmx CLI to analyze image content."""
        analysis = ImageAnalysis(image_ref=image_path)
        
        # Build the prompt for manga-relevant analysis
        prompt = """Analyze this image and provide structured information for manga/comic panel matching.

Respond ONLY with valid JSON in this exact format (no extra text):
{
  "objects": ["list of detected objects/elements, max 10 items"],
  "scene_type": "indoor|outdoor|close_up|medium_shot|wide_shot|portrait|landscape|unknown",
  "composition": "centered|rule_of_thirds|diagonal|frame_in_frame|symmetrical|dynamic|unknown",
  "emotional_tone": ["list of emotional qualities: romantic,intense,calm,mysterious,comedic,surprised,sad,tense - max 3 items"],
  "color_mood": "warm|cool|dark|bright|muted|colorful|monochrome|unknown",
  "character_count": 0-10,
  "has_face": true|false,
  "face_expression": "happy|sad|surprised|angry|neutral|determined|mysterious|unknown",
  "shot_type": "close_up|medium_shot|wide_shot|two_shot|over_shoulder|POV|aerial|insert|unknown",
  "aspect_ratio": "portrait|landscape|square",
  "raw_description": "brief description of the image content"
}

Focus on elements relevant for manga/comic panel selection."""

        # Call mmx vision
        cmd = [
            MMX_CLI, "vision", "describe",
            "--image", image_path,
            "--prompt", prompt,
            "--output", "json",
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
        
        if result.returncode != 0:
            logger.error(f"mmx vision failed: {result.stderr}")
            return self._fallback_analysis(image_path)
        
        # Parse JSON response
        try:
            # mmx outputs JSON with base_resp wrapper
            data = json.loads(result.stdout)
            
            # Extract the text content from mmx response
            content = data.get("content", "")
            if isinstance(content, list):
                for c in content:
                    if isinstance(c, dict) and c.get("type") == "text":
                        content = c.get("text", "")
                        break
            
            if isinstance(content, str):
                # Parse the content JSON
                # Find JSON object in the content
                json_start = content.find('{')
                json_end = content.rfind('}') + 1
                if json_start >= 0 and json_end > json_start:
                    parsed = json.loads(content[json_start:json_end])
                    self._apply_parsed_result(analysis, parsed)
            elif isinstance(data, dict):
                # Direct JSON response
                self._apply_parsed_result(analysis, data)
                
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Failed to parse mmx response: {e}, raw: {result.stdout[:200]}")
            # Try to extract description from raw output
            analysis.raw_description = result.stdout[:200]
        
        return analysis

    def _apply_parsed_result(self, analysis: ImageAnalysis, data: Dict[str, Any]) -> None:
        """Apply parsed JSON data to ImageAnalysis object."""
        analysis.objects = data.get("objects", [])
        analysis.scene_type = data.get("scene_type", "unknown")
        analysis.composition = data.get("composition", "unknown")
        analysis.emotional_tone = data.get("emotional_tone", [])
        analysis.color_mood = data.get("color_mood", "unknown")
        analysis.character_count = data.get("character_count", 0)
        analysis.has_face = data.get("has_face", False)
        analysis.face_expression = data.get("face_expression", "unknown")
        analysis.shot_type = data.get("shot_type", "unknown")
        analysis.aspect_ratio = data.get("aspect_ratio", "unknown")
        analysis.raw_description = data.get("raw_description", "")

    def _fallback_analysis(self, image_path: str) -> ImageAnalysis:
        """
        Fallback analysis when mmx is unavailable.
        Uses PIL to extract basic image metadata.
        """
        analysis = ImageAnalysis(image_ref=image_path)
        
        try:
            from PIL import Image
            with Image.open(image_path) as img:
                w, h = img.size
                analysis.aspect_ratio = "portrait" if h > w else "landscape" if w > h else "square"
                
                # Rough shot type estimate from aspect ratio
                if h > w * 1.5:
                    analysis.shot_type = "portrait"
                    analysis.scene_type = "close_up" if h > w * 2 else "medium_shot"
                elif w > h * 1.5:
                    analysis.shot_type = "wide_shot"
                    analysis.scene_type = "wide_shot"
                else:
                    analysis.shot_type = "medium_shot"
                    analysis.scene_type = "medium_shot"
                
                # Basic color analysis
                if img.mode == "RGB":
                    # Sample colors to estimate mood
                    import statistics
                    try:
                        img_small = img.resize((50, 50))
                        pixels = list(img_small.getdata())
                        avg_r = statistics.mean(p[0] for p in pixels)
                        avg_g = statistics.mean(p[1] for p in pixels)
                        avg_b = statistics.mean(p[2] for p in pixels)
                        
                        if avg_r > avg_b + 20:
                            analysis.color_mood = "warm"
                        elif avg_b > avg_r + 20:
                            analysis.color_mood = "cool"
                        elif avg_r + avg_g + avg_b < 150:
                            analysis.color_mood = "dark"
                        elif avg_r + avg_g + avg_b > 600:
                            analysis.color_mood = "bright"
                        else:
                            analysis.color_mood = "muted"
                    except:
                        analysis.color_mood = "unknown"
                
                analysis.raw_description = f"Image {w}x{h} {img.mode}"
                
        except Exception as e:
            logger.warning(f"Fallback analysis failed: {e}")
        
        return analysis


# --- Convenience function ---

def analyze_image(image_path: str) -> Dict[str, Any]:
    """
    Quick function to analyze a single image.
    
    Returns dict (for backward compatibility).
    """
    analyzer = ImageAnalyzer()
    result = analyzer.analyze(image_path)
    return result.to_dict()
