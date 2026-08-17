# TextView API

Painted text rendering + editing composite (no stock Qt text widgets): the
same painted surface is the read view and the editor, so both modes look
identical by construction. Monospace code mode with Python syntax spans;
rounded frame overlay and a toolkit scrollbar; the section page itself never
scrolls.

## Quick Start

```python
from sli_ui_toolkit.widgets import TextView

view = TextView("class Foo:\n    pass\n")
view.enter_edit_mode()          # the canvas IS the editor
view.editor().insert_text("x")
print(view.text())
view.exit_edit_mode()
```

The inspector's Code section uses this widget: `TextView(source)` →
`Edit`/`Revert`/`Save` via `is_editing()` / `enter_edit_mode()` /
`exit_edit_mode()` / `text()` / the `changed` signal. The section shows
ONE unified view: the generated **Configuration (live values)** snippet (a
synthetic constructor call built from `WidgetInspection.config`), the
widget class source, and the rest of the source file collapsed into
clickable gap rows (see the inspector docs); the **Full/Compact** toggle
sits at the top of the section and expands/collapses all gaps at once.
`set_panel_fill()` gives the surface the app's recent-projects shelf well
look.

## Line-number gutter

`set_line_number_start(n)` paints a VS Code-style left gutter with
right-aligned line numbers starting at `n` and a thin separator. Pass the
class's line in its source file to make the gutter match the actual file;
`set_line_number_start(None)` (the default) disables the gutter. Code mode
only — document mode never shows it.

For views with collapsed content (the inspector Code section), the per-line
gutter text can be overridden:

```python
view.set_line_number_map({0: "1", 1: "1-151", 2: "152"})  # display line -> label
view.canvas().line_at(y)   # display line for a widget-space y (click targets)
```

Lines missing from the map fall back to `start + index`; `None` clears the
override. `canvas()` returns the painted surface (event filters, hit-test
math).

## Panel well

`set_panel_fill(color)` paints a rounded "well" behind the text (the
viewport fill clipped to the frame radius — the recent-projects shelf
look); `set_panel_fill(None)` restores the page background. The mask
re-applies on resize.

## Constructor Parameters

```python
TextView(text: str = "")
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `text` | `str` | `""` | Initial line-based content |

## Document mode (markdown)

```python
view.set_markdown(md_text, resolve_asset=my_resolver)
print(view.plain_text())
view.set_text("back to code\n")
```

`set_markdown(markdown, *, resolve_asset=None)` switches to a read-only
document mode: the controlled markdown subset (headings `#`…`######` with
a strictly decreasing font scale, bold, italic, inline code, links, lists,
standalone images, `:::figure` fences, ` ```lang` fenced code blocks, and
GFM-style pipe tables with an optional bold header row — see the
`markdown.py` module docstring for the exact table syntax)
is laid out with the help-document engine (`QTextLayout` wrapping, bordered
tables, images) and painted by the same surface. Fenced code renders
monospaced
inside a shaded rounded box (`help.code.background` token) with the fence
language label in the box header. `resolve_asset(path)` maps image
paths to `QPixmap`/paths. `is_document()` reports the mode;
`set_text()` returns to code mode; `plain_text()` is the full plain text
of either mode.

Document mode interaction: click-drag selects text (offset-based, painted
with the same selection highlight), double-click selects the word and
triple-click the whole paragraph/segment (same multi-click chain as code
mode — both share one selection state machine; inside a fenced code block
triple-click selects the current line, not the whole fence), Ctrl+A
selects all, Ctrl+C copies the selection to the clipboard; clicking a link
emits `linkActivated(href)`; clicking an image emits
`imageActivated(path)` **and** opens the full-resolution image in the help
lightbox (zoom/pan via wheel, `+`/`-`, middle-drag; Esc/click dismisses).

## Signals

```python
changed = Signal()           # emitted after every successful edit
linkActivated = Signal(str)  # document mode: link clicked (href)
imageActivated = Signal(str) # document mode: image clicked (source path)
```

## Methods

| Method | Description |
|---|---|
| `text() -> str` | Current content |
| `set_text(text)` | Replace content; resets cursor and selection |
| `is_editing() -> bool` | True while in edit mode |
| `enter_edit_mode() -> TextCanvas` | Switch to editing (nothing is swapped — same painted canvas) |
| `exit_edit_mode()` | Back to read mode; clears selection |
| `editor() -> TextCanvas | None` | The editing surface while editing, else None |
| `changed` | See Signals |

`TextCanvas` (also exported) is the painted surface: `insert_text()`,
keyboard editing (arrows, Home/End, Backspace/Delete, Return, Tab → 4
spaces, Ctrl+C/V/X/Z), mouse cursor placement and drag selection, undo
stack (100 snapshots).

## Python highlighting

`python_line_spans(line)` tokenizes one line into
`(start, end, kind)` spans — kinds: `comment`, `string`, `decorator`,
`keyword`, `builtin`, `number`, `defclass`. Triple-quoted strings are
handled line-by-line. `python_span_colors(theme_manager)` returns the
theme-aware palette (keywords use the `accent` token).

## Notes

- The rounded frame is a painted overlay; `separator.color` token, no QSS.
- The scrollbar is the toolkit `MinimalistScrollBar`, inside the frame.
- The Tab key is intercepted before Qt focus traversal so it indents.
- The view fills whatever space its layout gives it: the canvas is resized
  to the viewport (`widgetResizable`) and its content height is a minimum
  — a short document leaves the canvas stretched to the view, a long one
  scrolls internally. There is no fixed content-derived size.
- Document mode (markdown blocks, images) is planned — see the
  implementation plan (kept private in the `improve-imgsli-internal-docs`
  repo, `sli-ui-toolkit/docs/dev/TEXT_VIEW_PLAN.md`).
