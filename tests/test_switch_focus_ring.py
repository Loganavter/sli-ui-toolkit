"""Switch focus indication: a keyboard-focused Switch must paint a focus ring.

Regression (owner report 2026-10-19): "на свиче непонятно, есть кольцо фокуса
или нет — отличить невозможно". ``Switch`` paints itself and never attached the
toolkit's ``FocusLayer`` (unlike ``Button``); its ``focusInEvent`` only called
``update()``, so a focused switch looked exactly like an unfocused one. The ring
now comes from the shared ``atomic/focus_ring.paint_focus_ring`` (the same
helper ``Slider`` uses), gated on the modality flag that
``resolve_keyboard_focus`` (NavigationManager) sets — a mouse click must not
paint one.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

from sli_ui_toolkit.ui.managers.navigation_manager import resolve_keyboard_focus
from sli_ui_toolkit.widgets import Switch


def _hosted(qtbot) -> tuple[Switch, QWidget]:
    host = QWidget()
    layout = QVBoxLayout(host)
    switch = Switch()
    layout.addWidget(switch)
    qtbot.addWidget(host)
    host.show()
    qtbot.waitExposed(host)
    QApplication.setActiveWindow(host)
    return switch, host


def _render(switch: Switch) -> QImage:
    image = QImage(switch.size(), QImage.Format.Format_ARGB32)
    image.fill(0)
    switch.render(image)
    return image


def _render(switch: Switch) -> QImage:
    image = QImage(switch.size(), QImage.Format.Format_ARGB32)
    image.fill(0)
    switch.render(image)
    return image


def _outer_band_diff(a: QImage, b: QImage) -> tuple[int, int]:
    """(differing pixels in the OUTER band, differing pixels anywhere).

    Colour-matching the accent proved fragile (the knob/track carry accent-ish
    pixels); a distinct-content comparison — focus changes the render, and the
    change lives in the ring band — is the honest check. Precedent: the paint
    identity tests.
    """
    band = max(1, min(a.width(), a.height()) // 6)
    # "inner" = the CENTRAL box only: the pill ring's antialiased arc passes
    # through the widget's vertical middle at its rounded ends, so a plain
    # outside-the-band test would count the ring itself as an interior change.
    x0, x1 = a.width() // 4, (3 * a.width()) // 4
    y0, y1 = a.height() // 4, (3 * a.height()) // 4
    outer = inner = 0
    for y in range(a.height()):
        for x in range(a.width()):
            if a.pixel(x, y) == b.pixel(x, y):
                continue
            if x0 <= x < x1 and y0 <= y < y1:
                inner += 1
            elif (
                x < band
                or y < band
                or x >= a.width() - band
                or y >= a.height() - band
            ):
                outer += 1
    return outer, inner


def test_a_keyboard_focused_switch_paints_a_visible_ring(qapp, qtbot):
    switch, host = _hosted(qtbot)
    switch.setFocus(Qt.FocusReason.TabFocusReason)
    qapp.processEvents()
    switch._keyboard_focus = False
    qapp.processEvents()
    unfocused = _render(switch)

    assert switch.hasFocus(), "the Switch could not take focus at all"
    switch._keyboard_focus = True
    qapp.processEvents()
    focused = _render(switch)
    outer, inner = _outer_band_diff(unfocused, focused)
    assert outer > 0, (
        "a keyboard-focused Switch painted no focus ring — the owner cannot tell "
        "whether it has focus"
    )
    assert inner == 0, f"the focus change repainted {inner} pixels inside the ring band"
    # …and the ring must clear the track (the reported overlap): the track is
    # inset by RING_GUTTER on every side, so the widget is taller than the track.
    from sli_ui_toolkit.ui.managers.ui_scale import scaled_px

    assert switch.sizeHint().height() >= scaled_px(switch.TRACK_HEIGHT) + 2 * scaled_px(
        switch.RING_GUTTER
    ), "no ring gutter: the focus ring would overlap the track"
    assert host.isVisible()


def test_focus_events_wire_the_central_modality_contract(qapp, qtbot):
    """focusIn must take the flag from NavigationManager's device-based resolver.

    The resolver is the single source of truth (input device, not the focus
    reason), so this asserts the wiring, not a hard-coded expectation: a mouse
    reason must never look like keyboard focus.
    """
    switch, host = _hosted(qtbot)
    switch.setFocus(Qt.FocusReason.MouseFocusReason)
    qapp.processEvents()
    assert switch._keyboard_focus is False

    switch.clearFocus()
    switch.setFocus(Qt.FocusReason.TabFocusReason)
    qapp.processEvents()
    assert switch._keyboard_focus == bool(resolve_keyboard_focus(Qt.FocusReason.TabFocusReason))
    assert host.isVisible()
