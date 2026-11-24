# Host Gates

The toolkit's UI conventions — no QSS on its widgets, no raw design pixels in
chrome geometry, no double scaling, no import-time colours — are enforced on
this repository by contract tests under `tests/`. Those tests are rooted at
`src/sli_ui_toolkit` and cannot judge a host application, so every host ended up
re-deriving the same AST rules (BlinkTable's `tests/contracts/`, REAL-Video-
Enhancer's `harness/scripts/ui_gates.py`). `sli_ui_toolkit.gates` is one
runnable copy of those rules.

It is a plain-AST checker: it parses source text, never imports the scanned
module, and needs no PySide6, no `QApplication` and no display.

```bash
python -m sli_ui_toolkit.gates app/            # scan a tree
python -m sli_ui_toolkit.gates app/ --json    # machine-readable report
python -m sli_ui_toolkit.gates app/ --rule raw-chrome-px
python -m sli_ui_toolkit.gates app/ --baseline .gates-baseline.json
```

`PATH` may be any number of files and directories; with no path it scans the
current working directory. Hidden directories, `venv`, `.venv`, `build`,
`dist`, `node_modules`, `__pycache__` and the usual tool caches are skipped.

Exit codes: `0` clean (or within the baseline), `1` findings (including a
baseline that grew), `2` the scan could not run (unreadable or unparsable file,
broken baseline JSON).

## Rules

Every rule returns `Finding(rule, path, line, message)` records.

| Rule | Fires on | Fix |
|------|----------|-----|
| `toolkit-qss` | `setStyleSheet(...)` applied to a toolkit widget instance, or to a receiver the checker cannot resolve | Theme through `ThemeManager` tokens; the painter pipeline owns visual output |
| `raw-chrome-px` | A bare number in `setFixedWidth/Height/Size`, `setMinimum*`, `setMaximum*`, `resize`, `QSize(...)`, `setContentsMargins`, `setSpacing` | Wrap the design value in `scaled_px(...)`; `0`, `1` and `QWIDGETSIZE_MAX` are structural and allowed |
| `double-scaled-px` | `scaled_px(scaled_px(x))`, or `size=scaled_px(...)` passed to `Button` / `ButtonConfig`, whose `size` is already design px | Scale once: `Button(size=(36, 36))` |
| `qcolor-at-import` | `QColor(...)` evaluated in module or class scope | Read the token at paint time, or register it through a palette so a theme switch reaches it |
| `empty-stylesheet` | `setStyleSheet("")` | Remove the call; it is dead theming text |
| `silent-swallow` | `except ...: pass` with no comment in the handler and no logging call | Log the failure, or comment why it is expected |
| `token-ownership` | A literal palette key from another widget family (`"dialog.text"` in an input widget) | Read the file family's own token (or a neutral one), or declare the file's family with `# token-family: <name>` |
| `token-ownership-dynamic` | An f-string token key (`f"{prefix}.border"`) whose prefix variable is assigned a literal from another family | Point the prefix at the file's own family, or declare the file's family |
| `token-ownership-unresolved` | An f-string token key whose prefix variable has no literal assignment in the file | Bind `prefix = "<family>.<variant>"` (or `token_prefix=`) so the family is checkable, or declare what the runtime prefix means with `# token-prefix: <expression> -> <family>` |

The three `token-*` rules skip **tables** as well as palette modules — see
[Token ownership](#token-ownership).

### `qcolor-at-import` and the palette module

A palette module is *made* of module-scope `QColor` constants, so the rule
cannot tell it from the defect it looks for. `palette.py`, `palettes.py`,
`colors.py` and `colours.py` (basename match) are therefore exempt, and a host
whose palette has another name adds it with `--allow-qcolor GLOB` (repeatable).
Everything else is still reported — the exemption is for the module that owns
colours, not for a widget that happens to read one.

### Why an unresolved receiver is a finding

`toolkit-qss` resolves simple local bindings — `button = Button()`,
`self._button = Button()`, and toolkit subclasses reached through `self` in
`class Mine(Button)`. Anything else (a function parameter, `self.viewport()`, a
call result, a chain the checker cannot follow) is reported as `unresolved`
instead of passing silently. A gate that guesses "probably not a toolkit widget"
is a gate a host learns to ignore; binding the receiver to a local variable, or
removing the stylesheet, makes the intent checkable.

Known non-toolkit receivers — `QLabel()` imported from PySide6, for example —
are not reported by this rule. Neither is `QApplication.setStyleSheet(...)`
(directly on `QApplication.instance()` or through a parameter annotated
`QApplication`): app-level QSS is the toolkit's documented path for native/stock
Qt widgets and never targets a toolkit widget. Use the host's own "no stock
widgets / no manual theming" contract for everything else.

## Token ownership

A palette key belongs to one widget family. `button.default.background` is the
button family's; `dialog.text` is the dialog family's. When another family
paints its states with it — the input family reading `dialog.text`, the
checkbox reading `dialog.button.hover` — the two drift apart and neither family
can restyle its own widget, because the colour it paints with is owned
somewhere else. `token-ownership` makes that borrow visible.

Family comes from the file path (`TOKEN_FAMILIES` in
`sli_ui_toolkit.gates.rules`, one fragment → one family, first match wins):

| Path fragment | Family |
|---|---|
| `buttons/` | `button` |
| `comboboxes/` (the field) | `input` |
| `comboboxes/_overlay` | `list_item` |
| `atomic/custom_line_edit`, `atomic/spinbox`, `atomic/time_line_edit` | `input` |
| `atomic/slider` | `slider` |
| `atomic/switch` | `switch` |
| `atomic/checkbox`, `atomic/radio` | `checkbox` |
| `list_panel`, `sidebar_nav_list`, `text_list_widget` | `list_item` |
| `context_menu`, `menustrip` | `menu` |
| `base_flyout`, `simple_options_flyout` | `flyout` |
| `toast` | `toast` |
| `timeline_widget` | `timeline` |
| `calendar_widget` | `calendar` |
| `custom_title_bar`, `window_controls` | `titlebar` |
| `dialogs/` | `dialog` |
| `progress_bar` | `progress` |
| `text/`, `atomic/text_labels` | `label` |

**Neutral tokens** — shared chrome, not a family's private palette — every file
may read: `accent`, `link`, `separator.*`, `shadow.*`, `surface.*`, and Qt's own
palette roles (`Window`, `WindowText`, `Base`, `AlternateBase`, `Text`, `Button`,
`ButtonText`, `Highlight`, `HighlightedText`, `ToolTipBase`, `ToolTipText`,
`BrightText`). A palette key whose root no family claims (`help.*`,
`tooltip.*`) is not judged.

**Declaring a family.** A file the map does not know owns nothing, so a family
token in it is a finding: a new widget tree cannot escape the gate by living in
an unmapped directory, and a helper that genuinely serves one family says so in
the file itself:

```python
# token-family: button
```

The comment wins over the path map in both directions: it can claim a family for
an unmapped helper, and it can re-own a mapped file. The combobox package is
split in the map itself because it holds two different widgets: the field
(`_layers.py`, `combo_box.py`, `scrollable_combobox.py`) is an input, the
dropdown card (`_overlay.py`) is a list surface.

**Dynamic keys.** `f"{prefix}.background.hover"` is checked through the literal
the prefix is bound to:

```python
prefix = "button.primary"          # literal assignment: judged as a literal
tm.get_color(f"{prefix}.border")   # button family — allowed in a button file

def resolve(tm, variant):          # no literal prefix here: reported
    return tm.get_color(f"{variant.token_prefix}.border")
```

`prefix` / `token_prefix` (any name ending in `_prefix`) assigned a string
literal is the resolved case; a prefix received as a parameter or read off an
object is `token-ownership-unresolved`, naming the variable, rather than passing
silently. Only strings shaped like a key are considered — an f-string with
whitespace in its literal parts (`f"{name}.emit(...) is blocked"`) is prose.

**Declaring what a runtime prefix means.** A painter may legitimately read keys
through a prefix the variant table binds at runtime
(`f"{variant.token_prefix}.background.hover"`). The file states the mapping once,
in a real comment next to the code that uses it:

```python
# token-prefix: variant.token_prefix -> button
```

The left side is the expression as it appears inside the f-string (a local alias
such as `prefix = variant.token_prefix` is followed); the right side is the
family the keys belong to. With the declaration the prefix is judged like a
literal: no `token-ownership-unresolved`, and `token-ownership-dynamic` fires
only when the declared family is not the file's own (a `-> slider` declaration
in a button painter is still a borrow). Without the comment both rules stay on —
the declaration is what makes the dynamic key checkable.

**A table is not a painter.** Some files name other families' tokens *by
design*: the inspector panels (`ui/inspector/`) display a widget family's tokens
so a host can inspect them, and the variant registries
(`widgets/buttons/variants.py`, `widgets/text/variants.py`) map a variant name to
its token prefix. They carry no painting code — no key they name is one they
paint with — so the ownership question does not apply. `TABLE_PATHS` in
`sli_ui_toolkit.gates.rules` lists those path fragments, and the three
`token-*` rules skip them:

| Path fragment | Why it is exempt |
|---|---|
| `ui/inspector/` | Displays every family's tokens and resolves them for the inspector UI |
| `buttons/variants.py` | Maps a button variant to its token prefix |
| `text/variants.py` | Maps a text variant to its colour token |

The exemption is a path fragment, not a basename: a painter layer beside a table
(`ui/widgets/buttons/layers/background.py`) is still judged, and declares the
prefix it reads with `# token-prefix:`.

**The palette module is exempt.** `palette.py`, `palettes.py`, `colors.py` and
`colours.py` (basename match) are *made* of every family's keys, exactly as they
are for `qcolor-at-import`; the exemption is for the module that owns colours,
not for a widget that reads one.

**Baseline policy.** The toolkit's own borrows are accepted debt, recorded in
`tests/token_ownership_baseline.json` and enforced by
`tests/test_gates.py::test_token_ownership_baseline_is_not_exceeded` with the
same per-file ratchet a host installs. The baseline may only shrink: fix a site
and the file's count may be lowered (or the file dropped) when the baseline is
regenerated; a new borrow in an old file, or a new file with findings, fails.
A table path (`TABLE_PATHS`) appearing in the baseline means the exemption
drifted — tables are exempt, never accepted debt.
Regenerate with all three rules selected, so the file stays a complete picture:

```bash
python -m sli_ui_toolkit.gates src/sli_ui_toolkit \
  --rule token-ownership --rule token-ownership-dynamic \
  --rule token-ownership-unresolved \
  --write-baseline tests/token_ownership_baseline.json
```

## Installing a baseline

The baseline is a per-rule, per-file ratchet. Generate it once on an existing
tree, commit it, and the gate then fails only on new debt:

```bash
python -m sli_ui_toolkit.gates app/ --write-baseline .gates-baseline.json
git add .gates-baseline.json
```

The file is a count map:

```json
{
  "version": 1,
  "counts": {
    "raw-chrome-px": {
      "app/widgets/panel.py": 3
    }
  }
}
```

Semantics:

- a file whose count is **at or below** its recorded count passes — fixing a
  site lowers the count and the baseline can be regenerated later;
- a file whose count **grew** fails;
- a file with findings that is **not in the baseline** fails — a new file never
  starts in debt;
- a rule or file that shrank to zero, or disappeared entirely, passes.

`--json` reports the same verdict under `"baseline": {"path": …, "violations":
[…]}`; the `counts` object in that payload can be used to regenerate the file.

## Running the rules inside a host test suite

```python
from pathlib import Path

from sli_ui_toolkit.gates import check_source


def test_ui_gates():
    findings = []
    for path in Path("app").rglob("*.py"):
        findings.extend(
            check_source(path.read_text(encoding="utf-8"), path=str(path))
        )
    assert findings == [], "\n".join(finding.format() for finding in findings)
```

`check_source(source, path, rules=[...])` limits the pass to named rules.
`check_paths(paths, rules=None)` is the tree-level equivalent used by the CLI,
and `findings_to_counts` / `baseline_violations` expose the baseline arithmetic
without shelling out.

## Relationship to the repository's contract tests

`tests/test_px_scaling_contract.py` and friends stay where they are: they encode
toolkit-specific scopes (chrome prefixes, allowlist ratchets) and run on every
commit. The gates are the host-facing subset — same detectors, portable
entry point, no toolkit source assumptions.
