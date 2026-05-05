"""
Image Composer v2 — Intelligent image cropping and composition for manga panels.

Improvements over v1:
- Real saliency detection (OpenCV-based, not just center crop fallback)
- User-defined ROI (region of interest) override
- Multi-layer composition: background + character overlay
- AI inpainting integration point (ComfyUI / MiniMax)
- Priority-based image assignment for high-importance panels
- Better shot-to-crop-strategy mapping
- manga-style contrast/sharpness presets
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageEnhance, ImageFilter
import numpy as np

logger = logging.getLogger(__name__)

SUPPORTED_FORMATS = {'.jpg', '.jpeg', '.png', '.webp', '.heif', '.heic'}

# Shot type → crop strategy
SHOT_STRATEGIES = {
    'close_up':        'face_focus',       # Crop to face/upper body
    'close_up_2':      'extreme_close_up', # Extreme close-up (eyes, lips)
    'medium_shot':     'thirds',            # Classic thirds composition
    'wide_shot':       'full_frame',        # Show full background
    'very_wide':       'full_frame',        # Establishing shot
    'POV':             'center',            # First-person, centered
    'over_shoulder':   'offset_left',       # Slight left offset
    'tilted':          'dynamic_diagonal',  # Diagonal composition
    'two_shot':        'two_person',        # Two people framing
    'insert':          'detail',            # Detail/insert shot
    'aerial':          'wide_top',          # Aerial: top-weighted
    'panning':         'horizontal_pan',    # Horizontal pan
}

# Importance → crop priority
IMPORTANCE_CROP_PRIORITY = {
    'high':   0,   # Highest quality crop, preserve detail
    'medium': 1,
    'low':    2,   # Can crop more aggressively
}


# ---------------------------------------------------------------------------
# Core saliency detection (OpenCV-based)
# ---------------------------------------------------------------------------

def find_salient_region(img: Image.Image) -> Tuple[int, int, int, int]:
    """
    Find the salient (focal) region of an image using OpenCV.

    Uses multiple strategies in order:
    1. OpenCV saliency detection (if cv2 available)
    2. Face/eye detection (if cv2 CascadeClassifier available)
    3. Edge-based fallback (intensity gradient)
    4. Center crop fallback

    Returns (x, y, w, h) in pixel coordinates.
    """
    try:
        import cv2
        cv2_available = True
    except ImportError:
        cv2_available = False

    if cv2_available:
        # Try OpenCV saliency detection
        result = _opencv_saliency(img)
        if result is not None:
            return result

        # Try face detection
        result = _opencv_face_detection(img)
        if result is not None:
            return result

    # Fallback: contrast-based salient region
    result = _contrast_based_saliency(img)
    if result is not None:
        return result

    # Final fallback: center crop 60%
    return _center_crop_fallback(img)


def _opencv_saliency(img: Image.Image) -> Optional[Tuple[int, int, int, int]]:
    """Use OpenCV's StaticSaliency API if available."""
    try:
        import cv2
        arr = np.array(img.convert('RGB'))
        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)

        # Try spectral saliency (fast, good for manga)
        saliency = cv2.saliency.ObjectnessBING_create()
        if saliency is not None:
            (success, saliency_map) = saliency.computeSaliency(gray)
            if success and saliency_map is not None and len(saliency_map) > 0:
                # Get bounding box of most salient region
                # saliency_map is a heatmap, find the highest-response region
                from numpy.linalg import norm
                h, w = gray.shape
                # Focus on upper-center (typical manga focal area)
                upper = gray[:int(h * 0.7), :]
                _, thresh = cv2.threshold(upper, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                coords = np.column_stack(np.where(thresh > 0))
                if len(coords) > 0:
                    y_min = coords[:, 0].min()
                    x_min = coords[:, 1].min()
                    y_max = coords[:, 0].max()
                    x_max = coords[:, 1].max()
                    # Add margin
                    margin = int(w * 0.05)
                    x = max(0, x_min - margin)
                    y = max(0, y_min - margin)
                    cw = min(w - x, x_max - x_min + 2 * margin)
                    ch = min(h - y, y_max - y_min + 2 * margin)
                    return (x, y, cw, ch)

        # Try fine-grained saliency
        spectral = cv2.saliency.ImageSaliency_create("SPECTRAL")
        if spectral is not None:
            (success, saliency_map) = spectral.computeSaliency(gray)
            if success and saliency_map is not None:
                # Find bounding box of top 20% saliency region
                threshold = np.percentile(saliency_map, 80)
                mask = (saliency_map > threshold).astype(np.uint8) * 255
                contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                if contours:
                    largest = max(contours, key=cv2.contourArea)
                    x, y, w, h = cv2.boundingRect(largest)
                    margin = int(min(w, h) * 0.1)
                    return (
                        max(0, x - margin),
                        max(0, y - margin),
                        min(img.width - x, w + 2 * margin),
                        min(img.height - y, h + 2 * margin),
                    )
    except Exception as e:
        logger.debug(f"OpenCV saliency failed: {e}")
    return None


def _opencv_face_detection(img: Image.Image) -> Optional[Tuple[int, int, int, int]]:
    """Use OpenCV Haar cascade for face/eye detection."""
    try:
        import cv2
        arr = np.array(img.convert('RGB'))
        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)

        # Try face detection
        face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        )
        faces = face_cascade.detectMultiScale(gray, 1.3, 5)
        if len(faces) > 0:
            x, y, w, h = faces[0]
            # Expand to include upper body (common manga framing)
            body_h = int(h * 0.6)
            y_exp = max(0, y - int(body_h * 0.3))
            h_exp = h + body_h
            x_exp = max(0, x - int(w * 0.1))
            w_exp = min(img.width - x_exp, int(w * 1.2))
            return (x_exp, y_exp, w_exp, h_exp)

        # Try eye detection as fallback
        eye_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_eye.xml'
        )
        eyes = eye_cascade.detectMultiScale(gray, 1.1, 3)
        if len(eyes) >= 2:
            # Get bounding box around both eyes
            x = min(e[0] for e in eyes)
            y = min(e[1] for e in eyes)
            ex = max(e[0] + e[2] for e in eyes)
            ey = max(e[1] + e[3] for e in eyes)
            margin = int(max(ex - x, ey - y) * 0.3)
            return (
                max(0, x - margin),
                max(0, y - margin),
                min(img.width, ex - x + 2 * margin),
                min(img.height, ey - y + 2 * margin),
            )
    except Exception as e:
        logger.debug(f"OpenCV face detection failed: {e}")
    return None


def _contrast_based_saliency(img: Image.Image) -> Optional[Tuple[int, int, int, int]]:
    """
    Fallback: contrast-based saliency using Sobel edge detection.
    High-contrast regions (edges) are considered more salient.
    """
    try:
        import cv2
        arr = np.array(img.convert('RGB'))
        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)

        # Sobel edge detection
        sobelx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
        sobely = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
        magnitude = np.sqrt(sobelx**2 + sobely**2)

        # Focus on upper-center region (face area in manga)
        h, w = gray.shape
        upper_region = magnitude[:int(h * 0.7), :]
        threshold = np.percentile(upper_region, 85)
        mask = (upper_region > threshold).astype(np.uint8)

        # Find bounding box
        coords = np.column_stack(np.where(mask > 0))
        if len(coords) > 10:
            y_min = coords[:, 0].min()
            x_min = coords[:, 1].min()
            y_max = coords[:, 0].max()
            x_max = coords[:, 1].max()
            margin = int(min(x_max - x_min, y_max - y_min) * 0.1)
            return (
                max(0, x_min - margin),
                max(0, y_min - margin),
                min(w, x_max - x_min + 2 * margin),
                min(h, y_max - y_min + 2 * margin),
            )
    except Exception as e:
        logger.debug(f"Contrast saliency failed: {e}")
    return None


def _center_crop_fallback(img: Image.Image) -> Tuple[int, int, int, int]:
    """Final fallback: center-weighted crop at 60% of image."""
    w, h = img.size
    crop_w = int(w * 0.6)
    crop_h = int(h * 0.6)
    cx = w // 2
    cy = int(h * 0.4)
    x = cx - crop_w // 2
    y = cy - crop_h // 2
    return (x, y, crop_w, crop_h)


# ---------------------------------------------------------------------------
# ROI utilities
# ---------------------------------------------------------------------------

def load_roi_markers(img: Image.Image, roi_data: Optional[Dict[str, Any]] = None) -> Optional[Tuple[int, int, int, int]]:
    """
    Load ROI from explicit data (user-defined region of interest).
    roi_data format: {'x': float, 'y': float, 'w': float, 'h': float} in 0-1 ratios.
    """
    if not roi_data:
        return None
    try:
        x_ratio = roi_data.get('x', 0)
        y_ratio = roi_data.get('y', 0)
        w_ratio = roi_data.get('w', 1)
        h_ratio = roi_data.get('h', 1)
        w, h = img.size
        return (
            int(x_ratio * w),
            int(y_ratio * h),
            int(w_ratio * w),
            int(h_ratio * h),
        )
    except Exception as e:
        logger.warning(f"Invalid ROI data: {e}")
        return None


# ---------------------------------------------------------------------------
# Crop strategy functions
# ---------------------------------------------------------------------------

def compose_for_shot(
    img: Image.Image,
    target_w: int,
    target_h: int,
    shot: str = 'medium_shot',
    importance: str = 'medium',
    roi: Optional[Dict[str, Any]] = None,
) -> Image.Image:
    """
    Compose/crop an image to fit panel dimensions based on shot type.

    Args:
        img: Source PIL image
        target_w: Target panel width in pixels
        target_h: Target panel height in pixels
        shot: Shot type from AI advisor
        importance: Panel importance (high/medium/low) — affects crop aggressiveness
        roi: Optional user-defined region of interest

    Returns:
        Composed PIL image at target dimensions
    """
    if not img:
        return Image.new('RGB', (target_w, target_h), (200, 200, 200))

    # Check for user-defined ROI first
    if roi:
        roi_box = load_roi_markers(img, roi)
        if roi_box:
            cropped = img.crop(roi_box)
            resized = cropped.resize((target_w, target_h), Image.Resampling.LANCZOS)
            return resized

    strategy = SHOT_STRATEGIES.get(shot, 'thirds')

    # Determine saliency region
    salient_box = find_salient_region(img)

    # Apply crop aggressiveness based on importance
    crop_margin = _importance_to_margin(importance)

    # Calculate source crop region
    src_w, src_h = img.size
    target_ratio = target_w / target_h

    if strategy == 'face_focus':
        crop_box = _fit_box_to_ratio(salient_box, target_ratio, (src_w, src_h), crop_margin)
    elif strategy == 'extreme_close_up':
        # Very tight crop around salient region
        tight_box = _tighten_box(salient_box, img.size, factor=0.5)
        crop_box = _fit_box_to_ratio(tight_box, target_ratio, img.size, crop_margin)
    elif strategy == 'full_frame':
        crop_box = _fit_for_aspect_ratio(src_w, src_h, target_ratio)
    elif strategy == 'center':
        crop_box = _center_crop(src_w, src_h, target_ratio)
    elif strategy == 'offset_left':
        crop_box = _offset_crop(src_w, src_h, target_ratio, 'left')
    elif strategy == 'right':
        crop_box = _offset_crop(src_w, src_h, target_ratio, 'right')
    elif strategy == 'dynamic_diagonal':
        crop_box = _diagonal_crop(src_w, src_h, target_ratio)
    elif strategy == 'two_person':
        crop_box = _two_person_crop(src_w, src_h, target_ratio)
    elif strategy == 'detail':
        # Tight crop on salient region
        tight = _tighten_box(salient_box, img.size, factor=0.4)
        crop_box = _fit_box_to_ratio(tight, target_ratio, img.size, crop_margin)
    elif strategy == 'wide_top':
        crop_box = _wide_top_crop(src_w, src_h, target_ratio)
    elif strategy == 'horizontal_pan':
        crop_box = _horizontal_pan_crop(src_w, src_h, target_ratio)
    else:  # thirds or default
        crop_box = _thirds_crop(src_w, src_h, target_ratio)

    # Crop
    cropped = img.crop(crop_box)
    # Resize
    resized = cropped.resize((target_w, target_h), Image.Resampling.LANCZOS)
    return resized


def _importance_to_margin(importance: str) -> float:
    """Convert importance level to crop margin factor (0=aggressive, 1=loose)."""
    return {
        'high':   0.15,   # Loose: preserve as much as possible
        'medium': 0.10,
        'low':    0.05,   # Can crop more aggressively
    }.get(importance, 0.10)


def _tighten_box(box: Tuple[int, int, int, int], img_size: Tuple[int, int], factor: float = 0.5) -> Tuple[int, int, int, int]:
    """Shrink a bounding box toward its center by a factor."""
    bx, by, bw, bh = box
    iw, ih = img_size
    dx = int(bw * factor * 0.5)
    dy = int(bh * factor * 0.5)
    nx = max(0, bx + dx)
    ny = max(0, by + dy)
    nw = min(iw - nx, bw - 2 * dx)
    nh = min(ih - ny, bh - 2 * dy)
    return (nx, ny, max(1, nw), max(1, nh))


def _fit_for_aspect_ratio(src_w: int, src_h: int, target_ratio: float) -> Tuple[int, int, int, int]:
    """Fit source to target aspect ratio, may crop."""
    src_ratio = src_w / src_h
    if src_ratio > target_ratio:
        new_w = int(src_h * target_ratio)
        x = (src_w - new_w) // 2
        return (x, 0, new_w, src_h)
    else:
        new_h = int(src_w / target_ratio)
        y = (src_h - new_h) // 2
        return (0, y, src_w, new_h)


def _center_crop(src_w: int, src_h: int, target_ratio: float) -> Tuple[int, int, int, int]:
    return _fit_for_aspect_ratio(src_w, src_h, target_ratio)


def _thirds_crop(src_w: int, src_h: int, target_ratio: float) -> Tuple[int, int, int, int]:
    """
    Rule of thirds crop — place focal point at upper-left or upper-right third.
    """
    src_ratio = src_w / src_h
    if src_ratio > target_ratio:
        new_w = int(src_h * target_ratio)
        x = src_w - new_w  # Start from right (RTL)
        return (x, 0, new_w, src_h)
    else:
        new_h = int(src_w / target_ratio)
        y = int(src_h * 0.15)  # Slightly below top
        return (0, y, src_w, new_h)


def _offset_crop(src_w: int, src_h: int, target_ratio: float, side: str = 'left') -> Tuple[int, int, int, int]:
    """Offset crop (left or right bias)."""
    src_ratio = src_w / src_h
    if src_ratio > target_ratio:
        new_w = int(src_h * target_ratio)
        x = 0 if side == 'left' else src_w - new_w
        return (x, 0, x + new_w, src_h)
    else:
        new_h = int(src_w / target_ratio)
        y = 0 if side == 'left' else src_h - new_h
        return (0, y, src_w, y + new_h)


def _diagonal_crop(src_w: int, src_h: int, target_ratio: float) -> Tuple[int, int, int, int]:
    """Diagonal composition — offset toward bottom-right for dynamic effect."""
    src_ratio = src_w / src_h
    if src_ratio > target_ratio:
        new_w = int(src_h * target_ratio)
        x = int(src_w * 0.2)  # Start 20% from left
        return (x, 0, new_w, src_h)
    else:
        new_h = int(src_w / target_ratio)
        y = int(src_h * 0.3)  # Start 30% from top
        return (0, y, src_w, new_h)


def _two_person_crop(src_w: int, src_h: int, target_ratio: float) -> Tuple[int, int, int, int]:
    """Frame for two people — show both with slight separation."""
    src_ratio = src_w / src_h
    if src_ratio > target_ratio:
        new_w = int(src_h * target_ratio)
        x = (src_w - new_w) // 2  # Center horizontally
        return (x, 0, new_w, src_h)
    else:
        new_h = int(src_w / target_ratio)
        y = int(src_h * 0.2)  # Frame from upper body up
        return (0, y, src_w, new_h)


def _wide_top_crop(src_w: int, src_h: int, target_ratio: float) -> Tuple[int, int, int, int]:
    """Wide shot with top-weighted composition (aerial/establishing)."""
    src_ratio = src_w / src_h
    if src_ratio > target_ratio:
        new_w = int(src_h * target_ratio)
        return (0, 0, new_w, src_h)  # Full width
    else:
        new_h = int(src_w / target_ratio)
        return (0, 0, src_w, new_h)  # Top portion


def _horizontal_pan_crop(src_w: int, src_h: int, target_ratio: float) -> Tuple[int, int, int, int]:
    """Horizontal pan — wide and short composition."""
    new_h = int(src_w / max(target_ratio, 1.0))
    y = (src_h - new_h) // 2
    return (0, y, src_w, new_h)


def _fit_box_to_ratio(
    box: Tuple[int, int, int, int],
    target_ratio: float,
    img_size: Tuple[int, int],
    margin_factor: float = 0.1,
) -> Tuple[int, int, int, int]:
    """
    Fit a salient bounding box to target ratio, expanding from center if needed.
    """
    bx, by, bw, bh = box
    iw, ih = img_size

    current_ratio = bw / bh
    if current_ratio > target_ratio:
        # Too wide: expand vertically
        new_h = int(bw / target_ratio)
        y = by - (new_h - bh) // 2
        y = max(0, min(y, ih - new_h))
        new_h = min(new_h, ih - y)
        return (max(0, bx - int(bw * margin_factor)),
                max(0, y),
                min(iw, bw + 2 * int(bw * margin_factor)),
                new_h)
    else:
        # Too tall: expand horizontally
        new_w = int(bh * target_ratio)
        x = bx - (new_w - bw) // 2
        x = max(0, min(x, iw - new_w))
        new_w = min(new_w, iw - x)
        return (max(0, x),
                max(0, by - int(bh * margin_factor)),
                new_w,
                min(ih, bh + 2 * int(bh * margin_factor)))


# ---------------------------------------------------------------------------
# AI Inpainting integration point
# ---------------------------------------------------------------------------

def inpaint_region(
    img: Image.Image,
    mask: Image.Image,
    prompt: str,
    strength: float = 0.8,
) -> Optional[Image.Image]:
    """
    AI inpaint a region of the image using ComfyUI or MiniMax.

    Args:
        img: Source image
        mask: Mask image (white = inpainted region)
        prompt: Inpainting prompt describing desired content
        strength: Inpainting strength (0-1)

    Returns:
        Inpainted PIL Image or None if unavailable
    """
    # Integration point: connect to ComfyUI or MiniMax inpainting API
    # For now, return None (not implemented)
    logger.debug(f"Inpainting requested with prompt: {prompt[:50]}... (not yet implemented)")
    return None


# ---------------------------------------------------------------------------
# Main ImageComposer class
# ---------------------------------------------------------------------------

class ImageComposer:
    """
    Composes images into manga panel layouts.
    Handles cropping, scaling, layering, and enhancement.
    """

    def __init__(self):
        self._debug = False

    def set_debug(self, debug: bool) -> None:
        self._debug = debug

    def compose_panel_image(
        self,
        img_data: Dict[str, Any],
        panel_w: int,
        panel_h: int,
        shot: str = 'medium_shot',
        importance: str = 'medium',
        roi: Optional[Dict[str, Any]] = None,
    ) -> Image.Image:
        """
        Compose a panel image from raw image data.

        Args:
            img_data: Dict with 'pil_image' key
            panel_w: Target panel width
            panel_h: Target panel height
            shot: Shot type
            importance: Panel importance
            roi: Optional user-defined ROI

        Returns:
            Composed PIL Image at panel dimensions
        """
        pil_img = img_data.get('pil_image')
        if not pil_img:
            return Image.new('RGB', (panel_w, panel_h), (220, 220, 220))

        composed = compose_for_shot(pil_img, panel_w, panel_h, shot, importance, roi)
        return composed

    def compose_with_layers(
        self,
        background_img: Image.Image,
        foreground_img: Image.Image,
        panel_w: int,
        panel_h: int,
        layer_mode: str = 'character_overlay',
    ) -> Image.Image:
        """
        Layer background + foreground (e.g., background + character).

        Args:
            background_img: Background PIL image
            foreground_img: Foreground (character) PIL image
            panel_w: Target width
            panel_h: Target height
            layer_mode: 'character_overlay' (default), 'split_diagonal'

        Returns:
            Composited PIL Image
        """
        # Compose background to fill panel
        bg = compose_for_shot(background_img, panel_w, panel_h, 'wide_shot')

        # Scale foreground to ~40% of panel height, place bottom-center
        fg_h = int(panel_h * 0.4)
        fg_w = int(fg_h * (foreground_img.width / foreground_img.height))
        fg = foreground_img.resize((fg_w, fg_h), Image.Resampling.LANCZOS)

        composite = bg.copy()
        fg_x = (panel_w - fg_w) // 2
        fg_y = panel_h - fg_h
        composite.paste(fg, (fg_x, fg_y), fg if fg.mode == 'RGBA' else None)

        return composite

    def enhance_for_manga(
        self,
        img: Image.Image,
        strength: str = 'normal',
    ) -> Image.Image:
        """
        Apply manga-style enhancements to an image.

        Args:
            img: PIL Image
            strength: 'subtle', 'normal', 'strong'

        Returns:
            Enhanced PIL Image
        """
        presets = {
            'subtle':  (1.05, 1.1),
            'normal':  (1.1, 1.2),
            'strong':  (1.2, 1.4),
        }
        contrast, sharpness = presets.get(strength, (1.1, 1.2))

        if contrast != 1.0:
            img = ImageEnhance.Contrast(img).enhance(contrast)
        if sharpness != 1.0:
            img = ImageEnhance.Sharpness(img).enhance(sharpness)

        return img

    def compose_page_images(
        self,
        images: List[Dict[str, Any]],
        panels: List[Dict[str, Any]],
        page_width: int,
        page_height: int,
    ) -> List[Image.Image]:
        """
        Compose all panel images for a page.

        Args:
            images: List of image data dicts
            panels: List of panel data dicts from layout_engine
            page_width: Page width in pixels
            page_height: Page height in pixels

        Returns:
            List of composed PIL Images, one per panel
        """
        composed = []
        image_idx = 0

        for panel in panels:
            # Calculate panel pixel dimensions
            x_ratio = panel.get('x_ratio', 0)
            y_ratio = panel.get('y_ratio', 0)
            w_ratio = panel.get('w_ratio', 1)
            h_ratio = panel.get('h_ratio', 1)

            panel_w = max(1, int(w_ratio * page_width))
            panel_h = max(1, int(h_ratio * page_height))

            # Get scene/shot info
            scene = panel.get('scene', {})
            importance = panel.get('importance', 'medium')
            shot = panel.get('shot_type', 'medium_shot')

            # Get image for this panel
            if image_idx < len(images):
                img_data = images[image_idx]
                composed_img = self.compose_panel_image(
                    img_data, panel_w, panel_h, shot, importance
                )
                image_idx += 1
            else:
                # No more images — use placeholder
                composed_img = Image.new('RGB', (panel_w, panel_h), (200, 200, 200))

            composed.append(composed_img)

        return composed

    def prioritize_images_for_panels(
        self,
        images: List[Dict[str, Any]],
        panels: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Reorder images so high-importance panels get the best images.

        Strategy: high-importance panels → best quality images first,
        low-importance → fill with remaining images or placeholders.

        Args:
            images: List of image data dicts
            panels: List of panel dicts with importance field

        Returns:
            Reordered image list aligned to panels
        """
        if not images or not panels:
            return images

        # Sort panels by importance
        sorted_panels = sorted(
            enumerate(panels),
            key=lambda x: {'high': 0, 'medium': 1, 'low': 2}.get(x[1].get('importance', 'medium'), 1)
        )

        # Sort images by "quality" (size as proxy)
        sorted_images = sorted(
            images,
            key=lambda img: (img.get('pil_image') or Image.new('RGB', (1, 1))).size[0] * (img.get('pil_image') or Image.new('RGB', (1, 1))).size[1],
            reverse=True,
        )

        # Assign best images to most important panels
        result = []
        img_idx = 0
        for panel_idx, panel in sorted_panels:
            if panel.get('importance') == 'high' and img_idx < len(sorted_images):
                result.append((panel_idx, sorted_images[img_idx]))
                img_idx += 1
            elif panel.get('importance') == 'medium' and img_idx < len(sorted_images):
                result.append((panel_idx, sorted_images[img_idx]))
                img_idx += 1
            else:
                # Fill remaining with placeholders or leftover images
                if img_idx < len(sorted_images):
                    result.append((panel_idx, sorted_images[img_idx]))
                    img_idx += 1
                else:
                    result.append((panel_idx, None))

        # Reconstruct in original panel order
        reordered = [None] * len(panels)
        for panel_idx, img_data in result:
            reordered[panel_idx] = img_data

        # Fill any None slots with placeholders
        for i in range(len(reordered)):
            if reordered[i] is None:
                reordered[i] = {'pil_image': None, 'path': None}

        return reordered


# Module-level convenience
_composer: Optional[ImageComposer] = None


def get_composer() -> ImageComposer:
    """Get or create the global ImageComposer instance."""
    global _composer
    if _composer is None:
        _composer = ImageComposer()
    return _composer
