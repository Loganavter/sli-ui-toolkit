"""The adaptive tab bar must re-fit its cached rects when the UI font changes.

Falsification (pre-fix): the bar connected ``scale_changed`` but NOT
``font_changed``. ``apply_ui_font`` re-applies a later font (startup font
correction) via ``UiFont.apply``, which only calls ``setFont``; the cached
``_rects`` (paint + hit-test) are recomputed only in ``_relayout`` — so the tab
rects stayed at the transient fallback font's width until an unrelated relayout
(the "first tab too small for ~0.5 s, then grows" report).
"""

from __future__ import annotations

from sli_ui_toolkit.ui.managers.ui_font import UiFont
from sli_ui_toolkit.ui.widgets.composite.adaptive_tab_strip.tab_bar import (
    _AdaptiveTabBar,
)


def test_tab_bar_relayouts_on_font_changed(qapp, qtbot) -> None:
    bar = _AdaptiveTabBar(close_button_design_width=20)
    qtbot.addWidget(bar)
    bar.addTab("A reasonably long tab title")
    calls: list[int] = []
    bar._relayout = lambda: calls.append(1)  # type: ignore[method-assign]
    # The unified metrics channel coalesces through a zero-timer (see
    # ui_metrics), so the re-fit lands on the next event-loop turn.
    UiFont.get_instance().sync_from_application()
    qapp.processEvents()
    assert calls, "tab bar did not re-fit rects on font_changed"
