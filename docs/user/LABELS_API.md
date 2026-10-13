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

## Text (plain mode)

`Text` is the replacement for `Label` in the unified text work (contract:
`docs/text-unification-plan`, `docs/dev/TEXT_UNIFICATION.md`). P1 ships `mode="plain"` only, at `Label`
parity: same keyword options, same variant registry, same pixels for unselected
text.

```python
from sli_ui_toolkit.widgets import Text, TextConfig

caption = Text("Secondary status", variant="caption", elide=True)
note = Text(config=TextConfig(text="Pinned", bold=True, selectable=True))
```

- `mode="document"` and `mode="code"` raise `NotImplementedError` until P2.
- `selectable=True` adds mouse drag, double-click word selection, `Ctrl+A`,
  `Ctrl+C`, arrow/Home/End keys with Shift, and the right-click Copy / Select
  all menu. `selectionChanged` fires on each change.
- Known gap vs `Label`: `sizeHint()` of a wrapped text is the single-line
  width, not `QLabel`'s area-balanced hint. Layouts should rely on
  `heightForWidth()`, which matches `Label`.
- Variants and `register_label_variant` are shared with `Label` until `Label`
  is retired; `register_text_variant` is the same registry under the new name.
