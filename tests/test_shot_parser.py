"""
漫画分镜解析器单元测试
"""
import json
import pytest
from pathlib import Path

# 导入待测试模块（直接导入避免 core/__init__. 链式导入 docx）
import importlib.util
_shot_parser_spec = importlib.util.spec_from_file_location(
    "shot_parser",
    str(Path(__file__).parent.parent / "core" / "shot_parser.py")
)
_shot_parser_mod = importlib.util.module_from_spec(_shot_parser_spec)
_shot_parser_spec.loader.exec_module(_shot_parser_mod)

ShotParser = _shot_parser_mod.ShotParser
parse = _shot_parser_mod.parse
parse_file = _shot_parser_mod.parse_file
CAMERA_TYPES = _shot_parser_mod.CAMERA_TYPES
CAMERA_KEYWORDS = _shot_parser_mod.CAMERA_KEYWORDS
HIGH_IMPORTANCE_KEYWORDS = _shot_parser_mod.HIGH_IMPORTANCE_KEYWORDS
MEDIUM_IMPORTANCE_KEYWORDS = _shot_parser_mod.MEDIUM_IMPORTANCE_KEYWORDS
LAYOUT_HINTS_BY_CAMERA = _shot_parser_mod.LAYOUT_HINTS_BY_CAMERA


class TestShotParserInit:
    """ShotParser 初始化测试"""

    def test_init(self):
        """测试初始化"""
        parser = ShotParser()
        assert parser is not None


class TestParse:
    """parse 函数测试"""

    def test_empty_script(self):
        """测试空剧本"""
        result = parse("")
        assert 'title' in result
        assert 'pages' in result

    def test_basic_parse(self):
        """基础解析测试"""
        script = """Page 1
男主在教室
男主：「你好」
"""
        result = parse(script)
        assert result['title'] == '未命名故事'
        assert len(result['pages']) >= 1

    def test_with_title(self):
        """带标题解析"""
        script = "男主在教室"
        result = parse(script, "我的故事")
        assert result['title'] == '我的故事'

    def test_multi_page(self):
        """多页面解析"""
        script = """Page 1
场景1

Page 2
场景2
"""
        result = parse(script)
        assert len(result['pages']) >= 2


class TestParsePanel:
    """parse_panel 方法测试"""

    def test_basic_panel(self):
        """基础分镜解析"""
        parser = ShotParser()
        panel = parser.parse_panel("男主在教室等待", 1)

        assert panel['id'] == 1
        assert panel['action'] != ""

    def test_panel_with_dialogue(self):
        """带对话的分镜"""
        parser = ShotParser()
        panel = parser.parse_panel("男主：「今天有话想说」", 1)

        assert len(panel['dialogue']) >= 1
        assert panel['dialogue'][0]['speaker'] == '男主'

    def test_panel_with_english_quotes(self):
        """英文引号对话"""
        parser = ShotParser()
        panel = parser.parse_panel('男主："Hello"', 1)

        assert len(panel['dialogue']) >= 1
        assert panel['dialogue'][0]['text'] == 'Hello'

    def test_panel_with_sfx(self):
        """带音效的分镜"""
        parser = ShotParser()
        panel = parser.parse_panel("场景【心跳】", 1)

        assert len(panel['sfx']) >= 1

    def test_panel_with_expression(self):
        """带表情的分镜"""
        parser = ShotParser()
        panel = parser.parse_panel("男主开心地笑\n男主脸红", 1)

        assert panel['expression'] != ""


class TestDetectCamera:
    """镜头类型检测测试"""

    def test_detect_wide(self):
        """远景检测"""
        parser = ShotParser()
        result = parser._detect_camera("远景镜头")
        assert result['type'] == 'wide'

    def test_detect_close_up(self):
        """特写检测"""
        parser = ShotParser()
        result = parser._detect_camera("脸部特写")
        assert result['type'] == 'close_up'

    def test_detect_two_shot(self):
        """双人镜头检测"""
        parser = ShotParser()
        result = parser._detect_camera("两人对话")
        assert result['type'] == 'two_shot'

    def test_explicit_camera_short(self):
        """显式镜头标记@CU"""
        parser = ShotParser()
        result = parser._detect_camera("@CU 脸部")
        assert result['type'] == 'close_up'

    def test_default_camera(self):
        """默认中景"""
        parser = ShotParser()
        result = parser._detect_camera("普通场景")
        assert result['type'] == 'medium'


class TestDetectImportance:
    """重要性检测测试"""

    def test_high_importance_kiss(self):
        """高重要性-接吻"""
        parser = ShotParser()
        result = parser._detect_importance("接吻场景")
        assert result == 'high'

    def test_high_importance_confession(self):
        """高重要性-告白"""
        parser = ShotParser()
        result = parser._detect_importance("告白")
        assert result == 'high'

    def test_medium_importance(self):
        """中重要性"""
        parser = ShotParser()
        result = parser._detect_importance("对话")
        assert result == 'medium'

    def test_default_importance(self):
        """默认重要性"""
        parser = ShotParser()
        result = parser._detect_importance("场景描述")
        assert result == 'medium'


class TestExtractDialogue:
    """对话提取测试"""

    def test_dialogue_cn_quotes(self):
        """中文引号「」"""
        parser = ShotParser()
        result = parser._extract_dialogue("男主：「台词」")
        assert result is not None
        assert result['speaker'] == '男主'
        assert result['text'] == '台词'

    def test_dialogue_en_quotes(self):
        """英文引号"""
        parser = ShotParser()
        result = parser._extract_dialogue('男主:"Hello"')
        assert result is not None
        assert result['speaker'] == '男主'
        assert result['text'] == 'Hello'

    def test_no_dialogue(self):
        """无对话"""
        parser = ShotParser()
        result = parser._extract_dialogue("场景描述")
        assert result is None


class TestDetectSfx:
    """音效检测测试"""

    def test_sfx_cn_brackets(self):
        """中文方括号"""
        parser = ShotParser()
        result = parser._detect_sfx("【心跳】")
        assert '心跳' in result

    def test_sfx_cn_quotes(self):
        """中文引号"""
        parser = ShotParser()
        result = parser._detect_sfx("「バシン」")
        assert 'バシン' in result

    def test_sfx_en_caps(self):
        """英文大写"""
        parser = ShotParser()
        result = parser._detect_sfx("(SLAM)")
        assert 'SLAM' in result


class TestDetectTags:
    """标签检测测试"""

    def test_tag_kiss(self):
        """接吻标签"""
        parser = ShotParser()
        result = parser._detect_tags("接吻")
        assert 'kiss' in result

    def test_tag_romance(self):
        """浪漫标签"""
        parser = ShotParser()
        result = parser._detect_tags("浪漫")
        assert 'romance' in result

    def test_tag_action(self):
        """战斗标签"""
        parser = ShotParser()
        result = parser._detect_tags("战斗")
        assert 'action' in result


class TestInferLayoutHint:
    """布局提示推断测试"""

    def test_wide_spread(self):
        """wide ��� spread"""
        parser = ShotParser()
        result = parser._infer_layout_hint('wide')
        assert result == 'spread'

    def test_close_up_centered(self):
        """close_up → centered"""
        parser = ShotParser()
        result = parser._infer_layout_hint('close_up')
        assert result == 'centered'

    def test_default_standard(self):
        """默认 standard"""
        parser = ShotParser()
        result = parser._infer_layout_hint('unknown')
        assert result == 'standard'


class TestSplitPages:
    """页面拆分测试"""

    def test_split_by_page_marker(self):
        """按页面标记拆分"""
        parser = ShotParser()
        text = "Page 1\n内容1\n\nPage 2\n内容2"
        result = parser._split_pages(text)
        assert len(result) >= 1


class TestSplitPanels:
    """分镜拆分测试"""

    def test_split_by_separator(self):
        """按分隔符拆分"""
        parser = ShotParser()
        text = "分镜1\n\n---\n\n分镜2"
        result = parser._split_panels(text)
        assert len(result) >= 1


class TestParseFile:
    """文件解析测试"""

    @pytest.fixture
    def temp_script_file(self, tmp_path):
        """创建临时剧本文件"""
        file = tmp_path / "script.txt"
        file.write_text("Page 1\n男主：「台词」", encoding='utf-8')
        return str(file)

    def test_parse_file(self, temp_script_file):
        """测试文件解析"""
        result = parse_file(temp_script_file)
        assert result is not None
        assert 'pages' in result

    def test_parse_nonexistent_file(self):
        """测试不存在的文件"""
        with pytest.raises(FileNotFoundError):
            parse_file("/nonexistent/script.txt")


class TestCameraTypes:
    """镜头类型常量测试"""

    def test_camera_types_nonempty(self):
        """常量非空"""
        assert len(CAMERA_TYPES) > 0

    def test_camera_keywords_nonempty(self):
        """关键词非空"""
        assert len(CAMERA_KEYWORDS) > 0

    def test_layout_hints_nonempty(self):
        """布局提示非空"""
        assert len(LAYOUT_HINTS_BY_CAMERA) > 0


class TestIntegration:
    """集成测试"""

    def test_full_script_parsing(self):
        """完整剧本解析"""
        script = """Page 1
男主在教室等待
男主：「今天有话想跟你说...」
女主（脸红）
【心跳加速】

女主握住男主的手
女主：「我也...」
@CU 两人手部特写
【接吻】【浪漫】

Page 2
教室门外
男主：「我们还能见面吗？」
女主：「...嗯」
"""
        result = parse(script, "青春恋语")

        # 验证结构
        assert result['title'] == '青春恋语'
        assert len(result['pages']) == 2

        # 验证第一页
        page1 = result['pages'][0]
        assert page1['page_number'] == 1
        assert len(page1['panels']) >= 2

        # 验证第二页
        page2 = result['pages'][1]
        assert page2['page_number'] == 2

    def test_camera_detection_accuracy(self):
        """镜头检测准确率测试"""
        test_cases = [
            ("远景镜头", "wide"),
            ("中景", "medium"),
            ("特写", "close_up"),
            ("双人", "two_shot"),
            ("俯视", "high_angle"),
            ("鸟瞰", "birds_eye"),
        ]

        parser = ShotParser()
        correct = 0
        for text, expected in test_cases:
            result = parser._detect_camera(text)
            if result['type'] == expected:
                correct += 1

        accuracy = correct / len(test_cases)
        assert accuracy >= 0.8, f"准确率 {accuracy} < 80%"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])