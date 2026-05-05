# MangaAutoLayout

Automatic manga/comic page layout application powered by AI.

**Core flow:** Script → Parse → AI Image Generation → Auto Layout → Add Dialogue → Export PDF/ZIP

## Features

- **Script Parsing** — Supports TXT and DOCX formats with scene detection, character dialogue, actions, and SFX
- **Auto Layout** — Automatic panel layout based on dialogue density
- **AI Integration** — Optional MiniMax API for layout suggestions
- **PDF/ZIP Export** — High-quality export with RTL reading direction support
- **PyQt6 UI** — Full desktop application with scene panel, canvas, and dialogue editor

## Installation

```bash
pip install -r requirements.txt
```

## Requirements

- Python 3.9+
- PyQt6>=6.4.0
- Pillow>=10.0.0
- requests>=2.28.0
- python-docx>=0.8.11
- reportlab>=4.0.0

## Usage

```bash
python main.py
```

## Script Format

```
场景1
天台，白天
男主：今天有话想跟你说...
女主：什么话？
（动作：男主握住女主的手）
《心跳加速》
```

Supported formats:
- `场景X` / `Scene X` / `第X页` / `Page X` — New scene/page
- `角色：对话` — Character dialogue
- `（动作描述）` / `【动作描述】` — Action/description
- `《效果字》` / `「効果音」` — Sound effects

## License

Private — 仅供个人使用
