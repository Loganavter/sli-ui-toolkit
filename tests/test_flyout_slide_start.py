"""Slide-in start must respect the shadow inset (no drop through the trigger)."""

from __future__ import annotations

from PySide6.QtCore import QRect

from sli_ui_toolkit.ui.widgets.composite.base_flyout import slide_start_delta


def test_vertical_slide_below_clamps_panel_to_anchor_bottom():
    # 36px toolbar button; flyout final outer top is just under it (offset=2).
    anchor = QRect(64, 48, 36, 36)
    final = QRect(64, anchor.bottom() + 2, 180, 200)
    distance = 24
    shadow = 8

    dx, dy = slide_start_delta(
        final,
        anchor,
        distance=distance,
        animation_axis="vertical",
        shadow_radius=shadow,
        ux=0.0,
        uy=1.0,
        length=1.0,
    )
    assert dx == 0
    start_y = final.y() + dy
    # Opaque panel top = start_y + shadow; must not sit inside the button.
    assert start_y + shadow >= anchor.bottom()
    # Naive start would be final.y - 24 = button_bottom - 22 (through center).
    assert start_y > final.y() - distance
    assert dy < 0  # still slides downward into place


def test_vertical_slide_below_keeps_full_distance_when_clearance_allows():
    anchor = QRect(0, 0, 40, 40)
    # Final far below the button so a 24px rise stays clear of the panel inset.
    final = QRect(0, 100, 120, 80)
    dx, dy = slide_start_delta(
        final,
        anchor,
        distance=24,
        animation_axis="vertical",
        shadow_radius=8,
        ux=0.0,
        uy=1.0,
        length=1.0,
    )
    assert (dx, dy) == (0, -24)


def test_show_below_drop_respects_shadow_inset(qtbot):
    """Interpolation-style show_below must not start through the combo body."""
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QWidget

    from sli_ui_toolkit.widgets import SimpleOptionsFlyout

    parent = QWidget()
    parent.resize(480, 360)
    qtbot.addWidget(parent)
    parent.show()

    combo = QWidget(parent)
    combo.setGeometry(80, 40, 160, 32)
    combo.show()

    flyout = SimpleOptionsFlyout(parent_widget=parent)
    flyout.populate(["Nearest", "Bilinear", "Bicubic"], 0)
    flyout.show_below(combo, exact_width_match=True)
    qtbot.wait(10)

    assert flyout._anim is not None
    start = flyout._anim.startValue()
    panel_start_top = start.y() + flyout.SHADOW_RADIUS
    anchor_bottom = combo.mapTo(flyout.parentWidget(), QPoint(0, combo.height())).y()
    assert panel_start_top >= anchor_bottom
    flyout.hide()
