from __future__ import annotations
from sli_ui_toolkit.ui.inspector.spec import InspectSpec, SpecField  # noqa: E402

from typing import TYPE_CHECKING, ClassVar

from PySide6.QtCore import (
    QEasingCurve,
    QPointF,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    Property,
    Signal,
)
from PySide6.QtGui import QBrush, QColor, QFontMetrics, QPainter, QPainterPath, QPen

from sli_ui_toolkit.ui.managers.ui_font import paint_font
from sli_ui_toolkit.ui.managers.ui_scale import scaled_px
from sli_ui_toolkit.ui.widgets.buttons import Button
from sli_ui_toolkit.ui.widgets.buttons.layers import FocusLayer
from sli_ui_toolkit.ui.widgets.buttons.layers._base import Layer
from sli_ui_toolkit.ui.widgets.buttons.state import ButtonState

if TYPE_CHECKING:
    from sli_ui_toolkit.ui.widget_descriptor import WidgetDescriptor


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
        # Qt paints the indeterminate state as a filled box with a dash, so the
        # fill/glyph branches key off "filled" rather than "checked".
        is_partial = (
            getattr(widget, "_check_state", Qt.CheckState.Unchecked)
            == Qt.CheckState.PartiallyChecked
        )
        is_filled = is_checked or is_partial

        accent = tm.get_color("accent")
        border = tm.get_color("dialog.border")
        text_color = tm.get_color("dialog.text")
        neutral_hover = tm.get_color("dialog.button.hover")
        disabled_alpha = 110
        indicator_radius = scaled_px(widget.INDICATOR_RADIUS)
        # The stroke's own rect: a pen of `OUTLINE_WIDTH` centred on an integer edge is drawn half outside the box and
        # antialiases into two grey rows - the stock `QCheckBox::indicator` border is crisp white. Half a pen width
        # inwards puts the line on whole pixels.
        stroke = float(widget.OUTLINE_WIDTH)
        stroke_rect = indicator_rect.adjusted(stroke / 2, stroke / 2, -stroke / 2, -stroke / 2)

        if is_filled:
            border_color = (
                border
                if not is_disabled
                else QColor(border.red(), border.green(), border.blue(), disabled_alpha)
            )
            painter.setPen(QPen(border_color, widget.OUTLINE_WIDTH))
            accent_fill = QColor(tm.try_get_color(widget.CHECKED_FILL_TOKEN) or accent)
            base_alpha = int(120 + 135 * widget._checked_progress)
            if is_disabled:
                base_alpha = int(base_alpha * 0.6)
            # The token's own alpha scales the animation instead of being overwritten by it: an opaque token keeps the
            # toolkit's look exactly, and a token with alpha 0 asks for an outline-and-glyph box (no fill at all).
            # Overwriting the alpha made "transparent fill" inexpressible - measured on RVE's check-square look.
            accent_fill.setAlpha(max(0, min(255, int(base_alpha * accent_fill.alpha() / 255))))
            painter.setBrush(QBrush(accent_fill) if accent_fill.alpha() > 0 else Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(stroke_rect, indicator_radius, indicator_radius)
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
            painter.drawRoundedRect(stroke_rect, indicator_radius, indicator_radius)

        if is_filled:
            glyph_color = QColor(
                tm.try_get_color(widget.CHECK_COLOR_TOKEN) or QColor(Qt.GlobalColor.white)
            )
            if is_disabled:
                glyph_color.setAlpha(disabled_alpha)

            if is_partial:
                # Qt's indeterminate mark: a horizontal dash, unrotated.
                painter.setPen(
                    QPen(
                        glyph_color,
                        widget.CHECK_STROKE_WIDTH,
                        Qt.PenStyle.SolidLine,
                        Qt.PenCapStyle.RoundCap,
                    )
                )
                dash_y = indicator_rect.center().y()
                painter.drawLine(
                    QPointF(
                        indicator_rect.left() + indicator_rect.width() * widget.DASH_X1,
                        dash_y,
                    ),
                    QPointF(
                        indicator_rect.left() + indicator_rect.width() * widget.DASH_X2,
                        dash_y,
                    ),
                )
            else:
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


_NEXT_CHECK_STATE = {
    Qt.CheckState.Unchecked: Qt.CheckState.PartiallyChecked,
    Qt.CheckState.PartiallyChecked: Qt.CheckState.Checked,
    Qt.CheckState.Checked: Qt.CheckState.Unchecked,
}


class CheckBox(Button):
    """Checkbox toggle, built on the shared ``Button`` painter pipeline, so it
    picks up ``FocusLayer``'s keyboard-focus ring like every other toolkit
    control.

    Two-state by default. ``CheckBox(text, tristate=True)`` mirrors Qt's
    ``QCheckBox`` with ``setTristate(True)``: clicks/keys cycle
    Unchecked → PartiallyChecked → Checked, ``checkState()`` answers the
    ``Qt.CheckState``, and the indeterminate mark paints as a dash. With the
    flag unset the widget behaves exactly as it always has.
    """

    inspect_spec: ClassVar[InspectSpec]
    widget_descriptor: ClassVar["WidgetDescriptor"]

    #: Qt emits ``stateChanged(int)`` alongside ``toggled``; hosts that read
    #: the tri-state listen to this one (``toggled`` cannot express partial).
    stateChanged = Signal(int)

    # Class-level defaults keep inspection/painting safe before __init__ has
    # stored the instance values (a paint cannot run that early, but a spec
    # read or a subclass query can).
    _tristate: bool = False
    _check_state: Qt.CheckState = Qt.CheckState.Unchecked

    #: Colours the checked state paints from. Defaults keep the toolkit's own look (white check on an `accent` fill);
    #: a host whose design language differs - a monochrome box with an outline and a tick, for instance - points these
    #: at its own tokens instead of forking the painter. A fully transparent fill means "outline + glyph only".
    CHECK_COLOR_TOKEN = "checkbox.check"
    CHECKED_FILL_TOKEN = "checkbox.background.checked"

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
    # Indeterminate dash, as fractions of the indicator box.
    DASH_X1 = 0.24
    DASH_X2 = 0.76

    def __init__(
        self,
        text: str | None = None,
        parent=None,
        *,
        tristate: bool = False,
    ):
        super().__init__(
            text=text or "",
            toggle=True,
            corner_radius=6,
            layers=[_CheckIndicatorLayer(), FocusLayer()],
            parent=parent,
        )
        self._tristate = bool(tristate)
        self._check_state = (
            Qt.CheckState.Checked if self.isChecked() else Qt.CheckState.Unchecked
        )
        self._hover_progress = 0.0
        self._checked_progress = 1.0 if self.isChecked() else 0.0
        #: True only while a user gesture (click / key) is flipping the state.
        #: A programmatic ``setChecked`` must snap: restoring a saved value is
        #: not a gesture, and animating it made a remembered "checked" paint as
        #: unchecked for the first frames (owner report 2026-10-22).
        self._user_toggle = False

        self._hover_anim = QPropertyAnimation(self, b"hoverProgress", self)
        self._hover_anim.setDuration(120)
        self._hover_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._checked_anim = QPropertyAnimation(self, b"checkedProgress", self)
        self._checked_anim.setDuration(150)
        self._checked_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.toggled.connect(self._animate_checked)

    def text(self) -> str:
        return self._text

    # -------- public API: Qt ``QCheckBox`` tri-state --------

    def isTristate(self) -> bool:
        return self._tristate

    def setTristate(self, enabled: bool) -> None:
        """Enable Qt's check-state cycle (Unchecked → Partial → Checked).

        Mirrors ``QCheckBox::setTristate``: the flag only governs *cycling*;
        ``setCheckState`` may store ``PartiallyChecked`` regardless, as in Qt.
        """
        self._tristate = bool(enabled)

    def checkState(self) -> Qt.CheckState:
        return self._check_state

    def setCheckState(self, state: Qt.CheckState) -> None:
        """Set the check state, emitting exactly what Qt emits.

        Qt's order is ``toggled(bool)`` (only when the bool changes), then
        ``stateChanged(int)`` — measured on ``QCheckBox`` 6.11: unchecked →
        partial fires both, partial → checked fires only ``stateChanged``.
        """
        state = state if isinstance(state, Qt.CheckState) else Qt.CheckState(int(state))
        if state == self._check_state:
            return
        self.setChecked(state != Qt.CheckState.Unchecked)
        # ``setChecked``/``setRegionChecked`` normalise to a bool state; the
        # tri-state value is the one this call was asked for.
        self._check_state = state
        self.update()
        self.stateChanged.emit(state.value)

    def _toggle_from_user(self, region_id: str) -> None:
        if not self._tristate:
            super()._toggle_from_user(region_id)
            return
        self.setCheckState(_NEXT_CHECK_STATE[self.checkState()])

    def setRegionChecked(self, region_id: str, checked: bool, *, emit: bool = True) -> None:
        super().setRegionChecked(region_id, checked, emit=emit)
        if region_id != "_main":
            return
        # Qt's ``QCheckBox::checkStateSet``: a bool write collapses the
        # tri-state to Checked/Unchecked (even when the bool did not change).
        self._check_state = (
            Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        )
        self.update()

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
        if not (self._user_toggle and self.isVisible()):
            # Same rule as Switch: a checkbox configured before it is shown must
            # paint its indicator already checked, not animate from 0.0 on the
            # first frames (owner report 2026-10-22).
            self.set_checked_progress(target)
            return
        self._checked_anim.setStartValue(self._checked_progress)
        self._checked_anim.setEndValue(target)
        self._checked_anim.start()

    def mouseReleaseEvent(self, event):  # noqa: N802
        self._user_toggle = True
        try:
            super().mouseReleaseEvent(event)
        finally:
            self._user_toggle = False

    def keyPressEvent(self, event):  # noqa: N802
        self._user_toggle = True
        try:
            super().keyPressEvent(event)
        finally:
            self._user_toggle = False

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
        SpecField("tristate", "isTristate"),
        SpecField("check_state", "checkState"),
        SpecField("hover_progress", "hoverProgress"),
        SpecField("checked_progress", "checkedProgress"),
    ),
    token_family=("accent", "dialog.border", "dialog.text", "dialog.button.hover",
                  "checkbox.check", "checkbox.background.checked"),
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
