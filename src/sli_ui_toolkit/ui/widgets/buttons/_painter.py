"""
Centralized painting logic for Button widget.
Handles all visual combinations: icon, text, badge, scroll value, underline, strikethrough.

Color scheme is driven entirely by the ``variant`` property:

    variant        theme prefix               border  checked states
    ─────────────  ─────────────────────────   ──────  ──────────────
    "default"      button.toggle              no      yes
    "accent"       button.default             yes     no
    "delete"       button.delete              yes     no
    "primary"      button.primary             yes     no  (text buttons)
    "surface"      button.dialog.default      yes     no  (text buttons)
    "ghost"        transparent                no      no
    "subtle"       Window color               no      yes

Any unknown variant falls back to "default" (button.toggle).
"""

from __future__ import annotations

from PyQt6.QtCore import QRect, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen

from sli_ui_toolkit.icons import get_named_icon, resolve_icon
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.helpers import UnderlineConfig, draw_bottom_underline
from sli_ui_toolkit.ui.widgets.style_bridge import read_widget_style

_VARIANT_PREFIX: dict[str, str] = {
    "default": "button.toggle",
    "accent": "button.default",
    "delete": "button.delete",
    "primary": "button.primary",
    "surface": "button.dialog.default",
}

class ButtonPainter:
    @staticmethod
    def paint(
        widget,
        painter: QPainter,
        icon_unchecked=None,
        icon_checked=None,
        text: str = "",
        rows=None,
        rows_compact: bool = False,
        is_checked: bool = False,
        is_pressed: bool = False,
        is_hovered: bool = False,
        is_scrolling: bool = False,
        badge_text: str | None = None,
        scroll_value: int | None = None,
        scroll_value_always_visible: bool = False,
        underline_color=None,
        show_underline: bool = False,
        icon_size: int = 22,
        show_strike_through: bool = False,
        override_bg_color: QColor | None = None,
        custom_bg_color: QColor | None = None,
        is_footer: bool = False,
    ):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        tm = ThemeManager.get_instance()
        style = read_widget_style(widget, default_icon_size=icon_size)

        variant = style.variant or "default"
        prefix = _VARIANT_PREFIX.get(variant, "button.toggle")

        bg_color = ButtonPainter._resolve_background(
            prefix, variant, style, tm,
            is_pressed, is_checked, is_hovered,
            override_bg=override_bg_color,
            custom_bg=custom_bg_color,
        )

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg_color)

        radius = max(0, int(style.corner_radius_px or 6))
        rect_f = QRectF(widget.rect()).adjusted(0.5, 0.5, -0.5, -0.5)

        if is_footer:
            path = ButtonPainter._footer_path(rect_f, radius)
            painter.drawPath(path)
        else:
            painter.drawRoundedRect(rect_f, radius, radius)

        if widget.isEnabled() and custom_bg_color is None:
            border_key = f"{prefix}.border"
            border_color = tm.try_get_color(border_key)
            if border_color is not None:
                painter.setPen(QPen(QColor(border_color), 1.0))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                if is_footer:
                    painter.drawPath(path)
                else:
                    painter.drawRoundedRect(rect_f, radius, radius)

        if rows:
            ButtonPainter._draw_rows(painter, widget, rows, style, tm, compact=rows_compact, custom_bg_color=custom_bg_color)
        elif text and not icon_unchecked:
            ButtonPainter._draw_text_only(painter, widget, text, style, tm, custom_bg_color=custom_bg_color)
        elif text and icon_unchecked:
            ButtonPainter._draw_icon_and_text(
                painter, widget, icon_unchecked, text, style, tm, icon_size, custom_bg_color=custom_bg_color
            )
        elif icon_unchecked:
            current_icon = icon_checked if (icon_checked and is_checked) else icon_unchecked
            is_toggle_scroll = scroll_value is not None and not scroll_value_always_visible

            if is_toggle_scroll and is_hovered and not is_scrolling:
                ButtonPainter._draw_icon_with_hover_value(
                    painter, widget, current_icon, scroll_value, style, tm, icon_size
                )
            else:
                ButtonPainter._draw_icon_standard(
                    painter, widget, current_icon, scroll_value,
                    scroll_value_always_visible, is_toggle_scroll,
                    style, tm, icon_size,
                )

        if badge_text is not None:
            ButtonPainter._draw_badge(painter, widget, badge_text, is_checked, tm, style)

        if widget.isEnabled():
            edge_key = f"{prefix}.bottom.edge"
            if tm.try_get_color(edge_key) is not None:

                scale = max(1.0, widget.rect().height() / 32.0)
                normalized_radius = radius / scale if scale > 0 else radius
                draw_bottom_underline(painter, widget.rect(), tm, UnderlineConfig(
                    alpha=40, thickness=1.0, vertical_offset=0.0, arc_radius=normalized_radius,
                ))

        resolved_underline = underline_color or style.underline_color
        has_explicit_color = resolved_underline is not None
        if not resolved_underline and show_underline:
            resolved_underline = style.accent_color if variant in {"primary", "accent"} else None
        if resolved_underline is not None:
            alpha = None
            if isinstance(resolved_underline, QColor):
                if has_explicit_color:
                    alpha = min(resolved_underline.alpha(), 100)
                else:
                    alpha = resolved_underline.alpha() if resolved_underline.alpha() < 255 else (
                        40 if scroll_value is not None else 200
                    )
            elif isinstance(resolved_underline, list):
                alpha = None

            scale = max(1.0, widget.rect().height() / 32.0)
            normalized_radius = radius / scale if scale > 0 else radius
            config = UnderlineConfig(
                thickness=2.0 if scroll_value is not None else 1.0,
                vertical_offset=0.0 if scroll_value is not None else 1.0,
                arc_radius=normalized_radius,
                alpha=alpha,
                color=resolved_underline,
            )
            draw_bottom_underline(painter, widget.rect(), tm, config)

        if show_strike_through:
            strike_color = QColor("#ff4444") if tm.is_dark() else QColor("#cc0000")
            strike_color.setAlpha(180)
            painter.setPen(QPen(strike_color, 2))
            painter.drawLine(4, widget.height() - 4, widget.width() - 4, 4)

    @staticmethod
    def _footer_path(rect: QRectF, radius: int) -> QPainterPath:
        """Flat top, rounded bottom corners."""
        path = QPainterPath()
        path.moveTo(rect.left(), rect.top())
        path.lineTo(rect.right(), rect.top())
        path.arcTo(
            rect.right() - 2 * radius, rect.bottom() - 2 * radius,
            2 * radius, 2 * radius, 0, -90,
        )
        path.arcTo(
            rect.left(), rect.bottom() - 2 * radius,
            2 * radius, 2 * radius, 270, -90,
        )
        path.closeSubpath()
        return path

    @staticmethod
    def _resolve_background(prefix, variant, style, tm,
                            is_pressed, is_checked, is_hovered,
                            override_bg=None, custom_bg=None) -> QColor:
        if override_bg is not None:
            return override_bg

        if custom_bg is not None:
            if is_pressed:
                return custom_bg.darker(115)
            if is_hovered:
                return custom_bg.lighter(108)
            return QColor(custom_bg)

        if style.background_color is not None:
            bg = QColor(style.background_color)
            if is_pressed:
                bg = QColor(tm.get_color(f"{prefix}.background.pressed"))
            elif is_checked:
                checked_key = f"{prefix}.background.checked"
                bg = QColor(tm.get_color(
                    f"{checked_key}.hover" if is_hovered and tm.try_get_color(f"{checked_key}.hover") else checked_key
                )) if tm.try_get_color(checked_key) else bg
            elif is_hovered:
                bg = QColor(tm.get_color(f"{prefix}.background.hover"))
            return bg

        if variant == "ghost":
            if is_pressed:
                return QColor(tm.get_color("button.toggle.background.pressed"))
            elif is_hovered:
                return QColor(tm.get_color("button.toggle.background.hover"))
            return QColor(0, 0, 0, 0)

        if variant == "subtle":
            if is_pressed:
                return QColor(tm.get_color("button.toggle.background.pressed"))
            elif is_checked:
                checked_color = tm.try_get_color("button.toggle.background.checked")
                if checked_color:
                    if is_hovered:
                        return QColor(tm.get_color("button.toggle.background.checked.hover"))
                    return QColor(checked_color)
            elif is_hovered:
                return QColor(tm.get_color("button.toggle.background.hover"))
            return QColor(tm.get_color("Window"))

        normal_key = f"{prefix}.background.normal" if prefix == "button.toggle" else f"{prefix}.background"

        if is_pressed:
            return QColor(tm.get_color(f"{prefix}.background.pressed"))

        if is_checked:
            checked_key = f"{prefix}.background.checked"
            if tm.try_get_color(checked_key) is not None:
                if is_hovered and tm.try_get_color(f"{checked_key}.hover") is not None:
                    return QColor(tm.get_color(f"{checked_key}.hover"))
                return QColor(tm.get_color(checked_key))

            return QColor(tm.get_color(f"{prefix}.background.pressed"))

        if is_hovered:
            return QColor(tm.get_color(f"{prefix}.background.hover"))

        return QColor(tm.get_color(normal_key))

    @staticmethod
    def _draw_text_only(painter, widget, text, style, tm, custom_bg_color=None):
        if custom_bg_color is not None:
            from sli_ui_toolkit.ui.widgets.buttons.tokens.resolver import TokenResolver
            text_color = TokenResolver.get_contrasting_text_color(custom_bg_color)
        else:
            text_color = style.foreground_color or tm.get_color("dialog.text")
        painter.setPen(text_color)

        # Поддержка многострочного текста (разделённого \n)
        lines = text.split('\n') if '\n' in text else [text]
        if len(lines) > 1:
            fm = painter.fontMetrics()
            line_height = fm.lineSpacing()
            total_height = line_height * len(lines)
            start_y = (widget.height() - total_height) // 2

            for i, line in enumerate(lines):
                line_rect = QRect(0, start_y + i * line_height, widget.width(), line_height)
                painter.drawText(line_rect, Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter, line)
        else:
            painter.drawText(widget.rect(), Qt.AlignmentFlag.AlignCenter, text)

    @staticmethod
    def _draw_icon_and_text(painter, widget, icon_key, text, style, tm, icon_size, custom_bg_color=None):
        icon_px = int(style.icon_size_px or min(icon_size, 16))
        icon = resolve_icon(icon_key)
        pixmap = icon.pixmap(icon_px, icon_px)

        total_width = icon_px + 6 + painter.fontMetrics().horizontalAdvance(text)
        start_x = (widget.width() - total_width) // 2
        icon_y = (widget.height() - icon_px) // 2

        painter.drawPixmap(start_x, icon_y, pixmap)

        if custom_bg_color is not None:
            from sli_ui_toolkit.ui.widgets.buttons.tokens.resolver import TokenResolver
            text_color = TokenResolver.get_contrasting_text_color(custom_bg_color)
        else:
            text_color = style.foreground_color or tm.get_color("dialog.text")
        painter.setPen(text_color)
        text_rect = QRect(start_x + icon_px + 6, 0, widget.width(), widget.height())
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter, text)

    @staticmethod
    def _draw_icon_standard(
        painter, widget, current_icon, scroll_value,
        scroll_value_always_visible, is_toggle_scroll,
        style, tm, icon_size,
    ):
        actual_icon_size = (
            max(12, int(style.icon_size_px or icon_size) - 4)
            if scroll_value_always_visible
            else int(style.icon_size_px or icon_size)
        )
        icon_pixmap = resolve_icon(current_icon).pixmap(actual_icon_size, actual_icon_size)

        opacity = 0.4 if is_toggle_scroll and scroll_value == 0 else 1.0
        painter.setOpacity(opacity)
        x = (widget.width() - actual_icon_size) // 2

        if scroll_value is not None and scroll_value_always_visible:
            value_h = 12
            gap = 2
            y = max(1, (widget.height() - actual_icon_size - value_h - gap) // 2)
        else:
            y = (widget.height() - actual_icon_size) // 2

        painter.drawPixmap(x, y, icon_pixmap)
        painter.setOpacity(1.0)

        if scroll_value is not None and scroll_value_always_visible:
            ButtonPainter._draw_scroll_value_below(painter, widget, scroll_value, tm, style)

    @staticmethod
    def _draw_icon_with_hover_value(painter, widget, current_icon, scroll_value, style, tm, icon_size):
        hover_icon_size = max(12, int(style.icon_size_px or icon_size) - 6)
        icon_pixmap = resolve_icon(current_icon).pixmap(hover_icon_size, hover_icon_size)
        h = widget.height()
        value_h = 10
        gap = 2
        icon_y = max(1, (h - hover_icon_size - value_h - gap) // 2)
        value_y = icon_y + hover_icon_size + gap

        opacity = 0.4 if scroll_value == 0 else 1.0
        painter.setOpacity(opacity)
        painter.drawPixmap(int((widget.width() - hover_icon_size) / 2), icon_y, icon_pixmap)
        painter.setOpacity(1.0)

        if scroll_value == 0:
            hidden_icon = get_named_icon("divider_hidden")
            eye_pixmap = resolve_icon(hidden_icon).pixmap(11, 11)
            center_x = widget.width() // 2
            painter.drawPixmap(center_x - 5, value_y, eye_pixmap)
        else:
            font = QFont()
            font.setPixelSize(9)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(style.foreground_color or tm.get_color("dialog.text"))
            text_rect = QRect(0, value_y, widget.width(), value_h)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, str(scroll_value))

    @staticmethod
    def _draw_scroll_value_below(painter, widget, value, tm, style):
        font = QFont()
        font.setPixelSize(9)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(style.foreground_color or QColor(tm.get_color("dialog.text")))
        value_h = 12
        value_y = widget.height() - value_h - 1
        text_rect = QRect(0, value_y, widget.width(), value_h)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, str(value))

    @staticmethod
    def _draw_rows(painter, widget, rows, style, tm, compact: bool = False, row_gap: int = 2, custom_bg_color=None):
        """Draw multiple rows of text with individual styling and height ratios.

        Args:
            compact: If True, rows are centered as a block. If False, rows are distributed by ratio.
        """
        if not rows:
            return

        widget_height = widget.height()
        widget_width = widget.width()

        if compact:
            # Compact mode: calculate real font heights and center the block
            line_heights = []
            for row in rows:
                font = QFont()
                font.setPixelSize(row.size)
                if row.weight == "bold":
                    font.setBold(True)
                line_heights.append(QFontMetrics(font).lineSpacing())

            total_h = sum(line_heights) + row_gap * max(0, len(rows) - 1)
            y_offset = max(0, (widget_height - total_h) // 2)

            for row, lh in zip(rows, line_heights):
                font = QFont()
                font.setPixelSize(row.size)
                if row.weight == "bold":
                    font.setBold(True)
                painter.setFont(font)
                if row.color:
                    color = row.color
                elif custom_bg_color is not None:
                    from sli_ui_toolkit.ui.widgets.buttons.tokens.resolver import TokenResolver
                    color = TokenResolver.get_contrasting_text_color(custom_bg_color)
                else:
                    color = style.foreground_color or tm.get_color("dialog.text")
                painter.setPen(color)
                h_align = getattr(row, "h_align", Qt.AlignmentFlag.AlignHCenter)
                painter.drawText(
                    QRect(0, y_offset, widget_width, lh),
                    h_align | Qt.AlignmentFlag.AlignVCenter,
                    row.text
                )
                y_offset += lh + row_gap
        else:
            # Ratio mode: distribute rows by their ratio (original behavior)
            y_offset = 0
            for row in rows:
                row_height = int(widget_height * row.ratio)
                if row_height <= 0:
                    continue

                # Set up font
                font = QFont()
                font.setPixelSize(row.size)
                if row.weight == "bold":
                    font.setBold(True)
                painter.setFont(font)

                # Set up color
                color = row.color or style.foreground_color or tm.get_color("dialog.text")
                painter.setPen(color)

                # Draw text in the allocated height
                h_align = getattr(row, "h_align", Qt.AlignmentFlag.AlignHCenter)
                row_rect = QRect(0, y_offset, widget_width, row_height)
                painter.drawText(
                    row_rect,
                    h_align | Qt.AlignmentFlag.AlignVCenter,
                    row.text
                )

                y_offset += row_height

    @staticmethod
    def _draw_badge(painter, widget, text, is_checked, tm, style):
        text_color = style.foreground_color or QColor(tm.get_color("dialog.text"))
        if is_checked:
            text_color.setAlpha(140)
        font = QFont()
        font.setBold(True)
        font.setPixelSize(9)
        painter.setFont(font)
        painter.setPen(text_color)
        text_rect = QRect(widget.width() - 14, 1, 12, 10)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, str(text))
