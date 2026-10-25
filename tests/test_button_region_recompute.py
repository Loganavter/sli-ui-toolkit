"""A no-change resize must not recompute the region rects.

Measured in the app: ``workspace.sync_session_mode`` toggles a button, and its
``resizeEvent`` recomputed every region rect per sync (~251 ms of GUI block).
The rects/paths are a pure function of the widget rect, the split/divider, the
region list and the shape inputs, so repeating that pass with the same inputs
can only reproduce what is already stored.

Every test here counts real ``ButtonController.recompute_rects`` calls, so a
"green" means the pass did not run — not merely that the result looked the
same.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QSize
from PySide6.QtGui import QResizeEvent

from sli_ui_toolkit.widgets import Button, ButtonRegion, HorizontalSplit

SIZE = (120, 36)


def _button(qtbot) -> Button:
    button = Button(
        regions=[
            ButtonRegion(id="left", text="Left", group="row", weight=1.0),
            ButtonRegion(id="right", text="Right", weight=1.0),
        ],
        split=HorizontalSplit(),
        size=SIZE,
    )
    qtbot.addWidget(button)
    button.show()
    qtbot.waitExposed(button)
    return button


def _rects(button: Button) -> dict[str, tuple[float, float, float, float]]:
    return {
        region_id: (rect.x(), rect.y(), rect.width(), rect.height())
        for region_id, rect in button.region_rects().items()
    }


def _spy(button: Button) -> list[tuple[int, int]]:
    """Record the size every controller recompute ran on."""
    calls: list[tuple[int, int]] = []
    original = button._controller.recompute_rects

    def counting():
        calls.append((button.width(), button.height()))
        return original()

    button._controller.recompute_rects = counting  # type: ignore[method-assign]
    return calls


def _resize_to_the_same_size(button: Button, qapp) -> None:
    """Deliver the resize event a layout pass sends for an unchanged geometry.

    A user drag cannot produce it (Qt drops a resize to the same size), but a
    host that re-applies its layout does — the case that cost the app's GUI.
    """
    qapp.sendEvent(button, QResizeEvent(button.size(), button.size()))


def test_resize_to_the_same_size_does_not_recompute(qtbot, qapp):
    button = _button(qtbot)
    before = _rects(button)
    calls = _spy(button)

    _resize_to_the_same_size(button, qapp)
    qapp.processEvents()

    assert calls == []
    assert _rects(button) == before


def test_hundred_no_op_resizes_cost_nothing(qtbot, qapp):
    button = _button(qtbot)
    calls = _spy(button)

    for _ in range(100):
        _resize_to_the_same_size(button, qapp)
    qapp.processEvents()

    assert calls == []


def test_a_real_resize_recomputes_once_and_restores_identical_rects(qtbot, qapp):
    button = _button(qtbot)
    before = _rects(button)
    calls = _spy(button)

    # The button is fixed-size by construction, so this is how its geometry
    # changes in a real layout too (a window resize ends in setGeometry).
    button.setFixedSize(200, 60)
    qapp.processEvents()
    assert calls == [(200, 60)]
    grown = _rects(button)
    assert grown["left"][2] == pytest.approx(100.0)
    assert grown["right"][0] == pytest.approx(100.0)

    button.setFixedSize(*SIZE)
    qapp.processEvents()
    assert len(calls) == 2
    assert _rects(button) == before

    # What the memo serves after the round trip is exactly what a
    # from-scratch controller pass produces for the same inputs.
    button._controller.recompute_rects()
    assert _rects(button) == before


def test_a_region_change_still_recomputes_rects(qtbot):
    """Weights/rect_fn live in the region list, which the geometry key cannot see."""
    button = _button(qtbot)
    before = _rects(button)
    calls = _spy(button)

    button.update_region("left", weight=3.0)

    assert calls, "a rebuilt region list must not be masked by the geometry memo"
    after = _rects(button)
    assert after["left"][2] > before["left"][2]


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda button: button.setDensity("compact"), id="density"),
        pytest.param(lambda button: button.setVariant("surface"), id="variant"),
        pytest.param(lambda button: button.setCornerRadiusPx(10), id="corner-radius"),
        pytest.param(lambda button: button.setIconSizePx(16), id="icon-size"),
    ],
)
def test_a_shape_or_style_change_recomputes_on_the_next_resize(qtbot, qapp, mutate):
    button = _button(qtbot)
    calls = _spy(button)

    mutate(button)
    assert button.size() == QSize(*SIZE)
    assert calls == [], "the style setter alone must not need a rect pass"

    # Same geometry, changed shape inputs: the memo must not swallow the pass.
    _resize_to_the_same_size(button, qapp)
    qapp.processEvents()

    assert calls == [SIZE]
