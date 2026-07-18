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

from pathlib import Path

from PySide6.QtCore import QRect, QRectF, Qt
from PySide6.QtGui import QColor, QFontMetrics, QImage, QPixmap

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.managers.ui_font import paint_font, ui_font
from sli_ui_toolkit.ui.widgets.helpers.icon_pixmap import normalized_icon_pixmap
from sli_ui_toolkit.ui.widgets.helpers.marquee_text import (
    draw_marquee_text,
    ensure_marquee_driver,
    text_overflows,
)
from sli_ui_toolkit.ui.widgets.style_bridge import read_widget_style

from .context import DrawContext
from .state import ButtonState

_IMAGE_FILLS = frozenset({"cover", "contain", "stretch"})


def normalize_image_fill(value: str | None) -> str:
    fill = str(value or "cover").strip().lower()
    return fill if fill in _IMAGE_FILLS else "cover"


def coerce_pixmap(value: Any) -> QPixmap | None:
    """Accept QPixmap / QImage / file path / QIcon-like; return a QPixmap or None."""
    if value is None:
        return None
    if isinstance(value, QPixmap):
        return value if not value.isNull() else None
    if isinstance(value, QImage):
        if value.isNull():
            return None
        pix = QPixmap.fromImage(value)
        return pix if not pix.isNull() else None
    if isinstance(value, (str, Path)):
        pix = QPixmap(str(value))
        return pix if not pix.isNull() else None
    # QIcon and other icon-like values: rasterize at a large size then scale
    # in PixmapContent — callers should prefer explicit QPixmap for photos.
    try:
        if hasattr(value, "pixmap") and callable(value.pixmap):
            pix = value.pixmap(256, 256)
            if isinstance(pix, QPixmap) and not pix.isNull():
                return pix
    except Exception:
        pass
    return None


def _scaled_pixmap_rect(
    source: QPixmap, target: QRect, fill: str
) -> tuple[QPixmap, QRect]:
    """Return (scaled_pixmap, dest_rect) for cover/contain/stretch into target."""
    tw = max(1, int(target.width()))
    th = max(1, int(target.height()))
    sw = max(1, source.width())
    sh = max(1, source.height())
    mode = normalize_image_fill(fill)

    if mode == "stretch":
        scaled = source.scaled(
            tw,
            th,
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        return scaled, QRect(target.x(), target.y(), tw, th)

    if mode == "contain":
        scaled = source.scaled(
            tw,
            th,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = target.x() + (tw - scaled.width()) // 2
        y = target.y() + (th - scaled.height()) // 2
        return scaled, QRect(x, y, scaled.width(), scaled.height())

    # cover — scale to fill, crop overflow by clipping to target
    scale = max(tw / sw, th / sh)
    nw = max(1, int(round(sw * scale)))
    nh = max(1, int(round(sh * scale)))
    scaled = source.scaled(
        nw,
        nh,
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    x = target.x() + (tw - scaled.width()) // 2
    y = target.y() + (th - scaled.height()) // 2
    return scaled, QRect(x, y, scaled.width(), scaled.height())


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


def _raw_rect(ctx: DrawContext) -> QRect:
    """Region/widget rect without ``content_padding`` (full bleed)."""
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
    # When True and the text is wider than the row, scroll left→right in a loop
    # via the shared marquee helper. Prefer a dedicated row for the overflowing
    # label — do not marquee composite "a · b" status lines.
    # Active marquee rows ignore horizontal ``content_padding`` (full-bleed).
    marquee: bool = False


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
        padded = _rect(ctx)
        full = _raw_rect(ctx)
        widget_h = padded.height()
        any_active = False

        def _emit_row(row: ButtonRow, y: int, height: int) -> None:
            nonlocal any_active
            if self._draw_row(
                p,
                row,
                ctx,
                style,
                tm,
                padded_x=padded.x(),
                padded_w=padded.width(),
                full_x=full.x(),
                full_w=full.width(),
                y=y,
                height=height,
            ):
                any_active = True

        if self.compact:
            heights = []
            for row in self.rows:
                f = ui_font(pixel_size=row.size, bold=(row.weight == "bold"))
                heights.append(QFontMetrics(f).lineSpacing())
            total = sum(heights) + self.row_gap * max(0, len(self.rows) - 1)
            y = padded.y() + max(0, (widget_h - total) // 2)
            for row, lh in zip(self.rows, heights):
                _emit_row(row, y, lh)
                y += lh + self.row_gap
        else:
            y = padded.y()
            for row in self.rows:
                rh = int(widget_h * row.ratio)
                if rh <= 0:
                    continue
                _emit_row(row, y, rh)
                y += rh

        driver = ensure_marquee_driver(widget)
        driver.set_active(any_active)

    @staticmethod
    def _draw_row(
        p,
        row,
        ctx,
        style,
        tm,
        *,
        padded_x: int,
        padded_w: int,
        full_x: int,
        full_w: int,
        y: int,
        height: int,
    ) -> bool:
        f = ui_font(pixel_size=row.size, bold=(row.weight == "bold"))
        p.setFont(f)
        if row.color:
            color = row.color
        else:
            color = style.foreground_color or tm.get_color("dialog.text")
        p.setPen(color)
        h_align = getattr(row, "h_align", Qt.AlignmentFlag.AlignHCenter)
        text = row.text or ""
        fm = QFontMetrics(f)
        # Marquee measures/draws against the unpadded width so the crawl can
        # use the full region (same idea as PixmapContent ignoring padding).
        wants_marquee = bool(getattr(row, "marquee", False))
        if wants_marquee and text_overflows(fm, text, full_w):
            row_rect = QRect(full_x, y, full_w, height)
            phase = float(getattr(ctx.widget, "_marquee_phase", 0.0) or 0.0)
            draw_marquee_text(p, row_rect, text, phase)
            return True

        row_rect = QRect(padded_x, y, padded_w, height)
        p.drawText(row_rect, h_align | Qt.AlignmentFlag.AlignVCenter, text)
        return False


@dataclass
class PixmapContent(Content):
    """Full-bleed photographic image for a region (cover/contain/stretch).

    Unlike ``IconContent``, this ignores ``content_padding`` and ``icon_size`` —
    the image fills ``ctx.effective_rect``. When ``region_corner_radii`` is set,
    the draw is clipped to that rounded path (crop radii for cards).
    """

    pixmap: Any = None
    image_fill: str = "cover"

    def draw(self, ctx: DrawContext, tm: ThemeManager) -> None:
        pix = coerce_pixmap(self.pixmap)
        if pix is None:
            return
        rect = ctx.effective_rect
        if isinstance(rect, QRectF):
            dest = rect.toAlignedRect()
        else:
            dest = QRect(rect)
        if dest.width() <= 0 or dest.height() <= 0:
            return

        scaled, paint_rect = _scaled_pixmap_rect(pix, dest, self.image_fill)
        p = ctx.painter
        p.save()
        radii = ctx.region_corner_radii
        if radii is not None:
            from .layers.background import rounded_rect_path

            clip = rounded_rect_path(QRectF(dest), tuple(int(r) for r in radii))
            p.setClipPath(clip)
        else:
            p.setClipRect(dest)
        p.drawPixmap(paint_rect, scaled)
        p.restore()


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
        # Font must be set before measuring — otherwise layout uses the painter's
        # previous face and Cyrillic advances can collapse until the next paint.
        font = _widget_paint_font(ctx.widget)
        p.setFont(font)
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
        p.setPen(_text_color(ctx, tm))
        text_x = start_x + icon_px + gap
        p.drawText(
            QRect(text_x, int(rect.y()), max(0, int(rect.right()) - text_x + 1), int(rect.height())),
            text_v | Qt.AlignmentFlag.AlignLeft,
            self.text,
        )
