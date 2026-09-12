"""Regression: _AdaptiveTabBar must relayout on font change.

sizeHint() reads the live font (QFontMetrics(self.font())), but _rects and
the close-slot positions were only recomputed in _relayout() from
addTab/insertTab/removeTab/setTabText/_on_scale_changed — never on a font
change. So after UiFont/theme/setFont switched the face, the parent layout
gave the bar the new (wider) hint while content still painted from the old
_rects: the close slot stayed at the old x and a dead zone opened between
the last tab content and the "+" button.
"""

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QTabBar

from sli_ui_toolkit.ui.widgets.composite.adaptive_tab_strip.tab_bar import (
    _AdaptiveTabBar,
)
from sli_ui_toolkit.widgets import AdaptiveTabStrip, CloseButtonPolicy


def _strip():
    return AdaptiveTabStrip(
        add_icon="add",
        close_icon="remove",
        close_policy=CloseButtonPolicy.ALL_WHEN_FIT_ELSE_CURRENT,
        single_tab_closable=True,
    )


def test_font_change_relayouts_tabs_and_close_slots(qapp):
    strip = _strip()
    strip.addTab("Workspace settings panel")
    strip.resize(900, strip.sizeHint().height())
    strip.show()
    qapp.processEvents()
    strip.refresh_close_buttons()
    qapp.processEvents()

    bar = strip.tab_bar
    slot = bar.tabButton(0, QTabBar.ButtonPosition.RightSide)
    assert slot is not None
    old_x = slot.x()

    font = QFont(bar.font())
    font.setPointSize(font.pointSize() + 8)
    bar.setFont(font)
    qapp.processEvents()
    # Host gives the bar the new (wider) hint, like a real parent layout.
    strip.resize(strip.width(), strip.sizeHint().height())
    qapp.processEvents()
    strip.refresh_close_buttons()
    qapp.processEvents()

    slot = bar.tabButton(0, QTabBar.ButtonPosition.RightSide)
    assert slot is not None
    # Tabs were re-measured with the new font: rects grew, slot moved right.
    assert bar.tabRect(0).width() > 0
    assert slot.x() > old_x
    # No dead zone inside the bar: slot right edge sits at the tab's right
    # edge minus the close margin (painted inset accounts for the +2 slack).
    dead_inside_bar = bar.width() - (slot.x() + slot.width())
    assert dead_inside_bar <= _AdaptiveTabBar._CLOSE_RIGHT_MARGIN + 2
