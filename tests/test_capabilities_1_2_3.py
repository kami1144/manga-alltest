#!/usr/bin/env python3
"""
Integration test for Capabilities 1, 2, 3.

Tests the complete manga layout pipeline:
1. Script → Storyboard (Capability 1)
2. Image Content Analysis (Capability 2)
3. Storyboard ↔ Image Matching (Capability 3)
"""

import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.storyboard_generator import generate_storyboard
from core.image_analyzer import ImageAnalyzer, analyze_image
from core.image_matcher import ImageMatcher
from core.image_processor import load_image
from utils.llm_client import LLMClient, LLMProvider

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_capability_1():
    """Test: Script → Storyboard"""
    print("\n" + "=" * 60)
    print("CAPABILITY 1: Script → Storyboard")
    print("=" * 60)
    
    script = '''场景1
大周学府，白天
众人：那个人......不是陈长安吗？
众人：一年前失踪，后来命魂灯熄灭，所有人都以为他死了！

场景2
陈长安走入，面容冷峻，脚步不紧不慢
陈长安：一年......还是......一百年？
（他的目光带着沧桑之感，毫无青涩）

场景3
顾倾城出现，身材高挑，婀娜多姿
顾倾城：大周国第一美女，精致且勾魂夺魄
（她一颦一动间，勾人心神）
'''
    
    result = generate_storyboard(script)
    scenes = result.get('scenes', [])
    
    print(f"Generated {len(scenes)} scenes:")
    for s in scenes:
        print(f"  {s['scene_id']}: {s['shot_type']}, {s['emotional_tone']}, {s['pacing']}")
    
    assert len(scenes) == 3, "Should generate 3 scenes"
    print("✅ Capability 1: PASS")
    return result


def test_capability_2():
    """Test: Image Content Analysis"""
    print("\n" + "=" * 60)
    print("CAPABILITY 2: Image Content Analysis")
    print("=" * 60)
    
    # Use available screenshot
    img_path = "/Users/jinyonghao/Desktop/截屏2026-05-04 22.33.51.png"
    
    if not os.path.exists(img_path):
        print(f"⚠️  Test image not found: {img_path}")
        print("✅ Capability 2: SKIP (no test image)")
        return None
    
    analyzer = ImageAnalyzer()
    result = analyzer.analyze(img_path)
    
    print(f"mmx available: {analyzer.is_available()}")
    print(f"Objects: {result.objects[:5]}")
    print(f"Scene type: {result.scene_type}")
    print(f"Emotional tone: {result.emotional_tone}")
    print(f"Shot type: {result.shot_type}")
    print(f"Character count: {result.character_count}")
    print(f"Has face: {result.has_face}")
    
    assert analyzer.is_available(), "mmx should be available"
    print("✅ Capability 2: PASS")
    return result


def test_capability_3():
    """Test: Storyboard ↔ Image Matching"""
    print("\n" + "=" * 60)
    print("CAPABILITY 3: Storyboard ↔ Image Matching")
    print("=" * 60)
    
    # Use available screenshot
    img_path = "/Users/jinyonghao/Desktop/截屏2026-05-04 22.33.51.png"
    
    if not os.path.exists(img_path):
        print(f"⚠️  Test image not found: {img_path}")
        print("✅ Capability 3: SKIP (no test image)")
        return None
    
    # Step 1: Generate storyboard
    script = '''场景1
大周学府，白天
众人：那个人......不是陈长安吗？
众人：一年前失踪，后来命魂灯熄灭，所有人都以为他死了！

场景2
陈长安走入，面容冷峻
陈长安：一年......还是......一百年？

场景3
顾倾城出现，大周国第一美女
'''
    
    storyboard = generate_storyboard(script)
    scenes = storyboard.get('scenes', [])
    
    # Step 2: Load images
    img_data = load_image(img_path)
    images = [img_data]
    
    # Step 3: Setup mock layout data (maps scenes to panels)
    layout_data = {
        'pages': [{
            'panels': [
                {'id': 'p1', 'scene': {'scene_id': 's1'}},
                {'id': 'p2', 'scene': {'scene_id': 's2'}},
                {'id': 'p3', 'scene': {'scene_id': 's3'}},
            ]
        }]
    }
    
    # Setup mock script_data
    script_data = {'pages': [{'scenes': scenes}]}
    
    # Step 4: Create LLM client
    llm_client = LLMClient(provider=LLMProvider.MINIMAX_CLI)
    print(f"LLM available: {llm_client.is_available()}")
    
    # Step 5: Run matcher
    matcher = ImageMatcher(
        images=images,
        script_data=script_data,
        layout_data=layout_data,
        llm_client=llm_client,
    )
    
    assignments = matcher.match()
    
    print(f"\nMatched {len(assignments)} panels:")
    for a in assignments:
        print(f"  Panel {a['panel_id']} → Scene {a['scene_id']}: {a.get('image_ref', '')[:50]}... (score: {a.get('match_score', 0):.2f})")
    
    assert len(assignments) == 3, "Should have 3 panel assignments"
    print("✅ Capability 3: PASS")
    return assignments


def main():
    print("=" * 60)
    print("MANGASTUDIO CAPABILITIES 1-2-3 INTEGRATION TEST")
    print("=" * 60)
    
    results = {}
    
    # Test Capability 1
    try:
        results['capability_1'] = test_capability_1()
    except Exception as e:
        print(f"❌ Capability 1 FAILED: {e}")
        results['capability_1'] = None
    
    # Test Capability 2
    try:
        results['capability_2'] = test_capability_2()
    except Exception as e:
        print(f"❌ Capability 2 FAILED: {e}")
        results['capability_2'] = None
    
    # Test Capability 3
    try:
        results['capability_3'] = test_capability_3()
    except Exception as e:
        print(f"❌ Capability 3 FAILED: {e}")
        results['capability_3'] = None
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for cap, result in results.items():
        status = "✅ PASS" if result is not None else "❌ FAIL"
        print(f"{cap}: {status}")
    
    all_pass = all(v is not None for v in results.values())
    print("\n" + ("🎉 ALL CAPABILITIES PASS!" if all_pass else "⚠️  SOME CAPABILITIES FAILED"))
    
    return 0 if all_pass else 1


if __name__ == '__main__':
    sys.exit(main())
