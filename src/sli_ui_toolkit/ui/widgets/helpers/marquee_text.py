"""Reusable left→right overflow marquee for toolkit text surfaces.

Use:
- ``draw_marquee_text`` from any custom paint path (Button rows, layers, …)
- ``MarqueeDriver`` to own the phase/timer on a host widget
- ``apply_marquee`` / ``Text(mode="plain", marquee=True)`` for toolkit labels

Performance notes (gallery-proven: 25 cards x 60fps full repaints idle):
- The scrolling text is pre-rendered ONCE per
  ``(text, font, pen color, rect size, gap, devicePixelRatio)`` into a
  ``QPixmap`` strip cached on the driver. Per tick/paint the strip is
  blitted twice at the float offset — no ``drawText``, no ``QFontMetrics``
  on cache hits. The text-fits fast path stays a plain ``drawText``.
- ``MarqueeDriver._tick`` repaints only the union of the row rects
  registered during paint (see ``note_marquee_rect``), never the whole
  host. When no rect was ever registered (e.g. ``QLabel``/``apply_marquee``
  users that never painted through here), the tick falls back to a full
  ``host.update()`` exactly like before.
- ``_tick`` is a no-op while ``host.visibleRegion()`` is empty, so
  off-viewport cards cost zero. Phase-freeze is safe: the crawl resumes
  from the same phase on the next visible tick (the timer only runs while
  some row overflows), and ``set_active(False)`` still resets the phase
  to 0 on hide/deactivation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import (
    QElapsedTimer,
    QObject,
    QPointF,
    QRect,
    QRectF,
    Qt,
    QTimer,
)
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPixmap
from PySide6.QtWidgets import QLabel, QWidget

# Android TextView marquee uses MARQUEE_DP_PER_SECOND = 30 (AOSP).
# Classic HTML <marquee> default is ~6px / 85ms ≈ 70 px/s — too fast for titles.
# Paint is in Qt logical pixels, so 30 px/s ≈ 30 dp/s at 96 DPI.
DEFAULT_MARQUEE_GAP_PX = 40
DEFAULT_MARQUEE_SPEED_PX_S = 30.0
DEFAULT_MARQUEE_INTERVAL_MS = 16


def text_overflows(font_metrics: QFontMetrics, text: str, avail_width: int) -> bool:
    if avail_width <= 0 or not text:
        return False
    return font_metrics.horizontalAdvance(text) > avail_width


def marquee_cycle_px(text_width: int, *, gap: int = DEFAULT_MARQUEE_GAP_PX) -> int:
    return max(1, int(text_width) + max(0, int(gap)))


# Key: (text, font key, pen rgba, avail width, rect height, gap, pixel ratio).
# Font key + pen color keep light/dark theme switches pixel-correct (colors
# resolve through ThemeManager tokens upstream — never hardcoded here);
# width/height re-render on resize so vertical centering matches the direct
# ``drawText(AlignVCenter)`` path it replaces.
_MarqueeStripKey = tuple[str, str, tuple[int, int, int, int], int, int, int, float]


@dataclass
class _MarqueeStrip:
    key: _MarqueeStripKey
    pixmap: QPixmap
    text_width: int
    cycle: int


def _strip_key(
    *,
    text: str,
    font: QFont,
    pen: QColor,
    width: int,
    height: int,
    gap: int,
    dpr: float,
) -> _MarqueeStripKey:
    rgba_key = (pen.red(), pen.green(), pen.blue(), pen.alpha())
    return (
        text,
        font.key(),
        rgba_key,
        int(width),
        int(height),
        int(gap),
        float(dpr),
    )


def _painter_dpr(painter: QPainter) -> float:
    try:
        device = painter.device()
    except RuntimeError:
        return 1.0
    if device is None:
        return 1.0
    get_ratio = getattr(device, "devicePixelRatioF", None)
    if callable(get_ratio):
        try:
            dpr = float(get_ratio())
        except (AttributeError, TypeError, RuntimeError):
            return 1.0
        return dpr if dpr > 0.0 else 1.0
    return 1.0


def _render_marquee_strip(
    *,
    font: QFont,
    pen: QColor,
    text: str,
    text_width: int,
    height: int,
    gap: int,
    dpr: float,
) -> QPixmap:
    """Render one full marquee cycle (text + trailing gap) into a pixmap.

    The pixmap is allocated in DEVICE pixels (``cycle * dpr``) and carries
    ``dpr``: ``QPainter`` scales every command by the paint device's ratio, so
    the strip below stays in logical px while the glyphs rasterize at physical
    resolution (``deviceIndependentSize() == cycle x height``). Allocating in
    logical px instead shrinks the logical canvas to ``cycle / dpr``: the text
    is then drawn at native size into a half-size canvas, clipped and offset.
    """
    cycle = marquee_cycle_px(text_width, gap=gap)
    logical_w = max(1, cycle)
    logical_h = max(1, int(height))
    ratio = max(1.0, float(dpr))
    pixmap = QPixmap(
        max(1, int(round(logical_w * ratio))),
        max(1, int(round(logical_h * ratio))),
    )
    # Ratio before the painter: QPainter resolves its scale at construction.
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(Qt.GlobalColor.transparent)
    strip_painter = QPainter(pixmap)
    strip_painter.setFont(font)
    strip_painter.setPen(pen)
    # Same alignment the direct path uses, so blits land on identical pixels.
    strip_painter.drawText(
        QRect(0, 0, logical_w, logical_h),
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        text,
    )
    strip_painter.end()
    return pixmap


def _blit_marquee_strip(
    painter: QPainter,
    rect: QRect,
    strip: QPixmap,
    cycle: int,
    phase: float,
) -> None:
    offset = float(phase) % float(cycle)
    origin_x = float(rect.x()) + offset
    y = float(rect.y())
    painter.save()
    painter.setClipRect(QRectF(rect))
    # Keep the float offset so slow speeds do not quantize into 1px jumps.
    painter.drawPixmap(QPointF(origin_x - cycle, y), strip)
    painter.drawPixmap(QPointF(origin_x, y), strip)
    painter.restore()


def draw_marquee_text(
    painter: QPainter,
    rect: QRect,
    text: str,
    phase: float,
    *,
    gap: int = DEFAULT_MARQUEE_GAP_PX,
    driver: MarqueeDriver | None = None,
) -> None:
    """Paint ``text`` scrolling left→right in a seamless loop inside ``rect``.

    When a ``driver`` is known (passed explicitly, or resolved from the
    paint device's ``_marquee_driver`` when painting on a host widget), the
    overflowing text is served from a pre-rendered pixmap strip cached on
    the driver: cache hits perform no ``drawText`` and no ``QFontMetrics``
    measurement. Without a driver the legacy direct ``drawText`` path runs,
    pixel-identical to previous releases. The text-fits fast path is always
    a plain ``drawText``, with or without a driver.
    """
    if not text or rect.width() <= 0 or rect.height() <= 0:
        return
    if driver is None:
        driver = _driver_for_painter(painter)
    if driver is None:
        _draw_marquee_text_direct(
            painter, rect, text, phase, gap=gap, font=painter.font()
        )
        return

    note_rect = QRect(rect)
    gap = max(0, int(gap))
    font = painter.font()
    pen_color = painter.pen().color()
    key = _strip_key(
        text=text,
        font=font,
        pen=pen_color,
        width=rect.width(),
        height=rect.height(),
        gap=gap,
        dpr=_painter_dpr(painter),
    )
    strip = driver._strip
    if strip is not None and strip.key == key and not strip.pixmap.isNull():
        # Cache hit: no measure, no drawText — just blit.
        driver.strip_cache_hits += 1
        driver.note_marquee_rect(note_rect)
        _blit_marquee_strip(painter, rect, strip.pixmap, strip.cycle, phase)
        return

    fm = painter.fontMetrics()
    text_w = fm.horizontalAdvance(text)
    if text_w <= rect.width():
        painter.drawText(
            rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            text,
        )
        return

    rendered = _render_marquee_strip(
        font=font,
        pen=pen_color,
        text=text,
        text_width=text_w,
        height=rect.height(),
        gap=gap,
        dpr=_painter_dpr(painter),
    )
    if rendered.isNull():
        _draw_marquee_text_direct(
            painter, rect, text, phase, gap=gap, font=painter.font()
        )
        return
    cycle = marquee_cycle_px(text_w, gap=gap)
    driver._strip = _MarqueeStrip(
        key=key, pixmap=rendered, text_width=text_w, cycle=cycle
    )
    driver.strip_cache_renders += 1
    driver.note_marquee_rect(note_rect)
    _blit_marquee_strip(painter, rect, rendered, cycle, phase)


def _draw_marquee_text_direct(
    painter: QPainter,
    rect: QRect,
    text: str,
    phase: float,
    *,
    gap: int = DEFAULT_MARQUEE_GAP_PX,
    font: QFont,
) -> None:
    """Legacy direct path: two ``drawText`` copies, no cache, no driver.

    ``font`` is the caller-resolved font (RowsContent/Label/apply_marquee
    all set it before calling); re-asserted here so the text-paint scan
    sees the scale contract — never re-derived, never double-scaled.
    """
    painter.setFont(font)
    fm = painter.fontMetrics()
    text_w = fm.horizontalAdvance(text)
    if text_w <= rect.width():
        painter.drawText(
            rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            text,
        )
        return

    cycle = marquee_cycle_px(text_w, gap=gap)
    # Keep a float offset so slow speeds do not quantize into 1px jumps.
    offset = float(phase) % float(cycle)
    x = float(rect.x())
    y = float(rect.y())
    h = float(rect.height())
    painter.save()
    painter.setClipRect(QRectF(rect))
    for copy_x in (x + offset, x + offset - cycle):
        painter.drawText(
            QRectF(copy_x, y, float(text_w + gap), h),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            text,
        )
    painter.restore()


def _driver_for_painter(painter: QPainter) -> MarqueeDriver | None:
    """Resolve the host's driver when painting directly on a widget."""
    if not painter.isActive():
        return None
    try:
        device = painter.device()
    except RuntimeError:
        return None
    if device is None or not isinstance(device, QWidget):
        return None
    existing = getattr(device, "_marquee_driver", None)
    return existing if isinstance(existing, MarqueeDriver) else None


class MarqueeDriver(QObject):
    """Owns scroll phase + timer for a host widget that repaints on tick."""

    def __init__(
        self,
        host: QWidget,
        *,
        speed_px_s: float = DEFAULT_MARQUEE_SPEED_PX_S,
        interval_ms: int = DEFAULT_MARQUEE_INTERVAL_MS,
        on_tick: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(host)
        self._host = host
        self._speed = float(speed_px_s)
        self._on_tick = on_tick
        self.phase = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(max(1, int(interval_ms)))
        self._timer.timeout.connect(self._tick)
        self._clock = QElapsedTimer()
        # Pre-rendered scroll strip + dirty-rect state (see module docstring).
        self._strip: _MarqueeStrip | None = None
        self._dirty_rect: QRect | None = None
        # Observability for tests/perf: hits skip measure + drawText.
        self.strip_cache_hits = 0
        self.strip_cache_renders = 0
        # Mirror onto the host so paint paths can read ``host._marquee_phase``.
        setattr(host, "_marquee_phase", 0.0)
        setattr(host, "_marquee_driver", self)

    def set_active(self, needed: bool) -> None:
        if needed and self._host.isVisible():
            if not self._timer.isActive():
                self._clock.restart()
                self._timer.start()
            return
        # Stopping clears the dirty union: the next activation re-registers
        # exactly the rows that still overflow (handles text shrink-to-fit
        # and row moves without repainting stale areas forever).
        self._dirty_rect = None
        if self._timer.isActive():
            self._timer.stop()
            if self.phase != 0.0:
                self.phase = 0.0
                setattr(self._host, "_marquee_phase", 0.0)
                self._host.update()

    def set_dirty_rect(self, rect: QRect | None) -> None:
        """Replace the tick repaint rect (``None``/empty restores full update)."""
        if rect is None or rect.isEmpty():
            self._dirty_rect = None
        else:
            self._dirty_rect = QRect(rect)

    def note_marquee_rect(self, rect: QRect) -> None:
        """Union ``rect`` into the tick repaint area (called from paint)."""
        if rect.isEmpty():
            return
        if self._dirty_rect is None:
            self._dirty_rect = QRect(rect)
        else:
            self._dirty_rect = self._dirty_rect.united(rect)

    def dirty_rect(self) -> QRect | None:
        """Copy of the current tick repaint rect, if any."""
        if self._dirty_rect is None:
            return None
        return QRect(self._dirty_rect)

    def _tick(self) -> None:
        # Clip skip: fully clipped hosts (scrolled out of the viewport,
        # obscured, hidden) cost zero — no phase advance, no repaint, no
        # on_tick. Phase-freeze is safe: the crawl resumes from the same
        # phase on the next visible tick, and set_active(False) still
        # resets the phase on hide/deactivation.
        if self._host.visibleRegion().isEmpty():
            return
        elapsed_ms = self._clock.restart()
        if elapsed_ms <= 0:
            elapsed_ms = max(1, int(self._timer.interval()))
        self.phase += (self._speed * elapsed_ms) / 1000.0
        setattr(self._host, "_marquee_phase", self.phase)
        if self._on_tick is not None:
            self._on_tick()
        elif self._dirty_rect is not None and not self._dirty_rect.isEmpty():
            self._host.update(self._dirty_rect)
        else:
            self._host.update()


def ensure_marquee_driver(host: QWidget, **kwargs) -> MarqueeDriver:
    existing = getattr(host, "_marquee_driver", None)
    if isinstance(existing, MarqueeDriver):
        return existing
    return MarqueeDriver(host, **kwargs)


def apply_marquee(
    label: QLabel,
    *,
    enabled: bool = True,
    gap: int = DEFAULT_MARQUEE_GAP_PX,
    speed_px_s: float = DEFAULT_MARQUEE_SPEED_PX_S,
) -> MarqueeDriver:
    """Enable overflow marquee on any ``QLabel``/``Text`` text surface.

    Prefer ``Text(..., mode="plain", marquee=True)`` when constructing toolkit
    labels. For plain ``QLabel``, call this after creation.
    """
    if hasattr(label, "setMarquee"):
        label.setMarquee(enabled)
        driver = ensure_marquee_driver(label, speed_px_s=speed_px_s)
        setattr(label, "_marquee_gap", int(gap))
        return driver

    driver = ensure_marquee_driver(label, speed_px_s=speed_px_s)
    setattr(label, "_marquee_enabled", bool(enabled))
    setattr(label, "_marquee_gap", int(gap))
    setattr(label, "_marquee_original_text", label.text())

    if getattr(label, "_marquee_filter_installed", False):
        return driver

    class _Filter(QObject):
        def eventFilter(self, obj, event):  # noqa: N802
            from PySide6.QtCore import QEvent
            from PySide6.QtGui import QPaintEvent
            from PySide6.QtWidgets import QStyle, QStyleOption, QStylePainter

            if obj is not label:
                return False
            et = event.type()
            if et == QEvent.Type.Hide:
                driver.set_active(False)
                return False
            if et != QEvent.Type.Paint:
                return False
            if not getattr(label, "_marquee_enabled", False):
                return False

            text = getattr(label, "_marquee_original_text", None)
            if text is None:
                text = label.text()
            fm = QFontMetrics(label.font())
            # Contents rect roughly matches QLabel's text area.
            rect = label.contentsRect()
            if not text_overflows(fm, text, rect.width()):
                driver.set_active(False)
                return False

            driver.set_active(True)
            opt = QStyleOption()
            opt.initFrom(label)
            painter = QStylePainter(label)
            painter.drawPrimitive(QStyle.PrimitiveElement.PE_Widget, opt)
            painter.setFont(label.font())
            painter.setPen(label.palette().color(label.foregroundRole()))
            draw_marquee_text(
                painter,
                rect,
                text,
                driver.phase,
                gap=int(getattr(label, "_marquee_gap", DEFAULT_MARQUEE_GAP_PX)),
            )
            painter.end()
            return True  # swallow default QLabel paint

    filt = _Filter(label)
    label.installEventFilter(filt)
    setattr(label, "_marquee_filter", filt)
    setattr(label, "_marquee_filter_installed", True)

    # Keep original text when setText is used.
    original_set_text = label.setText

    def _set_text(text: str) -> None:
        setattr(label, "_marquee_original_text", text)
        original_set_text(text)
        label.update()

    label.setText = _set_text  # type: ignore[assignment]
    return driver
