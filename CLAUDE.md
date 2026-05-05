# CLAUDE.md - MangaAutoLayout Development Guide

## Project Context
- This is a PyQt6 desktop application for manga/comic page layout automation
- Python 3.10+ required
- Uses PyQt6 for GUI, Pillow for image processing, reportlab for PDF export

## Key Conventions
- Type hints on all public functions/methods
- Google-style docstrings
- 4-space indentation
- No wildcard imports
- Use Python logging module, not print()

## Module Dependencies
- main.py: loads settings, creates MainWindow
- ui/main_window.py: central widget, layout management
- core/parser.py: Script → JSON scene data
- core/layout_engine.py: Scene data → Panel layout
- core/image_processor.py: Image loading and processing
- core/text_typesetter.py: Dialogue bubbles
- core/refiner.py: Layout cleanup
- utils/export.py: PDF/ZIP export
- utils/llm_client.py: Optional LLM suggestions

## Common Tasks
- Run: `python main.py`
- Install deps: `pip install -r requirements.txt`

## UI Layout
- Left: Scene panel (QListWidget)
- Center: Canvas (QGraphicsView)
- Right: Dialogue panel (QWidget)