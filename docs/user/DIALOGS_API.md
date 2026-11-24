# Dialogs & Navigation API

Sidebar-shell dialogs, in-dialog navigation lists, and markdown/native help
viewers.

| Widget | Description |
|--------|-------------|
| `SidebarDialogShell` | Sidebar + stacked pages dialog container. |
| `ScrollableDialogPage` | Ready-made scrollable page for dialog content. |
| `IconListWidget` / `IconListItem` | Icon-based navigation list for sidebar shells. Selected icons support `selected_icon_mode="invert"` (default color inversion) or `"replace"` with `selected_icon=` / `(normal_icon, selected_icon)` pairs. |
| `MarkdownHelpDialog` / `MarkdownHelpSection` | Painted markdown help dialog: markdown is parsed by the toolkit text view (document mode) and rendered through the painter pipeline — no `QTextBrowser`/HTML. Anchors, TOC, `help://slug#anchor` navigation, and an optional `resolve_asset` for inline images. |
| `Text` (`mode="document"`) + host chrome | A help page: the painted document body. The TOC list, the image lightbox and the search box compose in the HOST (`Text` emits `linkActivated`/`imageActivated`); see [LABELS_API.md](LABELS_API.md) and [API_CATALOG.md](API_CATALOG.md). `HelpDocumentView` was deleted in text-unification wave C. |
| `MessageDialog` / `MessageResult` | Painted message/confirm dialog — the `QMessageBox` replacement. Selectable body, optional "don't show again" box, `information`/`warning`/`critical`/`question` conveniences. |
| `TextInputDialog` | Single-line prompt on `CustomLineEdit` — the `QInputDialog.getText` replacement: `(text, ok)`, validator gate, Enter/Escape. |
| `DialogActionBar` | One primary (+optional secondary) button row with `accepted`/`rejected`; shared by both dialogs, usable standalone. |

`TopTabBar` / `TopTabHost` are also frequently used inside dialog content —
see [TABS_API.md](TABS_API.md).

Markdown help section discovery helpers are intentionally not exported from
`sli_ui_toolkit.widgets`. Import them only where needed from
`sli_ui_toolkit.ui.widgets.composite.help_sections`.

Block parsers for a help body live under
`sli_ui_toolkit.ui.widgets.text.engine.markdown`
(`parse_help_blocks`, `collect_heading_anchors`, `FigureBlock`, …) — they are the engine's,
shared by `Text(mode="document")` and `MarkdownHelpDialog`.

`SidebarDialogShell(*, sidebar_width=200, content_margins=(20, 20, 20, 20), content_spacing=10, sidebar_header=None, resizable_sidebar=False, parent=None)`
wraps an `IconListWidget` sidebar (exposed as `.sidebar`) plus a
`QStackedWidget` page area (`.pages_stack`). `sidebar_header` pins a widget
(e.g. a search field) above the nav list: the whole sidebar column tracks
the configured width and stays visible when the nav list is collapsed.
`resizable_sidebar=True` puts the sidebar and the content area into a
draggable `Splitter` (`.splitter`), so the user can widen/narrow the nav
column (the configured `sidebar_width` becomes the minimum). `Splitter` is
the public class, exported from `sli_ui_toolkit.widgets` for any host that
needs this divider: the same handle paints one **device** pixel wide at every
`devicePixelRatio` (`dialog.border` over `surface.background`), centred, so it
stays crisp and never merges with the content column's own border at a
fractional ratio (125 % / 150 %). It works in both orientations, scales its
handle width through `UiScale`, and a double-click on the handle resets the
panes to equal sizes — everything else (`setSizes`, `setChildrenCollapsible`,
`splitterMoved`) is inherited `QSplitter`.
`ScrollableDialogPage(*, content_margins=(0, 0, 12, 0), content_spacing=15, parent=None)`
is a single scrollable content column, meant to be pushed into that stack.
`content_margins`/`content_spacing` are **design px**: the shell and the page
re-resolve them through `UiScale` on every factor change (as they do their
sidebar width and divider width), so nothing is stamped at construction.
Its `minimumSizeHint()` includes the content widget's minimum width (plus
the vertical scrollbar) — a `QScrollArea` reports a fixed ~68×68 otherwise,
which would let a splitter squeeze the column under its own content. Height
stays scrollable: only the width is a hard requirement.

`IconListWidget` supports in-place search filtering — the rows stay built,
only visibility changes per keystroke (ComboBox-style visible-index pool):

```python
nav.set_no_results_text("No matching items")   # shown when a search hits nothing
nav.set_items([IconListItem(text="Settings", search_texts=("настройки", "настройка"))])
nav.set_search_text("настройки")                # filters in place; "" restores all
```

`search_texts` are pre-normalized alternate match texts (e.g. translations
in every UI language) — matching uses the same `match_score` scoring as the
toolkit ComboBox: NFKD-normalized, **non-fuzzy by default** (exact, word
prefix, or substring hits). Fuzzy subsequence matching is opt-in
(`fuzzy=True`) and should only be enabled when the UI explicitly advertises
it — a scatter hit cannot be located on a page, so it silently matches
almost any short query against long text.
`count()`/`item()`/`row_button()`/`setCurrentRow()`
all operate on *visible* rows while a filter is active; `clear()` keeps the
no-results row across rebuilds (it is hidden until a search needs it).

```python
from PySide6.QtCore import QSize

from sli_ui_toolkit.widgets import (
    IconListWidget,
    MarkdownHelpDialog,
    MarkdownHelpSection,
    ScrollableDialogPage,
    SidebarDialogShell,
    Text,
)

shell = SidebarDialogShell(sidebar_width=220, content_margins=(16, 16, 16, 16), content_spacing=12)
page = ScrollableDialogPage(content_margins=(0, 0, 12, 0), content_spacing=15)

nav = IconListWidget(icon_size=QSize(20, 20), row_height=40, selected_icon_mode="replace")
nav.add_item("General", icon=AppIcon.SETTINGS, selected_icon=AppIcon.SETTINGS_FILLED)
# button_factory=Callable[[IconListItem], Button] replaces the default toggle-Button
# row entirely (badges, custom variant, regions=...) — IconListWidget still owns
# layout/selection but leaves that row's icon/foreground styling to the app.

help_dialog = MarkdownHelpDialog(
    title="Help",
    toc_title="On this page",
    sections=[MarkdownHelpSection(order=0, slug="intro", title="Intro", body_md="# Intro\n...")],
)

# A help page body: painted document, host owns scrolling/TOC/lightbox.
page_body = Text(
    "# Intro\n\n...",
    mode="document",
    resolve_asset=lambda name: f"assets/{name}",
    open_external_links=False,
)
page_body.linkActivated.connect(...)     # help://slug#anchor, http(s)
page_body.imageActivated.connect(...)    # open your own lightbox
```

`Text.scroll_to_text(query)` highlights the first case-insensitive occurrence of
`query` in the body (accent selection wash) and returns the widget-space **y** a host
scroll area should scroll to — `None` when the query is absent. `scroll_to_anchor(anchor)`
returns the same kind of y for a heading anchor (`anchor_y` exposes it without scrolling).
`HelpDocumentView` used to return a target *widget* for `ensureWidgetVisible`; the int
contract is deliberate (the widget never scrolls itself).

`selected_icon_mode="invert"` (`IconListWidget`'s default) recolors the row
icon on selection; `"replace"` swaps in `selected_icon=` /
`(normal_icon, selected_icon)` pairs instead — the same knob referenced in
the table row above.

### Message, confirm and text-input dialogs

`MessageDialog` and `TextInputDialog` are `BaseDialog` subclasses, so they
inherit the painted `dialog.background` surface, size grip and normal window
flags. Apply the host's frameless/CSD decorator outside the dialog, like for
any other `BaseDialog` — the toolkit does not decide chrome. Both are
standalone painted widgets: no QSS, no `QMessageBox`/`QInputDialog`/
`QLineEdit`.

```python
from sli_ui_toolkit.widgets import MessageDialog, TextInputDialog

# Confirm / acknowledge; returns (ok, checked)
result = MessageDialog.show_message(
    window,
    "Delete preset",
    "The preset and its thumbnails will be removed.",
    kind="warning",
    checkbox_text="Don't ask again",
    ok_text="Delete",
    cancel_text="Cancel",
    default="cancel",
    destructive=True,
)
if result.ok:
    ...
if result.checked:
    settings.ask_before_delete = False

# One-button acknowledgement (no cancel_text)
MessageDialog.information(window, "Saved", "The export finished.")

# Question -> bool
if MessageDialog.question(window, "Overwrite?", "The file already exists."):
    ...

# Text prompt -> (text, ok), QInputDialog.getText's shape
text, ok = TextInputDialog.get_text(
    window,
    "Rename",
    "New name:",
    current_name,
    placeholder="Untitled",
    validator=None,          # any QValidator: invalid input keeps the dialog open
)
```

- Body text is `Text(mode="plain", selectable=True, word_wrap=True)`.
- Escape rejects; Enter activates the `default` button (`"ok"`/`"cancel"`).
  The text field accepts Enter itself and forwards it through the same
  validator gate.
- `cancel_text=None` in `show_message` builds a one-button acknowledgement;
  `question(...)` supplies `"Cancel"` unless the host passes a label.
- `destructive=True` seeds the primary button with the palette's error colour
  (`progress.error`); the palette has no dedicated button-danger token.
- `DialogActionBar(parent=None, *, primary_text, secondary_text=None,
  primary_min_size=(100, 36), secondary_min_size=(100, 36),
  destructive=False)` exposes `.primary`/`.secondary` and the
  `accepted`/`rejected` signals — use it directly for a host-built dialog
  that wants the same row.

See also [API_CATALOG.md](API_CATALOG.md) for the full widget index.
