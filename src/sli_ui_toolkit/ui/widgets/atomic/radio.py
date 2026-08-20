from __future__ import annotations
from sli_ui_toolkit.ui.inspector.spec import InspectSpec, SpecField  # noqa: E402

import shiboken6 as sip
from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRectF, QSize, Qt, Property
from PySide6.QtGui import QBrush, QColor, QFontMetrics, QPainter, QPainterPath, QPen

from sli_ui_toolkit.ui.managers.ui_font import paint_font
from sli_ui_toolkit.ui.managers.ui_scale import scaled_px
from sli_ui_toolkit.ui.widgets.buttons import Button
from sli_ui_toolkit.ui.widgets.buttons.layers import FocusLayer
from sli_ui_toolkit.ui.widgets.buttons.layers._base import Layer
from sli_ui_toolkit.ui.widgets.buttons.state import ButtonState


class _RadioIndicatorLayer(Layer):
    """Indicator dot + label, painted from scratch (no BackgroundLayer /
    ContentLayer in this widget's ``layers=`` — see ``RadioButton``)."""

    def draw(self, ctx, tm) -> None:
        widget: "RadioButton" = ctx.widget
        painter = ctx.painter
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rect = QRectF(ctx.rect)
        fm = QFontMetrics(paint_font(widget))
        indicator_rect = widget._indicator_rect(rect)
        text_rect_avail = widget._text_rect_available(rect, indicator_rect)
        text_rect = widget._text_rect_content(rect, indicator_rect, fm)

        states = ctx.effective_states
        is_disabled = ButtonState.DISABLED in states
        is_hovered = ButtonState.HOVERED in states
        is_checked = ButtonState.CHECKED in states

        accent = tm.get_color("accent")
        border = tm.get_color("dialog.border")
        text_color = tm.get_color("dialog.text")
        neutral_hover = tm.get_color("dialog.button.hover")
        disabled_alpha = 110

        center = indicator_rect.center()
        radius = indicator_rect.width() / 2.0

        if is_checked:
            inner_factor = (
                widget.INNER_HOLE_FACTOR_BASE
                + (widget.INNER_HOLE_FACTOR_HOVER - widget.INNER_HOLE_FACTOR_BASE)
                * widget._hover_progress
            )
            inner_r = radius * inner_factor

            path = QPainterPath()
            path.addEllipse(center, radius, radius)
            path.addEllipse(center, inner_r, inner_r)
            path.setFillRule(Qt.FillRule.OddEvenFill)

            fill_color = QColor(accent)
            if is_disabled:
                fill_color.setAlpha(disabled_alpha)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(fill_color))
            painter.drawPath(path)

            border_color = (
                border
                if not is_disabled
                else QColor(border.red(), border.green(), border.blue(), disabled_alpha)
            )
            painter.setPen(QPen(border_color, widget.OUTLINE_WIDTH))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(center, radius, radius)
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
            painter.drawEllipse(center, radius, radius)

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
                draw_rect = text_rect
            painter.setFont(paint_font(widget))
            painter.drawText(
                draw_rect,
                int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                full_text,
            )


class RadioButtonGroup:
    """Minimal ``QButtonGroup``-alike for ``RadioButton`` (see its docstring
    for why ``QButtonGroup`` itself doesn't apply here). ``addButton()``
    mirrors the one bit of ``QButtonGroup`` API this toolkit's host apps
    actually use: unchecking every other member once one becomes checked.
    """

    def __init__(self) -> None:
        self._buttons: list[RadioButton] = []

    def addButton(self, button: "RadioButton") -> None:
        self._buttons.append(button)
        button.toggled.connect(lambda checked, b=button: self._on_toggled(b, checked))

    def buttons(self) -> list["RadioButton"]:
        return list(self._buttons)

    def checkedButton(self) -> "RadioButton | None":
        return next((b for b in self._buttons if b.isChecked()), None)

    def _on_toggled(self, source: "RadioButton", checked: bool) -> None:
        if not checked:
            return
        for b in self._buttons:
            if b is not source and b.isChecked():
                b.setChecked(False)


class RadioButton(Button):
    """Radio-style toggle, built on the shared ``Button`` painter pipeline
    (was a standalone ``QRadioButton`` subclass — rebased so it picks up
    ``FocusLayer``'s keyboard-focus ring like every other toolkit control).

    ``Button`` has no native "exclusive group" concept (unlike
    ``QAbstractButton`` + ``QButtonGroup``, which ``QRadioButton`` used to
    get for free) -- use :class:`RadioButtonGroup` instead of
    ``QButtonGroup`` to keep a set of these mutually exclusive.

    Clicking an already-checked radio must stay checked (only a sibling
    becoming checked may uncheck it) -- ``Button``'s own ``toggle=True``
    click handling *flips* ``_checked`` on every click, which would uncheck
    a radio on a second click. ``_suppress_uncheck`` is set only around the
    two code paths that can trigger that flip (mouse release, keyboard
    Space/Enter/``click()``) -- ``_enforce_checked`` undoes the flip only
    while it's set, so a *programmatic* ``setChecked(False)`` from
    :class:`RadioButtonGroup` (unchecking a sibling once this one becomes
    checked) is left alone instead of being fought right back to checked.
    """

    INDICATOR_SIZE = 20
    OUTLINE_WIDTH = 1
    SPACING = 8
    PADDING_H = 2
    PADDING_V = 5

    INNER_HOLE_FACTOR_BASE = 0.50
    INNER_HOLE_FACTOR_HOVER = 0.60

    def __init__(self, text: str | None = None, parent=None):
        super().__init__(
            text=text or "",
            toggle=True,
            corner_radius=6,
            layers=[_RadioIndicatorLayer(), FocusLayer()],
            parent=parent,
        )
        self._hover_progress = 0.0
        self._suppress_uncheck = False
        self._hover_anim = QPropertyAnimation(self, b"hoverProgress", self)
        self._hover_anim.setDuration(120)
        self._hover_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._enforce_checked)

    def _enforce_checked(self, checked: bool) -> None:
        if not checked and self._suppress_uncheck:
            self.setChecked(True, emit=False)

    def isCheckable(self) -> bool:
        # QRadioButton API parity: app-side Find Action code (see
        # ui/actions/flyout_contribute.py, plugins/settings/member_resolve.py)
        # branches on isCheckable()/autoExclusive() to select a radio rather
        # than blindly toggle it (which would uncheck an already-selected
        # one) -- without these, that code falls into a generic toggle path
        # this class actively guards against everywhere else.
        return True

    def autoExclusive(self) -> bool:
        return True

    def mouseReleaseEvent(self, event):
        self._suppress_uncheck = True
        try:
            super().mouseReleaseEvent(event)
        finally:
            if sip.isValid(self):
                self._suppress_uncheck = False

    def _activate_via_keyboard(self):
        self._suppress_uncheck = True
        try:
            super()._activate_via_keyboard()
        finally:
            if sip.isValid(self):
                self._suppress_uncheck = False

    def text(self) -> str:
        return self._text

    def get_hover_progress(self) -> float:
        return self._hover_progress

    def set_hover_progress(self, value: float):
        self._hover_progress = max(0.0, min(1.0, float(value)))
        self.update()

    hoverProgress = Property(float, fget=get_hover_progress, fset=set_hover_progress)

    def hoverHitTest(self, pos) -> bool:
        # Button's own hoverHitTest is whole-widget-rect -- restrict to the
        # indicator + text (HoverCoordinator drives hover reconciliation off
        # this on every mouse move; empty trailing row space must read as a
        # miss, see test_radio_hover_hit_test_ignores_empty_widget_area).
        r = QRectF(self.rect())
        ind = self._indicator_rect(r)
        fm = QFontMetrics(paint_font(self))
        tx = self._text_rect_content(r, ind, fm)
        return ind.contains(pos) or tx.contains(pos)

    def setHoverActive(self, active: bool) -> None:
        # Button's own setHoverActive drives ButtonState.HOVERED (used by
        # the indicator-fill wash in _RadioIndicatorLayer); chain into it
        # rather than replacing it, and additionally drive the hole-shrink
        # micro-animation this widget had before the Button rebase.
        super().setHoverActive(active)
        self._animate_hover(bool(active))

    def _animate_hover(self, hovered: bool):
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover_progress)
        self._hover_anim.setEndValue(1.0 if hovered else 0.0)
        self._hover_anim.start()

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

    def sizeHint(self) -> QSize:
        fm = QFontMetrics(paint_font(self))
        text_width = fm.horizontalAdvance(self._text) if self._text else 0

        indicator = scaled_px(self.INDICATOR_SIZE)
        pad_v = scaled_px(self.PADDING_V)
        pad_h = scaled_px(self.PADDING_H)
        spacing = scaled_px(self.SPACING)
        extra = scaled_px(4)
        h = max(indicator + 2 * pad_v, fm.height() + 2 * pad_v)
        w = (
            pad_h
            + indicator
            + (spacing if text_width else 0)
            + text_width
            + pad_h
            + extra
        )
        return QSize(int(w), int(h))

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()


RadioButton.inspect_spec = InspectSpec(
    family="RadioButton",
    state=(
        SpecField("checked", "isChecked"),
        SpecField("hover_progress", "hoverProgress"),
    ),
    token_family=("accent", "dialog.border", "dialog.text", "dialog.button.hover"),
    docs='docs/user/INPUTS_API.md',
)

from sli_ui_toolkit.ui.widget_descriptor import InspectSection, WidgetDescriptor
RadioButton.widget_descriptor = WidgetDescriptor(
    family=RadioButton.inspect_spec.family,
    inspect=InspectSection(
        config=getattr(RadioButton.inspect_spec, 'config', ()),
        state=RadioButton.inspect_spec.state,
        token_family=getattr(RadioButton.inspect_spec, 'token_family', ()),
        regions=getattr(RadioButton.inspect_spec, 'regions', False),
        layers=getattr(RadioButton.inspect_spec, 'layers', False),
        docs=getattr(RadioButton.inspect_spec, 'docs', ''),
    ),
)
