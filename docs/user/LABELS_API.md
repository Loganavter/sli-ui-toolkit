# Label API

`Label` is the unified text component. Set the typography and behavior directly,
or start from a registered variant when a shared preset is useful.

```python
from sli_ui_toolkit.widgets import Label, LabelConfig

title = Label("Settings", variant="group-title")
body = Label("Ready", pixel_size=12)
caption = Label("Secondary status", pixel_size=11)
custom = Label(
    config=LabelConfig(
        text="Pinned",
        pixel_size=10,
        bold=True,
        color_token="accent",
        elide=True,
        minimum_width=80,
    )
)
```

**Common options:**

| Option | Description |
|--------|-------------|
| `text` | Label text. |
| `variant` | Optional registered preset name. |
| `family` | Font family override. |
| `pixel_size` | Font size in pixels. |
| `bold` / `italic` / `underline` / `strike_out` | Font styling flags. |
| `color` / `color_token` | Explicit `QColor` or `ThemeManager` token. |
| `alignment` | Qt alignment flags. |
| `elide` | Elide overflowing text with an ellipsis. |
| `marquee` | Scroll overflowing text left→right in a loop (wins over `elide`). Also: `apply_marquee(qlabel)`. |
| `minimum_width` | Minimum width used by size hints. |
| `expanding` | Use an expanding horizontal size policy. |
| `word_wrap` | Enable wrapped multiline text. |
| `selectable` | Enable mouse/keyboard text selection. |

**Built-in presets:**

| Variant | Size | Weight | Behavior |
|---------|------|--------|----------|
| `"body"` | 12 px | Normal | Standard body text |
| `"caption"` | 11 px | Normal | Small secondary/status text |
| `"compact"` | 10 px | Normal | Dense elided text |
| `"group-title"` | 13 px | Bold | Section headers |
| `"adaptive"` | 12 px | Normal | Expanding elided text |

Register a custom variant with `register_label_variant(name, LabelVariantSpec(...))`
and look it up with `get_label_variant(name)`.

**Widgets:**

| Widget | Description |
|--------|-------------|
| `Label` | Unified themed text label with direct typography and behavior options. |
| `LabelConfig` | Declarative configuration object for `Label`. |
| `LabelVariantSpec` | Typography/color variant registry entry. |
| `DropZoneLabel` | Label with drag-and-drop zone visuals and file accept logic. |

See also [API_CATALOG.md](API_CATALOG.md) for the full widget index.
