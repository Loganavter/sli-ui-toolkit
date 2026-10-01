"""AdaptiveTabStrip settles the tab-bar height synchronously (qt-selfsizing T1).

``_sync_visual_tab_height`` derives the tab-bar minimum from the add button
while the strip layout places both children. Raising the minimum
self-enforces, but lowering it never shrinks the bar — without a
synchronous settle the strip layout reclaims the height a turn late and
the bar paints one frame too tall. These tests mutate the add-button
height on a *shown* strip and assert bar/minimum agreement in the same
synchronous call — no ``processEvents()`` between the mutation and the
assertions.
"""

from __future__ import annotations

import math

from sli_ui_toolkit.widgets import AdaptiveTabStrip


def _shown_strip(qapp) -> AdaptiveTabStrip:
    strip = AdaptiveTabStrip(add_icon="add", close_icon="remove")
    strip.addTab("First")
    strip.addTab("Second")
    strip.resize(900, strip.sizeHint().height())
    strip.show()
    qapp.processEvents()
    qapp.processEvents()
    return strip


def _expected_bar_min(strip: AdaptiveTabStrip) -> int:
    plus = max(
        strip.add_button.sizeHint().height(),
        strip.add_button.minimumHeight(),
        strip.add_button.height(),
    )
    return plus + math.ceil(
        strip.tab_bar._SELECTED_SHADOW_OFFSET
        + strip.tab_bar._SELECTED_SHADOW_SPREAD
    )


def _assert_bar_agrees(strip: AdaptiveTabStrip) -> None:
    expected = _expected_bar_min(strip)
    assert strip.tab_bar.minimumHeight() == expected
    assert strip.tab_bar.height() == expected, (
        f"tab-bar/minimum mismatch: height={strip.tab_bar.height()} "
        f"minimum={strip.tab_bar.minimumHeight()}"
    )


def test_grow_settles_tab_bar_same_call(qapp):
    strip = _shown_strip(qapp)
    base = strip.tab_bar.height()

    strip.add_button.setFixedHeight(strip.add_button.height() + 20)
    strip._sync_visual_tab_height()
    # No processEvents() between the mutation and these assertions.
    assert strip.tab_bar.height() > base
    _assert_bar_agrees(strip)


def test_shrink_settles_tab_bar_same_call(qapp):
    strip = _shown_strip(qapp)
    strip.add_button.setFixedHeight(strip.add_button.height() + 20)
    strip._sync_visual_tab_height()
    qapp.processEvents()
    grown = strip.tab_bar.height()

    strip.add_button.setFixedHeight(strip.add_button.height() - 20)
    strip._sync_visual_tab_height()
    # No processEvents() between the mutation and these assertions.
    assert strip.tab_bar.height() < grown
    _assert_bar_agrees(strip)
