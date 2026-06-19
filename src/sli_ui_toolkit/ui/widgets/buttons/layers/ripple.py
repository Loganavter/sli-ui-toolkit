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
        return min(1.0, self._elapsed / self.DURATION_MS)

    def _on_tick(self) -> None:
        self._elapsed += self.TICK_MS
        if self._elapsed >= self.DURATION_MS:
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
        return ripple is not None and ripple.is_active()

    def draw(self, ctx: DrawContext, tm: ThemeManager) -> None:
        ripple = _ripple_for(ctx)
        if ripple is None:
            return
        center = ripple.center
        if center is None:
            return

        progress = ripple.progress()
        eased = 1.0 - (1.0 - progress) ** 2

        rect = ctx.effective_rect
        corners = (
            (rect.left(), rect.top()),
            (rect.right(), rect.top()),
            (rect.left(), rect.bottom()),
            (rect.right(), rect.bottom()),
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
            p.setClipPath(ctx.effective_path, Qt.ClipOperation.IntersectClip)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)

        if ripple.color_from is not None and ripple.color_to is not None:
            # Gradient-mode: state-layer заливается color_from на всю поверхность
            # (затирая мгновенно-применившийся новый bg от BackgroundLayer),
            # затем растущий круг color_to «открывает» новое состояние из точки клика.
            p.setBrush(QBrush(ripple.color_from))
            p.drawRect(rect)
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
