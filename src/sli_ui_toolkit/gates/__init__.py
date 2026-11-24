"""Host-facing UI gates: the toolkit's own conventions, runnable on host code.

Both host applications independently re-derived the same AST contracts (no QSS
on toolkit widgets, no raw design px in chrome geometry, no double scaling, no
import-time ``QColor``, no dead ``setStyleSheet("")``, no silent ``except:
pass``). The library's contract tests are hard-wired to ``src/sli_ui_toolkit``
and cannot judge a host tree, so the rules live here as a plain-AST package with
no PySide6 import:

    python -m sli_ui_toolkit.gates <paths...> [--json] [--baseline PATH]
                                    [--rule NAME] [--write-baseline PATH]

The same rules are importable for a host's pytest run::

    from sli_ui_toolkit.gates import check_source

    def test_no_raw_px():
        findings = check_source(Path("app/widgets.py").read_text(),
                                path="app/widgets.py")
        assert findings == []

See ``docs/user/GATES.md`` for what each rule means and how to install a
baseline.
"""

from __future__ import annotations

from .cli import main
from .model import Finding
from .rules import (
    RULE_DOUBLE_SCALED_PX,
    RULE_EMPTY_STYLESHEET,
    RULE_QCOLOR_AT_IMPORT,
    RULE_RAW_CHROME_PX,
    RULE_SILENT_SWALLOW,
    RULE_TOOLKIT_QSS,
    RULES,
    Rule,
    check_double_scaled_px,
    check_empty_stylesheet,
    check_qcolor_at_import,
    check_raw_chrome_px,
    check_silent_swallow,
    check_toolkit_qss,
)
from .runner import (
    BASELINE_VERSION,
    BaselineError,
    ScanResult,
    baseline_violations,
    check_paths,
    check_source,
    findings_to_counts,
    iter_python_files,
    load_baseline,
    write_baseline,
)

__all__ = [
    "BASELINE_VERSION",
    "BaselineError",
    "Finding",
    "RULE_DOUBLE_SCALED_PX",
    "RULE_EMPTY_STYLESHEET",
    "RULE_QCOLOR_AT_IMPORT",
    "RULE_RAW_CHROME_PX",
    "RULE_SILENT_SWALLOW",
    "RULE_TOOLKIT_QSS",
    "RULES",
    "Rule",
    "ScanResult",
    "baseline_violations",
    "check_double_scaled_px",
    "check_empty_stylesheet",
    "check_paths",
    "check_qcolor_at_import",
    "check_raw_chrome_px",
    "check_silent_swallow",
    "check_source",
    "check_toolkit_qss",
    "findings_to_counts",
    "iter_python_files",
    "load_baseline",
    "main",
    "write_baseline",
]
