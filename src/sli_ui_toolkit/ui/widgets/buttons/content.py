"""Content types — полиморфная отрисовка содержимого кнопки.

Добавление нового типа контента:
    class ProgressContent(Content):
        def draw(self, ctx, tm): ...

Painter ничего не знает о конкретных типах — вызывает ctx.content.draw().
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from PyQt6.QtCore import QRect, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics

from sli_ui_toolkit.icons import get_named_icon
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.helpers.icon_pixmap import normalized_icon_pixmap
from sli_ui_toolkit.ui.widgets.style_bridge import read_widget_style

from .context import DrawContext
from .state import ButtonState
def _text_color(ctx: DrawContext, tm: ThemeManager) -> QColor:
    """Цвет текста: style/theme; solid overrides can still set foregroundColor."""
    style = read_widget_style(ctx.widget)
    return style.foreground_color or QColor(tm.get_color("dialog.text"))


def _rect(ctx: DrawContext) -> QRect:
    rect = ctx.effective_rect
    if isinstance(rect, QRectF):
        return rect.toAlignedRect()
    return QRect(rect)


class Content(ABC):
    @abstractmethod
    def draw(self, ctx: DrawContext, tm: ThemeManager) -> None: ...


@dataclass
class TextContent(Content):
    text: str

    def draw(self, ctx: DrawContext, tm: ThemeManager) -> None:
        p = ctx.painter
        p.setPen(_text_color(ctx, tm))
        rect = _rect(ctx)

        lines = self.text.split("\n") if "\n" in self.text else [self.text]
        if len(lines) > 1:
            fm = p.fontMetrics()
            line_h = fm.lineSpacing()
            total_h = line_h * len(lines)
            start_y = rect.y() + (rect.height() - total_h) // 2
            for i, line in enumerate(lines):
                r = QRect(rect.x(), start_y + i * line_h, rect.width(), line_h)
                p.drawText(r, Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter, line)
        else:
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.text)


@dataclass
class ButtonRow:
    """Одна строка в RowsContent — размер/жирность/цвет/доля высоты."""
    text: str
    size: int = 12
    weight: str = "normal"
    color: QColor | None = None
    ratio: float = 0.5
    h_align: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignHCenter
    strikethrough: bool = False
    italic: bool = False


@dataclass
class RowsContent(Content):
    rows: list[ButtonRow] = field(default_factory=list)
    compact: bool = False
    row_gap: int = 2

    def draw(self, ctx: DrawContext, tm: ThemeManager) -> None:
        if not self.rows:
            return

        widget = ctx.widget
        p = ctx.painter
        style = read_widget_style(widget)
        rect = _rect(ctx)
        widget_h = rect.height()
        widget_w = rect.width()

        if self.compact:
            heights = []
            for row in self.rows:
                f = QFont()
                f.setPixelSize(row.size)
                if row.weight == "bold":
                    f.setBold(True)
                heights.append(QFontMetrics(f).lineSpacing())
            total = sum(heights) + self.row_gap * max(0, len(self.rows) - 1)
            y = rect.y() + max(0, (widget_h - total) // 2)
            for row, lh in zip(self.rows, heights):
                self._draw_row(p, row, ctx, style, tm, rect.x(), widget_w, y, lh)
                y += lh + self.row_gap
        else:
            y = rect.y()
            for row in self.rows:
                rh = int(widget_h * row.ratio)
                if rh <= 0:
                    continue
                self._draw_row(p, row, ctx, style, tm, rect.x(), widget_w, y, rh)
                y += rh

    @staticmethod
    def _draw_row(p, row, ctx, style, tm, x, width, y, height):
        f = QFont()
        f.setPixelSize(row.size)
        if row.weight == "bold":
            f.setBold(True)
        p.setFont(f)
        if row.color:
            color = row.color
        else:
            color = style.foreground_color or tm.get_color("dialog.text")
        p.setPen(color)
        h_align = getattr(row, "h_align", Qt.AlignmentFlag.AlignHCenter)
        p.drawText(
            QRect(x, y, width, height),
            h_align | Qt.AlignmentFlag.AlignVCenter,
            row.text,
        )


@dataclass
class IconContent(Content):
    icon_unchecked: Any = None
    icon_checked: Any = None

    def draw(self, ctx: DrawContext, tm: ThemeManager) -> None:
        p = ctx.painter
        rect = _rect(ctx)
        is_checked = ButtonState.CHECKED in ctx.effective_states

        current = self.icon_checked if (self.icon_checked and is_checked) else self.icon_unchecked
        if not current:
            return

        widget = ctx.widget
        style = read_widget_style(widget)
        icon_size = int(
            ctx.region_icon_size_px
            if ctx.region_icon_size_px is not None
            else (style.icon_size_px or ctx.effective_icon_size_px)
        )

        scroll_value = ctx.scroll_value
        always_visible = ctx.scroll_value_always_visible
        is_toggle_scroll = scroll_value is not None and not always_visible
        is_hovered = ButtonState.HOVERED in ctx.effective_states
        is_scrolling = ButtonState.SCROLLING in ctx.effective_states

        # toggle+scroll: value-under-icon visible ONLY on hover (and not while
        # actively scrolling — popup takes over then). Plain scrollable: value
        # always visible below icon.
        if is_toggle_scroll and is_hovered and not is_scrolling:
            self._draw_with_hover_value(p, rect, current, scroll_value, style, tm, icon_size)
        else:
            self._draw_standard(p, rect, current, scroll_value, always_visible,
                                is_toggle_scroll, style, tm, icon_size)

    @staticmethod
    def _draw_standard(p, rect, icon_key, scroll_value, always_visible,
                       is_toggle_scroll, style, tm, icon_size):
        show_value_chip = (
            scroll_value is not None and always_visible and scroll_value != 0
        )
        actual = max(12, int(icon_size) - 4) if show_value_chip else int(icon_size)
        pixmap = normalized_icon_pixmap(icon_key, actual)

        opacity = 0.4 if is_toggle_scroll and scroll_value == 0 else 1.0
        p.setOpacity(opacity)
        x = rect.x() + (rect.width() - actual) // 2
        if show_value_chip:
            value_h = 12
            gap = 2
            y = rect.y() + max(1, (rect.height() - actual - value_h - gap) // 2)
        else:
            y = rect.y() + (rect.height() - actual) // 2
        p.drawPixmap(x, y, pixmap)
        p.setOpacity(1.0)

        if show_value_chip:
            _draw_scroll_value_below(p, rect, scroll_value, style, tm)

    @staticmethod
    def _draw_with_hover_value(p, rect, icon_key, scroll_value, style, tm, icon_size):
        base = int(style.icon_size_px or icon_size)
        hover_size = max(14, base - 3)
        pixmap = normalized_icon_pixmap(icon_key, hover_size)
        h = rect.height()
        value_h = 10
        gap = 2
        icon_y = rect.y() + max(1, (h - hover_size - value_h - gap) // 2)
        value_y = icon_y + hover_size + gap

        opacity = 0.4 if scroll_value == 0 else 1.0
        p.setOpacity(opacity)
        p.drawPixmap(rect.x() + int((rect.width() - hover_size) / 2), icon_y, pixmap)
        p.setOpacity(1.0)

        if scroll_value == 0:
            hidden = get_named_icon("divider_hidden")
            eye = normalized_icon_pixmap(hidden, 11)
            if not eye.isNull():
                cx = rect.x() + rect.width() // 2
                p.drawPixmap(cx - 5, value_y, eye)
            else:
                _draw_value_text(p, rect, value_y, value_h, "0", style, tm)
        else:
            _draw_value_text(p, rect, value_y, value_h, str(scroll_value), style, tm)


def _draw_scroll_value_below(p, rect, value, style, tm):
    value_h = 12
    value_y = rect.y() + rect.height() - value_h - 1
    _draw_value_text(p, rect, value_y, value_h, str(value), style, tm)


def _draw_value_text(p, rect, y: int, height: int, text: str,
                     style, tm: ThemeManager) -> None:
    f = QFont()
    f.setPixelSize(9)
    f.setBold(True)
    p.setFont(f)
    color = style.foreground_color or QColor(tm.get_color("dialog.text"))
    p.setPen(color)
    p.drawText(QRect(rect.x(), y, rect.width(), height),
               Qt.AlignmentFlag.AlignCenter, text)


@dataclass
class IconTextContent(Content):
    icon: Any
    text: str

    def draw(self, ctx: DrawContext, tm: ThemeManager) -> None:
        widget = ctx.widget
        p = ctx.painter
        rect = _rect(ctx)
        style = read_widget_style(widget)
        icon_px = int(
            ctx.region_icon_size_px
            if ctx.region_icon_size_px is not None
            else (style.icon_size_px or ctx.effective_icon_size_px)
        )
        pixmap = normalized_icon_pixmap(self.icon, icon_px)

        total_w = icon_px + 6 + p.fontMetrics().horizontalAdvance(self.text)
        start_x = rect.x() + (rect.width() - total_w) // 2
        icon_y = rect.y() + (rect.height() - icon_px) // 2

        p.drawPixmap(start_x, icon_y, pixmap)
        p.setPen(_text_color(ctx, tm))
        p.drawText(
            QRect(start_x + icon_px + 6, rect.y(), rect.width(), rect.height()),
            Qt.AlignmentFlag.AlignVCenter,
            self.text,
        )
