"""
漫画分镜语义解析器

从漫画剧本文本解析出分镜 JSON 数据结构。

功能：
- 自动识别页面和分镜段落
- 镜头类型检测（基于关键词和语义推断）
- 对话/旁白提取（支持「」和""引号）
- 音效检测（基于括号或大写词）
- 重要性评估（高冲击关键词）
- 布局提示推断
- 标签提取

支持输入格式：
- Page N / P.N 页面标记
- 空行分段镜
- 人物名：「对话」 或 人物名:"对话"
- 【】标记角色/标签
- ★/☆ 重要性标记
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 镜头类型（日漫专用）
CAMERA_TYPES = {
    'wide': 'wide',
    'medium': 'medium',
    'close-up': 'close_up',
    'close_up': 'close_up',
    'extreme_close_up': 'extreme_close_up',
    'over_shoulder': 'over_shoulder',
    'over-shoulder': 'over_shoulder',
    'dutch': 'dutch',
    'high_angle': 'high_angle',
    'high-angle': 'high_angle',
    'low_angle': 'low_angle',
    'low-angle': 'low_angle',
    'birds_eye': 'birds_eye',
    'birds-eye': 'birds_eye',
    'profile': 'profile',
    'two_shot': 'two_shot',
    'two-shot': 'two_shot',
    'spread': 'spread',
}

# 镜头关键词映射（用于自动检测）
CAMERA_KEYWORDS = {
    'wide': ['远景', '全景', '全貌', 'wide', 'establishing', '建立镜头', '俯瞰', '广阔'],
    'medium': ['中景', '标准', 'medium', '半身'],
    'close_up': ['特写', 'close-up', 'closeup', 'close up', '脸部', '脸部特写', '表情', '大头'],
    'extreme_close_up': ['极特写', '大特写', 'extreme close', '目送'],
    'over_shoulder': ['过肩', 'over shoulder', 'over-shoulder', 'over-shoulder'],
    'dutch': ['荷兰角', 'dutch', '倾斜', 'tilt'],
    'high_angle': ['俯视', 'high angle', '高角度'],
    'low_angle': ['仰视', 'low angle', '低角度'],
    'birds_eye': ['鸟瞰', 'birds eye', 'bird\'s eye', ' aerial'],
    'profile': ['侧面', 'profile', '横'],
    'two_shot': ['双人', '两人', 'two shot', '二人在场', '并排'],
    'spread': ['跨页', 'spread', '展开'],
}

# 高重要性关键词
HIGH_IMPORTANCE_KEYWORDS = [
    '高潮', '告白', '接吻', '求婚', '分手', '流血', '死亡', '战斗',
    'climax', 'kiss', 'proposal', 'confession', '死', '殺',
    '初吻', '表白', '哭泣', '崩溃', '晕倒', '爆炸', '枪击',
]

# 中重要性关键词
MEDIUM_IMPORTANCE_KEYWORDS = [
    '惊讶', '生气', '开心', '尴尬', '沉默', '对话', '转向',
    'surprise', 'angry', 'happy', 'embarrassed',
    '脸红', '愣住', '转身', '回头', '开门', '坐下',
]

# 布局提示映射
LAYOUT_HINTS_BY_CAMERA = {
    'wide': 'spread',
    'spread': 'spread',
    'two_shot': 'horizontal',
    'medium': 'standard',
    'close_up': 'centered',
    'extreme_close_up': 'centered',
    'profile': 'vertical',
    'low_angle': 'bottom_heavy',
    'high_angle': 'top_heavy',
}

# 页面标记
_PAGE_MARKER = re.compile(
    r'^(?:page|Page|第)\s*(\d+)\b|^(?:P|p)\.(\d+)|^\[?第?\s*(\d+)\s*(?:页|page)',
    re.IGNORECASE | re.MULTILINE
)
_PANEL_SEPARATOR = re.compile(r'^--+$|^\.{3,}$|^={3,}$|^pane?l?\s*[:\-]?\s*(\d+)?$', re.IGNORECASE)
_DIALOGUE_CN = re.compile(r'^([^「」:：]+)[：:]「(.+)」\s*$')
_DIALOGUE_EN = re.compile(r'^([^"「」:：]+)[：:]"(.+)"\s*$')
_SFX_CN = re.compile(r'【(.+?)】|"「(.+?)」')
_SFX_EN = re.compile(r'\(([A-Z]{2,})\)')
_NARRATION = re.compile(r'^旁白[：:]?(.*)$|^ narration[：:]?(.*)$', re.IGNORECASE)
_CAMERA_SHORT = re.compile(r'@(wide|medium|cu|cu2|ws|ws2|pov|ov|tilt|2s|int|aerial|panning)', re.IGNORECASE)


class ShotParser:
    """漫画分镜语义解析器"""

    def __init__(self):
        """初始化解析器"""
        pass

    def parse(self, script_text: str, title: str = "") -> dict:
        """
        从剧本文本解析出分镜 JSON

        Args:
            script_text: 漫画剧本纯文本
            title: 故事标题（可选）

        Returns:
            分镜 JSON 数据结构
        """
        if not script_text.strip():
            logger.warning("Empty script text, returning default structure")
            return self._default_structure(title)

        # 按页面拆分
        pages = self._split_pages(script_text)

        # 解析每个页面
        parsed_pages = []
        for i, page_text in enumerate(pages):
            page_data = self.parse_page(page_text, i + 1)
            if page_data['panels']:
                parsed_pages.append(page_data)

        # 确保至少有一页
        if not parsed_pages:
            parsed_pages.append({
                'page_number': 1,
                'panels': [self._create_default_panel(1)],
            })

        result = {
            'title': title or '未命名故事',
            'pages': parsed_pages,
        }

        logger.info(f"Parsed {len(parsed_pages)} pages, {sum(len(p['panels']) for p in parsed_pages)} panels")
        return result

    def parse_page(self, page_text: str, page_number: int) -> dict:
        """
        解析单个页面

        Args:
            page_text: 页面文本
            page_number: 页码

        Returns:
            页面数据结构
        """
        # 按分镜拆分（空行或分隔符）
        panels_text = self._split_panels(page_text)

        panels = []
        for i, panel_text in enumerate(panels_text):
            panel_data = self.parse_panel(panel_text, i + 1)
            if panel_data['action'] or panel_data['dialogue']:
                panels.append(panel_data)

        # 确保至少有一个分镜
        if not panels:
            panels.append(self._create_default_panel(1))

        return {
            'page_number': page_number,
            'panels': panels,
        }

    def parse_panel(self, panel_text: str, panel_id: int) -> dict:
        """
        解析单个分镜

        Args:
            panel_text: 分镜文本
            panel_id: 分镜ID

        Returns:
            分镜数据结构
        """
        lines = [line.strip() for line in panel_text.strip().split('\n') if line.strip()]

        if not lines:
            return self._create_default_panel(panel_id)

        # 初始化分镜数据
        action = ""
        expression = ""
        camera_type: Optional[dict] = None
        importance = 'medium'
        dialogue_list: List[dict] = []
        narration = None
        sfx_list: List[str] = []
        tags: List[str] = []

        # 第一行通常作为动作描述
        first_line = lines[0]

        # 检查是否是镜头标记
        camera_match = _CAMERA_SHORT.match(first_line)
        if camera_match:
            # 显式镜头标记
            camera_type = self._detect_camera(first_line)
            first_line = _CAMERA_SHORT.sub('', first_line).strip()

        if first_line:
            action = first_line

        # 处理所有行（包括第一行之后的内容）
        for line in lines:
            # 对话提取
            dialogue = self._extract_dialogue(line)
            if dialogue:
                dialogue_list.append(dialogue)
                # 如果对话行也是 action，更新 action
                if not action or line == first_line:
                    action = line
                continue

            # 旁白提取
            narration_match = _NARRATION.match(line)
            if narration_match:
                narration = narration_match.group(1) or narration_match.group(2)
                if narration:
                    narration = narration.strip()
                continue

            # 音效提取
            sfx = self._detect_sfx(line)
            if sfx:
                sfx_list.extend(sfx)
                continue

            # 表情描述
            if any(kw in line for kw in ['表情', '神情', '脸红', '愣住']):
                expression = line
                continue

            # 标签提取
            detected_tags = self._detect_tags(line)
            if detected_tags:
                tags.extend(detected_tags)

        # 检测镜头类型（如果未显式指定）
        if camera_type is None:
            full_text = '\n'.join(lines)
            camera_type = self._detect_camera(full_text)

        # 检测重要性
        full_text = '\n'.join(lines)
        importance = self._detect_importance(full_text)

        # 检测标签
        if not tags:
            tags = self._detect_tags(full_text)

        # 推断布局提示
        camera_value = camera_type.get('type', 'medium') if camera_type else 'medium'
        layout_hint = self._infer_layout_hint(camera_value)

        return {
            'id': panel_id,
            'action': action,
            'expression': expression,
            'camera': camera_type,
            'dialogue': dialogue_list,
            'narration': narration,
            'sfx': sfx_list,
            'importance': importance,
            'layout_hint': layout_hint,
            'bleed': camera_value in ('spread', 'wide') or importance == 'high',
            'tags': tags,
        }

    def _detect_camera(self, text: str) -> dict:
        """
        检测镜头类型

        Args:
            text: 输入文本

        Returns:
            镜头类型字典 {'type': str, 'description': str}
        """
        text_lower = text.lower()

        # 首先检查显式标记
        for camera_key, keywords in CAMERA_KEYWORDS.items():
            for kw in keywords:
                if kw.lower() in text_lower:
                    normalized = CAMERA_TYPES.get(camera_key, camera_key)
                    return {
                        'type': normalized,
                        'description': f"{kw}镜头",
                    }

        # 检查短标记 @CU, @WS 等
        short_match = _CAMERA_SHORT.search(text)
        if short_match:
            short = short_match.group(1).lower()
            mapping = {
                'cu': 'close_up',
                'cu2': 'extreme_close_up',
                'ws': 'wide',
                'ws2': 'wide',
                'pov': 'POV',
                'ov': 'over_shoulder',
                'tilt': 'dutch',
                '2s': 'two_shot',
                'int': 'insert',
                'aerial': 'birds_eye',
                'panning': 'wide',
            }
            if short in mapping:
                return {
                    'type': mapping[short],
                    'description': f"@{short.upper()}镜头",
                }

        # 默认中景
        return {
            'type': 'medium',
            'description': '标准中景',
        }

    def _detect_importance(self, text: str) -> str:
        """
        检测重要性

        Args:
            text: 输入文本

        Returns:
            'high' | 'medium' | 'low'
        """
        text_lower = text.lower()

        # 高重要性检测
        for kw in HIGH_IMPORTANCE_KEYWORDS:
            if kw.lower() in text_lower:
                return 'high'

        # 中重要性检测
        for kw in MEDIUM_IMPORTANCE_KEYWORDS:
            if kw.lower() in text_lower:
                return 'medium'

        return 'medium'

    def _extract_dialogue(self, text: str) -> Optional[dict]:
        """
        提取对话

        Args:
            text: 行文本

        Returns:
            {'speaker': str, 'text': str} 或 None
        """
        # 中文引号「」
        match = _DIALOGUE_CN.match(text)
        if match:
            return {
                'speaker': match.group(1).strip(),
                'text': match.group(2).strip(),
            }

        # 英文引号 ""
        match = _DIALOGUE_EN.match(text)
        if match:
            return {
                'speaker': match.group(1).strip(),
                'text': match.group(2).strip(),
            }

        return None

    def _detect_sfx(self, text: str) -> List[str]:
        """
        检测音效

        Args:
            text: 行文本

        Returns:
            音效列表
        """
        sfx_list = []

        # 中文【】或「」
        for match in re.finditer(r'【(.+?)】', text):
            sfx_list.append(match.group(1).strip())
        for match in re.finditer(r'「(.+?)」', text):
            sfx_list.append(match.group(1).strip())

        # 英文大写 (SFX)
        for match in re.finditer(r'\(([A-Z]{2,})\)', text):
            sfx_list.append(match.group(1).strip())

        return sfx_list

    def _detect_tags(self, text: str) -> List[str]:
        """
        检测标签

        Args:
            text: 输入文本

        Returns:
            标签列表
        """
        tags = []

        # 常见标签关键词
        tag_keywords = {
            '接吻': 'kiss',
            '浪漫': 'romance',
            '战斗': 'action',
            'battle': 'action',
            '杀': 'action',
            'fight': 'action',
            '打': 'action',
            '哭': 'crying',
            '笑': 'laughing',
            '生气': 'angry',
            '脸红': 'blush',
            '惊讶': 'surprised',
            '汗': 'sweat',
            '晕': 'faint',
            '爆炸': 'explosion',
            '出血': 'blood',
            '死': 'death',
        }

        text_lower = text.lower()
        for cn, en in tag_keywords.items():
            if cn in text_lower or en in text_lower:
                tags.append(en)

        # 去重
        return list(dict.fromkeys(tags))

    def _infer_layout_hint(self, camera_type: str) -> str:
        """
        推断布局提示

        Args:
            camera_type: 镜头类型

        Returns:
            布局提示
        """
        return LAYOUT_HINTS_BY_CAMERA.get(camera_type, 'standard')

    def _split_pages(self, text: str) -> List[str]:
        """
        拆分页面（修复版）

        Args:
            text: 完整文本

        Returns:
            各页面文本列表
        """
        # 使用 finditer 找到所有页面标记位置，避免 re.split() 只匹配第一个的问题
        pages = []
        last_end = 0

        for m in _PAGE_MARKER.finditer(text):
            # 匹配到的位置之前是独立页面
            if m.start() > last_end:
                chunk = text[last_end:m.start()].strip()
                if chunk:
                    pages.append(chunk)
            last_end = m.end()

        # 最后一个页面标记之后的内容
        if last_end < len(text):
            chunk = text[last_end:].strip()
            if chunk:
                pages.append(chunk)

        # 如果没有页面标记，按三空行拆分
        if len(pages) <= 1:
            raw_pages = re.split(r'\n\s*\n\s*\n', text)
            pages = [p.strip() for p in raw_pages if p.strip()]

        if not pages:
            pages = [text]

        return pages

    def _split_panels(self, page_text: str) -> List[str]:
        """
        拆分分镜

        Args:
            page_text: 页面文本

        Returns:
            各分镜文本列表
        """
        # 按分隔符拆分
        # 按分隔符拆分（显式 panel 标记）
        panels = _PANEL_SEPARATOR.split(page_text)

        # 按双空行拆分（-panel 之间只有一个空行的情况）
        if len(panels) <= 1 or all(len(p.strip()) > 100 for p in panels):
            double_newline_split = re.split(r'\n\s*\n', page_text)
            if 1 < len(double_newline_split) <= 20:  # 有意义拆分时才用
                panels = [p.strip() for p in double_newline_split if p.strip()]

        # 过滤空段落
        result = []
        for panel in panels:
            panel = panel.strip()
            if panel:
                result.append(panel)

        return result if result else [page_text]

    def _default_structure(self, title: str) -> dict:
        """默认数据结构"""
        return {
            'title': title or '未命名故事',
            'pages': [
                {
                    'page_number': 1,
                    'panels': [self._create_default_panel(1)],
                },
            ],
        }

    def _create_default_panel(self, panel_id: int) -> dict:
        """创建默认分镜"""
        return {
            'id': panel_id,
            'action': '场景描述',
            'expression': '',
            'camera': {'type': 'medium', 'description': '标准中景'},
            'dialogue': [],
            'narration': None,
            'sfx': [],
            'importance': 'medium',
            'layout_hint': 'standard',
            'bleed': False,
            'tags': [],
        }


# 便捷函数
def parse(script_text: str, title: str = "") -> dict:
    """
    解析漫画剧本

    Args:
        script_text: 漫画剧本纯文本
        title: 故事标题（可选）

    Returns:
        分镜 JSON 数据结构
    """
    parser = ShotParser()
    return parser.parse(script_text, title)


def parse_file(file_path: str, title: str = "") -> dict:
    """
    从文件解析漫画剧本

    Args:
        file_path: 剧本文件路径
        title: 故事标题（可选）

    Returns:
        分镜 JSON 数据结构
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Script file not found: {file_path}")

    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()

    return parse(content, title)


from pathlib import Path

if __name__ == '__main__':
    # 测试代码
    import sys

    # 示例剧本
    sample_script = """Page 1

男主在教室等待
男主：「今天有话想跟你说...」
女主：（脸红）
【心跳加速】

女主握住男主的手
女主：「我也...」
@CU 两人手部特写
【接吻】【浪漫】

Page 2

教室门外
男主： "我们还能见面吗？"
女主："...嗯"
"""

    if len(sys.argv) > 1:
        # 从文件读取
        result = parse_file(sys.argv[1])
    else:
        # 使用示例剧本
        result = parse(sample_script, "青春恋语")

    print(json.dumps(result, indent=2, ensure_ascii=False))