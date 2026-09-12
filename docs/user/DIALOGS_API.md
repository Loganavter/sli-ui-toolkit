# Dialogs & Navigation API

Sidebar-shell dialogs, in-dialog navigation lists, and markdown/native help
viewers.

| Widget | Description |
|--------|-------------|
| `SidebarDialogShell` | Sidebar + stacked pages dialog container. |
| `ScrollableDialogPage` | Ready-made scrollable page for dialog content. |
| `IconListWidget` / `IconListItem` | Icon-based navigation list for sidebar shells. Selected icons support `selected_icon_mode="invert"` (default color inversion) or `"replace"` with `selected_icon=` / `(normal_icon, selected_icon)` pairs. |
| `MarkdownHelpDialog` / `MarkdownHelpSection` | Markdown→HTML help dialog (`QTextBrowser`) with anchors, TOC, and `help://slug#anchor` navigation. Useful for tests and simple HTML help. |
| `HelpDocumentView` | Native widget-tree help page renderer (controlled markdown subset, figures, kbd, links). Prefer for illustrated manuals; see Improve-ImgSLI `docs/dev/HELP_SYSTEM.md`. |

`TopTabBar` / `TopTabHost` are also frequently used inside dialog content —
see [TABS_API.md](TABS_API.md).

Markdown help section discovery helpers are intentionally not exported from
`sli_ui_toolkit.widgets`. Import them only where needed from
`sli_ui_toolkit.ui.widgets.composite.help_sections`.

Block parsers for `HelpDocumentView` live under
`sli_ui_toolkit.ui.widgets.composite.help_document`
(`parse_help_blocks`, `FigureBlock`, …).

`SidebarDialogShell(*, sidebar_width=200, content_margins=(20, 20, 20, 20), content_spacing=10, sidebar_header=None, resizable_sidebar=False, parent=None)`
wraps an `IconListWidget` sidebar (exposed as `.sidebar`) plus a
`QStackedWidget` page area (`.pages_stack`). `sidebar_header` pins a widget
(e.g. a search field) above the nav list: the whole sidebar column tracks
the configured width and stays visible when the nav list is collapsed.
`resizable_sidebar=True` puts the sidebar and the content area into a
draggable `QSplitter` (`.splitter`), so the user can widen/narrow the nav
column (the configured `sidebar_width` becomes the minimum).
`ScrollableDialogPage(*, content_margins=(0, 0, 12, 0), content_spacing=15, parent=None)`
is a single scrollable content column, meant to be pushed into that stack.

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
    HelpDocumentView,
    IconListWidget,
    MarkdownHelpDialog,
    MarkdownHelpSection,
    ScrollableDialogPage,
    SidebarDialogShell,
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

doc_view = HelpDocumentView(
    resolve_asset=lambda name: f"assets/{name}",
    open_external_links=False,
    show_toc=True,
    toc_title="On this page",
)
```

`HelpDocumentView.scroll_to_text(query)` highlights the first
case-insensitive occurrence of `query` in the body (via the document's
accent selection wash) and returns a zero-height scroll-target widget for
a parent `QScrollArea` to call `ensureWidgetVisible` on — `None` when the
query is absent. `scroll_to_anchor(anchor)` returns the equivalent target
for a heading anchor instead.

`selected_icon_mode="invert"` (`IconListWidget`'s default) recolors the row
icon on selection; `"replace"` swaps in `selected_icon=` /
`(normal_icon, selected_icon)` pairs instead — the same knob referenced in
the table row above.

See also [API_CATALOG.md](API_CATALOG.md) for the full widget index.
