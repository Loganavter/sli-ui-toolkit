"""The strip re-derives its cached bar geometry when the UI font lands.

Observed bug: ``AdaptiveTabStrip`` subscribed only to
``UiScale.scale_changed``, so the tab-bar minimum height derived in
``_sync_visual_tab_height()`` (from the add button's hint) was never
re-derived when the UI font landed a beat after construction — the strip sat
at the fallback-font geometry until an unrelated reflow.

Falsification: with the ``connect_ui_metrics`` wiring removed, the font
change reaches no strip slot (``calls == []`` / the stale minimum stays);
with it, the strip re-derives exactly once.
"""

from __future__ import annotations

import math

from sli_ui_toolkit.managers import UiFont
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


def test_strip_rederives_bar_min_height_on_font_change(qapp, monkeypatch):
    strip = _shown_strip(qapp)
    calls: list[int] = []
    original = strip._sync_visual_tab_height

    def _spy() -> None:
        calls.append(1)
        original()

    monkeypatch.setattr(strip, "_sync_visual_tab_height", _spy)
    UiFont.get_instance().sync_from_application()
    qapp.processEvents()
    assert calls == [1], (
        f"strip must re-derive geometry once on a UI font change; got {calls}"
    )
    assert strip.tab_bar.minimumHeight() == _expected_bar_min(strip)


def test_strip_refreshes_stale_bar_min_height_on_font_change(qapp):
    strip = _shown_strip(qapp)
    bar = strip.tab_bar
    # Startup shape: the derived minimum predates the UI font landing.
    bar.setMinimumHeight(1)
    assert bar.minimumHeight() == 1
    UiFont.get_instance().sync_from_application()
    qapp.processEvents()
    assert bar.minimumHeight() == _expected_bar_min(strip)
