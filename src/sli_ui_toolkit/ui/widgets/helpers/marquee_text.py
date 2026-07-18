"""Reusable left→right overflow marquee for toolkit text surfaces.

Use:
- ``draw_marquee_text`` from any custom paint path (Button rows, layers, …)
- ``MarqueeDriver`` to own the phase/timer on a host widget
- ``apply_marquee`` / ``Label(marquee=True)`` for ``QLabel``-based text
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QElapsedTimer, QObject, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QFontMetrics, QPainter
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


def draw_marquee_text(
    painter: QPainter,
    rect: QRect,
    text: str,
    phase: float,
    *,
    gap: int = DEFAULT_MARQUEE_GAP_PX,
) -> None:
    """Paint ``text`` scrolling left→right in a seamless loop inside ``rect``."""
    if not text or rect.width() <= 0 or rect.height() <= 0:
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
        # Mirror onto the host so paint paths can read ``host._marquee_phase``.
        host._marquee_phase = 0.0
        host._marquee_driver = self

    def set_active(self, needed: bool) -> None:
        if needed and self._host.isVisible():
            if not self._timer.isActive():
                self._clock.restart()
                self._timer.start()
            return
        if self._timer.isActive():
            self._timer.stop()
            if self.phase != 0.0:
                self.phase = 0.0
                self._host._marquee_phase = 0.0
                self._host.update()

    def _tick(self) -> None:
        elapsed_ms = self._clock.restart()
        if elapsed_ms <= 0:
            elapsed_ms = max(1, int(self._timer.interval()))
        self.phase += (self._speed * elapsed_ms) / 1000.0
        self._host._marquee_phase = self.phase
        if self._on_tick is not None:
            self._on_tick()
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
    """Enable overflow marquee on any ``QLabel`` (including toolkit ``Label``).

    Prefer ``Label(..., marquee=True)`` when constructing toolkit labels.
    For plain ``QLabel``, call this after creation.
    """
    if hasattr(label, "setMarquee"):
        label.setMarquee(enabled)
        driver = ensure_marquee_driver(label, speed_px_s=speed_px_s)
        label._marquee_gap = int(gap)
        return driver

    driver = ensure_marquee_driver(label, speed_px_s=speed_px_s)
    label._marquee_enabled = bool(enabled)
    label._marquee_gap = int(gap)
    label._marquee_original_text = label.text()

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
    label._marquee_filter = filt
    label._marquee_filter_installed = True

    # Keep original text when setText is used.
    original_set_text = label.setText

    def _set_text(text: str) -> None:
        label._marquee_original_text = text
        original_set_text(text)
        label.update()

    label.setText = _set_text  # type: ignore[method-assign]
    return driver
