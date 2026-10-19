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


def wrapped_line_count(font: QFont, text: str, max_width: int) -> int:
    """Number of word-wrapped lines ``text`` takes at ``max_width`` pixels.

    Reuses the toolkit's plain-text layout engine (``build_layout``, the same
    ``QTextLayout``/``WordWrap`` path the ``Text`` widget uses) instead of
    re-implementing word breaking, so the measured count matches what Qt
    paints for a row drawn with ``Qt.TextFlag.TextWordWrap``. Returns 1 for
    empty text or a non-positive width.

    The import is function-local: ``text`` transitively imports the buttons
    package, so importing it at module scope here would deadlock the cycle.
    """
    if not text:
        return 1
    from sli_ui_toolkit.ui.widgets.text.plain import build_layout

    layout = build_layout(
        text, font, max(1, int(max_width)), True, Qt.AlignmentFlag.AlignLeft
    )
    return max(1, layout.lineCount())


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


def resolve_content_insets(
    padding: tuple[float, float, float, float],
) -> tuple[int, int, int, int]:
    """Design-px ``content_padding`` → live scaled insets (left, top, right, bottom).

    ``content_padding`` is a host-facing design-px value, so it must grow with
    the interface scale like every other chrome metric — resolved through
    ``scaled_px`` at USE time (paint / sizeHint) instead of being cached at
    construction. A zero inset stays zero: ``scaled_px`` clamps to a minimum
    of 1, which would turn "no inset" into a 1px one.
    """
    left, top, right, bottom = padding
    return (
        0 if left <= 0 else scaled_px(left),
        0 if top <= 0 else scaled_px(top),
        0 if right <= 0 else scaled_px(right),
        0 if bottom <= 0 else scaled_px(bottom),
    )


def resolve_gap_px(design_gap: int) -> int:
    """Design-px icon↔label ``gap`` → live scaled px (0 stays 0)."""
    return 0 if design_gap <= 0 else scaled_px(design_gap)


def _rect(ctx: DrawContext) -> QRect:
    raw = ctx.effective_rect
    rect = raw.toAlignedRect() if isinstance(raw, QRectF) else QRect(raw)
    left, top, right, bottom = resolve_content_insets(ctx.content_padding)
    if left or top or right or bottom:
        rect = rect.adjusted(left, top, -right, -bottom)
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
    # When True (and marquee is False) and the text is wider than the row,
    # truncate with an ellipsis via QFontMetrics.elidedText instead of
    # clipping. Static paint, no timers.
    elide: bool = False
    # Opt-in word wrap. When True the row breaks the text across multiple
    # lines at word boundaries within the region's available width instead of
    # clipping/overflowing on one line; the row reserves the extra line
    # height (``RowsContent.measure_height``), so the region/Button can grow
    # via the usual sizeHint/minimumSizeHint path. Default False keeps the
    # historic single-line rendering and metrics exactly.
    wrap: bool = False
    # Declarative translation key for this row. When set, a bound translator
    # (see ``install_translator`` / ``bind_translator``) re-resolves the row's
    # painted text on every language change; the key wins over ``text`` on each
    # retranslate and a miss paints the key itself (never silent English).
    text_key: str | None = None


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
        """Yield ``(row, y, height)`` in paint order.

        Compact mode and any content with a wrapping row use stacked natural
        heights; otherwise the historic ratio distribution is kept verbatim.
        """
        if self.compact or self.has_wrap:
            heights = []
            for row in self.rows:
                f = ui_font(pixel_size=row.size, bold=(row.weight == "bold"))
                fm = QFontMetrics(f)
                if getattr(row, "wrap", False):
                    lines = wrapped_line_count(f, row.text or "", padded.width())
                else:
                    lines = 1
                heights.append(lines * fm.lineSpacing())
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

    @property
    def has_wrap(self) -> bool:
        """True when any row opted into word wrap."""
        return any(getattr(row, "wrap", False) for row in self.rows)

    def measure_height(self, width: int) -> int:
        """Natural pixel height needed to paint every row within ``width``.

        Wrapping rows reserve ``lines × lineSpacing``; non-wrapping rows one
        line. Row gaps included. ``Button`` uses this (via its size hints) to
        grow the region so wrapped text is never clipped.
        """
        total = 0
        for row in self.rows:
            f = ui_font(pixel_size=row.size, bold=(row.weight == "bold"))
            fm = QFontMetrics(f)
            if getattr(row, "wrap", False):
                lines = wrapped_line_count(f, row.text or "", width)
            else:
                lines = 1
            total += lines * fm.lineSpacing()
        total += self.row_gap * max(0, len(self.rows) - 1)
        return total

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
        text = resolved.row.text or ""
        RowsContent._paint_static_text(p, resolved, text)
        return False

    @staticmethod
    def _paint_static_text(p: QPainter, resolved: _ResolvedRow, text: str) -> None:
        """Paint a non-marquee row: word-wrapped, elided, or plain single line.

        Shared by the hot draw path and the compat shim so both stay
        pixel-identical by construction. The font is (re)set here so this
        function owns a scale-resolved font for the text paint scan.
        """
        p.setFont(resolved.font)
        p.setPen(resolved.pen)
        row = resolved.row
        if bool(getattr(row, "wrap", False)):
            # Qt-native word wrap: breaks at word boundaries within the row
            # rect and vertically centers the wrapped block. The row height
            # is reserved by ``_row_layout``/``measure_height``.
            flags = (
                int(resolved.h_align)
                | int(Qt.AlignmentFlag.AlignVCenter)
                | int(Qt.TextFlag.TextWordWrap)
            )
            p.drawText(resolved.rect, flags, text)
            return
        if bool(getattr(row, "elide", False)):
            text = p.fontMetrics().elidedText(
                text, Qt.TextElideMode.ElideRight, max(0, resolved.rect.width())
            )
        p.drawText(
            resolved.rect,
            int(resolved.h_align) | int(Qt.AlignmentFlag.AlignVCenter),
            text,
        )

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
        # Compat shim (no in-tree callers): resolves + paints one row through
        # the same resolve/paint path as the ``draw()`` hot path
        # (``_resolve_row`` + ``_paint_static_text``), so both stay
        # pixel-identical by construction.
        resolved = RowsContent._resolve_row(
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
        )
        p.setFont(resolved.font)
        p.setPen(resolved.pen)
        if resolved.marquee_active:
            phase = float(getattr(ctx.widget, "_marquee_phase", 0.0) or 0.0)
            draw_marquee_text(p, resolved.rect, resolved.row.text or "", phase)
            return True
        text = resolved.row.text or ""
        RowsContent._paint_static_text(p, resolved, text)
        return False


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

        gap = resolve_gap_px(int(getattr(ctx, "gap_px", 6) or 6))
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
