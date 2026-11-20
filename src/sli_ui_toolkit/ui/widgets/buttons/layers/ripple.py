"""RippleLayer — материал-стайл волна от точки клика.

Поддерживает два режима окрашивания:

1. **Overlay (по умолчанию):** полупрозрачная тёмная/светлая «прослойка» —
   как в текущем M3-state-layer.
2. **Gradient:** при вызове `trigger(pos, color_from=A, color_to=B)` волна
   интерполирует цвет от A к B по ходу прогресса. Удобно для перехода между
   статусами кнопки (hover → checked, default → pressed и т.п.).

State хранится на самой кнопке в `_ripple: RippleEffect`. Layer стейтлесс,
читает состояние из `ctx.widget`.

Время волны — настенное (`QElapsedTimer`), не счётчик тиков: между тиками
может пройти больше интервала (тяжёлый слот, разметка, медленная покраска), и
счётчик тиков добавлял это отставание к длительности волны. Геометрия и фазы —
по референсным реализациям Material 3 (Compose `RippleAnimation`, Flutter
`InkRipple`): старт `0.3 x длинная сторона`, конец — полдиагонали от центра
(+10 dp), центр едет от точки нажатия к центру контрола, фазы 75 / 225 / 150 мс.
Длинная сторона растягивает фазу расширения (225…450 мс), иначе край на
широком контроле прыгает ~90 px за кадр, и край рисуется мягким градиентом.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QElapsedTimer, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QRadialGradient
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.managers.ui_scale import scaled_px

from ..context import DrawContext
from ._base import Layer


#: Material 3 ripple phases (Compose `RippleAnimation`, Flutter `InkRipple`):
#: fade in 75 ms, expand 225 ms, fade out 150 ms. The expand length is the
#: host-facing knob (`set_ripple_duration_ms`); the two fades are fixed.
FADE_IN_MS = 75
FADE_OUT_MS = 150
#: Compose starts the wave at `0.3 x longest side` and ends it at half the
#: diagonal (+ padding) — a circle measured from the CENTRE. This layer used
#: to grow from the press point to the farthest corner instead, which makes
#: the edge of a long control travel its whole width in the same time (a
#: 1200 px button moved the edge ~100 px per 60 Hz frame: it read as two
#: strobing fronts rather than a wave).
START_RADIUS_FRACTION = 0.30
END_RADIUS_PAD_DP = 10.0
#: The reference implementations animate the expansion in a fixed 225 ms
#: because their surfaces are phone-sized. On a desktop-wide control the same
#: 225 ms sweeps the whole width and the edge teleports ~90 px per frame; the
#: expansion therefore stretches with the swept distance, inside the window
#: the platform implementations themselves use (M3 225 ms … Android views
#: 450 ms) and never faster than this many px per ms.
EXPAND_PX_PER_MS = 1.9
MAX_EXPAND_MS = 450
#: The outer fraction of the radius that fades to transparent. A hard 1 px
#: edge sampled at 60 Hz shows its previous position next to the current one
#: once it moves more than ~25 px per frame; a soft rim reads as a wash.
SOFT_EDGE_FRACTION = 0.85


def _bezier_axis(t: float, c1: float, c2: float) -> float:
    u = 1.0 - t
    return 3.0 * u * u * t * c1 + 3.0 * u * t * t * c2 + t * t * t


def ease_out_slow_in(progress: float) -> float:
    """Cubic-bezier(0.4, 0, 0.2, 1) — the M3 ripple expansion curve."""
    p = max(0.0, min(1.0, progress))
    if p <= 0.0:
        return 0.0
    if p >= 1.0:
        return 1.0
    lo, hi = 0.0, 1.0
    for _ in range(24):
        t = (lo + hi) / 2.0
        if _bezier_axis(t, 0.4, 0.2) < p:
            lo = t
        else:
            hi = t
    return _bezier_axis((lo + hi) / 2.0, 0.0, 1.0)


def wave_alpha(elapsed_ms: float, expand_ms: float) -> float:
    """Overlay opacity for the three M3 phases as a function of wall time."""
    t = max(0.0, elapsed_ms)
    if t < FADE_IN_MS:
        return t / FADE_IN_MS
    if t <= expand_ms:
        return 1.0
    return max(0.0, 1.0 - (t - expand_ms) / FADE_OUT_MS)


def wave_geometry(
    press: QPointF, rect: QRectF, progress: float, *, pad_px: float = 0.0
) -> tuple[QPointF, float]:
    """Centre and radius of the wave at ``progress`` (bounded M3 ripple).

    The radius interpolates from ``START_RADIUS_FRACTION`` of the long side to
    half the diagonal, while the centre slides from the press point to the
    rect's centre — so a long control ends with one centred circle instead of
    two fronts racing to the ends.
    """
    p = max(0.0, min(1.0, progress))
    start = START_RADIUS_FRACTION * max(rect.width(), rect.height())
    end = math.hypot(rect.width(), rect.height()) / 2.0 + pad_px
    radius = start + (end - start) * ease_out_slow_in(p)
    centre = rect.center()
    return (
        QPointF(
            press.x() + (centre.x() - press.x()) * p,
            press.y() + (centre.y() - press.y()) * p,
        ),
        radius,
    )


def _soft_disc(center: QPointF, radius: float, color: QColor) -> QRadialGradient:
    """Radial brush that fades the outer ``SOFT_EDGE_FRACTION`` of the disc.

    A hard edge sampled at 60 Hz shows as two positions once it moves more
    than ~25 px per frame; the soft rim turns the same step into a moving
    gradient band (the edge width scales with the radius).
    """
    gradient = QRadialGradient(center, max(0.01, float(radius)))
    gradient.setColorAt(0.0, color)
    gradient.setColorAt(SOFT_EDGE_FRACTION, color)
    edge = QColor(color)
    edge.setAlpha(0)
    gradient.setColorAt(1.0, edge)
    return gradient


def _lerp_color(a: QColor, b: QColor, t: float) -> QColor:
    t = max(0.0, min(1.0, t))
    return QColor(
        int(a.red() + (b.red() - a.red()) * t),
        int(a.green() + (b.green() - a.green()) * t),
        int(a.blue() + (b.blue() - a.blue()) * t),
        int(a.alpha() + (b.alpha() - a.alpha()) * t),
    )


class RippleEffect:
    # Class attribute kept in sync by ``set_ripple_duration_ms``; prefer
    # ``get_ripple_duration_ms()`` for new code. This is the EXPANSION phase
    # (the M3 `RadiusDuration`); the fade in/out phases are fixed.
    DURATION_MS = 225
    # 8 ms samples the wall clock finer than a 60 Hz frame, and because
    # ``update()`` coalesces, extra ticks never cost an extra paint — they
    # only remove the 62.5-vs-60 Hz beat a 16 ms timer produced.
    TICK_MS = 8
    PEAK_ALPHA_LIGHT = 31
    PEAK_ALPHA_DARK = 41

    def __init__(self, widget: QWidget) -> None:
        self._widget = widget
        self._timer = QTimer(widget)
        self._timer.setInterval(self.TICK_MS)
        self._timer.timeout.connect(self._on_tick)
        self._clock = QElapsedTimer()
        self._elapsed = 0
        self._expand_ms = self._duration_ms()
        self._center: QPointF | None = None
        self._color_from: QColor | None = None
        self._color_to: QColor | None = None

    def _duration_ms(self) -> int:
        from sli_ui_toolkit.ui.widgets.buttons.feedback import get_ripple_duration_ms

        return get_ripple_duration_ms()

    def _speed_limited_expand_ms(self) -> int:
        """Expansion length for this press: the base, stretched for long sweeps.

        The swept distance is the control's longest side; at 225 ms a
        1200 px side moves the edge ~90 px per 60 Hz frame, which the eye
        reads as two positions. Stretching the expansion keeps the edge
        inside the platform's own window (225 … 450 ms).
        """
        base = self._duration_ms()
        try:
            longest = max(self._widget.width(), self._widget.height())
        except RuntimeError:  # widget already deleted
            longest = 0
        if longest <= 0:
            return base
        scaled = int(longest / EXPAND_PX_PER_MS)
        return max(base, min(MAX_EXPAND_MS, scaled))

    def trigger(
        self,
        pos: QPointF,
        *,
        color_from: QColor | None = None,
        color_to: QColor | None = None,
    ) -> None:
        """Запустить волну из точки `pos`.

        Если переданы оба `color_from` и `color_to` — волна интерполирует
        полный цвет (с alpha) от первого ко второму по мере распространения.
        Если хотя бы один None — используется дефолтный overlay (тёмный на
        светлой теме, светлый на тёмной).
        """
        self._center = QPointF(pos)
        self._elapsed = 0
        self._expand_ms = self._speed_limited_expand_ms()
        self._color_from = QColor(color_from) if color_from is not None else None
        self._color_to = QColor(color_to) if color_to is not None else None
        self._clock.start()
        self._timer.start()
        self._widget.update()

    def is_active(self) -> bool:
        return self._center is not None

    def remaining_ms(self) -> int:
        """Milliseconds left in the wave (expansion + fade), or ``0`` idle."""
        if self._center is None:
            return 0
        return max(0, self.total_ms() - self._elapsed)

    def expand_ms(self) -> int:
        """Length of this press's expansion phase (speed-limited base)."""
        return self._expand_ms

    def total_ms(self) -> int:
        """Expansion plus the fade-out that follows it."""
        return self._expand_ms + FADE_OUT_MS

    def elapsed_ms(self) -> int:
        """Wall-clock milliseconds since the press started."""
        return self._elapsed

    def cancel(self) -> None:
        """Stop and clear the wave immediately, e.g. when the widget is
        repositioned out from under it (layout reflow) and the animation
        would otherwise keep visibly playing at the wrong spot."""
        if self._center is None and not self._timer.isActive():
            return
        self._clear()
        self._widget.update()

    def _clear(self) -> None:
        self._timer.stop()
        self._elapsed = 0
        self._center = None
        self._color_from = None
        self._color_to = None

    @property
    def center(self) -> QPointF | None:
        return self._center

    @property
    def color_from(self) -> QColor | None:
        return self._color_from

    @property
    def color_to(self) -> QColor | None:
        return self._color_to

    def progress(self) -> float:
        duration = self._expand_ms
        if duration <= 0:
            return 1.0
        return min(1.0, self._elapsed / duration)

    def _on_tick(self) -> None:
        if not self._widget.isVisible():
            if self._center is not None or self._timer.isActive():
                self._clear()
                self._widget.update()
            return
        # Advance by MEASURED time, not by the nominal interval: a GUI thread
        # that spent 20 ms painting used to add those 20 ms to the wave (413 ms
        # for a 280 ms request) and kept 18 frames over the longer span. Any
        # hitch now shortens the remaining frames instead of stretching them.
        delta = int(self._clock.restart()) if self._clock.isValid() else self.TICK_MS
        self._elapsed += max(0, delta)
        if self._elapsed >= self.total_ms():
            self._clear()
        self._widget.update()


class RippleLayer(Layer):
    def applies(self, ctx: DrawContext) -> bool:
        ripple = _ripple_for(ctx)
        if ripple is None or not ripple.is_active():
            return False
        # Shared group ripple is painted once for the whole group capsule
        # (including any layout gap between siblings). Painting per-region
        # with a per-region fill clip left a dead strip in gaps.
        return _is_group_ripple_paint_owner(ctx)

    def draw(self, ctx: DrawContext, tm: ThemeManager) -> None:
        ripple = _ripple_for(ctx)
        if ripple is None:
            return
        center = ripple.center
        if center is None:
            return

        radius_rect = ctx.effective_ripple_rect
        draw_rect = radius_rect if _region_group(ctx) else ctx.effective_rect
        center, radius = wave_geometry(
            center,
            radius_rect,
            ripple.progress(),
            pad_px=float(scaled_px(END_RADIUS_PAD_DP)),
        )
        if radius <= 0:
            return

        p = ctx.painter
        p.save()
        clip = QPainterPath()
        radius_corner = max(0, ctx.corner_radius - 1)
        clip.addRoundedRect(
            ctx.rect.adjusted(1.0, 1.0, -1.0, -1.0),
            radius_corner,
            radius_corner,
        )
        p.setClipPath(clip)
        if ctx.region_rect is not None:
            if _region_group(ctx) is not None:
                # Unite over the whole group — covers layout gaps inside the
                # shared capsule. Hairline fill-path overlap stays for
                # ungrouped abutting regions below.
                group_clip = QPainterPath()
                group_clip.addRect(radius_rect)
                p.setClipPath(group_clip, Qt.ClipOperation.IntersectClip)
            else:
                # Use effective_fill_path (not effective_path) — same hairline
                # overlap fix as BackgroundLayer: clipping to the exact
                # hit-test rect leaves a visible antialiased seam against the
                # neighboring region when the split boundary isn't pixel-aligned
                # (e.g. 0.33/0.66 fractional weights).
                p.setClipPath(ctx.effective_fill_path, Qt.ClipOperation.IntersectClip)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)

        if ripple.color_from is not None and ripple.color_to is not None:
            # Gradient-mode: state-layer заливается color_from на всю поверхность
            # (затирая мгновенно-применившийся новый bg от BackgroundLayer),
            # затем растущий круг color_to «открывает» новое состояние из точки клика.
            p.setBrush(QBrush(ripple.color_from))
            p.drawRect(draw_rect)
            p.setBrush(_soft_disc(center, radius, ripple.color_to))
            p.drawEllipse(center, radius, radius)
        else:
            # Overlay-mode: полупрозрачная тёмная/светлая прослойка, как M3-state-layer.
            is_dark = tm.is_dark()
            peak = (
                RippleEffect.PEAK_ALPHA_DARK if is_dark else RippleEffect.PEAK_ALPHA_LIGHT
            )
            alpha = int(round(peak * wave_alpha(ripple.elapsed_ms(), ripple.expand_ms())))
            if alpha > 0:
                color = (
                    QColor(255, 255, 255, alpha) if is_dark else QColor(0, 0, 0, alpha)
                )
                p.setBrush(_soft_disc(center, radius, color))
                p.drawEllipse(center, radius, radius)

        p.restore()


def _ripple_for(ctx: DrawContext) -> RippleEffect | None:
    if ctx.region_id is not None:
        controller = getattr(ctx.widget, "_controller", None)
        ripple = controller.ripple(ctx.region_id) if controller is not None else None
        if ripple is not None:
            return ripple
        ripples = getattr(ctx.widget, "_region_ripple", {})
        ripple = ripples.get(ctx.region_id)
        if ripple is not None:
            return ripple
    return getattr(ctx.widget, "_ripple", None)


def _region_group(ctx: DrawContext) -> str | None:
    if ctx.region_id is None:
        return None
    controller = getattr(ctx.widget, "_controller", None)
    regions = controller.regions if controller is not None else getattr(ctx.widget, "_regions", [])
    for region in regions:
        if region.id == ctx.region_id:
            return getattr(region, "group", None)
    return None


def _is_group_ripple_paint_owner(ctx: DrawContext) -> bool:
    """True if this scoped region should emit the (possibly shared) ripple.

    Ungrouped regions always own their own ripple. For ``group=``, only the
    first region in the button's region list that belongs to that group paints,
    so a layout gap between siblings is covered once via the united ripple rect.
    """
    group = _region_group(ctx)
    if group is None:
        return True
    if ctx.region_id is None:
        return False
    controller = getattr(ctx.widget, "_controller", None)
    regions = controller.regions if controller is not None else getattr(ctx.widget, "_regions", [])
    for region in regions:
        if getattr(region, "group", None) == group:
            return region.id == ctx.region_id
    return True
