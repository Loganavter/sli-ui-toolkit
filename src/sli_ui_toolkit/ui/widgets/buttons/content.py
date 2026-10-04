"""Content types — полиморфная отрисовка содержимого кнопки.

Добавление нового типа контента:
    class ProgressContent(Content):
        def draw(self, ctx, tm): ...

Painter ничего не знает о конкретных типах — вызывает ctx.content.draw().
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal

from pathlib import Path

from PySide6.QtCore import QRect, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter, QPixmap

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.managers.ui_font import paint_font, ui_font
from sli_ui_toolkit.ui.managers.ui_scale import scaled_px
from sli_ui_toolkit.ui.widgets.helpers.icon_pixmap import normalized_icon_pixmap
from sli_ui_toolkit.ui.widgets.helpers.marquee_text import (
    draw_marquee_text,
    ensure_marquee_driver,
    text_overflows,
)
from sli_ui_toolkit.ui.widgets.style_bridge import read_widget_style

from .context import DrawContext
from .state import ButtonState

ImageFill = Literal["cover", "contain", "stretch"]
_IMAGE_FILLS = frozenset({"cover", "contain", "stretch"})


def normalize_image_fill(value: str | None) -> ImageFill:
    fill = str(value or "cover").strip().lower()
    return fill if fill in _IMAGE_FILLS else "cover"  # type: ignore[return-value]


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
    raw = ctx.effective_rect
    rect = raw.toAlignedRect() if isinstance(raw, QRectF) else QRect(raw)
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
    # ``None`` = the current default UI font (``ui_font()``, point-based app
    # font) instead of an explicit pixel size — use it for rows that must
    # match the host's normal text (e.g. SimpleOptionsFlyout default rows).
    size: int | None = 12
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
class MarqueeRowPaint:
    """Pre-resolved marquee row blit for the static-layer fast path.

    Recorded during a full-pipeline paint (see ``RowsContent.draw``); the
    per-tick fast path replays these with no context build, no region walk
    and no ``QFontMetrics`` (the strip cache on the driver serves the blit).
    Rects are absolute widget coordinates; font/pen match the full paint
    exactly (same ``ui_font`` spec, same theme-token color).
    """

    text: str
    rect: QRect
    font: QFont
    pen: QColor


def draw_marquee_paints(
    painter: QPainter,
    paints: list[MarqueeRowPaint],
    phase: float,
    driver: Any = None,
) -> None:
    """Blit cached marquee rows at ``phase`` via the strip path.

    Single blit implementation shared by the Button fast path (cached
    paints, no ``DrawContext``) and ``RowsContent.draw_marquee_rows``
    (paints resolved from a context) — parity by construction.
    """
    for paint in paints:
        painter.setFont(paint.font)
        painter.setPen(paint.pen)
        draw_marquee_text(
            painter, QRect(paint.rect), paint.text, float(phase), driver=driver
        )


@dataclass
class _ResolvedRow:
    """One row with layout + style resolved (font/pen/rect/overflow)."""

    row: ButtonRow
    rect: QRect
    font: QFont
    pen: QColor
    h_align: Qt.AlignmentFlag
    marquee_active: bool


@dataclass
class RowsContent(Content):
    rows: list[ButtonRow] = field(default_factory=list)
    compact: bool = False
    row_gap: int = 2

    def draw(
        self, ctx: DrawContext, tm: ThemeManager, skip_marquee_rows: bool = False
    ) -> None:
        if not self.rows:
            return

        widget = ctx.widget
        p = ctx.painter
        style = read_widget_style(widget)
        # The layer pipeline calls ``draw(ctx, tm)`` without the flag, so a
        # static-layer snapshot render arms the widget-level flag around
        # ``Painter.paint`` instead (see ``Button._maybe_snapshot_static``).
        skip = bool(skip_marquee_rows) or bool(
            getattr(widget, "_paint_skip_marquee", False)
        )
        padded = _rect(ctx)
        full = _raw_rect(ctx)
        widget_h = padded.height()
        driver = ensure_marquee_driver(widget)
        phase = float(getattr(widget, "_marquee_phase", 0.0) or 0.0)
        any_active = False
        # Snapshot renders (skip) must not clobber the live paint list the
        # fast path replays — they only refresh the driver dirty union.
        paints: list[MarqueeRowPaint] | None = [] if not skip else None

        for row, y, height in self._row_layout(padded, widget_h):
            resolved = self._resolve_row(
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
            )
            if resolved.marquee_active:
                any_active = True
                if skip:
                    driver.note_marquee_rect(QRect(resolved.rect))
                    continue
            if self._draw_resolved(p, resolved, phase):
                if paints is not None:
                    paints.append(
                        MarqueeRowPaint(
                            text=resolved.row.text or "",
                            rect=QRect(resolved.rect),
                            font=resolved.font,
                            pen=QColor(resolved.pen),
                        )
                    )

        if paints:
            recorded = getattr(widget, "_marquee_row_paints", None)
            if isinstance(recorded, list):
                recorded.extend(paints)

        driver.set_active(any_active)

    def marquee_row_paints(self, ctx: DrawContext) -> list[MarqueeRowPaint]:
        """Resolve this content's currently-overflowing marquee rows (no paint).

        Same geometry/fonts/pens the full paint uses, without drawing —
        powers ``draw_marquee_rows`` and the pixel-parity tests.
        """
        tm = ThemeManager.get_instance()
        style = read_widget_style(ctx.widget)
        padded = _rect(ctx)
        full = _raw_rect(ctx)
        paints: list[MarqueeRowPaint] = []
        for row, y, height in self._row_layout(padded, padded.height()):
            resolved = self._resolve_row(
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
            )
            if resolved.marquee_active:
                paints.append(
                    MarqueeRowPaint(
                        text=resolved.row.text or "",
                        rect=QRect(resolved.rect),
                        font=resolved.font,
                        pen=QColor(resolved.pen),
                    )
                )
        return paints

    def draw_marquee_rows(
        self, painter: QPainter, ctx: DrawContext, phase: float
    ) -> None:
        """Draw ONLY this content's marquee rows at ``phase`` (strip path).

        Static rows, pixmaps, icons and backgrounds are untouched — the
        static-layer fast path owns those via its snapshot. The driver is
        passed explicitly so pixmap-device renders behave like widget ones.
        """
        driver = getattr(ctx.widget, "_marquee_driver", None)
        draw_marquee_paints(
            painter, self.marquee_row_paints(ctx), float(phase), driver
        )

    def _row_layout(self, padded: QRect, widget_h: int):
        """Yield ``(row, y, height)`` in paint order (compact or ratio mode)."""
        if self.compact:
            heights = []
            for row in self.rows:
                f = ui_font(pixel_size=row.size, bold=(row.weight == "bold"))
                heights.append(QFontMetrics(f).lineSpacing())
            total = sum(heights) + self.row_gap * max(0, len(self.rows) - 1)
            y = padded.y() + max(0, (widget_h - total) // 2)
            for row, lh in zip(self.rows, heights):
                yield row, y, lh
                y += lh + self.row_gap
        else:
            y = padded.y()
            for row in self.rows:
                rh = int(widget_h * row.ratio)
                if rh <= 0:
                    continue
                yield row, y, rh
                y += rh

    @staticmethod
    def _resolve_row(
        row: ButtonRow,
        ctx: DrawContext,
        style: Any,
        tm: ThemeManager,
        *,
        padded_x: int,
        padded_w: int,
        full_x: int,
        full_w: int,
        y: int,
        height: int,
    ) -> _ResolvedRow:
        f = ui_font(pixel_size=row.size, bold=(row.weight == "bold"))
        if row.color:
            color = row.color
        else:
            color = style.foreground_color or tm.get_color("dialog.text")
        pen = color if isinstance(color, QColor) else QColor(color)
        h_align = getattr(row, "h_align", Qt.AlignmentFlag.AlignHCenter)
        text = row.text or ""
        fm = QFontMetrics(f)
        # Marquee measures/draws against the unpadded width so the crawl can
        # use the full region (same idea as PixmapContent ignoring padding).
        wants_marquee = bool(getattr(row, "marquee", False))
        if wants_marquee and text_overflows(fm, text, full_w):
            return _ResolvedRow(
                row=row,
                rect=QRect(full_x, y, full_w, height),
                font=f,
                pen=pen,
                h_align=h_align,
                marquee_active=True,
            )
        return _ResolvedRow(
            row=row,
            rect=QRect(padded_x, y, padded_w, height),
            font=f,
            pen=pen,
            h_align=h_align,
            marquee_active=False,
        )

    @staticmethod
    def _draw_resolved(p: QPainter, resolved: _ResolvedRow, phase: float) -> bool:
        """Paint one resolved row; return True when it is marquee-active."""
        p.setFont(resolved.font)
        p.setPen(resolved.pen)
        if resolved.marquee_active:
            # Driver auto-resolves from the paint device (the host widget);
            # pixmap-device renders take the legacy direct path, as before.
            draw_marquee_text(p, resolved.rect, resolved.row.text or "", phase)
            return True
        p.drawText(
            resolved.rect,
            resolved.h_align | Qt.AlignmentFlag.AlignVCenter,
            resolved.row.text or "",
        )
        return False

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
        phase = float(getattr(ctx.widget, "_marquee_phase", 0.0) or 0.0)
        return RowsContent._draw_resolved(
            p,
            RowsContent._resolve_row(
                row,
                ctx,
                style,
                tm,
                padded_x=padded_x,
                padded_w=padded_w,
                full_x=full_x,
                full_w=full_w,
                y=y,
                height=height,
            ),
            phase,
        )


@dataclass
class PixmapContent(Content):
    """Full-bleed photographic image for a region (cover/contain/stretch).

    Unlike ``IconContent``, this ignores ``content_padding`` and ``icon_size`` —
    the image fills ``ctx.effective_rect``. When ``region_corner_radii`` is set,
    the draw is clipped to that rounded path (crop radii for cards).
    """

    pixmap: Any = None
    image_fill: ImageFill = "cover"

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
            from PySide6.QtGui import QPainter as _QP
            from .layers.background import rounded_rect_path

            # Smooth clip: without AA the rounded clip leaves stair-step
            # fringe pixels in the corners (visible as dirt on thumbs).
            p.setRenderHint(_QP.RenderHint.Antialiasing, True)
            clip = rounded_rect_path(QRectF(dest), radii)
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
            scaled_px(ctx.region_icon_size_px)
            if ctx.region_icon_size_px is not None
            else (read_widget_style(ctx.widget).icon_size_px or ctx.effective_icon_size_px)
        )
        pixmap = normalized_icon_pixmap(current, icon_size)
        x = rect.x() + (rect.width() - icon_size) // 2
        y = rect.y() + (rect.height() - icon_size) // 2
        p.drawPixmap(x, y, pixmap)


def build_button_content(button) -> "Content | None":
    """Content for the button's ``_main`` region, from its own text/icon/rows state."""
    if button._rows:
        return RowsContent(rows=button._rows, compact=button._rows_compact)
    if button._has_text and button._text and button._icon_unchecked:
        return IconTextContent(icon=button._icon_unchecked, text=button._text)
    if button._has_text and button._text:
        return TextContent(text=button._text)
    if button._icon_unchecked or button._icon_checked:
        return IconContent(icon_unchecked=button._icon_unchecked, icon_checked=button._icon_checked)
    return None


def build_region_content(button, region) -> "Content | None":
    """Content for one multi-region button's region, from its own field set."""
    rows = region.rows or []
    if rows:
        return RowsContent(rows=rows, compact=button._rows_compact)
    pixmap = getattr(region, "pixmap", None)
    if pixmap is not None:
        return PixmapContent(
            pixmap=pixmap,
            image_fill=getattr(region, "image_fill", "cover") or "cover",
        )
    icon = region.icon
    if isinstance(icon, (tuple, list)) and len(icon) >= 2:
        icon_unchecked, icon_checked = icon[0], icon[1]
    else:
        icon_unchecked = icon_checked = icon
    if region.text and icon_unchecked:
        return IconTextContent(icon=icon_unchecked, text=region.text)
    if region.text:
        return TextContent(text=region.text)
    if icon_unchecked or icon_checked:
        return IconContent(icon_unchecked=icon_unchecked, icon_checked=icon_checked)
    return None


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
            scaled_px(ctx.region_icon_size_px)
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
        text_w = max(0, int(rect.right()) - text_x + 1)
        elided = p.fontMetrics().elidedText(self.text, Qt.TextElideMode.ElideRight, text_w)
        p.drawText(
            QRect(text_x, int(rect.y()), text_w, int(rect.height())),
            text_v | Qt.AlignmentFlag.AlignLeft,
            elided,
        )
