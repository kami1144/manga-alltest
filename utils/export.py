"""
Export module for PDF and ZIP output.
Provides functions for exporting manga pages to PDF and ZIP formats.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image
from reportlab.lib.pagesizes import A4, B5
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.lib.utils import ImageReader
from zipfile import ZipFile

logger = logging.getLogger(__name__)

# Page size presets in mm
PAGE_SIZES = {
    "A4": (210, 297),
    "B5": (182, 257),
    "Japanese A5": (148, 210),
}

# Default page size
DEFAULT_PAGE_SIZE = (210, 297)  # A4 in mm


def export_pdf(
    layout_data: Dict[str, Any],
    images: List[Dict[str, Any]],
    text_elements: List[Dict[str, Any]],
    output_path: str,
    page_size_mm: Tuple[float, float] = (210, 297),
    reading_direction: str = "RTL",
) -> bool:
    """
    Export manga layout to PDF.

    Args:
        layout_data: Layout data from layout_engine
        images: Processed images from image_processor
        text_elements: Text/bubble elements to render
        output_path: Path for output PDF file
        page_size_mm: Page size as (width, height) in mm
        reading_direction: RTL or LTR

    Returns:
        True if export successful
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    pages = layout_data.get('pages', [])
    if not pages:
        logger.error("No pages in layout data")
        return False

    # Validate page_size_mm
    if not page_size_mm or not isinstance(page_size_mm, tuple) or len(page_size_mm) != 2:
        logger.warning(f"Invalid page_size_mm: {page_size_mm}, using default A4")
        page_size_mm = (210, 297)

    c = pdf_canvas.Canvas(str(output_path), pagesize=A4)
    width_pt = page_size_mm[0] * mm
    height_pt = page_size_mm[1] * mm

    # Sort pages by reading direction
    if reading_direction == "RTL":
        pages = sorted(pages, key=lambda p: p.get('page_num', 0), reverse=True)

    for page_idx, page in enumerate(pages):
        if page_idx > 0:
            c.showPage()

        page_num = page.get('page_num', page_idx + 1)
        panels = page.get('panels', [])

        # Render each panel
        for panel in panels:
            _render_panel_to_pdf(
                c, panel, images, width_pt, height_pt, reading_direction
            )

        # Render text elements for this page
        page_text_elements = [
            te for te in text_elements
            if te.get('page_num') == page_num
        ]
        for text_elem in page_text_elements:
            _render_text_to_pdf(c, text_elem, width_pt, height_pt)

        # Add page number
        c.setFont("Helvetica", 10)
        c.drawRightString(
            width_pt - 10 * mm,
            10 * mm,
            f"{page_num}"
        )

    c.save()
    logger.info(f"Exported PDF to {output_path}")
    return True


def export_zip(
    layout_data: Dict[str, Any],
    images: List[Dict[str, Any]],
    text_elements: List[Dict[str, Any]],
    output_dir: str,
    reading_direction: str = "RTL",
    image_format: str = "PNG",
    output_filename: str = "manga_export.zip",
) -> bool:
    """
    Export manga layout to ZIP with processed images.

    Args:
        layout_data: Layout data from layout_engine
        images: Processed images from image_processor
        text_elements: Text/bubble elements to render
        output_dir: Directory for output ZIP file
        reading_direction: RTL or LTR
        image_format: Image format (PNG, JPG)
        output_filename: Name of the output ZIP file

    Returns:
        True if export successful
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    pages = layout_data.get('pages', [])
    if not pages:
        logger.error("No pages in layout data")
        return False

    # Sort pages by reading direction
    if reading_direction == "RTL":
        pages = sorted(pages, key=lambda p: p.get('page_num', 0), reverse=True)

    # Create ZIP file
    zip_path = output_dir / output_filename
    with ZipFile(str(zip_path), 'w') as zf:

        # Add images folder marker
        for page_idx, page in enumerate(pages):
            page_num = page.get('page_num', page_idx + 1)
            panels = page.get('panels', [])

            # Render panels to image
            pil_image = render_page_to_pil(
                page, images, text_elements,
                page_size_mm=(210, 297),
                reading_direction=reading_direction,
            )

            # Save page image to bytes
            import io
            img_buffer = io.BytesIO()
            save_format = image_format.upper()
            pil_image.save(img_buffer, format=save_format)
            img_buffer.seek(0)

            # Add to ZIP
            page_filename = f"pages/page_{page_num:03d}.{image_format.lower()}"
            zf.writestr(page_filename, img_buffer.getvalue())

            logger.info(f"Added page {page_num} to ZIP")

    logger.info(f"Exported ZIP to {zip_path}")
    return True


def render_page_to_pil(
    layout: Dict[str, Any],
    img: Any,
    text_elements: List[Dict[str, Any]],
    page_size_mm: Tuple[float, float] = (210, 297),
    reading_direction: str = "RTL",
) -> Image.Image:
    """
    Render a manga page layout to PIL Image.

    Args:
        layout: Single page layout data
        image: PIL Image for the page background
        text_elements: Text/bubble elements to render
        page_size_mm: Page size as (width, height) in mm
        reading_direction: RTL or LTR

    Returns:
        Rendered PIL Image
    """
    width_px = int(page_size_mm[0] * mm / 72 * 300)
    height_px = int(page_size_mm[1] * mm / 72 * 300)

    # Create blank page (white background)
    page_image = Image.new('RGB', (width_px, height_px), 'white')

    if img:
        # Resize and paste the main image
        img_copy = img.copy()
        img_copy.thumbnail((width_px, height_px), Image.Resampling.LANCZOS)

        # Determine paste position based on panel layout
        panels = layout.get('panels', [])
        if panels:
            # Get primary panel bounds
            primary_panel = panels[0]
            x_ratio = primary_panel.get('x_ratio', 0)
            y_ratio = primary_panel.get('y_ratio', 0)
            w_ratio = primary_panel.get('w_ratio', 1)
            h_ratio = primary_panel.get('h_ratio', 1)

            x = int(x_ratio * width_px)
            y = int(y_ratio * height_px)
            w = int(w_ratio * width_px)
            h = int(h_ratio * height_px)

            # Resize to fit panel
            img = img.resize((w, h), Image.Resampling.LANCZOS)
            page_image.paste(img, (x, y))

    return page_image


def _render_panel_to_pdf(
    c: pdf_canvas.Canvas,
    panel: Dict[str, Any],
    images: List[Dict[str, Any]],
    width_pt: float,
    height_pt: float,
    reading_direction: str,
) -> None:
    """Render a single panel to PDF canvas."""
    x_ratio = panel.get('x_ratio', 0)
    y_ratio = panel.get('y_ratio', 0)
    w_ratio = panel.get('w_ratio', 1)
    h_ratio = panel.get('h_ratio', 1)

    # Calculate bounds
    x = x_ratio * width_pt
    y = (1 - y_ratio - h_ratio) * height_pt
    w = w_ratio * width_pt
    h = h_ratio * height_pt

    # Draw panel border
    c.setLineWidth(0.5)
    c.setStrokeColorRGB(0.8, 0.8, 0.8)
    c.rect(x, y, w, h)

    # Get image for panel
    image_ref = panel.get('image_ref')
    pil_image = panel.get('pil_image')

    if pil_image:
        try:
            # Convert PIL to reportlab ImageReader
            img_reader = ImageReader(pil_image)
            c.drawImage(img_reader, x, y, width=w, height=h, mask='auto')
        except Exception as e:
            logger.warning(f"Could not render image: {e}")


def _render_text_to_pdf(
    c: pdf_canvas.Canvas,
    text_elem: Dict[str, Any],
    width_pt: float,
    height_pt: float,
) -> None:
    """Render text element to PDF canvas."""
    x_ratio = text_elem.get('x_ratio', 0.1)
    y_ratio = text_elem.get('y_ratio', 0.9)
    text = text_elem.get('text', '')
    font_size = text_elem.get('font_size', 12)

    x = x_ratio * width_pt
    y = (1 - y_ratio) * height_pt

    c.setFont("Helvetica", font_size)
    c.drawString(x, y, text)


def get_page_size(name: str) -> Tuple[float, float]:
    """
    Get page size by name.

    Args:
        name: Page size name (A4, B5, Japanese A5)

    Returns:
        Page size as (width, height) in mm
    """
    return PAGE_SIZES.get(name, DEFAULT_PAGE_SIZE)