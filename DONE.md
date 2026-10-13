# DONE — text-r62: P2c motion resolved onto main tip

- Task: task-text-r62-resolve-2026-10-13
- Branch: `agent/text-r62/work`
- Base: `1122202b7b143c3877559dfa2b92f0f30651fc99` (main tip)
- Motion applied: `51c8b09333c8a50697e5861032b9d1a7cb3a9a79` via `git cherry-pick -n`
- Previous branch tip (superseded by `git checkout -B` to base, per brief): `c830278`

## Conflicts met

`git cherry-pick -n` produced **one** content conflict:

| File | Conflict |
|---|---|
| `src/sli_ui_toolkit/ui/widgets/composite/text_view/layout/hit_test.py` | main has the strict glyph hit-test (`naturalTextWidth` bound, empty-line skip); motion replaced the module with a delegate shim |

The brief expected conflicts in `composite/text_view/canvas.py`, `canvas_paint.py`, `layout/builder.py`, and possibly `text/text.py`. Git auto-merged all of those. I did not trust the auto-merge, so I checked every moved file against its main counterpart with path names normalized (`composite.text_view` → `text.engine`). Results:

| File | Non-path diff vs main | Verdict |
|---|---|---|
| `text/engine/canvas.py` | 4 lines: `TextCanvas` → `TextCanvasCore` | intended (core class) |
| `text/engine/document_canvas.py` | `HelpDocumentBodyCanvas` → `HelpDocumentBodyCore` | intended |
| `text/engine/canvas_paint.py`, `layout/builder.py`, `document.py`, `editing.py`, `events.py`, `highlight.py`, `markdown.py`, `painter.py`, `selection.py`, `structure.py`, `text_index.py`, `layout/*` (except hit_test) | 0 | P2b content present, no edits needed |
| `text/text.py` (host) | 22 lines: `TextCanvas` → `TextCanvasCore` hosting, plus import paths | intended; P2b hooks (`textContextMenuRequested`, `open_external_links`, `scroll_to_text`, `set_blocks`, `selectionChanged`) present on both sides |
| `composite/text_view/__init__.py` | 0 vs main | unchanged, as intended |
| `text/engine/layout/hit_test.py` | motion copy had the pre-P2b body | **resolved** (see log) |

## Per-file resolution log

1. **`text/engine/layout/hit_test.py`** (KEEP BOTH): motion moved the module into the engine. main's strict `hit_test_text_offset` was then written into the engine file with engine import paths. Content: `naturalTextWidth` bound, `textLength() <= 0` skip, and line-span check. `hit_test_link` and `hit_test_pixmap` are unchanged. Moved structure carries the strict behavior. Nothing was deleted.
2. **`composite/text_view/layout/hit_test.py`** (motion side): the conflicting HEAD block was dropped, leaving the motion's delegate shim. It re-exports `QPointF`, `fragment_layout_to_index`, `line_for_y`, `LayoutResult`, `hit_test_text_offset`, `hit_test_link`, and `hit_test_pixmap` from the engine module. Those are the same names as before.
3. **Scaffolding**: `DONE.md` and `MOVEPLAN.md` were removed from the index and the worktree before commit. `MOVEPLAN.md` was never tracked. `PROMPT.md` stays uncommitted.

## Verification (run against this tree with `PYTHONPATH=src`)

- Motion tests: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src QT_QPA_PLATFORM=offscreen python3 -m pytest tests/test_text_engine_motion.py -q -p no:cacheprovider` → **7 passed**.
- Full suite: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src QT_QPA_PLATFORM=offscreen python3 -m pytest tests/ -p no:cacheprovider -W ignore -rfE` → **1462 passed in 45.53s**, exit 0. The `-W ignore` only silences deprecation warnings; the first run without it did not capture a summary line, so I reran with it.
- mypy: `MYPYPATH=src python3 -m mypy src/sli_ui_toolkit` → **Success: no issues found in 322 source files** (0 errors, same as CI baseline).

## INTERFACE

The resolution itself adds **no new symbols**. Checked with `git diff --cached 1122202 -G "^def |^class "`:

- Every `def` appears as a `-`/`+` pair, so the functions were moved and not changed.
- The classes are moved (`-`/`+` pairs), plus two renames that come from the motion, not from this resolution: `TextCanvas` → `TextCanvasCore` (old `TextCanvas` is now a thin subclass), and `HelpDocumentBodyCanvas` → `HelpDocumentBodyCore` (old name is now a thin subclass).
- New test functions: the 7 in `tests/test_text_engine_motion.py`.

So the brief's `INTERFACE: none` is not literally accurate. The two new core class names and the new test file come from the motion commit. They are recorded in the CHANGELOG entry. Nothing new was added by the conflict resolution.

## Known gaps

- The brief's expected conflicts (`canvas.py`, `canvas_paint.py`, `builder.py`, `text.py`) did not conflict on this run. They were verified by normalized diff instead of by conflict hunks.
- `main`'s P2b content in the engine copies was checked by normalized diff only. There is no separate behavior test for the strict hit-test beyond the existing suite.
- Lightbox relocation, the TOC decision, and public selection-name questions are unchanged. They are the same open items recorded in the motion's CHANGELOG entry.
- The previous branch tip `c830278` was replaced by `git checkout -B` to the base, as the brief instructs. It is still in reflog and history.
