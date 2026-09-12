# ContextMenu API

`ContextMenu` is a theme-aware native `QMenu` for right-click commands. It is
intended for app/domain context actions such as rename, duplicate, remove,
properties, and submenus. Compared with flyouts (see
[FLYOUT_SYSTEM.md](FLYOUT_SYSTEM.md)), it uses Qt's menu behavior for focus,
keyboard navigation, submenus, and native popup lifecycle.

```python
from sli_ui_toolkit.widgets import ContextMenuBuilder

menu = (
    ContextMenuBuilder()
    .action("rename", "Rename", shortcut="F2")
    .action("duplicate", "Duplicate")
    .separator()
    .action("remove", "Remove", danger=True)
    .build(parent, on_triggered=lambda action_id, data: ...)
)
menu.popup_at(global_pos)
```

`ContextMenuAction.defer_trigger: bool = False` — the context-menu equivalent
of `Button(defer_click=DEFER_CLICK_AWAIT_RIPPLE)`. A row click normally hides
the whole menu and invokes `on_triggered` synchronously, which for a row whose
action opens a modal (`.exec()`) dialog means the row (and its own click
ripple) is destroyed by the menu closing before the ripple gets to play at
all. `defer_trigger=True` waits one ripple duration
(`get_ripple_duration_ms()`) with the menu still open before hiding + firing.

**Public names:**

| Name | Description |
|------|-------------|
| `ContextMenu` | `QMenu` subclass built from declarative entries. |
| `ContextMenuAction` | Action item model: id, text, icon, enabled, checked, danger, shortcut, data, children, defer_trigger. |
| `ContextMenuSeparator` | Separator model. |
| `ContextMenuSection` | Group of entries with optional disabled title. |
| `ContextMenuBuilder` | Chainable builder for common menus. |
| `entries_from_labeled_data(items, current=..., checkable=...)` | Build picker entries from `[(label, data), ...]`; current row is highlighted (no check glyph). |
| `entries_from_callbacks(items)` | Build command entries from `[(label, callback_or_data), ...]`. |
| `popup_context_menu_for_anchor(parent, anchor, entries, ...)` | Anchor-aligned dropdown (replaces removed `Button.menu` / `DropdownMenu`). |
| `show_context_menu(parent, global_pos, entries, on_triggered=...)` | Convenience function that builds and pops up a menu. |

`configure_toolkit(context_menu_surface="in_window" | "popup")` sets the
process-wide default rendering surface when a call site doesn't specify one
explicitly — see [CONFIGURATION.md](CONFIGURATION.md).

See also [API_CATALOG.md](API_CATALOG.md) for the full widget index.
