"""Shared sizing / chrome constants for TopTabBar + TopTabHost."""

from __future__ import annotations

TAB_H_PAD = 14
TAB_MIN_WIDTH = 80
# Gap between tab buttons. Must clear the selected folder outline (1px stroke
# + AA) so neighbouring labels are not crowded by the selection frame.
TAB_SPACING = 8
TAB_BAR_H_MARGIN = 6
INDICATOR_H = 2
DEFAULT_TAB_RADIUS = 10
DEFAULT_PANE_RADIUS = 10
PANE_BORDER_WIDTH = 1.0
# Keep square page content inside the rounded fill without QWidget masks.
PANE_CONTENT_INSET = 2


def content_inset_for_radii(pane_radii: tuple[int, int, int, int]) -> int:
    return max(PANE_CONTENT_INSET, max(pane_radii))
