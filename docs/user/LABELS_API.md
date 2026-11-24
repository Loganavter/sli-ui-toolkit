# Text API

`Text` is the unified text display widget: one `QWidget`
(`src/sli_ui_toolkit/ui/widgets/text/text.py`), configured like `Button` —
keyword arguments or a frozen `TextConfig`, no subclasses. Three modes:

| `mode` | What it paints |
|--------|----------------|
| `"plain"` (default) | Static text. The replacement for the retired public `Label`. |
| `"document"` | Markdown through the painted engine (TOC / lightbox compose in the host). |
| `"code"` | Editable painted code buffer. |

Set typography and behavior directly, or start from a registered variant when a
shared preset is useful.

```python
from sli_ui_toolkit.widgets import Text, TextConfig

title = Text("Settings", variant="group-title")
body = Text("Ready", pixel_size=12)
caption = Text("Secondary status", pixel_size=11)
custom = Text(
    config=TextConfig(
        text="Pinned",
        pixel_size=10,
        bold=True,
        color_token="accent",
        elide=True,
        minimum_width=80,
    )
)
```

**Common options** (`Text.__init__` kwargs; `TextConfig` carries the same fields):

| Option | Description |
|--------|-------------|
| `text` | Text content (first positional argument). |
| `mode` | `"plain"` (default) / `"document"` / `"code"`; fixed at construction. |
| `variant` | Optional registered preset name (default `"body"`). |
| `family` | Font family override. |
| `pixel_size` | Font size in pixels. |
| `bold` / `italic` / `underline` / `strike_out` | Font styling flags. |
| `color` / `color_token` | Explicit `QColor` or `ThemeManager` token. |
| `alignment` | Qt alignment flags. |
| `elide` | Elide overflowing text with an ellipsis. |
| `marquee` | Scroll overflowing text left→right in a loop (wins over `elide`). |
| `minimum_width` | Minimum width used by size hints. |
| `expanding` | Use an expanding horizontal size policy. |
| `word_wrap` | Enable wrapped multiline text. |
| `selectable` | Enable mouse/keyboard text selection. |
| `editable` | Editable buffer (`mode="code"`). |
| `resolve_asset` | Document-mode image resolver (callable). |
| `open_external_links` | Open `http(s)` links via `QDesktopServices` (default `True`). |
| `text_key` | Translation key; retranslate repaints from it. |

**Built-in presets** (`ui/widgets/text/variants.py`):

| Variant | Size | Weight | Behavior |
|---------|------|--------|----------|
| `"body"` | 12 px | Normal | Standard body text |
| `"caption"` | 11 px | Normal | Small secondary/status text |
| `"compact"` | 10 px | Normal | Dense elided text |
| `"group-title"` | 13 px | Bold | Section headers |
| `"adaptive"` | 12 px | Normal | Expanding elided text |

Register a custom variant with `register_text_variant(TextVariantSpec(...))`
and look it up with `get_text_variant(name)`. `register_label_variant` /
`get_label_variant` remain as aliases of the same registry, and
`LabelVariantSpec` is the same class as `TextVariantSpec`.

**Widgets:**

| Widget | Description |
|--------|-------------|
| `Text` | The display widget: `plain` / `document` / `code` modes. |
| `TextConfig` | Frozen declarative configuration object for `Text`. |
| `TextScrollArea` | Scroll host for one `Text` (toolkit scrollbar, rounded border overlay); import from `sli_ui_toolkit.ui.widgets.composite`. |
| `LabelVariantSpec` | Typography/color variant registry entry (alias of `TextVariantSpec`). |
| `DropZoneLabel` | Label with drag-and-drop zone visuals and file accept logic. |

See also [API_CATALOG.md](API_CATALOG.md) for the full widget index.

## `Label` is internal

`Label` and `LabelConfig` are **not** part of the public surface
(text-unification wave C): `from sli_ui_toolkit.widgets import Label` raises
`ImportError`, and neither name appears in `sli_ui_toolkit.widgets.__all__` or
`sli_ui_toolkit.__all__`. The class survives only at
`src/sli_ui_toolkit/ui/widgets/atomic/text_labels.py` as an internal, documented
exception, for two reasons:

- `DropZoneLabel` subclasses `Label` (`atomic/drop_zone_label.py`);
- three capabilities `Text` does not cover yet — native text-interaction flags
  (`setTextInteractionFlags`), plain-mode rich text with clickable anchors, and
  inline pixmaps — each tracked as its own ticket.

New host code imports `Text` and uses `mode="plain"`.

## Text (plain mode)

`mode="plain"` is the `Label` replacement (contract:
`docs/dev/TEXT_UNIFICATION.md`): same keyword options, same variant registry,
same pixels for unselected text.

```python
from sli_ui_toolkit.widgets import Text, TextConfig

caption = Text("Secondary status", variant="caption", elide=True)
note = Text(config=TextConfig(text="Pinned", bold=True, selectable=True))
```

- `mode="document"` renders markdown through the painted engine:
  `Text(md, mode="document", resolve_asset=...)`, `set_markdown(md)`,
  `set_blocks(blocks)`, `anchor_y(anchor)` (content y, `None` if absent),
  `scroll_to_text(query)` (selects the first match, returns its content y or
  `None`), `selected_markdown(source)` — the *selected* fragment of the page
  markdown (`selected_plain_text()` when the blocks carry no source),
  `copy_selection()` / `copy_selection_markdown(source)` — copy to the
  clipboard **and drop the selection** (the standard copy rule; host menus call
  these instead of setting the clipboard themselves). `set_resolve_asset(fn)` replaces the
  image resolver and re-lays out. Text never scrolls: wrap it in a
  `QScrollArea`; a change in content height re-lays out the host.
- `mode="code"` is the painted code editor: `Text(src, mode="code",
  editable=True)`, `set_editing(bool)`, `is_editing()`,
  `set_line_number_start(n)`.
- Both engine modes share `selectedText()`, `hasSelectedText()`,
  `selectAll()`/`select_all_text()`, `clear_selection()` and
  `selected_plain_text()`. Forwarded signals: `textChanged` (code edits),
  `linkActivated(str)`, `imageActivated(str)`, `selectionChanged` (on value
  change, either mode).
- `textContextMenuRequested(QPoint)` (global position) fires on right-click in
  every mode; the built-in label menu still opens for plain `selectable=True`.
- `open_external_links` (default `True`, ctor kwarg / `TextConfig` field /
  `set_open_external_links`): `http(s)` links in engine modes also open via
  `QDesktopServices`; `linkActivated` is emitted either way.
- Engine typography: code mode honors `pixel_size`, `bold`, `italic`,
  `underline`, `strike_out`, `family` and the variant's `pixel_size`/`bold`;
  document mode honors `pixel_size` and `family` for body text. `color` /
  `color_token` set the code-mode base color (syntax colors stay).
- Plain mode hover: I-beam only over glyphs, Arrow over empty space (for
  `selectable=True`).
- `selectable=True` adds mouse drag, double-click word selection, `Ctrl+A`,
  `Ctrl+C`, arrow/Home/End keys with Shift, and the right-click Copy / Select
  all menu. `selectionChanged` fires on each change.
- Known gap vs the internal `Label`: `sizeHint()` of a wrapped text is the
  single-line width, not `QLabel`'s area-balanced hint. Layouts should rely on
  `heightForWidth()`, which matches `Label`.
- `register_text_variant` owns the registry; `register_label_variant` is the
  same function under the old name.
