"""Host gates: each rule fires on the bad shape and stays quiet on the good one.

The package is a plain-AST checker, so these tests need no widget: they build
source strings, run the rules, and assert on `Finding` records. The CLI tests
drive `main()` in-process against a small fixture tree; the last test proves the
package imports in an interpreter where PySide6 is unreachable.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from sli_ui_toolkit.gates import (
    BaselineError,
    Finding,
    RULES,
    baseline_violations,
    check_source,
    findings_to_counts,
    iter_python_files,
    load_baseline,
    main,
    write_baseline,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"


def findings_for(source: str, rule: str, path: str = "fixture.py") -> list[Finding]:
    return check_source(source, path, rules=[rule])


# ---------------------------------------------------------------- each rule


FIRES = {
    "toolkit-qss": """
from sli_ui_toolkit.widgets import Button
button = Button()
button.setStyleSheet("color: red;")
""",
    "raw-chrome-px": """
def build(widget):
    widget.setFixedWidth(240)
""",
    "double-scaled-px": """
from sli_ui_toolkit.ui.managers.ui_scale import scaled_px
size = scaled_px(scaled_px(8))
""",
    "qcolor-at-import": """
from PySide6.QtGui import QColor
ACCENT = QColor("#0078d4")
""",
    "empty-stylesheet": """
def build(widget):
    widget.setStyleSheet("")
""",
    "silent-swallow": """
try:
    widget.update()
except Exception:
    pass
""",
}

CLEAN = {
    "toolkit-qss": """
from PySide6.QtWidgets import QLabel
label = QLabel()
label.setStyleSheet("color: red;")
""",
    "raw-chrome-px": """
from sli_ui_toolkit.ui.managers.ui_scale import scaled_px
def build(widget):
    widget.setFixedWidth(scaled_px(240))
    widget.setFixedHeight(0)
    widget.setContentsMargins(0, 0, 0, 0)
""",
    "double-scaled-px": """
from sli_ui_toolkit.widgets import Button
from sli_ui_toolkit.ui.managers.ui_scale import scaled_px
button = Button(size=(36, 36))
width = scaled_px(36)
""",
    "qcolor-at-import": """
from PySide6.QtGui import QColor
def accent():
    return QColor("#0078d4")
""",
    "empty-stylesheet": """
def build(widget):
    widget.setStyleSheet("QWidget { background: transparent; }")
""",
    "silent-swallow": """
try:
    widget.update()
except Exception:
    pass  # the C++ object may already be gone; nothing to do
""",
}


@pytest.mark.parametrize("rule", sorted(FIRES))
def test_rule_fires_on_the_bad_shape(rule: str) -> None:
    findings = findings_for(FIRES[rule], rule)
    assert findings, f"{rule} did not fire"
    assert all(finding.rule == rule for finding in findings)
    assert all(finding.path == "fixture.py" for finding in findings)
    assert all(finding.line > 0 for finding in findings)


@pytest.mark.parametrize("rule", sorted(CLEAN))
def test_rule_stays_quiet_on_the_good_shape(rule: str) -> None:
    assert findings_for(CLEAN[rule], rule) == []


# ------------------------------------------------------ toolkit-qss resolution


def test_toolkit_qss_reports_unresolved_receivers() -> None:
    source = """
def paint(widget):
    widget.setStyleSheet("color: red;")
"""
    findings = findings_for(source, "toolkit-qss")
    assert len(findings) == 1
    assert "unresolved" in findings[0].message


def test_toolkit_qss_resolves_module_attribute_constructor() -> None:
    source = """
import sli_ui_toolkit.widgets as toolkit
toolkit.Button().setStyleSheet("color: red;")
"""
    assert len(findings_for(source, "toolkit-qss")) == 1


def test_toolkit_qss_resolves_a_toolkit_subclass_self() -> None:
    source = """
from sli_ui_toolkit.widgets import Button

class Mine(Button):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("color: red;")
"""
    findings = findings_for(source, "toolkit-qss")
    assert len(findings) == 1
    assert "unresolved" not in findings[0].message


def test_toolkit_qss_ignores_an_empty_stylesheet() -> None:
    """``empty-stylesheet`` owns that shape; one site, one finding."""
    source = """
from sli_ui_toolkit.widgets import Button
button = Button()
button.setStyleSheet("")
"""
    assert findings_for(source, "toolkit-qss") == []
    assert len(findings_for(source, "empty-stylesheet")) == 1


def test_toolkit_qss_allows_application_level_stylesheets() -> None:
    """App-level QSS is the documented path for stock/native widgets."""
    source = """
from PySide6.QtWidgets import QApplication

def apply(app: QApplication | None, qss: str) -> None:
    if app is not None:
        app.setStyleSheet(qss)
    QApplication.instance().setStyleSheet(qss)
"""
    assert findings_for(source, "toolkit-qss") == []


# ------------------------------------------------------------ rule internals


def test_raw_chrome_px_covers_every_gated_call() -> None:
    source = """
def build(w, layout):
    w.setFixedHeight(32)
    w.setMinimumSize(10, 10)
    w.setMaximumWidth(400)
    w.resize(640, 480)
    w.setContentsMargins(12, 8, 12, 8)
    layout.setSpacing(6)
"""
    findings = findings_for(source, "raw-chrome-px")
    assert len(findings) == 6


def test_raw_chrome_px_accepts_structural_sentinels() -> None:
    source = """
def build(w):
    w.setFixedWidth(0)
    w.setFixedHeight(1)
    w.setMaximumWidth(16777215)
"""
    assert findings_for(source, "raw-chrome-px") == []


def test_double_scaled_px_flags_design_size_argument() -> None:
    source = """
from sli_ui_toolkit.widgets import Button, ButtonConfig
from sli_ui_toolkit.ui.managers.ui_scale import scaled_px
button = Button(size=(scaled_px(36), scaled_px(36)))
config = ButtonConfig(size=(scaled_px(36), 36))
"""
    findings = findings_for(source, "double-scaled-px")
    assert len(findings) == 2
    assert "Button" in findings[0].message
    assert "ButtonConfig" in findings[1].message


def test_qcolor_at_import_flags_a_class_body() -> None:
    source = """
from PySide6.QtGui import QColor

class Palette:
    ACCENT = QColor("#0078d4")
"""
    assert len(findings_for(source, "qcolor-at-import")) == 1


def test_silent_swallow_accepts_a_logging_handler() -> None:
    source = """
try:
    widget.update()
except Exception:
    logger.debug("update skipped")
"""
    assert findings_for(source, "silent-swallow") == []


def test_rule_registry_is_the_documented_set() -> None:
    assert list(RULES) == [
        "toolkit-qss",
        "raw-chrome-px",
        "double-scaled-px",
        "qcolor-at-import",
        "empty-stylesheet",
        "silent-swallow",
    ]


def test_finding_format_is_path_line_rule_message() -> None:
    assert Finding("raw-chrome-px", "app/x.py", 7, "msg").format() == (
        "app/x.py:7: raw-chrome-px: msg"
    )


def test_counts_group_by_rule_then_path() -> None:
    findings = [
        Finding("raw-chrome-px", "a.py", 1, "x"),
        Finding("raw-chrome-px", "a.py", 2, "y"),
        Finding("toolkit-qss", "b.py", 3, "z"),
    ]
    assert findings_to_counts(findings) == {
        "raw-chrome-px": {"a.py": 2},
        "toolkit-qss": {"b.py": 1},
    }


# ------------------------------------------------------------------ baseline


def _write_bad_file(path: Path, count: int) -> None:
    calls = "\n".join(f"    w.setFixedWidth({10 + index})" for index in range(count))
    path.write_text(f"def build(w):\n{calls}\n", encoding="utf-8")


def test_baseline_accepts_a_shrinking_count(tmp_path: Path) -> None:
    source = tmp_path / "app.py"
    _write_bad_file(source, count=1)
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps(
            {"version": 1, "counts": {"raw-chrome-px": {str(source): 2}}}
        ),
        encoding="utf-8",
    )
    assert main([str(source), "--baseline", str(baseline)]) == 0


def test_baseline_rejects_a_growing_count(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "app.py"
    _write_bad_file(source, count=2)
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps(
            {"version": 1, "counts": {"raw-chrome-px": {str(source): 1}}}
        ),
        encoding="utf-8",
    )
    assert main([str(source), "--baseline", str(baseline)]) == 1
    assert "grown" in capsys.readouterr().err


def test_baseline_rejects_a_new_file_with_findings(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "app.py"
    _write_bad_file(source, count=1)
    baseline = tmp_path / "baseline.json"
    baseline.write_text(
        json.dumps(
            {"version": 1, "counts": {"raw-chrome-px": {str(tmp_path / "other.py"): 1}}}
        ),
        encoding="utf-8",
    )
    assert main([str(source), "--baseline", str(baseline)]) == 1
    assert "not in the baseline" in capsys.readouterr().err


def test_write_baseline_round_trips(tmp_path: Path) -> None:
    source = tmp_path / "app.py"
    _write_bad_file(source, count=2)
    baseline = tmp_path / "nested" / "baseline.json"
    assert main([str(source), "--write-baseline", str(baseline)]) == 0
    assert load_baseline(baseline) == {"raw-chrome-px": {str(source): 2}}
    assert main([str(source), "--baseline", str(baseline)]) == 0


def test_load_baseline_rejects_a_non_mapping(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    baseline.write_text("[]", encoding="utf-8")
    with pytest.raises(BaselineError):
        load_baseline(baseline)


def test_baseline_violation_message_is_per_file() -> None:
    counts = {"raw-chrome-px": {"a.py": 3}}
    assert baseline_violations(counts, {}) == [
        "raw-chrome-px: a.py has 3 finding(s) and is not in the baseline "
        "(new file with findings)"
    ]
    assert baseline_violations(counts, {"raw-chrome-px": {"a.py": 4}}) == []


# ---------------------------------------------------------------------- CLI


@pytest.fixture
def fixture_tree(tmp_path: Path) -> Path:
    tree = tmp_path / "app"
    (tree / ".venv" / "lib").mkdir(parents=True)
    (tree / "widgets").mkdir()
    (tree / "widgets" / "panel.py").write_text(
        "def build(w):\n    w.setFixedWidth(240)\n", encoding="utf-8"
    )
    (tree / "clean.py").write_text(
        "from sli_ui_toolkit.ui.managers.ui_scale import scaled_px\n"
        "def build(w):\n    w.setFixedWidth(scaled_px(240))\n",
        encoding="utf-8",
    )
    (tree / ".venv" / "lib" / "ignored.py").write_text(
        "def build(w):\n    w.setFixedWidth(240)\n", encoding="utf-8"
    )
    return tree


def test_cli_scans_a_tree_and_reports_json(
    fixture_tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main([str(fixture_tree), "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["findings"] == 1
    assert payload["findings"][0]["rule"] == "raw-chrome-px"
    assert payload["findings"][0]["path"].endswith("widgets/panel.py")
    assert payload["errors"] == []
    reported = {path for files in payload["counts"].values() for path in files}
    assert all(".venv" not in path for path in reported)


def test_cli_skips_vendored_directories(fixture_tree: Path) -> None:
    files = [path.name for path in iter_python_files([fixture_tree])]
    assert files == ["clean.py", "panel.py"]


def test_cli_rule_filter_runs_one_rule(
    fixture_tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main([str(fixture_tree), "--rule", "empty-stylesheet"]) == 0
    assert "no findings" in capsys.readouterr().out
    assert main([str(fixture_tree), "--rule", "raw-chrome-px"]) == 1


def test_cli_clean_tree_exits_zero(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "clean.py").write_text("value = 1\n", encoding="utf-8")
    assert main([str(tmp_path)]) == 0
    assert "no findings" in capsys.readouterr().out


def test_cli_reports_a_missing_path_as_an_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main([str(tmp_path / "missing")]) == 2
    assert "no such file or directory" in capsys.readouterr().err


# ------------------------------------------------------- no PySide6 required


def test_package_imports_without_pyside6(tmp_path: Path) -> None:
    script = tmp_path / "standalone.py"
    script.write_text(
        """
import importlib.util
import sys

class Blocker:
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "PySide6" or fullname.startswith("PySide6."):
            raise ImportError("PySide6 blocked by the gate self-check")
        return None

sys.meta_path.insert(0, Blocker())
root = sys.argv[1]
spec = importlib.util.spec_from_file_location(
    "_gates_standalone", root + "/__init__.py",
    submodule_search_locations=[root],
)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
assert sorted(module.RULES) == [
    "double-scaled-px", "empty-stylesheet", "qcolor-at-import",
    "raw-chrome-px", "silent-swallow", "toolkit-qss",
]
assert not [name for name in sys.modules if name.startswith("PySide6")]
findings = module.check_source("def build(w):\\n    w.setFixedWidth(240)\\n")
assert [finding.rule for finding in findings] == ["raw-chrome-px"]
print("ok")
""",
        encoding="utf-8",
    )
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(SRC)
    environment.pop("QT_QPA_PLATFORM", None)
    completed = subprocess.run(
        [sys.executable, str(script), str(SRC / "sli_ui_toolkit" / "gates")],
        capture_output=True,
        text=True,
        env=environment,
        cwd=REPO_ROOT,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "ok"


# --------------------------------------------------- qcolor palette exemption
_PALETTE_SOURCE = 'from PySide6.QtGui import QColor\n\nWINDOW = QColor("#101010")\n'


def test_qcolor_palette_module_is_exempt_by_default(tmp_path):
    (tmp_path / "palettes.py").write_text(_PALETTE_SOURCE)
    result = __import__("sli_ui_toolkit.gates", fromlist=["check_paths"]).check_paths([tmp_path])
    assert not [f for f in result.findings if f.rule == "qcolor-at-import"]


def test_qcolor_widget_module_still_reports(tmp_path):
    (tmp_path / "widgets.py").write_text(_PALETTE_SOURCE)
    result = __import__("sli_ui_toolkit.gates", fromlist=["check_paths"]).check_paths([tmp_path])
    assert [f for f in result.findings if f.rule == "qcolor-at-import"]


def test_qcolor_allow_glob_exempts_a_custom_palette_name(tmp_path):
    (tmp_path / "my_colors.py").write_text(_PALETTE_SOURCE)
    from sli_ui_toolkit.gates import check_paths

    assert [f for f in check_paths([tmp_path]).findings if f.rule == "qcolor-at-import"]
    allowed = check_paths([tmp_path], qcolor_allow=("my_colors.py",))
    assert not [f for f in allowed.findings if f.rule == "qcolor-at-import"]
