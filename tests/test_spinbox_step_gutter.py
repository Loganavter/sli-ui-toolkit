"""``SpinBox``/``DoubleSpinBox`` carry Qt's ▲/▼ step gutter.

Why (2026-11-22): a host app deleted its Qt compatibility layer and builds
toolkit widgets directly. Its Designer ``QSpinBox``/``QDoubleSpinBox`` rows had
Qt's default up/down buttons; the migrated settings page showed a bare number,
so mouse stepping was gone. Measured off the host's screenshots: field height
29 px, gutter 20 px wide, arrows stacked (▲ above ▼) in one column — Qt's own
shape, not ``Stepper``'s wide side-by-side gauge.

The gutter is opt-in (``show_step_buttons=True``) so an untouched ``SpinBox``
keeps the geometry and behaviour it always had.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest

from sli_ui_toolkit.widgets import DoubleSpinBox, SpinBox, Stepper

HOST_FIELD_HEIGHT = 29
HOST_GUTTER_WIDTH = 20


def _host_field(**kwargs) -> DoubleSpinBox:
    """A ``DoubleSpinBox`` shaped like the host's migrated Designer row."""
    field = DoubleSpinBox(
        show_step_buttons=True,
        field_height=HOST_FIELD_HEIGHT,
        step_button_width=HOST_GUTTER_WIDTH,
        **kwargs,
    )
    field.setRange(0.0, 10.0)
    field.setSingleStep(0.5)
    field.setValue(2.0)
    field.resize(field.sizeHint().width(), field.sizeHint().height())
    field.show()
    return field


def _click_arrow(field, up: bool) -> None:
    """Click the gutter the way the mouse does: at the arrow's own centre."""
    button = field._up_button if up else field._down_button
    rect = field._up_button_rect() if up else field._down_button_rect()
    QTest.mouseClick(
        button,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        rect.center() - rect.topLeft(),
    )


# -- geometry ---------------------------------------------------------------


def test_the_host_numbers_are_reachable_by_constructor(qapp):
    field = _host_field()

    assert field.height() == HOST_FIELD_HEIGHT
    assert field._step_gutter_width() == HOST_GUTTER_WIDTH
    assert field.stepButtonsVisible() is True

    field.close()


def test_the_two_arrows_are_stacked_in_one_right_hand_column(qapp):
    field = _host_field()

    up = field._up_button_rect()
    down = field._down_button_rect()

    assert up.left() == down.left() == field.width() - HOST_GUTTER_WIDTH
    assert up.right() == field.width() - 1
    assert up.bottom() < down.top(), "the up arrow must sit above the down arrow"
    assert up.intersected(down).isEmpty()
    assert up.top() == 0 and down.bottom() == field.height() - 1

    field.close()


def test_the_text_area_shrinks_by_exactly_the_gutter(qapp):
    def build(show: bool) -> DoubleSpinBox:
        field = DoubleSpinBox(
            default_value=2.0,
            show_step_buttons=show,
            field_height=HOST_FIELD_HEIGHT,
            step_button_width=HOST_GUTTER_WIDTH,
        )
        field.setRange(0.0, 10.0)
        field.setSingleStep(0.5)
        field.setValue(2.0)
        return field

    plain = build(False)
    gutter = build(True)

    assert plain._step_gutter_width() == 0
    assert gutter.textMargins().right() - plain.textMargins().right() == HOST_GUTTER_WIDTH
    assert plain.textMargins().left() == gutter.textMargins().left()
    assert gutter.sizeHint().width() - plain.sizeHint().width() == HOST_GUTTER_WIDTH

    plain.close()
    gutter.close()


def test_hiding_the_gutter_leaves_a_plain_field(qapp):
    field = _host_field()

    field.setStepButtonsVisible(False)

    assert field._step_gutter_width() == 0
    assert field._up_button.isVisible() is False
    assert field._down_button.isVisible() is False

    field.close()


# -- pixels -----------------------------------------------------------------


def _rect_colors(image, rect) -> set[str]:
    return {
        image.pixelColor(x, y).name()
        for x in range(rect.left(), rect.right() + 1)
        for y in range(rect.top(), rect.bottom() + 1)
    }


def test_the_gutter_paints_two_distinct_arrow_regions(qapp):
    """A rendered field shows arrow glyphs in BOTH halves of the gutter.

    Not a full pixel-golden (the palette is host-owned): each half must contain
    at least one colour that is not its own fill, i.e. something was painted
    there — the ▲/▼ the stock control had and the bare number did not. Run
    under a REGISTERED palette so the glyph and the gutter wash both resolve
    instead of falling back to the theme-less black.
    """
    from sli_ui_toolkit import FLUENT_DARK, FLUENT_LIGHT
    from sli_ui_toolkit.ui.managers.theme_manager import ThemeManager

    tm = ThemeManager.get_instance()
    tm.register_palettes(FLUENT_LIGHT, FLUENT_DARK)
    tm.set_theme("light")

    field = _host_field()
    qapp.processEvents()

    image = field.grab().toImage()
    up_rect = field._up_button_rect()
    down_rect = field._down_button_rect()

    up_colors = _rect_colors(image, up_rect)
    down_colors = _rect_colors(image, down_rect)
    assert len(up_colors) > 1, "no ▲ glyph painted in the upper half"
    assert len(down_colors) > 1, "no ▼ glyph painted in the lower half"

    field.close()


# -- behaviour --------------------------------------------------------------


def test_clicking_the_lower_arrow_decreases_by_single_step(qapp):
    field = _host_field()
    assert field.value() == pytest.approx(2.0)

    _click_arrow(field, up=False)

    assert field.value() == pytest.approx(1.5), "the lower arrow steps DOWN by singleStep"

    field.close()


def test_clicking_the_upper_arrow_increases_by_single_step(qapp):
    field = _host_field()

    _click_arrow(field, up=True)

    assert field.value() == pytest.approx(2.5)

    field.close()


def test_an_arrow_is_disabled_at_its_bound(qapp):
    field = _host_field()

    field.setValue(10.0)
    assert field._up_button.isEnabled() is False
    assert field._down_button.isEnabled() is True

    field.setValue(0.0)
    assert field._up_button.isEnabled() is True
    assert field._down_button.isEnabled() is False

    field.close()


def test_the_int_variant_steps_by_one(qapp):
    field = SpinBox(default_value=4, show_step_buttons=True, field_height=HOST_FIELD_HEIGHT)
    field.setRange(0, 9)
    field.resize(field.sizeHint().width(), field.sizeHint().height())
    field.show()

    _click_arrow(field, up=False)
    assert field.value() == 3

    _click_arrow(field, up=True)
    assert field.value() == 4

    field.close()


# -- unchanged by default ---------------------------------------------------


def test_a_plain_spinbox_has_no_gutter(qapp):
    field = SpinBox(default_value=5)

    assert field.stepButtonsVisible() is False
    assert field._step_gutter_width() == 0
    assert field.textMargins().left() == field.textMargins().right()
    assert field.height() == 32

    field.close()


def test_stepper_keeps_its_wide_side_by_side_gauge(qapp):
    stepper = Stepper(default_value=3)
    stepper.setRange(1, 8)
    stepper.resize(160, 32)
    stepper.show()

    up = stepper._up_button_rect()
    down = stepper._down_button_rect()

    assert stepper._step_gutter_width() == 44, "Stepper's own gutter is unchanged"
    assert down.left() > up.left(), "Stepper keeps ▲/▼ side by side, not stacked"
    assert up.bottom() == down.bottom()

    stepper.close()


def test_a_step_field_keeps_its_text_cursor_and_an_arrow_over_the_gutter(qapp):
    """Qt's own split, and the toolkit's ``Text`` precedent: I-beam over the text, arrow over the non-text region.

    Pinning one arrow cursor over the whole field (an earlier attempt) cost the text its I-beam, so a value that is
    still edited by hand stopped looking editable (owner, 2026-11-22).
    """
    field = _host_field()
    qapp.processEvents()
    assert field.cursor().shape() == Qt.CursorShape.IBeamCursor, "the text keeps its I-beam"
    assert field._up_button.cursor().shape() == Qt.CursorShape.ArrowCursor
    assert field._down_button.cursor().shape() == Qt.CursorShape.ArrowCursor

    gutter_left = field._button_area_rect().left()
    QTest.mouseMove(field, QPoint(gutter_left // 2, field.height() // 2))
    qapp.processEvents()
    assert field.cursor().shape() == Qt.CursorShape.IBeamCursor

    QTest.mouseMove(field, QPoint(gutter_left + 2, field.height() // 2))
    qapp.processEvents()
    assert field.cursor().shape() == Qt.CursorShape.ArrowCursor

    field.setReadOnly(True)
    assert field.cursor().shape() == Qt.CursorShape.ArrowCursor, "a read-only field is not an editor"
    field.close()


def test_a_step_moves_the_value_the_field_can_show(qapp):
    """A whole-number field steps by whole units, so ▲ is never a press that changes nothing on screen.

    The host's migrated rows pass the adapter's fine step (``0.1``) and then pin ``decimals(0)``; with the step left at
    0.1 every press added a tenth under a text that stayed ``2`` (owner, 2026-11-22: "the arrows do nothing").
    """
    field = DoubleSpinBox(show_step_buttons=True, single_step=0.1, decimals=1)
    field.setRange(1.0, 4.0)
    field.setValue(2.0)
    field.setDecimals(0)
    field.resize(field.sizeHint().width(), field.sizeHint().height())
    field.show()
    qapp.processEvents()

    assert field.singleStep() == pytest.approx(1.0), "the step was raised to the shown precision"
    text_before = field.text()
    QTest.mouseClick(field._up_button, Qt.MouseButton.LeftButton)
    qapp.processEvents()
    assert field.value() == pytest.approx(3.0)
    assert field.text() != text_before, "the press is visible on screen"

    QTest.mouseClick(field._down_button, Qt.MouseButton.LeftButton)
    qapp.processEvents()
    assert field.value() == pytest.approx(2.0)
    field.close()


def test_a_fine_step_survives_a_field_that_shows_that_precision(qapp):
    """The guard must not coarsen a field that really shows tenths (scene-change threshold and friends)."""
    field = DoubleSpinBox(show_step_buttons=True, single_step=0.1, decimals=1)
    field.setRange(0.0, 5.0)
    field.setValue(2.0)
    field.show()
    qapp.processEvents()
    assert field.singleStep() == pytest.approx(0.1)
    QTest.mouseClick(field._up_button, Qt.MouseButton.LeftButton)
    qapp.processEvents()
    assert field.value() == pytest.approx(2.1)
    field.close()
