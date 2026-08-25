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

# P2: shared ticker for all MarqueeDrivers + cached text widths
_shared_timer: QTimer | None = None
_shared_drivers: set["MarqueeDriver"] = set()
_marquee_width_cache: dict[tuple[str, int, int], int] = {}


def _cached_text_width(font_metrics: QFontMetrics, text: str) -> int:
    """Cached horizontalAdvance (keyed by text + font metrics height)."""
    try:
        h = int(font_metrics.height())
        acw = int(font_metrics.averageCharWidth())
        cache_key = (text, h, acw)
    except Exception:
        cache_key = (text, 0, 0)  # type: ignore[assignment]
    hit = _marquee_width_cache.get(cache_key)  # type: ignore[arg-type]
    if hit is not None:
        return hit
    w = int(font_metrics.horizontalAdvance(text))
    # bound cache size
    if len(_marquee_width_cache) > 512:
        _marquee_width_cache.clear()
    _marquee_width_cache[cache_key] = w  # type: ignore[index]
    return w


def text_overflows(font_metrics: QFontMetrics, text: str, avail_width: int) -> bool:
    if avail_width <= 0 or not text:
        return False
    return _cached_text_width(font_metrics, text) > avail_width


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
    text_w = _cached_text_width(fm, text)
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


def _ensure_shared_timer() -> QTimer:
    global _shared_timer
    if _shared_timer is not None:
        return _shared_timer
    from PySide6.QtWidgets import QApplication as _QA

    app = _QA.instance()
    parent = app if app is not None else None
    t = QTimer(parent)  # type: ignore[arg-type]
    t.setInterval(DEFAULT_MARQUEE_INTERVAL_MS)
    t.timeout.connect(_shared_tick)  # type: ignore[arg-type]
    _shared_timer = t
    return t


def _shared_tick() -> None:
    for drv in list(_shared_drivers):
        try:
            drv._tick()
        except RuntimeError:
            _shared_drivers.discard(drv)


def _shared_set_active(driver: "MarqueeDriver", active: bool) -> None:
    if active:
        _shared_drivers.add(driver)
        t = _ensure_shared_timer()
        if not t.isActive():
            t.start()
    else:
        _shared_drivers.discard(driver)
        if not _shared_drivers and _shared_timer is not None and _shared_timer.isActive():
            _shared_timer.stop()


class MarqueeDriver(QObject):
    """Owns scroll phase + shared ticker for a host widget that repaints on tick."""

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
        self._interval_ms = max(1, int(interval_ms))
        self._on_tick = on_tick
        self.phase = 0.0
        self._clock = QElapsedTimer()
        self._active = False
        # Mirror onto the host so paint paths can read ``host._marquee_phase``.
        setattr(host, "_marquee_phase", 0.0)
        setattr(host, "_marquee_driver", self)
        # keep a compat alias for code that checks driver._timer
        self._timer = _ensure_shared_timer()

    def set_active(self, needed: bool) -> None:
        if needed and self._host.isVisible():
            if not self._active:
                self._clock.restart()
                _shared_set_active(self, True)
                self._active = True
            return
        if self._active:
            _shared_set_active(self, False)
            self._active = False
            if self.phase != 0.0:
                self.phase = 0.0
                setattr(self._host, "_marquee_phase", 0.0)
                self._host.update()

    def _tick(self) -> None:
        elapsed_ms = self._clock.restart()
        if elapsed_ms <= 0:
            elapsed_ms = max(1, int(self._interval_ms))
        # if the driver was just (re)started, elapsed may be huge on first tick
        # after a long idle — clamp to 2 intervals to avoid a jump
        elapsed_ms = min(elapsed_ms, self._interval_ms * 2)
        self.phase += (self._speed * elapsed_ms) / 1000.0
        setattr(self._host, "_marquee_phase", self.phase)
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
