"""
漫画阅读节奏分析器单元测试
"""
import json
import pytest
from pathlib import Path

# 导入待测试模块
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.narrative_pacing import (
    NarrativePacingAnalyzer,
    analyze_page,
    analyze_segment,
    PacingType,
)


class TestNarrativePacingAnalyzer:
    """NarrativePacingAnalyzer 测试类"""

    def test_init(self):
        """测试初始化"""
        analyzer = NarrativePacingAnalyzer(vision_provider="mmx")
        assert analyzer.vision_provider == "mmx"
        assert analyzer._previous_rhythm is None

    def test_init_without_vision(self):
        """测试禁用视觉分析"""
        analyzer = NarrativePacingAnalyzer(vision_provider="none")
        assert analyzer.vision_provider == "none"

    def test_reset_history(self):
        """测试重置节奏记忆"""
        analyzer = NarrativePacingAnalyzer()
        analyzer._previous_rhythm = "climax"

        analyzer.reset_history()

        assert analyzer._previous_rhythm is None

    def test_set_previous_rhythm(self):
        """测试手动设置上一页节奏"""
        analyzer = NarrativePacingAnalyzer()
        analyzer.set_previous_rhythm("tension")
        assert analyzer._previous_rhythm == "tension"


class TestAnalyzePage:
    """analyze_page 测试类"""

    @pytest.fixture
    def sample_panel_layout(self):
        """标准分镜布局数据"""
        return {
            "page_index": 0,
            "panels": [
                {
                    "panel_id": "p1",
                    "bounds": {"x": 0, "y": 0, "w": 300, "h": 200},
                    "gaps": {"left": 5, "right": 5, "top": 3, "bottom": 3},
                    "border_style": "solid",
                    "splash": False,
                },
                {
                    "panel_id": "p2",
                    "bounds": {"x": 310, "y": 0, "w": 300, "h": 200},
                    "gaps": {"left": 15, "right": 5, "top": 3, "bottom": 3},
                    "border_style": "solid",
                    "splash": False,
                },
            ],
            "page_size": {"w": 800, "h": 1200},
        }

    def test_basic_analysis(self, sample_panel_layout):
        """基础分镜分析测试"""
        analyzer = NarrativePacingAnalyzer(vision_provider="none")
        result = analyzer.analyze_page("", sample_panel_layout)

        # 验证返回结构
        assert "page_index" in result
        assert "overall_rhythm" in result
        assert "panel_pacings" in result

        # 验证 page_index
        assert result["page_index"] == 0

        # 验证整体节奏有效值
        assert result["overall_rhythm"] in (
            PacingType["CLIMAX"],
            PacingType["TENSION"],
            PacingType["TRANSITION"],
            PacingType["CALM"],
        )

    def test_splash_detection(self):
        """测试出血格识别"""
        analyzer = NarrativePacingAnalyzer(vision_provider="none")

        panel_layout = {
            "page_index": 0,
            "panels": [
                {
                    "panel_id": "p1",
                    "bounds": {"x": 0, "y": 0, "w": 610, "h": 800},
                    "gaps": {"left": 5, "right": 5, "top": 5, "bottom": 5},
                    "border_style": "solid",
                    "splash": True,
                },
            ],
            "page_size": {"w": 800, "h": 1200},
        }

        result = analyzer.analyze_page("", panel_layout)

        # 出血格应该识别为 climax
        assert result["panel_pacings"][0]["pacing"] == "climax"
        assert "出血格" in result["panel_pacings"][0]["visual_indicators"]

    def test_large_gap_detection(self):
        """测试大间距识别"""
        analyzer = NarrativePacingAnalyzer(vision_provider="none")

        panel_layout = {
            "page_index": 0,
            "panels": [
                {
                    "panel_id": "p1",
                    "bounds": {"x": 0, "y": 0, "w": 200, "h": 300},
                    "gaps": {"left": 50, "right": 50, "top": 5, "bottom": 5},
                    "border_style": "solid",
                    "splash": False,
                },
            ],
            "page_size": {"w": 800, "h": 1200},
        }

        # 提取几何特征
        features = analyzer._geometric_features(panel_layout)

        # 大间距检测
        assert features[0]["is_large_gap"] is True
        assert features[0]["max_gap"] == 50

    def test_slant_border_detection(self):
        """测试斜线分割识别"""
        analyzer = NarrativePacingAnalyzer(vision_provider="none")

        panel_layout = {
            "page_index": 0,
            "panels": [
                {
                    "panel_id": "p1",
                    "bounds": {"x": 0, "y": 0, "w": 300, "h": 400},
                    "gaps": {"left": 5, "right": 5, "top": 5, "bottom": 5},
                    "border_style": "slant",
                    "splash": False,
                },
            ],
            "page_size": {"w": 800, "h": 1200},
        }

        result = analyzer.analyze_page("", panel_layout)

        # 斜线边框 → tension
        assert result["panel_pacings"][0]["pacing"] == "tension"
        assert "斜线分割" in result["panel_pacings"][0]["visual_indicators"]

    def test_small_gap_detection(self):
        """测试小间距识别"""
        analyzer = NarrativePacingAnalyzer(vision_provider="none")

        panel_layout = {
            "page_index": 0,
            "panels": [
                {
                    "panel_id": "p1",
                    "bounds": {"x": 0, "y": 0, "w": 200, "h": 300},
                    "gaps": {"left": 3, "right": 3, "top": 3, "bottom": 3},
                    "border_style": "solid",
                    "splash": False,
                },
            ],
            "page_size": {"w": 800, "h": 1200},
        }

        # 提取几何特征
        features = analyzer._geometric_features(panel_layout)

        # 小间距检测
        assert features[0]["is_small_gap"] is True

    def test_empty_panels(self):
        """测试空分镜列表"""
        analyzer = NarrativePacingAnalyzer(vision_provider="none")

        panel_layout = {
            "page_index": 0,
            "panels": [],
            "page_size": {"w": 800, "h": 1200},
        }

        result = analyzer.analyze_page("", panel_layout)

        # 空分镜应返回过渡节奏
        assert result["overall_rhythm"] == "transition"
        assert result["panel_pacings"] == []


class TestRhythmContinuity:
    """节奏连贯性测试"""

    def test_calm_to_climax_transition(self):
        """测试从平静到高潮的过渡"""
        analyzer = NarrativePacingAnalyzer(vision_provider="none")

        # 上一页是平静
        analyzer.set_previous_rhythm(PacingType["CALM"])

        # 当前页分析出血格
        panel_layout = {
            "page_index": 1,
            "panels": [
                {
                    "panel_id": "p1",
                    "bounds": {"x": 0, "y": 0, "w": 610, "h": 800},
                    "gaps": {"left": 5, "right": 5, "top": 5, "bottom": 5},
                    "border_style": "solid",
                    "splash": True,
                },
            ],
            "page_size": {"w": 800, "h": 1200},
        }

        result = analyzer.analyze_page("", panel_layout)

        # 从平静直接到高潮，应该有缓冲
        assert result["overall_rhythm"] != PacingType["CLIMAX"]

    def test_climax_to_calm_transition(self):
        """测试从高潮到平静的过渡"""
        analyzer = NarrativePacingAnalyzer(vision_provider="none")

        # 上一页是高潮
        analyzer.set_previous_rhythm(PacingType["CLIMAX"])

        # 当前页是规则小格
        panel_layout = {
            "page_index": 1,
            "panels": [
                {
                    "panel_id": "p1",
                    "bounds": {"x": 0, "y": 0, "w": 200, "h": 200},
                    "gaps": {"left": 5, "right": 5, "top": 5, "bottom": 5},
                    "border_style": "solid",
                    "splash": False,
                },
                {
                    "panel_id": "p2",
                    "bounds": {"x": 210, "y": 0, "w": 200, "h": 200},
                    "gaps": {"left": 5, "right": 5, "top": 5, "bottom": 5},
                    "border_style": "solid",
                    "splash": False,
                },
            ],
            "page_size": {"w": 800, "h": 1200},
        }

        result = analyzer.analyze_page("", panel_layout)

        # 从高潮到平静需要过渡
        assert result["overall_rhythm"] == PacingType["TRANSITION"]


class TestAnalyzeSegment:
    """analyze_segment 测试类"""

    def test_basic_segment_analysis(self):
        """基础段落分析"""
        analyzer = NarrativePacingAnalyzer(vision_provider="none")

        pages = [
            {
                "manga_page_image": "",
                "panel_layout": {
                    "page_index": 0,
                    "panels": [
                        {
                            "panel_id": "p1",
                            "bounds": {"x": 0, "y": 0, "w": 200, "h": 300},
                            "gaps": {"left": 5, "right": 5, "top": 5, "bottom": 5},
                            "border_style": "solid",
                            "splash": False,
                        },
                    ],
                },
            },
            {
                "manga_page_image": "",
                "panel_layout": {
                    "page_index": 1,
                    "panels": [
                        {
                            "panel_id": "p1",
                            "bounds": {"x": 0, "y": 0, "w": 610, "h": 800},
                            "gaps": {"left": 5, "right": 5, "top": 5, "bottom": 5},
                            "border_style": "solid",
                            "splash": True,
                        },
                    ],
                },
            },
        ]

        result = analyzer.analyze_segment(pages)

        # 验证返回结构
        assert "segment_summary" in result
        assert "reading_tension_curve" in result
        assert "page_results" in result

        # 验证节奏曲线
        assert len(result["reading_tension_curve"]) == 2

    def test_tension_curve_values(self):
        """测试节奏曲线数值"""
        analyzer = NarrativePacingAnalyzer(vision_provider="none")

        pages = [
            {
                "manga_page_image": "",
                "panel_layout": {
                    "page_index": 0,
                    "panels": [
                        {
                            "panel_id": "p1",
                            "bounds": {"x": 0, "y": 0, "w": 200, "h": 200},
                            "gaps": {"left": 5, "right": 5, "top": 5, "bottom": 5},
                            "border_style": "solid",
                            "splash": False,
                        },
                    ],
                },
            },
        ]

        result = analyzer.analyze_segment(pages)

        # 验证数值范围
        for v in result["reading_tension_curve"]:
            assert 0 <= v <= 1


class TestGeometricFeatures:
    """几何特征提取测试"""

    def test_extract_splash_features(self):
        """测试出血特征"""
        analyzer = NarrativePacingAnalyzer(vision_provider="none")

        panel_layout = {
            "page_index": 0,
            "panels": [
                {
                    "panel_id": "p1",
                    "bounds": {"x": 0, "y": 0, "w": 610, "h": 800},
                    "gaps": {"left": 5, "right": 5, "top": 5, "bottom": 5},
                    "border_style": "solid",
                    "splash": True,
                },
            ],
        }

        features = analyzer._geometric_features(panel_layout)

        assert features[0]["is_splash"] is True
        assert features[0]["breakout_level"] >= 1

    def test_extract_large_gap_features(self):
        """测试大间距特征"""
        analyzer = NarrativePacingAnalyzer(vision_provider="none")

        panel_layout = {
            "page_index": 0,
            "panels": [
                {
                    "panel_id": "p1",
                    "bounds": {"x": 0, "y": 0, "w": 200, "h": 300},
                    "gaps": {"left": 30, "right": 5, "top": 5, "bottom": 5},
                    "border_style": "solid",
                    "splash": False,
                },
            ],
        }

        features = analyzer._geometric_features(panel_layout)

        assert features[0]["is_large_gap"] is True
        assert features[0]["max_gap"] == 30

    def test_extract_border_style(self):
        """测试边框样式提取"""
        analyzer = NarrativePacingAnalyzer(vision_provider="none")

        panel_layout = {
            "page_index": 0,
            "panels": [
                {
                    "panel_id": "p1",
                    "bounds": {"x": 0, "y": 0, "w": 300, "h": 400},
                    "gaps": {"left": 5, "right": 5, "top": 5, "bottom": 5},
                    "border_style": "slant",
                    "splash": False,
                },
            ],
        }

        features = analyzer._geometric_features(panel_layout)

        assert features[0]["is_slant"] is True
        assert features[0]["border_style"] == "slant"


class TestConvenienceFunctions:
    """便捷函数测试"""

    def test_analyze_page_function(self):
        """测试 analyze_page 便捷函数"""
        panel_layout = {
            "page_index": 0,
            "panels": [
                {
                    "panel_id": "p1",
                    "bounds": {"x": 0, "y": 0, "w": 300, "h": 400},
                    "gaps": {"left": 5, "right": 5, "top": 5, "bottom": 5},
                    "border_style": "solid",
                    "splash": False,
                },
            ],
            "page_size": {"w": 800, "h": 1200},
        }

        result = analyze_page("", panel_layout, vision_provider="none")

        assert "page_index" in result
        assert "overall_rhythm" in result

    def test_analyze_segment_function(self):
        """测试 analyze_segment 便捷函数"""
        pages = [
            {
                "manga_page_image": "",
                "panel_layout": {
                    "page_index": 0,
                    "panels": [
                        {
                            "panel_id": "p1",
                            "bounds": {"x": 0, "y": 0, "w": 300, "h": 400},
                            "gaps": {"left": 5, "right": 5, "top": 5, "bottom": 5},
                            "border_style": "solid",
                            "splash": False,
                        },
                    ],
                },
            },
        ]

        result = analyze_segment(pages, vision_provider="none")

        assert "segment_summary" in result
        assert "reading_tension_curve" in result


if __name__ == '__main__':
    pytest.main([__file__, '-v'])