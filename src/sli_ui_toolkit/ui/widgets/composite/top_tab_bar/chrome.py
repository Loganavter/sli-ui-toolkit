"""Pane chrome painting for TopTabHost.

No ``QWidget.setMask`` and no translucent page stack: those leave unpainted
corner pixels that pick up neighbouring framebuffer garbage (preview, etc.)
when switching tabs under CSD/composited windows.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.buttons.layers.background import rounded_rect_path
from sli_ui_toolkit.ui.widgets.composite.top_tab_bar.constants import PANE_BORDER_WIDTH


def clear_stack_content_clip(stack: QWidget) -> None:
    """Ensure no residual mask from older builds."""
    stack.clearMask()


def selected_tab_cover_rect(
    *,
    host: QWidget,
    pane: QWidget,
    tab_bar,
    current_index: int,
    content_inset: int,
) -> QRect | None:
    """Map selected tab button into pane coords via the common host ancestor.

    ``QWidget.mapTo(target)`` requires ``target`` to be an *ancestor*; the tab
    button and pane are siblings under the host, so we map through ``host``.
    """
    if current_index < 0 or current_index >= tab_bar.count():
        return None
    button = tab_bar._tabs[current_index].button
    if button.window() is not pane.window():
        return None
    top_left = pane.mapFrom(host, button.mapTo(host, button.rect().topLeft()))
    return QRect(
        top_left.x() + 1,
        0,
        max(0, button.width() - 2),
        max(2, content_inset),
    )


def _surface_color(tm: ThemeManager) -> QColor:
    for key in ("dialog.background", "Window", "window"):
        color = tm.try_get_color(key)
        if color is not None and color.isValid():
            return QColor(color)
    return QColor(240, 240, 240)


def _pane_fill_color(tm: ThemeManager) -> QColor | None:
    color = tm.try_get_color("dialog.input.background")
    if color is not None and color.isValid():
        return QColor(color)
    window = tm.try_get_color("Window")
    return QColor(window) if window is not None else None


def paint_pane_chrome(
    pane: QWidget,
    *,
    pane_radii: tuple[int, int, int, int],
    selected_cover: QRect | None,
) -> None:
    """Draw opaque surface + rounded fill/stroke (and optional top join cover)."""
    tm = ThemeManager.get_instance()
    bg = _pane_fill_color(tm)
    border = tm.try_get_color("separator.color")

    painter = QPainter(pane)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    # Opaque clear of the full rectangular pane first — kills neighbour garbage
    # in the corner pixels outside the rounded fill.
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(_surface_color(tm))
    painter.drawRect(QRectF(pane.rect()))

    if bg is None and border is None:
        painter.end()
        return

    stroke_rect = QRectF(pane.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
    stroke_radii = tuple(float(r) for r in pane_radii)
    stroke_path = rounded_rect_path(stroke_rect, stroke_radii)

    if bg is not None:
        inset = PANE_BORDER_WIDTH
        fill_rect = stroke_rect.adjusted(inset, inset, -inset, -inset)
        fill_radii = tuple(max(0.0, r - inset) for r in stroke_radii)
        fill_path = rounded_rect_path(fill_rect, fill_radii)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg)
        painter.drawPath(fill_path)

    if border is not None:
        pen = QPen(QColor(border), PANE_BORDER_WIDTH)
        pen.setCosmetic(True)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(pen)
        painter.drawPath(stroke_path)

    if bg is not None and selected_cover is not None and selected_cover.width() > 0:
        painter.fillRect(selected_cover, bg)
    painter.end()


def apply_stack_fill(stack: QWidget) -> None:
    """Keep the page stack opaque with the pane fill colour."""
    tm = ThemeManager.get_instance()
    bg = _pane_fill_color(tm)
    stack.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
    stack.setAutoFillBackground(True)
    if bg is None:
        return
    palette = stack.palette()
    palette.setColor(stack.backgroundRole(), bg)
    stack.setPalette(palette)
