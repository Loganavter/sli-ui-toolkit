"""RippleLayer — материал-стайл волна от точки клика.

Поддерживает два режима окрашивания:

1. **Overlay (по умолчанию):** полупрозрачная тёмная/светлая «прослойка» —
   как в текущем M3-state-layer.
2. **Gradient:** при вызове `trigger(pos, color_from=A, color_to=B)` волна
   интерполирует цвет от A к B по ходу прогресса. Удобно для перехода между
   статусами кнопки (hover → checked, default → pressed и т.п.).

State хранится на самой кнопке в `_ripple: RippleEffect`. Layer стейтлесс,
читает состояние из `ctx.widget`.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.theme import ThemeManager

from ..context import DrawContext
from ._base import Layer


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
    # ``get_ripple_duration_ms()`` for new code.
    DURATION_MS = 280
    TICK_MS = 16
    PEAK_ALPHA_LIGHT = 31
    PEAK_ALPHA_DARK = 41

    def __init__(self, widget: QWidget) -> None:
        self._widget = widget
        self._timer = QTimer(widget)
        self._timer.setInterval(self.TICK_MS)
        self._timer.timeout.connect(self._on_tick)
        self._elapsed = 0
        self._center: QPointF | None = None
        self._color_from: QColor | None = None
        self._color_to: QColor | None = None

    def _duration_ms(self) -> int:
        from sli_ui_toolkit.ui.widgets.buttons.feedback import get_ripple_duration_ms

        return get_ripple_duration_ms()

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
        self._color_from = QColor(color_from) if color_from is not None else None
        self._color_to = QColor(color_to) if color_to is not None else None
        self._timer.start()
        self._widget.update()

    def is_active(self) -> bool:
        return self._center is not None

    def remaining_ms(self) -> int:
        """Milliseconds left in the wave, or ``0`` when idle."""
        if self._center is None:
            return 0
        return max(0, self._duration_ms() - self._elapsed)

    def cancel(self) -> None:
        """Stop and clear the wave immediately, e.g. when the widget is
        repositioned out from under it (layout reflow) and the animation
        would otherwise keep visibly playing at the wrong spot."""
        if self._center is None and not self._timer.isActive():
            return
        self._timer.stop()
        self._elapsed = 0
        self._center = None
        self._color_from = None
        self._color_to = None
        self._widget.update()

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
        duration = self._duration_ms()
        if duration <= 0:
            return 1.0
        return min(1.0, self._elapsed / duration)

    def _on_tick(self) -> None:
        self._elapsed += self.TICK_MS
        if self._elapsed >= self._duration_ms():
            self._timer.stop()
            self._center = None
            self._color_from = None
            self._color_to = None
        if not self._widget.isVisible():
            self._timer.stop()
            self._center = None
            self._color_from = None
            self._color_to = None
            return
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

        progress = ripple.progress()
        eased = 1.0 - (1.0 - progress) ** 2

        radius_rect = ctx.effective_ripple_rect
        draw_rect = radius_rect if _region_group(ctx) else ctx.effective_rect
        corners = (
            (radius_rect.left(), radius_rect.top()),
            (radius_rect.right(), radius_rect.top()),
            (radius_rect.left(), radius_rect.bottom()),
            (radius_rect.right(), radius_rect.bottom()),
        )
        max_radius = max(
            math.hypot(center.x() - cx, center.y() - cy) for cx, cy in corners
        )
        radius = max_radius * eased
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
            p.setBrush(QBrush(ripple.color_to))
            p.drawEllipse(center, radius, radius)
        else:
            # Overlay-mode: полупрозрачная тёмная/светлая прослойка, как M3-state-layer.
            try:
                is_dark = tm.is_dark()
            except Exception:
                is_dark = False
            peak = (
                RippleEffect.PEAK_ALPHA_DARK if is_dark else RippleEffect.PEAK_ALPHA_LIGHT
            )
            alpha = int(peak * (1.0 - progress))
            if alpha > 0:
                color = (
                    QColor(255, 255, 255, alpha) if is_dark else QColor(0, 0, 0, alpha)
                )
                p.setBrush(color)
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
