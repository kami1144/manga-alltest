# MangaAutoLayout Specification

## Project Overview / 项目概述

### English
MangaAutoLayout is a Python PyQt6 desktop application for automatic manga/comic page layout from scripts and images. It parses script files (TXT or DOCX), processes images, automatically generates panel layouts using templates, and exports to PDF or ZIP formats.

### 中文
MangaAutoLayout 是一个使用 Python PyQt6 构建的桌面应用程序，用于从剧本和图像自动生成漫画/连环画页面布局。它解析脚本文件（TXT 或 DOCX），处理图像，使用模板自动生成面板布局，并导出为 PDF 或 ZIP 格式。

## Architecture / 架构

```
manga-auto-layout/
├── main.py              # Entry point
├── ui/                 # User Interface
│   ├── main_window.py   # Main window
│   ├── canvas.py      # Graphics canvas
│   ├── scene_panel.py # Scene list panel
│   └── dialogue_panel.py # Dialogue editor
├── core/              # Core logic
│   ├── parser.py      # Script parser
│   ├── layout_engine.py # Layout algorithm
│   ├── image_processor.py # Image handling
│   ├── text_typesetter.py # Text placement
│   └── refiner.py    # Layout refinement
├── utils/             # Utilities
│   ├── llm_client.py # LLM API client
│   └── export.py    # Export functions
└── templates/        # Layout templates
```

## UI Layout / 界面布局

### Main Window
- **Window Title**: "MangaAutoLayout"
- **Minimum Size**: 1200x800
- **Layout**: Three-column
  - Left: Scene Panel (250px)
  - Center: Canvas (flexible)
  - Right: Dialogue Panel (280px)

### Menu Bar
- **File**: Import Script, Import Images, Export PDF, Export ZIP, Exit
- **Edit**: Undo, Redo
- **View**: Zoom In, Zoom Out, Fit Page
- **Help**: About

### Toolbar
- Import Script, Import Images, Auto Layout, Export

### Status Bar
- "Scenes: X | Images: Y | Page: current/total"

## Data Flow / 数据流

1. **Import Script** → Parse TXT/DOCX → Scene data
2. **Import Images** → Load images → Processed images
3. **Auto Layout** → Layout algorithm → Panel layout
4. **Text Typeset** → Bubble placement → Final layout
5. **Export** → PDF or ZIP → Output file

## Module Specifications / 模块规范

### core/parser.py

**Input Formats**:
- TXT file with UTF-8 encoding
- DOCX file (python-docx)

**Syntax**:
- `场景1` / `Scene 1` / `第1页` = New scene
- `角色：对话` = Dialogue
- `（动作）` / `【动作】` = Action/description
- `《SFX》` = Sound effects

**Output JSON**:
```json
{
  "pages": [{
    "page_num": 1,
    "scenes": [{
      "scene_id": "scene_1",
      "description": "...",
      "dialogue_lines": ["..."],
      "sfx_list": ["..."],
      "dialogue_count": 3
    }]
  }]
}
```

**Dialogue Density**:
- High: >5 lines → 4-6 panels
- Medium: 3-5 lines → 2-4 panels
- Low: <3 lines → 1-2 panels

### core/layout_engine.py

**Algorithm**:
1. Determine panel count from dialogue_density
2. Select template based on panel count
3. Assign images to panels
4. Apply RTL reading order
5. Output layout data

**Template Selection**:
- 1 panel: full_bleed
- 2 panels: half_vertical
- 3 panels: thirds / manga_classic / dynamic_diagonal
- 4 panels: grid_4
- 5-6 panels: grid_6
- Importance=high: splash

**Shape Types**:
- rect: Normal rectangle
- bleed: Extends to page edge

### core/image_processor.py

**Supported Formats**: jpg, jpeg, png, webp, heif

**Crop Modes**:
- fit: Letterbox/pillarbox
- fill: Crop to fill

**Saliency Detection**:
- Center crop as fallback
- Face detection if OpenCV available

### core/text_typesetter.py

**Bubble Types**:
- normal: Rounded rectangle
- shout: Jagged/explosion
- thought: Cloud shape
- whisper: Dotted outline
- sfx: Bold stylized

**Auto-placement**:
- Panel corners
- Avoid center (main action)

**Sizing**:
- Minimum 80px width
- Font size scales with bubble size

### core/refiner.py

- gutter_width: 12px default
- bleed: 3mm extension
- overflow_check: Scale down or move

### utils/export.py

**Page Sizes (mm)**:
- A4: 210x297
- B5: 182x257
- Japanese A5: 148x210

**PDF Export**:
- reportlab-based
- 72/150/300 DPI

**ZIP Export**:
- PNG sequence
- dialogue.json sidecar

## File Formats / 文件格式

### Template JSON
```json
{
  "name": "full_bleed",
  "description": "Single full-page panel",
  "panels": [{
    "x_ratio": 0,
    "y_ratio": 0,
    "w_ratio": 1,
    "h_ratio": 1,
    "shape": "rect",
    "bleed_edge": null
  }]
}
```

## Phase 1 Acceptance Criteria / 第一阶段验收标准

### Must Pass / 必须通过
- [ ] Application launches without errors
- [ ] Main window displays with three panels
- [ ] Can import TXT script file
- [ ] Can import DOCX script file
- [ ] Scenes appear in scene panel
- [ ] Can import images from folder
- [ ] Auto Layout generates panels
- [ ] Canvas displays page preview
- [ ] Can navigate pages
- [ ] Can export to PDF
- [ ] Can export to ZIP

### Visual Checkpoints / 视觉检查点
- [ ] Scene icons display correctly
- [ ] Dialogue count badges visible
- [ ] Panel borders highlight on selection
- [ ] RTL reading order numbers shown
- [ ] Dialogue bubbles render correctly

### Edge Cases / 边缘情况
- [ ] Empty script handling
- [ ] Missing images handling
- [ ] Multiple pages
- [ ] Large image files
- [ ] Special characters in dialogue