"""
漫画阅读节奏分析模块
- 基于视觉分析和几何特征计算分镜叙事节奏标签
- 支持 mmx CLI (MiniMax vision) 视觉分析，fallback 到规则引擎
- 记忆上一页节奏实现全局连贯性
"""
import json
import logging
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

# 节奏类型
PacingType = {
    "CLIMAX": "climax",      # 高潮
    "TENSION": "tension",   # 紧张
    "TRANSITION": "transition",  # 过渡
    "CALM": "calm",         # 平静
}


class NarrativePacingAnalyzer:
    """漫画阅读节奏分析器"""

    def __init__(self, vision_provider: str = "mmx"):
        """
        初始化分析器

        Args:
            vision_provider: 视觉分析提供商 ("mmx" 或 "none")
        """
        self.vision_provider = vision_provider
        self._previous_rhythm: Optional[str] = None  # 上一页节奏记忆

    def reset_history(self):
        """重置节奏记忆（用于新章节）"""
        self._previous_rhythm = None

    def set_previous_rhythm(self, rhythm: str):
        """手动设置上一页节奏（用于跨页连续分析）"""
        self._previous_rhythm = rhythm

    # ─────────────────────────────────────────────
    # 主入口：分析单页漫画
    # ─────────────────────────────────────────────

    def analyze_page(
        self,
        manga_page_image: str,
        panel_layout: Dict,
        prev_rhythm: Optional[str] = None,
    ) -> Dict:
        """
        分析单页漫画的阅读节奏

        Args:
            manga_page_image: 漫画页面图片路径
            panel_layout: 分镜布局数据，格式如下：
                {
                    "page_index": int,
                    "panels": [
                        {
                            "panel_id": str,
                            "bounds": {"x": int, "y": int, "w": int, "h": int},
                            "gaps": {"left": float, "right": float, "top": float, "bottom": float},
                            "border_style": str,  # "solid", "slant", "wave"
                            "splash": bool,
                            "overlay": bool,
                        },
                        ...
                    ],
                    "page_size": {"w": int, "h": int}
                }
            prev_rhythm: 上一页节奏（用于连贯性判断）

        Returns:
            {
                "page_index": int,
                "overall_rhythm": "climax"|"tension"|"transition"|"calm",
                "panel_pacings": [
                    {
                        "panel_id": str,
                        "pacing": "climax"|"tension"|"transition"|"calm",
                        "reason": str,
                        "visual_indicators": [str],
                        "emotion": "intense"|"neutral"|"climactic"|"calm"
                    },
                    ...
                ]
            }
        """
        page_index = panel_layout.get("page_index", 0)
        panels = panel_layout.get("panels", [])

        if prev_rhythm:
            self._previous_rhythm = prev_rhythm

        if not panels:
            logger.warning(f"Page {page_index} has no panels, returning empty result")
            return {
                "page_index": page_index,
                "overall_rhythm": "transition",
                "panel_pacings": [],
            }

        # 1. 几何特征提取
        geo_features = self._geometric_features(panel_layout)

        # 2. 视觉分析（优先 mmx CLI，fallback 到空描述）
        vision_result = self._call_vision(manga_page_image)

        # 3. 计算每格节奏标签
        panel_pacings = self._classify_pacing(
            vision_result, geo_features, self._previous_rhythm
        )

        # 4. 计算整体节奏
        overall_rhythm = self._compute_overall_rhythm(
            panel_pacings, geo_features, self._previous_rhythm
        )

        # 5. 更新节奏记忆
        self._previous_rhythm = overall_rhythm

        result = {
            "page_index": page_index,
            "overall_rhythm": overall_rhythm,
            "panel_pacings": panel_pacings,
        }

        logger.info(f"Page {page_index} analysis: rhythm={overall_rhythm}, {len(panels)} panels")

        return result

    # ─────────────────────────────────────────────
    # 分析段落（多页）
    # ─────────────────────────────────────────────

    def analyze_segment(
        self,
        pages: List[Dict],
    ) -> Dict:
        """
        分析多个连续页的节奏曲线

        Args:
            pages: 每页数据，格式：
                [
                    {"manga_page_image": str, "panel_layout": Dict},
                    ...
                ]

        Returns:
            {
                "segment_summary": str,
                "reading_tension_curve": [float],
                "page_results": [...]
            }
        """
        if not pages:
            return {
                "segment_summary": "无页面数据",
                "reading_tension_curve": [],
                "page_results": [],
            }

        results = []
        tension_curve = []

        prev_rhythm = None

        for i, page_data in enumerate(pages):
            image_path = page_data.get("manga_page_image", "")
            panel_layout = page_data.get("panel_layout", {})

            # 分析当前页
            page_result = self.analyze_page(image_path, panel_layout, prev_rhythm)
            results.append(page_result)

            # 记录节奏值
            rhythm_value = self._rhythm_to_value(page_result.get("overall_rhythm", "transition"))
            tension_curve.append(rhythm_value)

            # 更新前一页节奏
            prev_rhythm = page_result.get("overall_rhythm")

        # 生成段落摘要
        segment_summary = self._generate_segment_summary(results)

        return {
            "segment_summary": segment_summary,
            "reading_tension_curve": tension_curve,
            "page_results": results,
        }

    def _rhythm_to_value(self, rhythm: str) -> float:
        """将节奏标签转换为数值 (0-1)"""
        mapping = {
            "calm": 0.25,
            "transition": 0.5,
            "tension": 0.75,
            "climax": 1.0,
        }
        return mapping.get(rhythm, 0.5)

    def _generate_segment_summary(self, results: List[Dict]) -> str:
        """生成段落摘要"""
        if not results:
            return "无数据"

        # 简化：用起始页和结束页的节奏描述
        first = results[0].get("overall_rhythm", "transition")
        last = results[-1].get("overall_rhythm", "transition")

        start_label = {
            "calm": "平静段",
            "transition": "过渡段",
            "tension": "紧张段",
            "climax": "高潮段",
        }.get(first, "过渡段")

        end_label = {
            "calm": "平静",
            "transition": "过渡",
            "tension": "紧张",
            "climax": "高潮",
        }.get(last, "过渡")

        page_count = len(results)
        if page_count <= 3:
            return f"第1-{page_count}页为{start_label}"
        else:
            return f"第1页为{start_label}，第{page_count}页为{end_label}"

    # ─────────────────────────────────────────────
    # 视觉分析层
    # ─────────────────────────────────────────────

    def _call_vision(self, image_path: str) -> Dict:
        """
        调用 mmx CLI 进行视觉分析

        Args:
            image_path: 图片路径

        Returns:
            视觉分析结果，包含 content_type, emotion 等
            失败时返回空 dict（不报错）
        """
        if not image_path:
            logger.info("No image path provided, using empty vision result")
            return {}

        # 检查文件是否存在
        if not Path(image_path).exists():
            logger.warning(f"Image file not found: {image_path}, using empty vision result")
            return {}

        if self.vision_provider != "mmx":
            logger.info(f"Vision provider '{self.vision_provider}' not supported, using empty result")
            return {}

        try:
            # 构建 mmx 命令
            cmd = [
                "mmx", "vision",
                "--image", str(image_path),
                "--prompt", "Describe this manga panel: content type (dialog/action/establishing/closeup), emotion (intense/neutral/climactic/calm)"
            ]

            logger.info(f"Calling mmx CLI: {' '.join(cmd)}")

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0 and result.stdout and result.stdout.strip():
                # 尝试解析输出
                try:
                    data = json.loads(result.stdout)
                    return data if isinstance(data, dict) else {}
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse mmx output: {result.stdout[:200]}")
                    return {}
            else:
                # returncode != 0 或 stdout 为空均视为失败
                logger.warning(f"mmx CLI failed (code={result.returncode}): {result.stderr or 'no output'}")
                return {}

        except FileNotFoundError:
            logger.warning("mmx CLI not found, using empty vision result")
            return {}
        except Exception as e:
            logger.warning(f"mmx CLI error: {e}, using empty vision result")
            return {}

    # ─────────────────────────────────────────────
    # 几何特征提取
    # ─────────────────────────────────────────────

    def _geometric_features(self, panel_layout: Dict) -> List[Dict]:
        """
        从 panel_layout 提取几何特征

        ��别：
        - 出血格 (splash=True)
        - 斜线分割 (border_style="slant")
        - 大间距 (>10px)
        - 小间距 (<=5px)

        Args:
            panel_layout: 分镜布局

        Returns:
            每格的几何特征列表
        """
        features = []
        panels = panel_layout.get("panels", [])

        for panel in panels:
            panel_id = panel.get("panel_id", "")
            gaps = panel.get("gaps", {})
            splash = panel.get("splash", False)
            border_style = panel.get("border_style", "solid")
            bounds = panel.get("bounds", {})

            # 计算间距
            left_gap = gaps.get("left", 0)
            right_gap = gaps.get("right", 0)
            top_gap = gaps.get("top", 0)
            bottom_gap = gaps.get("bottom", 0)

            # gaps 可能为 None 或空（防御性检查）
            all_gaps = [g for g in [left_gap, right_gap, top_gap, bottom_gap] if g is not None]
            max_gap = max(all_gaps) if all_gaps else 0

            # 判断大间距/小间距
            is_large_gap = max_gap > 10
            is_small_gap = max_gap <= 5

            # 判断出血格
            is_splash = bool(splash)

            # 判断斜线分割
            is_slant = border_style == "slant"

            # 计算破格级别 (0-3)
            breakout_level = 0
            if splash:
                breakout_level = 1
            w = bounds.get("w", 0)
            h = bounds.get("h", 0)
            if w > 600 or h > 600:
                breakout_level = max(breakout_level, 2)
            if splash and (w > 600 or h > 600):
                breakout_level = 3

            features.append({
                "panel_id": panel_id,
                "is_splash": is_splash,
                "is_slant": is_slant,
                "is_large_gap": is_large_gap,
                "is_small_gap": is_small_gap,
                "max_gap": max_gap,
                "breakout_level": breakout_level,
                "border_style": border_style,
            })

        return features

    # ─────────────────────────────────────────────
    # 节奏分类
    # ─────────────────────────────────────────────

    def _classify_pacing(
        self,
        vision_result: Dict,
        geo_features: List[Dict],
        prev_rhythm: Optional[str],
    ) -> List[Dict]:
        """
        综合判断每格的节奏分类

        Args:
            vision_result: 视觉分析结果
            geo_features: 几何特征列表
            prev_rhythm: 上一页节奏

        Returns:
            每格的节奏标签列表
        """
        results = []

        for geo in geo_features:
            panel_id = geo.get("panel_id", "")
            indicators = []
            reason_parts = []
            emotion = "neutral"
            pacing = PacingType["TRANSITION"]

            # 1. 基于几何特征判断
            if geo.get("is_splash"):
                indicators.append("出血格")
                pacing = PacingType["CLIMAX"]
                emotion = "climactic"
                reason_parts.append("出血格表示高潮或重要场景")
            elif geo.get("is_slant"):
                indicators.append("斜线分割")
                pacing = PacingType["TENSION"]
                emotion = "intense"
                reason_parts.append("斜线分割增加动感")
            elif geo.get("is_large_gap"):
                indicators.append("大间距")
                pacing = PacingType["TENSION"]
                emotion = "intense"
                reason_parts.append("大间距增加张力")
            elif geo.get("is_small_gap"):
                indicators.append("小间距")
                pacing = PacingType["CALM"]
                emotion = "calm"
                reason_parts.append("小间距，阅读节奏平稳")
            else:
                indicators.append("规则网格")
                # 默认是中性格式
                pacing = PacingType["TRANSITION"]
                emotion = "neutral"
                reason_parts.append("规则网格，标准漫画格")

            # 2. 考虑上一页节奏（连贯性）
            if prev_rhythm:
                if prev_rhythm == PacingType["CLIMAX"] and pacing == PacingType["CALM"]:
                    # 高潮后转平静需要过渡
                    pacing = PacingType["TRANSITION"]
                    reason_parts.append("承上页高潮，需要过渡")

            results.append({
                "panel_id": panel_id,
                "pacing": pacing,
                "reason": " ".join(reason_parts),
                "visual_indicators": indicators,
                "emotion": emotion,
            })

        # 3. 视觉结果仅影响整体节奏（在所有格循环之后）
        # vision_result 是 page-level 分析，不应覆盖每格的几何特征标签
        if vision_result:
            vis_emotion = vision_result.get("emotion", "")
            vis_content = vision_result.get("content_type", "")
            logger.info(f"Vision result (page-level): emotion={vis_emotion}, content={vis_content}")
            # 将 page-level 视觉信息记录到 logger，不修改已确定的 per-panel 结果
            # 如需 per-panel 视觉分析，应传入 per-panel image crop paths

        return results

    # ─────────────────────────────────────────────
    # 整体节奏计算
    # ─────────────────────────────────────────────

    def _compute_overall_rhythm(
        self,
        panel_pacings: List[Dict],
        geo_features: List[Dict],
        prev_rhythm: Optional[str],
    ) -> str:
        """
        计算单页整体阅读节奏

        Args:
            panel_pacings: 每格节奏标签
            geo_features: 几何特征
            prev_rhythm: 上一页节奏

        Returns:
            整体节奏类型
        """
        if not panel_pacings:
            return PacingType["TRANSITION"]

        # 统计各类型数量
        has_climax = False
        has_tension = False
        has_calm = True

        for panel in panel_pacings:
            pacing = panel.get("pacing", "")

            if pacing == PacingType["CLIMAX"]:
                has_climax = True
            elif pacing == PacingType["TENSION"]:
                has_tension = True
            elif pacing != PacingType["CALM"]:
                has_calm = False

        # 计算整体节奏
        if has_climax:
            rhythm = PacingType["CLIMAX"]
        elif has_tension:
            rhythm = PacingType["TENSION"]
        elif has_calm:
            rhythm = PacingType["CALM"]
        else:
            rhythm = PacingType["TRANSITION"]

        # 考虑出血格
        for geo in geo_features:
            if geo.get("is_splash"):
                rhythm = PacingType["CLIMAX"]
                break

        # 考虑上一页节奏（连贯性）
        if prev_rhythm:
            # 从高潮到平静需要过渡
            if rhythm == PacingType["CALM"] and prev_rhythm == PacingType["CLIMAX"]:
                rhythm = PacingType["TRANSITION"]
            # 从平静到高潮之间有过渡
            elif rhythm == PacingType["CLIMAX"] and prev_rhythm == PacingType["CALM"]:
                rhythm = PacingType["TENSION"]

        return rhythm


# ─────────────────────────────────────────────
# 便捷函数
# ─────────────────────────────────────────────

def analyze_page(
    manga_page_image: str,
    panel_layout: Dict,
    prev_rhythm: Optional[str] = None,
    vision_provider: str = "mmx",
) -> Dict:
    """
    便捷函数：分析单页漫画节奏

    Args:
        manga_page_image: 漫画页面图片路径
        panel_layout: 分镜布局数据
        prev_rhythm: 上一页节奏
        vision_provider: 视觉分析提供商

    Returns:
        分析结果字典
    """
    analyzer = NarrativePacingAnalyzer(vision_provider=vision_provider)
    return analyzer.analyze_page(manga_page_image, panel_layout, prev_rhythm)


def analyze_segment(
    pages: List[Dict],
    vision_provider: str = "mmx",
) -> Dict:
    """
    便捷函数：分析多个连续页的节奏曲线

    Args:
        pages: 每页数据列表
        vision_provider: 视觉分析提供商

    Returns:
        段落分析结果
    """
    analyzer = NarrativePacingAnalyzer(vision_provider=vision_provider)
    return analyzer.analyze_segment(pages)


if __name__ == '__main__':
    # 测试代码
    import sys

    test_panel_layout = {
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
            {
                "panel_id": "p3",
                "bounds": {"x": 0, "y": 210, "w": 610, "h": 400},
                "gaps": {"left": 5, "right": 5, "top": 10, "bottom": 5},
                "border_style": "slant",
                "splash": True,
            },
        ],
        "page_size": {"w": 800, "h": 1200},
    }

    # 读取命令行参数
    image_path = sys.argv[1] if len(sys.argv) > 1 else ""

    # 创建分析器并分析（禁用 mmx，使用规则引擎）
    analyzer = NarrativePacingAnalyzer(vision_provider="none")
    result = analyzer.analyze_page(image_path, test_panel_layout)

    print(json.dumps(result, indent=2, ensure_ascii=False))