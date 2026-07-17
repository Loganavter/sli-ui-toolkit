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

from PySide6.QtCore import QRect, QRectF, Qt
from PySide6.QtGui import QColor, QFontMetrics

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.managers.ui_font import paint_font, ui_font
from sli_ui_toolkit.ui.widgets.helpers.icon_pixmap import normalized_icon_pixmap
from sli_ui_toolkit.ui.widgets.style_bridge import read_widget_style

from .context import DrawContext
from .state import ButtonState


def _widget_paint_font(widget):
    return paint_font(widget)


def _text_color(ctx: DrawContext, tm: ThemeManager) -> QColor:
    """Цвет текста: style/theme; solid overrides can still set foregroundColor."""
    style = read_widget_style(ctx.widget)
    return style.foreground_color or QColor(tm.get_color("dialog.text"))


def _rect(ctx: DrawContext) -> QRect:
    rect = ctx.effective_rect
    if isinstance(rect, QRectF):
        rect = rect.toAlignedRect()
    else:
        rect = QRect(rect)
    left, top, right, bottom = ctx.content_padding
    if left or top or right or bottom:
        rect = rect.adjusted(int(left), int(top), -int(right), -int(bottom))
    return rect


class Content(ABC):
    @abstractmethod
    def draw(self, ctx: DrawContext, tm: ThemeManager) -> None: ...


@dataclass
class TextContent(Content):
    text: str

    def draw(self, ctx: DrawContext, tm: ThemeManager) -> None:
        p = ctx.painter
        font = _widget_paint_font(ctx.widget)
        p.setFont(font)
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
                f = ui_font(pixel_size=row.size, bold=(row.weight == "bold"))
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
        f = ui_font(pixel_size=row.size, bold=(row.weight == "bold"))
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

        icon_size = int(
            ctx.region_icon_size_px
            if ctx.region_icon_size_px is not None
            else (read_widget_style(ctx.widget).icon_size_px or ctx.effective_icon_size_px)
        )
        pixmap = normalized_icon_pixmap(current, icon_size)
        x = rect.x() + (rect.width() - icon_size) // 2
        y = rect.y() + (rect.height() - icon_size) // 2
        p.drawPixmap(x, y, pixmap)


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

        gap = max(0, int(getattr(ctx, "gap_px", 6) or 6))
        text_w = p.fontMetrics().horizontalAdvance(self.text)
        total_w = icon_px + gap + text_w
        align = getattr(
            ctx,
            "content_align",
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
        )
        if align & Qt.AlignmentFlag.AlignLeft:
            start_x = int(rect.x())
        elif align & Qt.AlignmentFlag.AlignRight:
            start_x = int(rect.x() + rect.width() - total_w)
        else:
            start_x = int(rect.x() + (rect.width() - total_w) // 2)

        if align & Qt.AlignmentFlag.AlignTop:
            icon_y = int(rect.y())
            text_v = Qt.AlignmentFlag.AlignTop
        elif align & Qt.AlignmentFlag.AlignBottom:
            icon_y = int(rect.y() + rect.height() - icon_px)
            text_v = Qt.AlignmentFlag.AlignBottom
        else:
            icon_y = int(rect.y() + (rect.height() - icon_px) // 2)
            text_v = Qt.AlignmentFlag.AlignVCenter

        p.drawPixmap(start_x, icon_y, pixmap)
        font = _widget_paint_font(ctx.widget)
        p.setFont(font)
        p.setPen(_text_color(ctx, tm))
        text_x = start_x + icon_px + gap
        p.drawText(
            QRect(text_x, int(rect.y()), max(0, int(rect.right()) - text_x + 1), int(rect.height())),
            text_v | Qt.AlignmentFlag.AlignLeft,
            self.text,
        )
