"""The workspace tab's geometry and chrome are stable across drivable states.

Owner report (live, merged build): the single selected tab changed width and
chrome within seconds — a ~180 px rounded pill with the close ``×``, then a
~159 px pill with **no** ``×``, then a ~157 px pill whose text had shrunk.
Two derived-state staleness bugs produced the spread:

* the close-button width reserved in every tab (``_tab_width``) was a
  **scaled snapshot** taken in the bar's constructor and never refreshed, so
  the moment ``UiScale`` changed afterwards the slots rescaled
  (``_CloseButtonSlot.resync``) while every tab stayed ``new − old`` px too
  narrow — the "tab shrinks" state;
* the width is measured with the bar's own font, so it must be the *settled*
  UI face (the T1 class: ``4737cfa`` re-fits the rects on ``font_changed``,
  but only from whatever face the bar holds);
* with ``CloseButtonPolicy.ALL`` the ``×`` is promised on every tab — a slot
  that appears/disappears with the tab count is the missing-``×`` state.

Falsification (recorded in DONE.md): the same file run against the pre-fix
source (``git archive 1ca5a59`` into a scratch dir inside the clone) is red
on the width composition and on the single-non-closable ``×``; the fixed tree
is green.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint
from PySide6.QtGui import QFont, QFontMetrics
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QTabBar

import pytest

from sli_ui_toolkit.managers import UiFont, UiScale
from sli_ui_toolkit.ui.managers.ui_scale import scaled_px
from sli_ui_toolkit.widgets import AdaptiveTabStrip, CloseButtonPolicy

RS = QTabBar.ButtonPosition.RightSide
TEXT = "Новая вкладка"


def _strip(*, single_tab_closable: bool = True) -> AdaptiveTabStrip:
    return AdaptiveTabStrip(
        add_icon="add",
        close_icon="remove",
        close_policy=CloseButtonPolicy.ALL,
        single_tab_closable=single_tab_closable,
    )


def _shown_strip(qapp, **kwargs) -> AdaptiveTabStrip:
    strip = _strip(**kwargs)
    strip.addTab(TEXT)
    strip.resize(900, strip.sizeHint().height())
    strip.show()
    _flush(qapp)
    return strip


def _flush(qapp, turns: int = 2) -> None:
    """Run the coalescing bus zero-timer plus the emission it schedules."""
    for _ in range(turns):
        qapp.processEvents()


def _width_from_real_close(bar) -> int:
    """The tab width the live state implies, from real objects only.

    ``standard_tab_width`` measures with the bar's live font (the same face
    the painter uses), the close reservation comes from the **real slot**
    (or the design size at the current factor when no slot is placed), and
    the gap is the bar's own token — no cached scaled snapshot anywhere.
    """
    slot = bar.tabButton(0, RS)
    reserve = (
        slot.width()
        if slot is not None and slot.width() > 0
        else scaled_px(bar._close_button_design_width)
    )
    return bar.standard_tab_width(0) + reserve + scaled_px(bar._CLOSE_GAP)


def _drive_states(qapp, strip, record) -> None:
    """Call ``record(label)`` through settled / hover / focus / font states."""
    record("settled (constructed + shown)")
    rect = strip.tab_bar.tabRect(0)
    QTest.mouseMove(strip.tab_bar, QPoint(rect.left() + 12, rect.center().y()))
    _flush(qapp)
    record("hover enter")
    QTest.mouseMove(strip.tab_bar, QPoint(5, 5))
    _flush(qapp)
    record("hover leave")
    strip.tab_bar.setFocus()
    _flush(qapp)
    record("keyboard focus")
    strip.tab_bar.clearFocus()
    _flush(qapp)
    record("focus lost")
    UiFont.get_instance().sync_from_application()
    _flush(qapp)
    record("font sync")


def test_tab_width_is_invariant_across_drivable_states(qapp):
    strip = _shown_strip(qapp)
    bar = strip.tab_bar
    seen: list[tuple[str, int]] = []

    def record(label: str) -> None:
        width = bar.tabRect(0).width()
        # The width must account for the REAL close slot, measured now —
        # never a value cached before the state changed.
        assert width == _width_from_real_close(bar), (
            f"{label}: tabRect(0).width()={width} but the live font + real "
            f"close slot imply {_width_from_real_close(bar)}"
        )
        seen.append((label, width))

    _drive_states(qapp, strip, record)

    widths = {width for _, width in seen}
    assert len(widths) == 1, f"tab width drifted across states: {seen}"


def test_tab_width_keeps_the_real_close_slot_after_a_scale_change(qapp):
    """A live UiScale change rescales the slot — the reservation follows it.

    Pre-fix: ``_tab_width`` added a scaled snapshot cached in ``__init__``,
    so at factor 1.5 the real slot was 42 px while every tab reserved 28 —
    the tab came out 14 px narrower than the chrome it had to hold.
    """
    strip = _shown_strip(qapp)
    bar = strip.tab_bar
    base = bar.tabRect(0).width()
    scale = UiScale.get_instance()
    try:
        scale.set_factor(1.5)
        _flush(qapp)
        slot = bar.tabButton(0, RS)
        assert slot is not None and slot.width() > 28, (
            "the close slot must really have rescaled for this test to bite"
        )
        assert bar.tabRect(0).width() == _width_from_real_close(bar)
        scale.set_factor(1.0)
        _flush(qapp)
        assert bar.tabRect(0).width() == base
    finally:
        scale.set_factor(1.0)
        _flush(qapp)


@pytest.mark.parametrize("single_tab_closable", [True, False])
def test_close_slot_is_visible_and_placed_with_policy_all(qapp, single_tab_closable):
    """``CloseButtonPolicy.ALL`` promises the ``×`` on every tab, always.

    Pre-fix, a single tab built with ``single_tab_closable=False`` had its
    slot dropped by ``_should_show_close_button`` — the owner's no-``×``
    state (their workspace strip runs ALL).
    """
    strip = _shown_strip(qapp, single_tab_closable=single_tab_closable)
    bar = strip.tab_bar
    placed: list[str] = []

    def record(label: str) -> None:
        slot = bar.tabButton(0, RS)
        assert slot is not None, f"{label}: policy ALL must place a close slot"
        assert not slot.isHidden(), f"{label}: the close slot must not be hidden"
        assert slot.isVisible(), f"{label}: the close slot must be visible"
        painted = bar._painted_tab_rect(bar.tabRect(0))
        assert painted.contains(slot.geometry()), (
            f"{label}: close slot {slot.geometry()} is not inside the painted "
            f"tab {painted}"
        )
        assert slot.button.width() > 0 and slot.button.height() > 0, label
        placed.append(label)

    _drive_states(qapp, strip, record)
    assert len(placed) == 6


def test_tab_width_follows_the_resolved_font_on_a_scale_only_change(qapp):
    """The width is measured from the settled UI face, not a lagging one.

    The bar owns its font (``apply_ui_font``), so an application-font change
    alone does not reach it; a later *scale-only* metrics pass must still
    recompute the width from the resolved face rather than from the face the
    bar happens to hold.
    """
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    ui_font = UiFont.get_instance()
    scale = UiScale.get_instance()
    previous_app = QFont(app.font())
    previous_override = ui_font._family_override
    strip = None
    try:
        strip = _shown_strip(qapp)
        bar = strip.tab_bar

        host_font = QFont(previous_app)
        host_font.setPointSizeF(max(1.0, previous_app.pointSizeF()) + 4)
        app.setFont(host_font)
        # The bar keeps its own (now stale) face: no UiFont notification yet.
        stale = QFont(bar.font())
        stale.setPointSizeF(max(1.0, stale.pointSizeF()) - 4)
        bar.setFont(stale)
        _flush(qapp)
        stale_advance = QFontMetrics(bar.font()).horizontalAdvance(TEXT)

        scale.set_factor(1.25)
        _flush(qapp)

        resolved = ui_font.resolve()
        assert QFontMetrics(bar.font()).horizontalAdvance(TEXT) == QFontMetrics(
            resolved
        ).horizontalAdvance(TEXT), (
            "a scale-only metrics pass must re-assert the resolved UI font "
            "before the tab width is recomputed"
        )
        assert QFontMetrics(bar.font()).horizontalAdvance(TEXT) > stale_advance
        assert bar.tabRect(0).width() == _width_from_real_close(bar)
    finally:
        scale.set_factor(1.0)
        app.setFont(previous_app)
        ui_font.set_family(previous_override)
        ui_font.sync_from_application()
        _flush(qapp)
        if strip is not None:
            strip.close()
