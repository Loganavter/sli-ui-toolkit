"""Pure edge hit-testing math for frameless resize.

No Qt event handling, no widget state — everything here is a function of
plain numbers. ``RESIZE_MARGIN``/``QWIDGETSIZE_MAX`` are the package's
default constants; the live, possibly-host-overridden margin used by
``_ResizeFilter`` at runtime is read off the ``frameless`` package
namespace itself (see ``resize_filter.py``), not off this module.
"""

from __future__ import annotations

from PySide6.QtCore import Qt


RESIZE_MARGIN = 4
# Qt unbound max when maximumWidth/Height were never set.
QWIDGETSIZE_MAX = 16777215


def resolve_csd_band(window) -> int:
    """Effective CSD outer-band inset for ``window``.

    The frameless surface carries a transparent outer band (resize-grab
    margin) beyond the visible body. Maximized/fullscreen windows cannot be
    edge-resized, so the band (and everything inset by it — the painted
    body, the root-layout content) must collapse to 0 there; otherwise an
    invisible strip remains around the window that window-capture tools
    include (painted with the window background once the body fills the
    surface).
    """
    try:
        if window.isMaximized() or window.isFullScreen():
            return 0
    except Exception:
        pass
    try:
        return int(window.property("_csd_outer_band") or 0)
    except Exception:
        return 0


_LEFT = int(Qt.Edge.LeftEdge.value)
_RIGHT = int(Qt.Edge.RightEdge.value)
_TOP = int(Qt.Edge.TopEdge.value)
_BOTTOM = int(Qt.Edge.BottomEdge.value)


def _edges_for_pos(
    rect_w: int, rect_h: int, x: int, y: int, margin: int = RESIZE_MARGIN
) -> int:
    m = margin
    value = 0
    if x <= m:
        value |= _LEFT
    elif x >= rect_w - m:
        value |= _RIGHT
    if y <= m:
        value |= _TOP
    elif y >= rect_h - m:
        value |= _BOTTOM
    return value


def _cursor_for_edges(value: int) -> Qt.CursorShape:
    left = bool(value & _LEFT)
    right = bool(value & _RIGHT)
    top = bool(value & _TOP)
    bottom = bool(value & _BOTTOM)
    if (top and left) or (bottom and right):
        return Qt.CursorShape.SizeFDiagCursor
    if (top and right) or (bottom and left):
        return Qt.CursorShape.SizeBDiagCursor
    if left or right:
        return Qt.CursorShape.SizeHorCursor
    return Qt.CursorShape.SizeVerCursor
