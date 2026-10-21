# TextView API — **removed** (text-unification wave C)

`TextView` no longer exists. Nothing in this file is importable: the class and the whole
`ui/widgets/composite/text_view/` package were deleted once every caller moved to `Text`.

## What replaced it

`TextView` fused two things. Both halves exist, separately:

| Old | Now |
|---|---|
| the painted buffer (`TextCanvas`) | `Text(..., mode="code")` (editable) / `mode="document"` — [LABELS_API.md](LABELS_API.md) |
| the scroll host (QScrollArea + toolkit scrollbar + rounded border overlay + optional raised well) | `TextScrollArea(source, mode="code")` from `sli_ui_toolkit.ui.widgets.composite` — it composes one `Text` and forwards `text`/`plain_text`/`set_text`/`set_markdown`/`anchor_y`/`scroll_to_anchor`/`is_editing`/`set_editing`/`enter_edit_mode`/`exit_edit_mode`/`editor`/`canvas`/`set_line_number_start`, re-emitting `changed`/`linkActivated`/`imageActivated` |

`Text.canvas()` returns the hosted engine surface (the same object `TextView.canvas()` returned) for
chrome a host owns around a code buffer: the line-number map, collapsed fold rows, y→line hit-testing
and event filters. Typography, selection and edit state stay on `Text`.

## Migration

```python
# before
view = TextView(code, line_number_start=1)
view.enter_edit_mode()

# after
view = TextScrollArea(code, mode="code", editable=True)
view.set_editing(True)          # enter_edit_mode()/exit_edit_mode() are kept as host spellings
```

- `TextView.set_document(md)` → `Text(md, mode="document")` — **the mode is fixed at construction**
  (there is no in-place document↔code switch any more).
- `TextView.is_document()` → `mode() == "document"` (the host keeps `is_document()` as a forwarder).
- `scroll_to_anchor()` returns **`int | None`** (the y a host scrolls to), not a marker widget.
- Help pages: `HelpDocumentView(md)` → `Text(md, mode="document")` + host-owned TOC list / image
  lightbox / search box (`Text` emits `linkActivated` and `imageActivated`).

## Where the docs live now

- [LABELS_API.md](LABELS_API.md) — `Text`, its modes, typography, selection, edit state.
- [API_CATALOG.md](API_CATALOG.md) — the full public surface, including `TextScrollArea`.
- [../dev/TEXT_UNIFICATION.md](../dev/TEXT_UNIFICATION.md) — the plan and the decided divergences.
- `CHANGELOG.md` (`### Removed`) — the exact deletion record and the per-test ledger.

This stub exists so links from older notes and host documentation land on the migration instead of a
404. Do not re-add a compatibility package: `tests/test_text_engine_motion.py` has an import gate that
fails if `composite/text_view` or `composite/help_document` ever comes back.
