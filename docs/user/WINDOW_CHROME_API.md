# Window Chrome API

Composable client-side window decorations: title bar zones, Button and flyout
anchors, and a one-call `WindowChrome.install` helper for dialogs.

The title bar is a **generic shell**: it hosts whatever leading-zone widget the
host app injects. The toolkit does not know about menus — the app owns its
title-bar content (File/Help triggers and how their dropdowns open) and decides
popup vs in-window per menu.

For bootstrap imports:

```python
from sli_ui_toolkit import (
    CustomTitleBar,
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

The app builds its own leading content (e.g. File/Help trigger buttons that
open its own menus) and injects it into the generic title bar:

```python
from PySide6.QtWidgets import QHBoxLayout, QWidget
from sli_ui_toolkit import TitleBarPresets
from sli_ui_toolkit.ui.widgets.buttons import Button

def build_menus(parent):
    strip = QWidget(parent)
    layout = QHBoxLayout(strip)
    layout.addWidget(Button("File", variant="ghost", size=(64, 24), parent=strip))
    layout.addWidget(Button("Help", variant="ghost", size=(64, 24), parent=strip))
    # …wire each trigger to open the app's own menu (popup or in-window)…
    return strip

bar = TitleBarPresets.app_shell("Improve ImgSLI", leading=build_menus(main_window))
bar.attach_window(main_window)
```

---

## Title bar zones

`CustomTitleBar` layout:

| Zone | API | Purpose |
|------|-----|---------|
| `leading` | `set_leading(widget)` / `set_icon(QIcon)` | App icon, app-provided controls |
| `center` | `set_center(widget)` / `set_title(text)` | Window title |
| `trailing` | `set_trailing(widget)` | Extra controls before window buttons |
| window controls | `window_controls()` | Min / max / close |

Convenience helpers:

- `add_button(button, zone="leading")`
- `add_buttons(buttons, zone="leading")`
- `set_icon(QIcon)` — leading app icon (transparent for drag)
- `add_widget(widget, zone=...)`

Title alignment: `set_title(text, align="center"|"leading")`.

Centered titles balance leading chrome (app controls/icon) against trailing
chrome (window buttons). After `set_leading` / language rebuilds the bar
schedules a deferred balance pass so measurement waits for the new leading
widget's layout — syncing against a zero `sizeHint` would leave a stale left
pad and shove the title off-center.

Drag policy: window move starts only on non-interactive chrome. Buttons and
widgets registered via `register_drag_exclusion` block drag.

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

For dropdown menus the app constructs a toolkit `ContextMenu` with an explicit
surface (`surface="in_window"` for an in-window overlay below the title bar, or
`surface="popup"` for a frameless Qt popup) and anchors it to the trigger with
`show_aligned`. The toolkit `ContextMenu` defaults to the in-window surface.

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
| `TitleBarPresets.app_shell(title, leading=…)` | Leading app widget, center title, full window controls |

---

## Theme tokens

| Token | Role |
|-------|------|
| `titlebar.background` | Title bar fill |
| `titlebar.text` | Title label |
| `titlebar.menu.hover` | Menu trigger hover (via ghost Button) |

Fallback: `Window` / `WindowText` when titlebar tokens are absent.

`CustomTitleBar(..., bg_color=None, text_color=None)` overrides the
background fill / title text color per-instance (`None`, the default,
keeps the theme token above). Runtime setters: `set_background_color(color)`,
`set_title_color(color)` — pass `None` to revert to the theme token.

```python
bar = CustomTitleBar(title="Export", bg_color="#202020", text_color="#ffffff")
bar.set_background_color(None)  # back to the titlebar.background token
```

---

## Extending a minimal CustomTitleBar

`CustomTitleBar(title=..., icons...)` works as a standalone title bar. Add
leading controls later with `set_leading` or build the full shell via
`TitleBarPresets.app_shell`.

Use `WindowChrome.install` when the window needs automatic `theme_changed`
background refresh without app-side dialog theme wiring.
