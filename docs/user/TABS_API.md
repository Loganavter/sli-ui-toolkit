# Tabs API

Two independent tab families for two different jobs — pick by what the tabs
represent, not by look.

## TopTabBar / TopTabHost

Horizontal content-section tabs for dialogs (export settings, wizards). Twin of
`IconListWidget` on the other axis — not for closable workspace documents.

```python
from sli_ui_toolkit.widgets import TopTabHost

tabs = TopTabHost()
tabs.addTab(standard_page, "Standard")
tabs.addTab(manual_page, "Manual")
tabs.currentChanged.connect(on_tab_changed)
```

`TopTabBar` alone is enough when the host already owns a stack. Tab chrome is
painter-driven (`top_tab` Button variant); do not style tabs with QSS.

Implementation lives under `sli_ui_toolkit.ui.widgets.composite.top_tab_bar/`
(`bar`, `host`, `pane`, `chrome`, `tab_button`, …) — import the public types
from `sli_ui_toolkit.widgets`.

`TopTabBar` / `TopTabItem` / `TopTabHost` — `TopTabBar` is the painted strip;
`TopTabHost` adds a bordered page stack with folder-tab chrome and a
`QTabWidget`-like API (`addTab`, `setCurrentIndex`, `setTabText`, …).

## AdaptiveTabStrip

Compact workspace-style tabs with a trailing add button and adaptive close
buttons.

```python
from sli_ui_toolkit.widgets import AdaptiveTabStrip, CloseButtonPolicy

tabs = AdaptiveTabStrip(
    add_icon=AppIcon.ADD,
    close_icon=AppIcon.CLOSE,
    close_policy=CloseButtonPolicy.ALL_WHEN_FIT_ELSE_CURRENT,
    single_tab_closable=True,
)
tabs.addRequested.connect(create_workspace)
tabs.tabCloseRequested.connect(close_workspace)
tabs.currentChanged.connect(activate_workspace)
```

The strip reserves close-button width for every tab, so switching the selected
tab never changes tab widths. With the default close policy, every close button
is shown while full-size tabs fit; otherwise only the current tab keeps one.

`AdaptiveTabStrip` exposes common `QTabBar`-style methods such as `addTab`,
`removeTab`, `count`, `setCurrentIndex`, `setTabData`, and `tabData`. The
underlying widgets are available as `tab_bar` and `add_button`.

See also [API_CATALOG.md](API_CATALOG.md) for the full widget index.
