# Window Chrome API

Composable client-side window decorations: title bar zones, menu strips, Button
and flyout anchors, and a one-call `WindowChrome.install` helper for dialogs.

For bootstrap imports:

```python
from sli_ui_toolkit import (
    CustomTitleBar,
    TitleBarMenu,
    TitleBarMenuStrip,
    TitleBarPresets,
    WindowChrome,
    WindowChromeConfig,
    WindowControlsConfig,
    decorate_dialog,
)
```

---

## Quick start

### Dialog (centered title + close)

```python
from sli_ui_toolkit import decorate_dialog

bar = decorate_dialog(dialog, title="Export", show_close=True)
bar.set_title("Updated title")
```

### Main window (IDE-style shell)

```python
from PySide6.QtGui import QIcon
from sli_ui_toolkit import TitleBarMenu, TitleBarMenuStrip, TitleBarPresets

menus = TitleBarMenuStrip([
    TitleBarMenu(label="File", icon=QIcon("app.png"), entries=[("Quit", app.quit)]),
    TitleBarMenu(
        label="Help",
        entries=[ContextMenuAction("help", "Show Help", shortcut="F1")],
    ),
])
bar = TitleBarPresets.app_shell("Improve ImgSLI", menus=menus)
bar.attach_window(main_window)
```

---

## Title bar zones

`CustomTitleBar` layout:

| Zone | API | Purpose |
|------|-----|---------|
| `leading` | `set_leading(widget)` / `set_icon(QIcon)` | App icon, menu strip |
| `center` | `set_center(widget)` / `set_title(text)` | Window title |
| `trailing` | `set_trailing(widget)` | Extra controls before window buttons |
| window controls | `window_controls()` | Min / max / close |

Convenience helpers:

- `add_button(button, zone="leading")`
- `add_buttons(buttons, zone="leading")`
- `set_menu_strip(TitleBarMenuStrip)`
- `set_icon(QIcon)` — leading app icon (transparent for drag)
- `add_widget(widget, zone=...)`

Title alignment: `set_title(text, align="center"|"leading")`.

Centered titles balance leading chrome (menus/icon) against trailing chrome
(window buttons). After `set_menu_strip` / language rebuilds the bar schedules
a deferred balance pass so measurement waits for the new strip's layout —
syncing against a zero `sizeHint` would leave a stale left pad and shove the
title off-center.

`TitleBarMenuStrip` triggers use equal top/bottom insets (`V_INSET=4`) so File/Help
buttons are not flush against the title-bar edges. Pass `icon=` on a `TitleBarMenu`
to put an app icon inside the same trigger capsule; spacing uses `Button(gap=…)` /
`TitleBarMenuStrip.GAP` — not a multi-region split.

Drag policy: window move starts only on non-interactive chrome. Buttons,
menu triggers, and widgets registered via `register_drag_exclusion` block drag.

---

## Menu strip

`TitleBarMenu` supports popup modes (auto-detected unless `mode=` is set):

| Mode | Entries | Mechanism |
|------|---------|-----------|
| `context_menu` | `ContextMenuAction`, sections, or `[(label, callback), ...]` | `popup_context_menu_for_anchor` |
| `flyout` | `flyout_factory=callable` | Caller-owned `BaseFlyout.show_aligned` |

Menu triggers are toolkit `Button(variant="ghost")` — full Button API applies
(icon, toggle, regions, etc.).

---

## Embedding Button and flyouts

Any `Button` can be placed in a title bar zone:

```python
btn = Button(icon="settings", variant="ghost", size=(36, CustomTitleBar.HEIGHT))
bar.add_button(btn, zone="trailing")

flyout = SimpleOptionsFlyout(parent_widget=main_window)
btn.clicked.connect(lambda: flyout.show_aligned(btn, anchor_point="bottom-center"))
```

Flyouts use the host window overlay (`attach_in_window_widget`). Active flyouts
close when the attached window moves or resizes (via `FlyoutManager`).

---

## WindowChrome installer

```python
chrome = WindowChrome.install(
    dialog,
    config=WindowChromeConfig(
        title_bar=bar,
        corner_radius=10,
        bg_token="Window",
        resizable=True,
        resize_margin=8,
    ),
)
chrome.set_background_token("Window")
chrome.title_bar().set_title("New title")
```

`decorate_dialog(...)` is a thin wrapper that builds a default title bar and
calls `WindowChrome.install`. Theme changes refresh the rounded body automatically.

---

## Presets

| Preset | Layout |
|--------|--------|
| `TitleBarPresets.dialog(title)` | Center title, close only |
| `TitleBarPresets.app_shell(title, menus=...)` | Leading menus, center title, full window controls |

---

## Theme tokens

| Token | Role |
|-------|------|
| `titlebar.background` | Title bar fill |
| `titlebar.text` | Title label |
| `titlebar.menu.hover` | Menu trigger hover (via ghost Button) |

Fallback: `Window` / `WindowText` when titlebar tokens are absent.

---

## Extending a minimal CustomTitleBar

`CustomTitleBar(title=..., icons...)` works as a standalone title bar. Add menus
later with `set_menu_strip` or rebuild via `TitleBarPresets.app_shell`.

Use `WindowChrome.install` when the window needs automatic `theme_changed`
background refresh without app-side dialog theme wiring.
