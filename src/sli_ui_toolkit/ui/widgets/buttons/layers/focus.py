"""FocusLayer — keyboard focus ring for the painter pipeline.

Widget-scoped layer drawn on top of content: a thin accent rounded outline
around the whole button when it holds *keyboard* focus. The Button records
the focus-grant reason in ``_keyboard_focus`` (focusInEvent), so a mouse
click does not flash the ring while Tab/arrow navigation does.
"""

from __future__ import annotations

import logging
import os

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainterPath, QPen

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.managers.ui_scale import UiScale

from ..context import DrawContext
from ._base import Layer

# [focus-ring] trace lines fire on every paint of a focused widget once the
# host app's --debug is on, drowning out other subsystems' debug output.
# Gated on its own opt-in flag, off by default even under --debug -- same
# convention as sidebar_nav_list/debug.py's SLI_UI_NAVLIST_DEBUG.
logger = logging.getLogger(__name__)
if os.environ.get("UI_NAV_DEBUG", "").strip().lower() in (
    "",
    "0",
    "false",
    "no",
    "off",
):
    logger.setLevel(logging.WARNING)
else:
    logger.setLevel(logging.DEBUG)


class FocusLayer(Layer):
    scope = "widget"

    def applies(self, ctx: DrawContext) -> bool:
        widget = ctx.widget
        result = bool(getattr(widget, "_keyboard_focus", False)) and widget.hasFocus()
        if result:
            logger.debug(
                "[focus-ring] applies! widget=%s(%s) keyboard_focus=%s hasFocus=%s",
                type(widget).__name__,
                getattr(widget, "objectName", lambda: "")() or "",
                getattr(widget, "_keyboard_focus", None),
                widget.hasFocus(),
            )
        return result

    def draw(self, ctx: DrawContext, tm: ThemeManager) -> None:
        factor = UiScale.get_instance().factor()
        radius = max(0, ctx.corner_radius)
        # ctx.corner_radius is already scale-resolved (scaled_px); the
        # painter scales arc_radius by the factor exactly once — divide it
        # back out so the ring wraps the painted corner circle at every
        # interface scale (same convention as UnderlineLayer).
        design_radius = radius / factor if factor > 0 else radius

        rect = ctx.rect
        if hasattr(rect, "toAlignedRect"):
            rect = rect.toAlignedRect()

        thickness = max(1.0, 2.0 * factor)
        inset = thickness * 0.5
        ring = QRectF(rect).adjusted(inset, inset, -inset, -inset)
        if ring.width() <= 0 or ring.height() <= 0:
            return

        path = QPainterPath()
        path.addRoundedRect(ring, design_radius, design_radius)

        color = QColor(tm.get_color("accent"))
        color.setAlpha(220)

        painter = ctx.painter
        painter.save()
        try:
            painter.setRenderHint(painter.RenderHint.Antialiasing, True)
            pen = QPen(color)
            pen.setWidthF(thickness)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)
        finally:
            painter.restore()
