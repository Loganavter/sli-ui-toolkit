"""Guard: hot toolkit UI paths must not call QApplication.font() / bare QFont()."""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1] / "src" / "sli_ui_toolkit"

_PATHS = [
    _ROOT / "ui" / "widgets" / "buttons",
    _ROOT / "ui" / "widgets" / "comboboxes",
    _ROOT / "ui" / "widgets" / "composite" / "unified_flyout",
    _ROOT / "ui" / "widgets" / "composite" / "simple_options_flyout.py",
    _ROOT / "ui" / "widgets" / "composite" / "context_menu",
    _ROOT / "ui" / "widgets" / "list_items",
    _ROOT / "ui" / "widgets" / "atomic" / "text_labels.py",
    _ROOT / "ui" / "widgets" / "atomic" / "custom_group_widget.py",
    _ROOT / "ui" / "widgets" / "overlays" / "drag_drop_overlay.py",
    _ROOT / "ui" / "windows",
]

_FORBIDDEN_CALLS = (
    "QApplication.font(",
    "= QFont()",
    "QFont()",
)


def _collect_py_files() -> list[Path]:
    files: list[Path] = []
    for path in _PATHS:
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files.extend(path.rglob("*.py"))
    return files


def test_no_raw_application_font_bypass_in_hot_ui_paths():
    real: list[str] = []
    for path in _collect_py_files():
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if "QApplication.font(" in stripped:
                real.append(f"{path.relative_to(_ROOT)}:{i}: {stripped}")
                continue
            if "= QFont()" in stripped or "QFont()" in stripped and (
                "setFont(QFont())" in stripped
                or stripped.startswith("font = QFont()")
                or "QFont()" == stripped.rstrip(")")
            ):
                real.append(f"{path.relative_to(_ROOT)}:{i}: {stripped}")

    assert not real, "UiFont bypasses still present:\n" + "\n".join(real)
