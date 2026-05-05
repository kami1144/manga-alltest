"""
Image processor for loading and processing manga images.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image

logger = logging.getLogger(__name__)

# Supported image formats
SUPPORTED_FORMATS = {'.jpg', '.jpeg', '.png', '.webp', '.heif', '.heic'}


def load_images_from_folder(folder_path: str) -> List[Dict[str, Any]]:
    """
    Load all images from a folder.

    Args:
        folder_path: Path to folder containing images

    Returns:
        List of image data dicts

    Raises:
        FileNotFoundError: If folder doesn't exist
        ValueError: If no images found
    """
    folder = Path(folder_path)
    if not folder.exists():
        raise FileNotFoundError(f"Images folder not found: {folder_path}")

    images: List[Dict[str, Any]] = []
    for file_path in sorted(folder.iterdir()):
        if file_path.suffix.lower() in SUPPORTED_FORMATS:
            with Image.open(file_path) as img:
                try:
                    img.load()  # Force load to check for corruption
                    images.append({
                        'path': str(file_path),
                        'filename': file_path.name,
                        'pil_image': img.copy(),  # Copy to avoid keeping file handle
                        'width': img.width,
                        'height': img.height,
                        'format': img.format,
                        'mode': img.mode,
                    })
                except Exception as e:
                    logger.warning(f"Failed to load image {file_path}: {e}")

    if not images:
        raise ValueError(f"No valid images found in {folder_path}")

    logger.info(f"Loaded {len(images)} images from {folder_path}")
    return images


def load_image(file_path: str) -> Dict[str, Any]:
    """
    Load a single image.

    Args:
        file_path: Path to image file

    Returns:
        Image data dict
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {file_path}")

    img = Image.open(path)
    img.load()

    return {
        'path': str(path),
        'filename': path.name,
        'pil_image': img,
        'width': img.width,
        'height': img.height,
        'format': img.format,
        'mode': img.mode,
    }


def process_image(
    img_data: Dict[str, Any],
    target_width: int,
    target_height: int,
    crop_mode: str = 'fit'
) -> Image.Image:
    """
    Process an image to target dimensions.

    Args:
        img_data: Image data from load_image
        target_width: Target width in pixels
        target_height: Target height in pixels
        crop_mode: 'fit' (letterbox/pillarbox) or 'fill' (crop to fill)

    Returns:
        Processed PIL Image
    """
    img = img_data['pil_image']

    if crop_mode == 'fill':
        # Crop to fill
        img_thumb = _crop_to_fill(img, target_width, target_height)
    else:
        # Fit with letterbox/pillarbox
        img_thumb = _fit_to_box(img, target_width, target_height)

    return img_thumb


def _fit_to_box(img: Image.Image, target_width: int, target_height: int) -> Image.Image:
    """Fit image to box with letterbox/pillarbox."""
    img_copy = img.copy()
    img_copy.thumbnail((target_width, target_height), Image.Resampling.LANCZOS)
    return img_copy


def _crop_to_fill(img: Image.Image, target_width: int, target_height: int) -> Image.Image:
    """Crop image to fill target dimensions."""
    img_ratio = img.width / img.height
    target_ratio = target_width / target_height

    if img_ratio > target_ratio:
        # Image is wider, crop sides
        new_width = int(img.height * target_ratio)
        left = (img.width - new_width) // 2
        img = img.crop((left, 0, left + new_width, img.height))
    else:
        # Image is taller, crop top/bottom
        new_height = int(img.width / target_ratio)
        top = (img.height - new_height) // 2
        img = img.crop((0, top, img.width, top + new_height))

    img = img.resize((target_width, target_height), Image.Resampling.LANCZOS)
    return img


def get_saliency_region(
    img: Image.Image,
    region: Optional[Tuple[int, int, int, int]] = None
) -> Tuple[int, int, int, int]:
    """
    Get saliency region for an image.
    Uses center crop as fallback.
    (Face detection would be used if OpenCV available)

    Args:
        img: PIL Image
        region: Optional pre-computed region (x, y, w, h)

    Returns:
        Saliency region as (x, y, w, h)
    """
    if region:
        return region

    # Fallback: center region (60% of image)
    w, h = img.size
    crop_w = int(w * 0.6)
    crop_h = int(h * 0.6)
    x = (w - crop_w) // 2
    y = (h - crop_h) // 2

    return (x, y, crop_w, crop_h)


def crop_to_panel(
    img: Image.Image,
    panel_x: int,
    panel_y: int,
    panel_width: int,
    panel_height: int,
    crop_mode: str = 'fill'
) -> Image.Image:
    """
    Crop an image to fit a panel.

    Args:
        img: Source image
        panel_x: Panel x position
        panel_y: Panel y position
        panel_width: Panel width
        panel_height: Panel height
        crop_mode: 'fit' or 'fill'

    Returns:
        Cropped image
    """
    if crop_mode == 'fill':
        return _crop_to_fill(img, panel_width, panel_height)
    else:
        return _fit_to_box(img, panel_width, panel_height)


def validate_image_count(
    images: List[Dict[str, Any]],
    scene_count: int
) -> bool:
    """
    Validate that there are enough images for scenes.

    Args:
        images: List of loaded images
        scene_count: Number of scenes

    Returns:
        True if valid

    Raises:
        ValueError: If not enough images
    """
    if len(images) < scene_count:
        raise ValueError(
            f"Not enough images ({len(images)}) for scenes ({scene_count})"
        )
    return True


def get_image_info(images: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Get summary info about loaded images."""
    if not images:
        return {'count': 0, 'total_width': 0, 'total_height': 0}

    return {
        'count': len(images),
        'total_width': sum(img.get('width', 0) for img in images),
        'total_height': sum(img.get('height', 0) for img in images),
        'formats': list(set(img.get('format') for img in images)),
    }