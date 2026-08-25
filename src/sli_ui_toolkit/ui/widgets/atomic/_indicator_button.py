"""Shared hover/animation/hit-test base for indicator buttons.

Consolidates ~130 LOC duplicated between ``CheckBox`` and ``RadioButton``.
``sizeHint`` stays on the concrete subclasses (already diverged).
"""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRectF, Qt, Property
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.ui.managers.ui_font import paint_font
from sli_ui_toolkit.ui.managers.ui_scale import scaled_px
from sli_ui_toolkit.ui.timings import HOVER_DURATION_MS
from sli_ui_toolkit.ui.widgets.buttons import Button


class _IndicatorButtonBase(Button):
    """Common indicator-button machinery (hover progress + hit-test + rects)."""

    INDICATOR_SIZE = 20
    OUTLINE_WIDTH = 1
    SPACING = 8
    PADDING_H = 2
    PADDING_V = 5

    def __init__(
        self,
        text: str | None = None,
        parent: QWidget | None = None,
        *,
        layers=None,
        corner_radius: int = 6,
    ):
        super().__init__(
            text=text or "",
            toggle=True,
            corner_radius=corner_radius,
            layers=layers,
            parent=parent,
        )
        self._hover_progress = 0.0
        self._hover_anim = QPropertyAnimation(self, b"hoverProgress", self)
        self._hover_anim.setDuration(HOVER_DURATION_MS)
        self._hover_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    # ---- hover progress property (used by painter layers) ----

    def get_hover_progress(self) -> float:
        return self._hover_progress

    def set_hover_progress(self, value: float) -> None:
        self._hover_progress = max(0.0, min(1.0, float(value)))
        self.update()

    hoverProgress = Property(float, fget=get_hover_progress, fset=set_hover_progress)  # type: ignore[assignment]

    # ---- hit-test / hover activation ----

    def hoverHitTest(self, pos) -> bool:  # noqa: N802
        r = QRectF(self.rect())
        ind = self._indicator_rect(r)
        fm = QFontMetrics(paint_font(self))
        tx = self._text_rect_content(r, ind, fm)
        return ind.contains(pos) or tx.contains(pos)

    def setHoverActive(self, active: bool) -> None:  # noqa: N802
        super().setHoverActive(active)
        self._animate_hover(bool(active))

    def _animate_hover(self, hovered: bool) -> None:
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover_progress)
        self._hover_anim.setEndValue(1.0 if hovered else 0.0)
        self._hover_anim.start()

    # ---- geometry helpers ----

    def _indicator_rect(self, full_rect: QRectF) -> QRectF:
        pad_h = scaled_px(self.PADDING_H)
        size = scaled_px(self.INDICATOR_SIZE)
        return QRectF(
            full_rect.x() + pad_h,
            full_rect.y() + (full_rect.height() - size) / 2,
            size,
            size,
        )

    def _text_rect_available(self, full_rect: QRectF, indicator_rect: QRectF) -> QRectF:
        text_left = indicator_rect.right() + scaled_px(self.SPACING)
        available_w = max(
            0.0,
            full_rect.width()
            - (text_left - full_rect.left())
            - scaled_px(self.PADDING_H),
        )
        return QRectF(text_left, full_rect.y(), available_w, full_rect.height())

    def _text_rect_content(self, full_rect: QRectF, indicator_rect: QRectF, fm: QFontMetrics) -> QRectF:
        avail = self._text_rect_available(full_rect, indicator_rect)
        text = self._text or ""
        content_w = min(avail.width(), float(fm.horizontalAdvance(text)))
        return QRectF(avail.left(), avail.top(), content_w, avail.height())

    def text(self) -> str:  # noqa: N802
        return self._text
