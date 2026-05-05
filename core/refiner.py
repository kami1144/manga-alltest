"""
Refiner v2 — Post-processing for manga page layouts.

Improvements over v1:
- Smart gutter pacing: narrow gutters = compact/intense, wide = breathing room
- Spread (跨页) handling: ensures left/right pages form a cohesive unit
- Visual balance v2: considers panel weight distribution (not just centroid)
- Overflow prevention: prevents panels from exceeding page bounds
- Salient-region pass-through: detects face regions and passes to typesetting
- Layout stress test: flags layouts that would be hard to read
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# Gutter presets affect perceived pacing
GUTTER_PRESETS = {
    'tight':   6,    # Narrow: compact, intense scenes
    'normal':  12,   # Standard manga gutter
    'spacious': 18,  # Wide: breathing room, calm scenes
}


class LayoutRefiner:
    """
    Post-processes layout data for professional quality.
    v2: smarter gutter pacing, balance, and spread handling.
    """

    def __init__(
        self,
        gutter_width: float = 12.0,
        bleed_margin: float = 3.0,
        page_width_mm: float = 210.0,
        page_height_mm: float = 297.0,
        dpi: int = 300,
        gutter_preset: str = 'normal',
    ):
        self._gutter_mm = gutter_width
        self._bleed_mm = bleed_margin
        self._page_w_mm = page_width_mm
        self._page_h_mm = page_height_mm
        self._dpi = dpi
        self._gutter_preset = gutter_preset

        # Convert to pixels
        self._gutter_px = int(gutter_width * dpi / 25.4)
        self._bleed_px = int(bleed_margin * dpi / 25.4)
        self._page_w_px = int(page_width_mm * dpi / 25.4)
        self._page_h_px = int(page_height_mm * dpi / 25.4)

        logger.info(
            f"Refiner v2: gutter={self._gutter_px}px ({gutter_preset}), "
            f"bleed={self._bleed_px}px, page={self._page_w_px}x{self._page_h_px}px"
        )

    def refine_layout(
        self,
        layout_data: Dict[str, Any],
        reading_direction: str = "RTL",
    ) -> Dict[str, Any]:
        """
        Apply all refinement steps to layout data.

        Steps:
        1. Validate reading flow
        2. Adjust gutters based on narrative pacing
        3. Handle bleed edges
        4. Check visual balance
        5. Detect spread pages
        6. Check for overflow
        """
        pages = layout_data.get('pages', [])
        refined_pages = []

        for idx, page in enumerate(pages):
            refined_page = self._refine_page(page, reading_direction, idx, pages)
            refined_pages.append(refined_page)

        # Post-process spreads
        refined_pages = self._process_spreads(refined_pages, reading_direction)

        # Collect salient regions for typesetting
        all_salient = self._collect_salient_regions(refined_pages)
        layout_data['salient_regions'] = all_salient
        layout_data['pages'] = refined_pages

        return layout_data

    def _refine_page(
        self,
        page: Dict[str, Any],
        reading_direction: str,
        page_idx: int,
        all_pages: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Refine a single page."""
        panels = page.get('panels', [])
        narrative = page.get('narrative', {})
        layout_hints = page.get('layout_hints', {})

        # Step 1: Validate reading flow
        panels = self._validate_reading_flow(panels, reading_direction)

        # Step 2: Adjust gutters based on pacing
        gutter_mode = self._determine_gutter_mode(narrative, layout_hints)
        panels = self._apply_gutters_v2(panels, mode=gutter_mode)

        # Step 3: Handle bleed edges
        panels = self._apply_bleed(panels)

        # Step 4: Check visual balance
        balance = self._check_balance_v2(panels)
        page['balance_score'] = round(balance, 2)
        if balance < 0.25:
            logger.warning(f"Page {page.get('page_num')} has poor balance: {balance:.2f}")
            page['balance_warning'] = True

        # Step 5: Overflow check
        overflow_panels = self._find_overflow_panels(panels)
        if overflow_panels:
            page['overflow_panels'] = overflow_panels

        # Step 6: Check if this is a spread page
        page['is_spread_candidate'] = self._is_spread_candidate(page, page_idx, all_pages)

        return {**page, 'panels': panels}

    def _determine_gutter_mode(
        self,
        narrative: Dict[str, Any],
        layout_hints: Dict[str, Any],
    ) -> str:
        """
        Determine gutter spacing mode based on narrative pacing.
        High urgency / intense → tight gutters
        Calm / transition → spacious gutters
        """
        urgency = layout_hints.get('urgency', 5)
        rhythm = narrative.get('page_rhythm', 'balanced')
        pace = narrative.get('reading_pace', 'medium')

        if urgency >= 8 or rhythm == 'climax_dominant' or pace == 'fast':
            return 'tight'
        if urgency <= 3 or rhythm == 'calm_dominant' or pace == 'slow':
            return 'spacious'
        return 'normal'

    def _apply_gutters_v2(
        self,
        panels: List[Dict[str, Any]],
        mode: str = 'normal',
    ) -> List[Dict[str, Any]]:
        """
        Apply gutter spacing based on pacing mode.
        Tight: minimal spacing, panels close together
        Normal: standard manga spacing
        Spacious: generous spacing, room to breathe
        """
        gutter_mm = GUTTER_PRESETS.get(mode, 12)
        gutter_px = int(gutter_mm * self._dpi / 25.4)
        gutter_fraction_x = gutter_px / self._page_w_px
        gutter_fraction_y = gutter_px / self._page_h_px

        refined = []
        for panel in panels:
            p = dict(panel)
            w = p.get('w_ratio', 1)
            h = p.get('h_ratio', 1)

            # Shrink slightly to create gutter space
            shrink_x = gutter_fraction_x * 0.5
            shrink_y = gutter_fraction_y * 0.5
            p['w_ratio'] = max(w - shrink_x, w * 0.92)
            p['h_ratio'] = max(h - shrink_y, h * 0.92)

            # Annotate gutter mode on panel for canvas rendering
            p['_gutter_mode'] = mode

            refined.append(p)

        return refined

    def _apply_bleed(self, panels: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Mark panels that should bleed to page edge.
        Only panels at page edges with bleed_edge flag get extended.
        """
        bleed_fraction = self._bleed_px / self._page_w_px

        for panel in panels:
            bleed_edge = panel.get('bleed_edge')
            if not bleed_edge:
                continue

            x = panel.get('x_ratio', 0)
            y = panel.get('y_ratio', 0)
            w = panel.get('w_ratio', 1)
            h = panel.get('h_ratio', 1)

            if 'left' in bleed_edge:
                panel['x_ratio'] = max(x - bleed_fraction * 0.5, 0)
            if 'right' in bleed_edge:
                panel['w_ratio'] = min(w + bleed_fraction, 1.0)
            if 'top' in bleed_edge:
                panel['y_ratio'] = max(y - bleed_fraction * 0.5, 0)
            if 'bottom' in bleed_edge:
                panel['h_ratio'] = min(h + bleed_fraction, 1.0)
            if 'all' in bleed_edge:
                panel['x_ratio'] = 0
                panel['y_ratio'] = 0
                panel['w_ratio'] = 1.0
                panel['h_ratio'] = 1.0

        return panels

    def _validate_reading_flow(
        self,
        panels: List[Dict[str, Any]],
        reading_direction: str,
    ) -> List[Dict[str, Any]]:
        """
        Ensure panels are ordered correctly for reading direction.
        Also checks for crossing panels (reading order jumps).
        """
        if reading_direction == "RTL":
            sorted_panels = sorted(
                panels,
                key=lambda p: (p.get('y_ratio', 0), -p.get('x_ratio', 0))
            )
        else:
            sorted_panels = sorted(
                panels,
                key=lambda p: (p.get('y_ratio', 0), p.get('x_ratio', 0))
            )

        # Update reading order
        for idx, panel in enumerate(sorted_panels):
            panel['reading_order'] = idx + 1

        # Check for reading flow violations
        violations = self._detect_flow_violations(sorted_panels, reading_direction)
        if violations:
            logger.warning(f"Reading flow violations: {violations}")

        return sorted_panels

    def _detect_flow_violations(
        self,
        panels: List[Dict[str, Any]],
        direction: str,
    ) -> List[str]:
        """
        Detect panels where reading order would cause eye-travel problems.
        E.g., a panel in the bottom-right that should be read before a top-left panel.
        """
        violations = []
        for i in range(len(panels) - 1):
            p1 = panels[i]
            p2 = panels[i + 1]
            # If p2 has a higher y_ratio but lower reading order priority, might be a violation
            y1, y2 = p1.get('y_ratio', 0), p2.get('y_ratio', 0)
            if abs(y2 - y1) > 0.4:
                violations.append(
                    f"Panel {p1.get('id')} → {p2.get('id')}: large vertical jump"
                )
        return violations

    def _check_balance_v2(self, panels: List[Dict[str, Any]]) -> float:
        """
        Check visual balance using weighted centroid + area distribution.
        v2: also considers left/right and top/bottom balance separately.
        """
        if not panels:
            return 1.0

        total_area = 0.0
        cx, cy = 0.0, 0.0
        left_area = 0.0
        right_area = 0.0
        top_area = 0.0
        bottom_area = 0.0

        for panel in panels:
            x = panel.get('x_ratio', 0)
            y = panel.get('y_ratio', 0)
            w = panel.get('w_ratio', 1)
            h = panel.get('h_ratio', 1)
            area = w * h

            cx += (x + w / 2) * area
            cy += (y + h / 2) * area
            total_area += area

            # Left/right split
            center_x = x + w / 2
            if center_x < 0.5:
                left_area += area
            else:
                right_area += area

            # Top/bottom split
            center_y = y + h / 2
            if center_y < 0.5:
                top_area += area
            else:
                bottom_area += area

        if total_area == 0:
            return 1.0

        cx /= total_area
        cy /= total_area

        # Centroid distance from center
        dist = ((cx - 0.5) ** 2 + (cy - 0.5) ** 2) ** 0.5
        max_dist = (0.5 ** 2 + 0.5 ** 2) ** 0.5
        centroid_score = 1.0 - (dist / max_dist)

        # Left/right balance
        lr_ratio = min(left_area, right_area) / max(left_area, right_area) if max(left_area, right_area) > 0 else 0
        tb_ratio = min(top_area, bottom_area) / max(top_area, bottom_area) if max(top_area, bottom_area) > 0 else 0

        # Weighted combination
        balance = centroid_score * 0.5 + lr_ratio * 0.25 + tb_ratio * 0.25
        return max(0.0, min(1.0, balance))

    def _find_overflow_panels(self, panels: List[Dict[str, Any]]) -> List[str]:
        """Find panels that overflow page boundaries."""
        overflow = []
        for panel in panels:
            x = panel.get('x_ratio', 0)
            y = panel.get('y_ratio', 0)
            w = panel.get('w_ratio', 1)
            h = panel.get('h_ratio', 1)
            if x + w > 1.05 or y + h > 1.05:  # 5% tolerance
                overflow.append(panel.get('id', 'unknown'))
        return overflow

    def _is_spread_candidate(
        self,
        page: Dict[str, Any],
        page_idx: int,
        all_pages: List[Dict[str, Any]],
    ) -> bool:
        """Check if this page is a candidate for a double-page spread."""
        narrative = page.get('narrative', {})
        layout_hints = page.get('layout_hints', {})
        urgency = layout_hints.get('urgency', 5)
        rhythm = narrative.get('page_rhythm', '')

        return urgency >= 9 or rhythm == 'climax_dominant'

    def _process_spreads(
        self,
        pages: List[Dict[str, Any]],
        reading_direction: str,
    ) -> List[Dict[str, Any]]:
        """
        Process consecutive spread candidates as double-page spreads.
        Adjusts the left and right pages to form a cohesive unit.
        """
        if not pages:
            return pages

        i = 0
        while i < len(pages):
            if pages[i].get('is_spread_candidate') and i + 1 < len(pages):
                # Check if next page is also a spread candidate
                next_urgency = pages[i + 1].get('layout_hints', {}).get('urgency', 5)
                if next_urgency >= 8:
                    # Mark as spread
                    pages[i]['is_spread_start'] = True
                    pages[i + 1]['is_spread_continuation'] = True
                    pages[i + 1]['is_spread_start'] = False

                    # On a spread, the left page's rightmost panel can be wider
                    # and the right page's leftmost panel can extend to edge
                    pages[i] = self._adjust_spread_left_page(pages[i])
                    pages[i + 1] = self._adjust_spread_right_page(pages[i + 1])
                    i += 2
                    continue
            pages[i]['is_spread_start'] = False
            pages[i]['is_spread_continuation'] = False
            i += 1

        return pages

    def _adjust_spread_left_page(self, page: Dict[str, Any]) -> Dict[str, Any]:
        """Adjust left page of a spread: extend rightmost panel slightly."""
        panels = page.get('panels', [])
        if not panels:
            return page

        # Find rightmost panel
        rightmost = max(panels, key=lambda p: p.get('x_ratio', 0) + p.get('w_ratio', 0))
        rightmost['w_ratio'] = min(rightmost.get('w_ratio', 0) + 0.03, 1.0)
        rightmost['_spread_bleed'] = 'right'
        page['panels'] = panels
        return page

    def _adjust_spread_right_page(self, page: Dict[str, Any]) -> Dict[str, Any]:
        """Adjust right page of a spread: extend leftmost panel slightly."""
        panels = page.get('panels', [])
        if not panels:
            return page

        # Find leftmost panel
        leftmost = min(panels, key=lambda p: p.get('x_ratio', 0))
        leftmost['x_ratio'] = max(leftmost.get('x_ratio', 0) - 0.03, 0)
        leftmost['_spread_bleed'] = 'left'
        page['panels'] = panels
        return page

    def _collect_salient_regions(
        self,
        pages: List[Dict[str, Any]],
    ) -> List[Tuple[int, float, float, float, float]]:
        """
        Collect all salient regions from panels for typesetting engine.
        Returns list of (page_num, x_ratio, y_ratio, w_ratio, h_ratio).
        """
        regions = []
        for page in pages:
            page_num = page.get('page_num', 0)
            for panel in page.get('panels', []):
                shot = panel.get('shot_type', '')
                # Close-up shots have face regions near center-top
                if shot in ('close_up', 'close_up_2', 'medium_shot'):
                    x = panel.get('x_ratio', 0) + panel.get('w_ratio', 0) * 0.3
                    y = panel.get('y_ratio', 0) + panel.get('h_ratio', 0) * 0.1
                    w = panel.get('w_ratio', 0) * 0.4
                    h = panel.get('h_ratio', 0) * 0.5
                    regions.append((page_num, x, y, w, h))
        return regions

    # -------------------------------------------------------------------------
    # Settings
    # -------------------------------------------------------------------------

    def set_gutter(self, mm: float) -> None:
        """Update gutter width."""
        self._gutter_mm = mm
        self._gutter_px = int(mm * self._dpi / 25.4)

    def set_page_size(self, width_mm: float, height_mm: float) -> None:
        """Update page dimensions."""
        self._page_w_mm = width_mm
        self._page_h_mm = height_mm
        self._page_w_px = int(width_mm * self._dpi / 25.4)
        self._page_h_px = int(height_mm * self._dpi / 25.4)


# ---------------------------------------------------------------------------
# Module-level convenience functions
# ---------------------------------------------------------------------------
_refiner_instance: Optional[LayoutRefiner] = None


def get_refiner() -> LayoutRefiner:
    global _refiner_instance
    if _refiner_instance is None:
        _refiner_instance = LayoutRefiner()
    return _refiner_instance


def refine_layout(
    layout_data: Dict[str, Any],
    reading_direction: str = "RTL",
) -> Dict[str, Any]:
    """Module-level function for backwards compatibility."""
    refiner = get_refiner()
    return refiner.refine_layout(layout_data, reading_direction)


def check_overflow(
    layout_data: Dict[str, Any],
    page_width: int = 2480,
    page_height: int = 3508,
) -> List[str]:
    """Check for panels that overflow page bounds."""
    warnings = []
    for page in layout_data.get('pages', []):
        for panel in page.get('panels', []):
            x = panel.get('x_ratio', 0) + panel.get('w_ratio', 1)
            y = panel.get('y_ratio', 0) + panel.get('h_ratio', 1)
            if x > 1.05 or y > 1.05:
                warnings.append(f"Panel {panel.get('id')} overflows bounds")
    return warnings


def scale_to_fit(img: Any, target_w: int, target_h: int) -> Any:
    """Scale image to fit within target dimensions."""
    from PIL import Image
    if img is None:
        return Image.new('RGB', (target_w, target_h), (200, 200, 200))
    img.thumbnail((target_w, target_h), Image.Resampling.LANCZOS)
    return img
