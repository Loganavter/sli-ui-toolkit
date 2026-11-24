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
