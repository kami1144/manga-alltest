#!/usr/bin/env python3
"""
Test script for ImageAnalyzer module.

Tests the image content analysis capability (Capability 2).
"""

import json
import logging
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.image_analyzer import ImageAnalyzer, analyze_image

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_image_analyzer():
    """Test ImageAnalyzer with available images."""
    analyzer = ImageAnalyzer()
    
    print("=" * 60)
    print("Testing ImageAnalyzer module (Capability 2)")
    print("=" * 60)
    
    # Check availability
    print(f"\nmmx available: {analyzer.is_available()}")
    
    # Test with screenshot
    screenshot_path = "/Users/jinyonghao/Desktop/截屏2026-05-04 22.33.51.png"
    if os.path.exists(screenshot_path):
        print(f"\n--- Test: Screenshot analysis ---")
        result = analyzer.analyze(screenshot_path)
        print(f"Objects: {result.objects[:5]}...")  # First 5
        print(f"Scene type: {result.scene_type}")
        print(f"Composition: {result.composition}")
        print(f"Emotional tone: {result.emotional_tone}")
        print(f"Color mood: {result.color_mood}")
        print(f"Character count: {result.character_count}")
        print(f"Has face: {result.has_face}")
        print(f"Shot type: {result.shot_type}")
        print(f"Aspect ratio: {result.aspect_ratio}")
        print(f"Raw description: {result.raw_description[:100]}...")
        
        # Validate expected fields
        assert result.objects, "Should detect objects"
        assert result.scene_type != "", "Should have scene_type"
        assert result.composition != "", "Should have composition"
        assert result.emotional_tone, "Should detect emotional tone"
        assert result.shot_type != "", "Should have shot_type"
        print("\n✅ All field validations passed!")
    else:
        print(f"\n⚠️  Test image not found: {screenshot_path}")
    
    # Test convenience function
    print(f"\n--- Test: analyze_image() convenience function ---")
    if os.path.exists(screenshot_path):
        result_dict = analyze_image(screenshot_path)
        print(f"Result type: {type(result_dict)}")
        print(f"Keys: {list(result_dict.keys())}")
        assert isinstance(result_dict, dict), "Should return dict"
        print("✅ Convenience function works!")
    
    print("\n" + "=" * 60)
    print("ImageAnalyzer tests completed!")
    print("=" * 60)


if __name__ == '__main__':
    test_image_analyzer()
