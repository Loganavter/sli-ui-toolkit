"""The thumb's thickness is a host-facing number, not a module constant.

The bar's *slot* was public (``MINIMAL_SCROLLBAR_WIDTH``) while the thumb's own idle/hover/drag widths stayed private, so
a host that wanted a heavier or lighter handle had to fork the widget (owner's open item, 2026-11-22). The setter states
the three widths, clamps them to the slot, and the painted handle follows.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt

from sli_ui_toolkit.ui.widgets.atomic.minimalist_scrollbar import (
    MINIMAL_SCROLLBAR_WIDTH,
    MinimalistScrollBar,
)


def test_the_defaults_are_the_documented_look(qapp):
    bar = MinimalistScrollBar(Qt.Orientation.Vertical)
    assert bar.thumb_thickness() == (4, 6, MINIMAL_SCROLLBAR_WIDTH)


def test_setting_the_three_states_clamps_to_the_slot(qapp):
    bar = MinimalistScrollBar(Qt.Orientation.Vertical)
    bar.set_thumb_thickness(idle=6, hover=8, drag=12)  # drag wider than the slot
    assert bar.thumb_thickness() == (6, 8, MINIMAL_SCROLLBAR_WIDTH)


def test_a_partial_update_leaves_the_other_states_alone(qapp):
    bar = MinimalistScrollBar(Qt.Orientation.Vertical)
    bar.set_thumb_thickness(hover=2)
    assert bar.thumb_thickness() == (4, 2, MINIMAL_SCROLLBAR_WIDTH)


def test_the_painted_handle_follows_the_idle_thickness(qapp):
    """No `show()` here on purpose: a mapped bar can already be `_hovered`, and then the painted width is the hover
    width - the assertion would be about the wrong state instead of the setter."""
    bar = MinimalistScrollBar(Qt.Orientation.Vertical)
    bar.setRange(0, 100)
    bar.setValue(0)
    bar.resize(MINIMAL_SCROLLBAR_WIDTH, 200)

    before = bar._get_handle_rect().width()
    bar.set_thumb_thickness(idle=2)
    after = bar._get_handle_rect().width()

    assert bar.thumb_thickness()[0] == 2
    assert after < before, f"the painted thumb did not get thinner ({before} -> {after})"
