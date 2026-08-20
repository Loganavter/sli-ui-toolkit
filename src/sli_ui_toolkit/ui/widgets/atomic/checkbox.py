from __future__ import annotations
from sli_ui_toolkit.ui.inspector.spec import InspectSpec, SpecField  # noqa: E402

from PySide6.QtCore import (
    QEasingCurve,
    QPointF,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    Property,
)
from PySide6.QtGui import QBrush, QColor, QFontMetrics, QPainter, QPainterPath, QPen

from sli_ui_toolkit.ui.managers.ui_font import paint_font
from sli_ui_toolkit.ui.managers.ui_scale import scaled_px
from sli_ui_toolkit.ui.widgets.buttons import Button
from sli_ui_toolkit.ui.widgets.buttons.layers import FocusLayer
from sli_ui_toolkit.ui.widgets.buttons.layers._base import Layer
from sli_ui_toolkit.ui.widgets.buttons.state import ButtonState


class _CheckIndicatorLayer(Layer):
    """Indicator square + checkmark + label, painted from scratch (no
    BackgroundLayer / ContentLayer in this widget's ``layers=`` — see
    ``CheckBox``)."""

    def draw(self, ctx, tm) -> None:
        widget: "CheckBox" = ctx.widget
        painter = ctx.painter
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rect = QRectF(ctx.rect)
        fm = QFontMetrics(paint_font(widget))
        indicator_rect = widget._indicator_rect(rect)
        text_rect_avail = widget._text_rect_available(rect, indicator_rect)

        states = ctx.effective_states
        is_disabled = ButtonState.DISABLED in states
        is_hovered = ButtonState.HOVERED in states
        is_checked = ButtonState.CHECKED in states

        accent = tm.get_color("accent")
        border = tm.get_color("dialog.border")
        text_color = tm.get_color("dialog.text")
        neutral_hover = tm.get_color("dialog.button.hover")
        disabled_alpha = 110
        indicator_radius = scaled_px(widget.INDICATOR_RADIUS)

        if is_checked:
            border_color = (
                border
                if not is_disabled
                else QColor(border.red(), border.green(), border.blue(), disabled_alpha)
            )
            painter.setPen(QPen(border_color, widget.OUTLINE_WIDTH))
            accent_fill = QColor(accent)
            base_alpha = int(120 + 135 * widget._checked_progress)
            if is_disabled:
                base_alpha = int(base_alpha * 0.6)
            accent_fill.setAlpha(max(0, min(255, base_alpha)))
            painter.setBrush(QBrush(accent_fill))
            painter.drawRoundedRect(indicator_rect, indicator_radius, indicator_radius)
        else:
            border_color = (
                border
                if not is_disabled
                else QColor(border.red(), border.green(), border.blue(), disabled_alpha)
            )
            painter.setPen(QPen(border_color, widget.OUTLINE_WIDTH))
            if is_hovered and not is_disabled:
                hover_fill = QColor(neutral_hover)
                alpha = int(40 + 100 * widget._hover_progress)
                hover_fill.setAlpha(max(0, min(255, alpha)))
                painter.setBrush(QBrush(hover_fill))
            else:
                painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(indicator_rect, indicator_radius, indicator_radius)

        if is_checked:
            glyph_color = QColor(Qt.GlobalColor.white)
            if is_disabled:
                glyph_color.setAlpha(disabled_alpha)

            painter.save()
            center = indicator_rect.center()
            painter.translate(center)
            painter.rotate(widget.CHECK_ROTATION_DEG)
            painter.translate(-center)

            painter.setPen(
                QPen(
                    glyph_color,
                    widget.CHECK_STROKE_WIDTH,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                    Qt.PenJoinStyle.MiterJoin,
                )
            )

            x1 = indicator_rect.left() + indicator_rect.width() * widget.CHECK_X1
            y1 = indicator_rect.top() + indicator_rect.height() * widget.CHECK_Y1_NORM
            x2 = indicator_rect.left() + indicator_rect.width() * widget.CHECK_X2
            y2_pre = indicator_rect.top() + indicator_rect.height() * widget.CHECK_Y2_PRE
            x3 = indicator_rect.left() + indicator_rect.width() * widget.CHECK_X3
            y3_pre = indicator_rect.top() + indicator_rect.height() * widget.CHECK_Y3_PRE

            cx = indicator_rect.center().y()
            y2 = cx + widget.CHECK_BOTTOM_FACTOR * (y2_pre - cx)
            y3 = cx + widget.CHECK_TOP_FACTOR * (y3_pre - cx)

            path = QPainterPath()
            path.moveTo(QPointF(x1, y1))
            path.lineTo(QPointF(x2, y2))
            path.lineTo(QPointF(x3, y3))
            painter.drawPath(path)
            painter.restore()

        if widget._text:
            painter.setPen(
                QPen(
                    QColor(text_color)
                    if not is_disabled
                    else QColor(
                        text_color.red(),
                        text_color.green(),
                        text_color.blue(),
                        disabled_alpha,
                    )
                )
            )
            full_text = widget._text
            if fm.horizontalAdvance(full_text) > text_rect_avail.width():
                full_text = fm.elidedText(
                    full_text, Qt.TextElideMode.ElideRight, int(text_rect_avail.width())
                )
                draw_rect = text_rect_avail
            else:
                draw_rect = QRectF(
                    text_rect_avail.left(),
                    text_rect_avail.top(),
                    float(fm.horizontalAdvance(full_text)),
                    text_rect_avail.height(),
                )
            painter.setFont(paint_font(widget))
            painter.drawText(
                draw_rect,
                int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                full_text,
            )


class CheckBox(Button):
    """Checkbox toggle, built on the shared ``Button`` painter pipeline (was
    a standalone ``QCheckBox`` subclass — rebased so it picks up
    ``FocusLayer``'s keyboard-focus ring like every other toolkit control).

    Two-state only (no ``Qt.CheckState.PartiallyChecked`` indeterminate) —
    nothing in this toolkit's host apps used tri-state, and ``Button``'s own
    ``_checked`` is a plain bool.
    """

    INDICATOR_SIZE = 20
    INDICATOR_RADIUS = 4
    OUTLINE_WIDTH = 1
    SPACING = 8
    PADDING_H = 2
    PADDING_V = 5

    CHECK_ROTATION_DEG = -21.0
    CHECK_STROKE_WIDTH = 1.1
    CHECK_X1 = 0.26
    CHECK_Y1_NORM = 0.42
    CHECK_X2 = 0.36
    CHECK_Y2_PRE = 0.63
    CHECK_X3 = 0.82
    CHECK_Y3_PRE = 0.34
    CHECK_BOTTOM_FACTOR = 0.75
    CHECK_TOP_FACTOR = 0.55

    def __init__(self, text: str | None = None, parent=None):
        super().__init__(
            text=text or "",
            toggle=True,
            corner_radius=6,
            layers=[_CheckIndicatorLayer(), FocusLayer()],
            parent=parent,
        )
        self._hover_progress = 0.0
        self._checked_progress = 1.0 if self.isChecked() else 0.0

        self._hover_anim = QPropertyAnimation(self, b"hoverProgress", self)
        self._hover_anim.setDuration(120)
        self._hover_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._checked_anim = QPropertyAnimation(self, b"checkedProgress", self)
        self._checked_anim.setDuration(150)
        self._checked_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.toggled.connect(self._animate_checked)

    def text(self) -> str:
        return self._text

    def get_hover_progress(self) -> float:
        return self._hover_progress

    def set_hover_progress(self, value: float):
        self._hover_progress = max(0.0, min(1.0, float(value)))
        self.update()

    hoverProgress = Property(float, fget=get_hover_progress, fset=set_hover_progress)

    def get_checked_progress(self) -> float:
        return self._checked_progress

    def set_checked_progress(self, value: float):
        self._checked_progress = max(0.0, min(1.0, float(value)))
        self.update()

    checkedProgress = Property(float, fget=get_checked_progress, fset=set_checked_progress)

    def hoverHitTest(self, pos) -> bool:
        # Button's own hoverHitTest is whole-widget-rect -- restrict to the
        # indicator + text (HoverCoordinator drives hover reconciliation off
        # this on every mouse move; empty trailing row space must read as a
        # miss, see test_checkbox_hover_hit_test_ignores_empty_widget_area).
        r = QRectF(self.rect())
        ind = self._indicator_rect(r)
        fm = QFontMetrics(paint_font(self))
        tx = self._text_rect_content(r, ind, fm)
        return ind.contains(pos) or tx.contains(pos)

    def setHoverActive(self, active: bool) -> None:
        super().setHoverActive(active)
        self._animate_hover(bool(active))

    def _animate_hover(self, hovered: bool):
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover_progress)
        self._hover_anim.setEndValue(1.0 if hovered else 0.0)
        self._hover_anim.start()

    def _animate_checked(self, checked: bool) -> None:
        target = 1.0 if checked else 0.0
        self._checked_anim.stop()
        self._checked_anim.setStartValue(self._checked_progress)
        self._checked_anim.setEndValue(target)
        self._checked_anim.start()

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
        available_w = max(0.0, self.width() - text_left - scaled_px(self.PADDING_H))
        return QRectF(text_left, full_rect.y(), available_w, full_rect.height())

    def _text_rect_content(self, full_rect: QRectF, indicator_rect: QRectF, fm: QFontMetrics) -> QRectF:
        avail = self._text_rect_available(full_rect, indicator_rect)
        text = self._text or ""
        content_w = min(avail.width(), float(fm.horizontalAdvance(text)))
        return QRectF(avail.left(), avail.top(), content_w, avail.height())

    def sizeHint(self) -> QSize:
        fm = QFontMetrics(paint_font(self))
        indicator = scaled_px(self.INDICATOR_SIZE)
        pad_v = scaled_px(self.PADDING_V)
        pad_h = scaled_px(self.PADDING_H)
        spacing = scaled_px(self.SPACING)

        text_width = fm.horizontalAdvance(self._text) + 10 if self._text else 0
        h = max(indicator + 2 * pad_v, fm.height() + 2 * pad_v)
        w = (
            pad_h
            + indicator
            + (spacing if text_width else 0)
            + text_width
            + pad_h
        )
        return QSize(int(w), int(h))

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()


CheckBox.inspect_spec = InspectSpec(
    family="CheckBox",
    state=(
        SpecField("checked", "isChecked"),
        SpecField("hover_progress", "hoverProgress"),
        SpecField("checked_progress", "checkedProgress"),
    ),
    token_family=("accent", "dialog.border", "dialog.text", "dialog.button.hover"),
    docs='docs/user/INPUTS_API.md',
)

from sli_ui_toolkit.ui.widget_descriptor import InspectSection, WidgetDescriptor
CheckBox.widget_descriptor = WidgetDescriptor(
    family=CheckBox.inspect_spec.family,
    inspect=InspectSection(
        config=getattr(CheckBox.inspect_spec, 'config', ()),
        state=CheckBox.inspect_spec.state,
        token_family=getattr(CheckBox.inspect_spec, 'token_family', ()),
        regions=getattr(CheckBox.inspect_spec, 'regions', False),
        layers=getattr(CheckBox.inspect_spec, 'layers', False),
        docs=getattr(CheckBox.inspect_spec, 'docs', ''),
    ),
)
