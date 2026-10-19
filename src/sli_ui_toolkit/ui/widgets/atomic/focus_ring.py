"""One keyboard-focus ring for hand-painted atomic widgets.

Layer-based widgets (`Button` and friends) get the ring from
``buttons/layers/focus.py``. A widget that owns its own ``paintEvent`` and has
no layer pipeline (``Slider``, ``Switch``) cannot attach that layer, and the
alternative — a second, private ring implementation per widget — is how the
two rings drift apart. Hence this one helper: same accent colour, alpha,
thickness and inset as ``FocusLayer``, pill-shaped by default (the short axis
rounded), or with an explicit corner radius for a widget that has one.

Callers gate on ``widget._keyboard_focus and widget.hasFocus()`` — the modality
flag is set centrally in ``focusInEvent`` via
``sli_ui_toolkit.ui.managers.navigation_manager.resolve_keyboard_focus`` (input
device is the source of truth; the focus reason is only a hint), so a mouse
click never paints a ring.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.managers.ui_scale import UiScale


def paint_focus_ring(
    widget: QWidget,
    painter: QPainter,
    theme_manager: ThemeManager | None = None,
    *,
    corner_radius: float | None = None,
) -> bool:
    """Draw the keyboard-focus ring around *widget*; True when it was drawn.

    ``corner_radius=None`` (default) makes the ring pill-shaped — fully rounded
    on the short axis, matching a control with no corner-radius concept of its
    own; pass a number for a control that has one.
    """
    theme = theme_manager or ThemeManager.get_instance()
    factor = UiScale.get_instance().factor()
    thickness = max(1.0, 2.0 * factor)
    inset = thickness * 0.5
    ring = QRectF(widget.rect()).adjusted(inset, inset, -inset, -inset)
    if ring.width() <= 0 or ring.height() <= 0:
        return False
    radius = (
        float(corner_radius)
        if corner_radius is not None
        else min(ring.width(), ring.height()) / 2.0
    )
    path = QPainterPath()
    path.addRoundedRect(ring, radius, radius)
    color = QColor(theme.get_color("accent"))
    color.setAlpha(220)
    painter.save()
    try:
        pen = QPen(color)
        pen.setWidthF(thickness)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
    finally:
        painter.restore()
    return True
