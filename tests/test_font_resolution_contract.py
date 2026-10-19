"""Contract: a font copy handed to a widget must have its size asserted.

The bug class this closes (measured live, 2026-10-19): ``QFont`` copies carry
a size *value* but not necessarily a resolved size bit, and
``QWidget.setFont`` fills every unresolved attribute from the widget's
inherited font — the ancestor chain, which may still hold the face from before
the host applied its UI font. Improve-ImgSLI's workspace tab bar pinned
``Source Sans 3`` 12 pt, Qt applied 11 pt from the window chain, the first tab
was measured/painted 178x37 instead of 186x38, and it jumped a beat later when
the shown window re-resolved the chain. ``ConsoleView`` cached the same
half-resolved copy for its whole lifetime.

Resolution point: ``UiFont`` (``ui_font`` / ``paint_font`` / ``apply_ui_font``
/ ``rebase_*``) — all of which call ``pin_font_size``. A raw copy is allowed
only when the same code pins the size itself (``setPixelSize`` /
``setPointSizeF``) or when the file is a recorded exemption below.
"""

from __future__ import annotations

import ast
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent / "src" / "sli_ui_toolkit"

#: Files allowed to copy a widget/application font raw, with the reason.
EXEMPTIONS: dict[str, str] = {
    "ui/managers/ui_font.py": (
        "the resolver itself: builds base_font() from QApplication.font() and "
        "pins it via pin_font_size()"
    ),
}

#: Calls that count as pinning the size of the copied font.
_PIN_CALLS = ("pin_font_size(", "setPixelSize(", "setPointSizeF(", "setPointSize(")
#: Calls that resolve the face from the UI font source of truth.
_RESOLVER_CALLS = (
    "pin_font_size(",
    "ui_font(",
    "paint_font(",
    "apply_ui_font(",
    "rebase_font(",
    "rebase_family(",
)
#: How far ahead a pin may appear (copy first, then set the size).
_LOOKAHEAD = 3


def _scoped_bodies(tree: ast.AST):
    """Yield each block body (module / function / class / branch) in order."""
    for node in ast.walk(tree):
        for field in ("body", "orelse", "finalbody"):
            body = getattr(node, field, None)
            if isinstance(body, list) and all(isinstance(s, ast.stmt) for s in body):
                yield body
        for handler in getattr(node, "handlers", None) or ():
            if getattr(handler, "body", None):
                yield handler.body


def _source(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:  # pragma: no cover - unparse is stable on 3.9+
        return ""


_SIMPLE_STATEMENTS = (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.Expr, ast.Return)


def _scoped_statements(path: Path) -> list[list[ast.stmt]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [body for body in _scoped_bodies(tree)]


def _raw_font_copies(path: Path) -> list[int]:
    """Lines of ``QFont(<...>.font())`` copies whose size is never pinned."""
    offenders: list[int] = []
    for body in _scoped_statements(path):
        for index, statement in enumerate(body):
            if not isinstance(statement, _SIMPLE_STATEMENTS):
                continue
            source = _source(statement)
            if "QFont(" not in source or ".font()" not in source:
                continue
            window = "\n".join(
                _source(s) for s in body[index:index + _LOOKAHEAD]
            )
            if any(call in window for call in _PIN_CALLS):
                continue
            offenders.append(statement.lineno)
    return offenders


def _unresolved_widget_font_metrics(path: Path) -> list[int]:
    """Lines of ``QFontMetrics(self.font())`` in files with no resolver use."""
    text = path.read_text(encoding="utf-8")
    if any(call in text for call in _RESOLVER_CALLS):
        return []
    offenders: list[int] = []
    for body in _scoped_statements(path):
        for statement in body:
            if not isinstance(statement, _SIMPLE_STATEMENTS):
                continue
            source = _source(statement)
            if "QFontMetrics(self.font())" in source and "ui_font(" not in source:
                offenders.append(statement.lineno)
    return offenders


def _rel(left: Path, right: Path) -> str:
    return left.relative_to(PACKAGE_ROOT).as_posix()


def test_no_unpinned_font_copies_in_the_toolkit() -> None:
    offenders: list[str] = []
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        rel = _rel(path, PACKAGE_ROOT)
        if rel in EXEMPTIONS:
            continue
        for line in _raw_font_copies(path):
            offenders.append(f"{rel}:{line}")
    assert not offenders, (
        "raw font copy without pinning the size (Qt will merge the ancestor "
        f"chain's stale size): {offenders} — use pin_font_size()/ui_font()/"
        "paint_font()/apply_ui_font(), or set the size explicitly"
    )


def test_no_widget_font_metrics_outside_the_resolver() -> None:
    offenders: list[str] = []
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        for line in _unresolved_widget_font_metrics(path):
            offenders.append(f"{_rel(path, PACKAGE_ROOT)}:{line}")
    assert not offenders, (
        "text is measured from the widget's own font in a file that never "
        f"resolves the UI face: {offenders} — pin it (apply_ui_font(self)) or "
        "measure with ui_font()/paint_font()"
    )


def test_detector_flags_the_pre_fix_shapes(tmp_path: Path) -> None:
    """The detector itself must not be blind (house style: falsify it)."""
    raw = tmp_path / "raw.py"
    raw.write_text(
        "from PySide6.QtGui import QFont\n"
        "class W:\n"
        "    def __init__(self):\n"
        "        self._font = QFont(self.font())\n",
        encoding="utf-8",
    )
    assert _raw_font_copies(raw) == [4]

    pinned = tmp_path / "pinned.py"
    pinned.write_text(
        "from PySide6.QtGui import QFont\n"
        "from sli_ui_toolkit.ui.managers.ui_font import pin_font_size\n"
        "class W:\n"
        "    def __init__(self):\n"
        "        self._font = pin_font_size(QFont(self.font()))\n",
        encoding="utf-8",
    )
    assert _raw_font_copies(pinned) == []

    resized = tmp_path / "resized.py"
    resized.write_text(
        "from PySide6.QtGui import QFont\n"
        "class W:\n"
        "    def __init__(self):\n"
        "        font = QFont(self.font())\n"
        "        font.setPixelSize(13)\n"
        "        self.setFont(font)\n",
        encoding="utf-8",
    )
    assert _raw_font_copies(resized) == []
