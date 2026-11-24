"""Paint layers for ``ComboBox``'s field surface — background/border and the
current-text label. Split out of ``combo_box.py`` to mirror the buttons/
family's own painter/layers convention.

The field is an input control, not a button: its plate, text and border are the
input family's own tokens. The dropdown CARD next door (``_overlay.py``) is a
list surface and keeps its ``list_item`` reads.
"""


from __future__ import annotations

from PySide6.QtCore import QRect, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFontMetrics, QPainter, QPen

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.managers.ui_font import paint_font
from sli_ui_toolkit.ui.managers.ui_scale import scaled_px
from sli_ui_toolkit.ui.widgets.buttons.layers._base import Layer
from sli_ui_toolkit.ui.widgets.buttons.state import ButtonState
from sli_ui_toolkit.ui.widgets.helpers.overlay_geometry import centered_inner_offset


class _ComboFieldBgLayer(Layer):
    def draw(self, ctx, tm: ThemeManager) -> None:
        from sli_ui_toolkit.ui.managers.ui_scale import scaled_px

        widget = ctx.widget
        states = ctx.effective_states
        p = ctx.painter
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rectf = QRectF(ctx.rect).adjusted(0.5, 0.5, -0.5, -0.5)
        if ButtonState.PRESSED in states or widget._expanded:
            # Still the input plate: an open dropdown is the field's own pressed state, not a second surface.
            bg_color = QColor(tm.get_color("input.background"))
        elif ButtonState.HOVERED in states:
            # No input hover token exists yet, so the field still takes the row plate here (accepted debt in
            # tests/token_ownership_baseline.json); a host that restyles `list_item` moves this hover with it.
            bg_color = QColor(tm.get_color("input.background.hover"))
        else:
            bg_color = QColor(tm.get_color("input.background"))
        radius = scaled_px(widget.RADIUS)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(bg_color))
        p.drawRoundedRect(rectf, radius, radius)
        pen_border = QPen(QColor(tm.get_color("input.border.thin")))
        pen_border.setWidthF(1.0)
        p.setPen(pen_border)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rectf, radius, radius)


class _ComboFieldContentLayer(Layer):
    def draw(self, ctx, tm: ThemeManager) -> None:
        widget = ctx.widget
        current_text = widget.currentText()
        if not current_text:
            return
        is_disabled = ButtonState.DISABLED in ctx.effective_states
        if is_disabled:
            # "Not editable" is the family's disabled-text token, not a fade of the enabled ink.
            disabled = tm.try_get_color("input.text.disabled")
            if disabled is not None:
                text_color = QColor(disabled)
            else:
                text_color = QColor(tm.get_color("input.text"))
                text_color.setAlpha(140 if tm.is_dark() else 120)
        else:
            text_color = QColor(tm.get_color("input.text"))
        rect = ctx.rect.toRect()
        fm = QFontMetrics(paint_font(widget))
        inner_h = widget._item_height()
        # centered_inner_offset (not plain // 2): the popup geometry aligns
        # the same row height under the field with this same helper, so a
        # different rounding here left the label a px off from the row's own
        # text at odd height-diffs.
        inner_top = centered_inner_offset(rect.height(), inner_h)
        pad_x = scaled_px(widget.TEXT_HORIZONTAL_PADDING)
        text_rect = QRect(
            pad_x,
            inner_top,
            rect.width() - 2 * pad_x,
            inner_h,
        )
        display_text = current_text
        query = widget._typing_query_text()
        if query and widget._expanded:
            display_text = f"{query} -> {current_text}"
        p = ctx.painter
        p.setFont(paint_font(widget))
        p.setPen(QPen(text_color))
        p.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            fm.elidedText(display_text, Qt.TextElideMode.ElideRight, text_rect.width()),
        )
        # The affordance: a chevron at the right edge, the same glyph `ScrollableComboBox` draws. Without it the field
        # reads as a text input - the plain `ComboBox` had no arrow at all (measured against a stock QComboBox, which
        # shows one in a fixed-height plate).
        from PySide6.QtCore import QPoint
        from PySide6.QtGui import QPolygon

        p.setPen(QPen(QColor(tm.get_color("input.text")), 1.5))
        center_x = rect.x() + rect.width() - pad_x
        center_y = rect.center().y()
        p.drawPolyline(QPolygon([
            QPoint(center_x - 4, center_y - 1),
            QPoint(center_x, center_y + 2),
            QPoint(center_x + 4, center_y - 1),
        ]))
