"""BadgeLayer — мелкий счётчик в правом верхнем углу."""

from __future__ import annotations

from PySide6.QtCore import QRect, QRectF, Qt
from PySide6.QtGui import QColor, QPen

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.managers.ui_font import ui_font
from sli_ui_toolkit.ui.managers.ui_scale import scaled_px
from sli_ui_toolkit.ui.widgets.style_bridge import read_widget_style

from ..context import DrawContext
from ..state import ButtonState
from ._base import Layer


class BadgeLayer(Layer):
    scope = "widget"

    def applies(self, ctx: DrawContext) -> bool:
        return ctx.badge_text is not None

    def draw(self, ctx: DrawContext, tm: ThemeManager) -> None:
        widget = ctx.widget
        p = ctx.painter

        f = ui_font(pixel_size=9, bold=True)
        p.setFont(f)

        if not self._has_custom_badge_style(widget):
            style = read_widget_style(widget)
            text_color = style.foreground_color or QColor(tm.get_color("dialog.text"))
            if ButtonState.CHECKED in ctx.states:
                text_color.setAlpha(140)
            elif ButtonState.DISABLED in ctx.states:
                text_color.setAlpha(120)
            p.setPen(text_color)
            # Design px, resolved at paint time: the badge box must grow with
            # the interface scale like the (already scaled) badge font, or a
            # chip's badge reads cramped/misaligned after a live scale change.
            text_rect = QRect(
                widget.width() - scaled_px(14), scaled_px(1), scaled_px(12), scaled_px(10)
            )
            p.drawText(
                text_rect,
                Qt.AlignmentFlag.AlignCenter,
                str(ctx.badge_text),
            )
            return

        metrics = p.fontMetrics()
        badge_text = str(ctx.badge_text)
        badge_height = scaled_px(14)
        badge_width = max(
            scaled_px(14), metrics.horizontalAdvance(badge_text) + scaled_px(8)
        )
        badge_rect = QRectF(
            widget.width() - badge_width - scaled_px(2),
            scaled_px(2),
            badge_width,
            badge_height,
        )

        accent = QColor(tm.get_color("accent"))
        fill_enabled = bool(widget.property("badgeFilled"))

        bordered_prop = widget.property("badgeBordered")
        if bordered_prop is None:
            bordered_enabled = not fill_enabled
        else:
            bordered_enabled = bool(bordered_prop)

        badge_bg = widget.property("badgeBackgroundColor")
        border_color = widget.property("badgeBorderColor")
        text_color = widget.property("badgeTextColor")

        badge_bg = QColor(badge_bg) if isinstance(badge_bg, QColor) else QColor(accent)
        border_color = QColor(border_color) if isinstance(border_color, QColor) else QColor(accent)
        text_color = QColor(text_color) if isinstance(text_color, QColor) else QColor(accent)

        if ButtonState.DISABLED in ctx.states:
            border_color.setAlpha(120)
            text_color.setAlpha(150)
            badge_bg.setAlpha(60)
        elif ButtonState.CHECKED in ctx.states:
            border_color.setAlpha(180)
            text_color.setAlpha(220)
            badge_bg.setAlpha(80)

        if bordered_enabled:
            p.setPen(QPen(border_color, 1.0))
        else:
            p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(badge_bg if fill_enabled else Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(badge_rect, badge_height / 2, badge_height / 2)

        p.setPen(text_color)
        p.drawText(
            badge_rect.toRect(),
            Qt.AlignmentFlag.AlignCenter,
            badge_text,
        )

    @staticmethod
    def _has_custom_badge_style(widget) -> bool:
        return any(
            widget.property(name) is not None
            for name in (
                "badgeFilled",
                "badgeBordered",
                "badgeBackgroundColor",
                "badgeBorderColor",
                "badgeTextColor",
            )
        )
