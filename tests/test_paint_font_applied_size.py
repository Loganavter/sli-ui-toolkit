"""`paint_font()` must not scale a size that `apply()` already scaled.

The bug (measured 2026-11-24 on a built window): `apply(pixel_size=12)` writes the RESOLVED size onto the widget
(12 px at factor 1.0, 24 px at 2.0), while `paint_font()` -> `rebase()` treats a source size as DESIGN space and
multiplies it by the factor again. At factor 2.0 a toolkit `Button` therefore PAINTED at 48 px and measured
424 px for "Encoder Options" instead of 236, and the process tab strip needed 1475 px in a 500 px column instead of
~886. `rebase_family()` already documented the rule ("fonts that are *already* scale-resolved ... must not be scaled
a second time"); `paint_font()` just did not use it.

The contract is now: a widget whose font matches what `apply()` resolved keeps its size; a widget whose font was
set to a DESIGN size (the toolkit's own convention for painter-measured widgets) is scaled exactly once; an explicit
`pixel_size=`/`point_size=` argument to `paint_font()` is design space and wins either way. The marker is a dynamic
property compared against the live size, so a widget whose font is replaced later silently falls back to design
semantics instead of inheriting a stale claim.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtGui import QFont  # noqa: E402

from sli_ui_toolkit.ui.managers import UiFont, UiScale  # noqa: E402
from sli_ui_toolkit.ui.managers.ui_font import APPLIED_SIZE_PROPERTY  # noqa: E402
from sli_ui_toolkit.widgets import Button  # noqa: E402

DESIGN_PX = 12


@pytest.fixture()
def scale(qapp):
    """The singleton factor, restored afterwards (it is process-wide by design)."""
    manager = UiScale.get_instance()
    before = manager.factor()
    yield manager
    manager.set_factor(before)


def _applied_button(scale, factor: float) -> Button:
    scale.set_factor(factor)
    button = Button(text="Encoder Options")
    UiFont.get_instance().apply(button, pixel_size=DESIGN_PX)
    return button


def test_an_applied_font_is_not_scaled_twice_when_painted(scale):
    painter = UiFont.get_instance()
    for factor in (1.0, 1.5, 2.0):
        button = _applied_button(scale, factor)
        expected = scale.scaled_px(DESIGN_PX)
        assert button.font().pixelSize() == expected, "apply() resolves the design size through the scale"
        assert painter.paint_font(button).pixelSize() == expected, (
            f"at factor {factor} the painted size must equal the applied one, not its square")


def test_a_design_sized_widget_font_is_scaled_exactly_once(scale):
    """The toolkit's own convention: a painter-measured widget carries a DESIGN size."""
    painter = UiFont.get_instance()
    for factor in (1.0, 1.5, 2.0):
        scale.set_factor(factor)
        button = Button(text="Encoder Options")
        design = QFont(qapp_font())
        design.setPixelSize(DESIGN_PX)
        button.setFont(design)
        assert painter.paint_font(button).pixelSize() == scale.scaled_px(DESIGN_PX)


def qapp_font() -> QFont:
    from PySide6.QtWidgets import QApplication

    return QApplication.font()


def test_an_explicit_paint_size_still_wins_over_the_applied_one(scale):
    painter = UiFont.get_instance()
    button = _applied_button(scale, 2.0)
    assert painter.paint_font(button, pixel_size=10).pixelSize() == 20, (
        "a caller's pixel_size is design space: it goes through the resolver once, whatever the widget carries")


def test_replacing_an_applied_font_drops_the_stale_claim(scale):
    """The marker self-validates: a different size on the widget means design semantics again."""
    painter = UiFont.get_instance()
    button = _applied_button(scale, 2.0)
    assert button.property(APPLIED_SIZE_PROPERTY) == ("px", DESIGN_PX)

    other = QFont(qapp_font())
    other.setPixelSize(30)
    button.setFont(other)
    assert painter.paint_font(button).pixelSize() == 60, (
        "a 30 px widget font that no longer matches the recorded 24 px resolution is design space, so it scales")
