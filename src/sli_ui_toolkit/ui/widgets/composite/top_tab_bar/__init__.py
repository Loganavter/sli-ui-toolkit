"""TopTabBar / TopTabHost — horizontal section navigation (IconListWidget twin).

Package layout:

- ``bar`` / ``tab_button`` / ``items`` — strip API and painted tabs
- ``host`` / ``pane`` / ``chrome`` — folder-tab frame + stack clip
- ``variant`` / ``constants`` — theme registration and sizing tokens
"""

from __future__ import annotations

from sli_ui_toolkit.ui.widgets.composite.top_tab_bar.bar import TopTabBar
from sli_ui_toolkit.ui.widgets.composite.top_tab_bar.host import TopTabHost
from sli_ui_toolkit.ui.widgets.composite.top_tab_bar.items import TopTabItem

__all__ = [
    "TopTabBar",
    "TopTabHost",
    "TopTabItem",
]
