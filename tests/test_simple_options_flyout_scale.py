"""SimpleOptionsFlyout row metrics scale exactly once with UiScale.

Regression: the simple rows' label font was re-based onto an already
scale-resolved font (``ui_font()``), multiplying the factor a second time
— at 150%/200% UI scale the flyout's width grew ~factor^2 (2.9x at 2.0)
instead of ~factor. Row heights also failed to scale: ``sizeHint()``
returned the design ``_item_height`` while the row Button itself was
``setFixedHeight(scaled_px(...))``, so the container clipped the scaled
rows.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.managers import UiScale
from sli_ui_toolkit.ui.widgets.composite.simple_options_flyout import SimpleOptionsFlyout


@pytest.fixture(autouse=True)
def _reset_ui_scale():
    yield
    UiScale.get_instance().set_factor(1.0)


def _make_flyout(qtbot, labels) -> SimpleOptionsFlyout:
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(600, 500)
    host.show()
    flyout = SimpleOptionsFlyout(parent_widget=host)
    qtbot.addWidget(flyout)
    flyout.populate(labels, current_index=0)
    return flyout


def test_rows_and_flyout_grow_proportionally_with_scale(qtbot):
    labels = ["Off", "Highlight", "Grayscale", "Edge Comparison", "SSIM Map"]

    flyout_1 = _make_flyout(qtbot, labels)
    row_h_1 = flyout_1.rows()[0].height()
    w_1, h_1 = flyout_1.width(), flyout_1.height()

    UiScale.get_instance().set_factor(2.0)
    flyout_2 = _make_flyout(qtbot, labels)
    row_h_2 = flyout_2.rows()[0].height()
    w_2, h_2 = flyout_2.width(), flyout_2.height()

    # Row height scales exactly once: 36 design -> 72 at 2.0.
    assert row_h_2 == pytest.approx(row_h_1 * 2, abs=1)
    # Height scales (fixed outer margins dampen the ratio a little).
    assert h_2 > h_1 * 1.7
    # Width must track the font (once), not the font squared: the pre-fix
    # double rebase made the panel ~3x at 2.0.
    assert w_2 < w_1 * 2.1
    # Every scaled row must fit inside the panel it is sized for.
    container = flyout_2.container.height()
    rows_height = sum(r.height() for r in flyout_2.rows())
    spacing = flyout_2._rows_layout.spacing() * (len(flyout_2.rows()) - 1)
    margins = flyout_2.content_layout.contentsMargins()
    assert rows_height + spacing + margins.top() + margins.bottom() <= container


def test_set_row_height_scales_once(qtbot):
    flyout = _make_flyout(qtbot, ["A", "B"])

    UiScale.get_instance().set_factor(1.5)
    flyout.set_row_height(34)  # design px
    flyout.populate(["A", "B"], current_index=0)

    assert flyout.rows()[0].height() == pytest.approx(34 * 1.5, abs=1)


def test_reopen_after_scale_change_resolves_fresh_font(qtbot):
    """A cached flyout must not freeze its row font at first-open size."""
    flyout = _make_flyout(qtbot, ["RGB", "SSIM"])
    font_1 = flyout.rows()[0].label.font().pointSizeF()

    UiScale.get_instance().set_factor(1.5)
    flyout.populate(["RGB", "SSIM"], current_index=0)

    assert flyout.rows()[0].label.font().pointSizeF() == pytest.approx(
        font_1 * 1.5, abs=0.5
    )


def test_live_scale_change_while_open_resizes_text_and_panel(qtbot):
    flyout = _make_flyout(qtbot, ["RGB", "SSIM"])
    font_1 = flyout.rows()[0].label.font().pointSizeF()
    height_1 = flyout.height()

    UiScale.get_instance().set_factor(2.0)
    qtbot.wait(20)  # deferred _update_size runs after rows re-resolve

    assert flyout.rows()[0].label.font().pointSizeF() == pytest.approx(
        font_1 * 2, abs=0.5
    )
    assert flyout.height() > height_1
