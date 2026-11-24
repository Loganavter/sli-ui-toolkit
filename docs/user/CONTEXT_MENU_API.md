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

**Popup mode and QRhiWidgets.** A `popup` menu is a real `Qt.Popup` top-level
whose QWidget parent is the host's top-level window. In a window that also
hosts a `QRhiWidget` (including the toolkit's own `StripBand` and
`FlyoutGpuFillWidget`), that combination breaks the window's compositing on
Wayland/XWayland with NVIDIA: in-window translucent surfaces (toasts, flyouts)
render opaque and existing QRhiWidgets slow down. The first popup menu opened
in such a window logs one `logging` warning naming the `QRhiWidget` subclasses
and the alternative; the menu still opens in the requested mode. Use
`in_window` for menus in a window that owns QRhi surfaces. Recorded cases:
BlinkTable `inv-2026-10-06-ql-rhi-menu-first`, REAL-Video-Enhancer commit
`f471d71f` (its only `Qt.Popup` removed).

## MenuStrip — title-bar menu triggers

`MenuStrip` is the row of File/Help-style triggers a title bar hosts. Each
trigger is a toolkit `Button` (`variant="ghost"`); each dropdown is a
`ContextMenu` filled with the SAME `ContextMenuEntry` models documented above —
actions, shortcuts, disabled/danger rows, separators, sections and submenus all
work without a second menu model.

```python
from sli_ui_toolkit.widgets import ContextMenuAction, MenuStrip

strip = MenuStrip(parent, surface="in_window")   # the default surface
strip.add_menu("File", (
    ContextMenuAction("file.new", "New", shortcut="Ctrl+N"),
    ContextMenuAction("file.open", "Open…", shortcut="Ctrl+O"),
    ContextMenuSeparator(),
    ContextMenuAction("file.quit", "Quit", danger=True),
))
strip.add_menu("Help", (ContextMenuAction("help.about", "About"),))
strip.actionTriggered.connect(dispatch)          # (action_id, data)
title_bar.set_leading(strip)
navigation_manager.register(window, strip.navigation_section())
```

| Method | Behaviour |
|--------|-----------|
| `MenuStrip(parent=None, *, surface="in_window", trigger_height=None)` | `surface` is passed to every dropdown (`"in_window"` or `"popup"`). |
| `add_menu(title, entries, *, text_key=None, icon=None, tooltip="", enabled=True, on_triggered=None)` | One trigger + its entries. `text_key` wins over `title` and re-resolves on language change. |
| `set_menus(menus)` | Replace all: `MenuStripMenu` items or `(title, entries)` pairs. |
| `menu_titles()` / `menu_count()` | Trigger labels in strip order / trigger count. |
| `reveal(action_id, *, pulse=True)` | Open the menu owning `action_id`, focus its row (pulsing it); returns that row, or `None` when the id is unknown or only inside a submenu. |
| `close_menu()` / `current_menu()` | Close the dropdown / the visible `ContextMenu`, if any. |
| `navigation_section(tag="menu-strip")` | A `ToolbarRowsSection` over the triggers for the host to register. Left/Right walk triggers, Down/Enter open, Esc closes. |
| `clear()` | Drop every trigger. |

The strip never registers itself globally and never opens on hover. Only one
dropdown is open at a time; clicking the same trigger again, Esc, or an outside
click closes it (the last two via `ContextMenu`/`FlyoutManager`). Translatable
hosts bind a translator as usual (`bind_translator` / `install_translator`) and
menu titles plus keyed rows follow `language_changed`.

See also [WINDOW_CHROME_API.md](WINDOW_CHROME_API.md) for the title-bar zones a
strip is normally placed in.

---

See also [API_CATALOG.md](API_CATALOG.md) for the full widget index.
