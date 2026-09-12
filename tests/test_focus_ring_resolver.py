"""Focus-ring resolver contract (4.2.4 unification).

(a) ``NavigationManager.resolve`` / ``is_keyboard_focus`` matrix: every
    ``Qt.FocusReason`` × last-input modality.  The input device is the
    source of truth, ``reason`` is only a documented hint.
(b) Anti-divergence guard: the ONLY surviving reason-formula is the
    unified degraded triple ``(Mouse, MenuBar, Popup)`` (plus the helper
    itself); every ``focusInEvent`` outside ``navigation_manager.py``
    must go through ``resolve_keyboard_focus`` / ``is_keyboard_focus``.
"""

from __future__ import annotations

import ast
from pathlib import Path

from PySide6.QtCore import Qt

from sli_ui_toolkit.ui.managers.navigation_manager import (
    NavigationManager,
    resolve_keyboard_focus,
)

ALL_REASONS = list(Qt.FocusReason)

# The single blessed degraded set: mouse-driven grants draw no ring.
DEGRADED_NON_KEYBOARD = frozenset(
    {
        Qt.FocusReason.MouseFocusReason,
        Qt.FocusReason.MenuBarFocusReason,
        Qt.FocusReason.PopupFocusReason,
    }
)


def test_resolve_matrix_reason_is_hint_only():
    """Static resolver needs no QApplication: result == last input."""
    for reason in ALL_REASONS:
        assert NavigationManager.resolve(reason, True) is True, reason
        assert NavigationManager.resolve(reason, False) is False, reason


def test_is_keyboard_focus_last_input_seam_without_gui():
    """Instance method honors the ``_last_input`` seam without live state."""
    mgr = NavigationManager.__new__(NavigationManager)
    mgr._last_input_keyboard = False  # live flag must not leak into the seam
    for reason in ALL_REASONS:
        assert mgr.is_keyboard_focus(reason, _last_input=True) is True, reason
        assert mgr.is_keyboard_focus(reason, _last_input=False) is False, reason


def test_module_helper_bypasses_manager_when_seam_given():
    for reason in ALL_REASONS:
        assert resolve_keyboard_focus(reason, _last_input=True) is True, reason
        assert resolve_keyboard_focus(reason, _last_input=False) is False, reason


def test_module_helper_degraded_fallback_without_manager(monkeypatch):
    def _boom():
        raise RuntimeError("no manager")

    monkeypatch.setattr(NavigationManager, "get_instance", staticmethod(_boom))
    for reason in ALL_REASONS:
        expected = reason not in (
            Qt.FocusReason.MouseFocusReason,
            Qt.FocusReason.MenuBarFocusReason,
            Qt.FocusReason.PopupFocusReason,
        )
        assert resolve_keyboard_focus(reason) is expected, reason


def _iter_src_modules():
    root = Path(__file__).resolve().parents[1] / "src" / "sli_ui_toolkit"
    assert root.is_dir(), root
    for path in sorted(root.rglob("*.py")):
        yield path


def _focus_reason_names(tree: ast.AST):
    """Yield (node, attr-name) for every ``Qt.FocusReason.X`` attribute."""
    found = []

    class _Visitor(ast.NodeVisitor):
        def visit_Attribute(self, node: ast.Attribute) -> None:  # noqa: N802
            value = node.value
            if (
                isinstance(value, ast.Attribute)
                and value.attr == "FocusReason"
                and isinstance(value.value, ast.Name)
                and value.value.id == "Qt"
            ):
                found.append((node, node.attr))
            self.generic_visit(node)

    _Visitor().visit(tree)
    return found


def test_no_divergent_reason_formulas():
    """Only the unified degraded triple may appear as a reason literal set.

    Forbids the old разнобой (``(Mouse, MenuBar)`` vs ``(Mouse, Popup)``,
    ``ActiveWindow`` special-cases, ``last_input_was_keyboard`` re-reads in
    widgets) forever: any NEW divergent tuple fails here.
    """
    violations: list[str] = []
    for path in _iter_src_modules():
        if path.name == "navigation_manager.py":
            continue  # the single interpretation site + blessed fallback
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Tuple, ast.List)):
                continue
            names = {
                elt.attr
                for elt in node.elts
                if isinstance(elt, ast.Attribute)
                and isinstance(elt.value, ast.Attribute)
                and elt.value.attr == "FocusReason"
                and isinstance(elt.value.value, ast.Name)
                and elt.value.value.id == "Qt"
            }
            if not names:
                continue  # no reason literals — not our concern
            if len(names) != len(node.elts):
                violations.append(f"{path}:{node.lineno}: mixed tuple {sorted(names)}")
            elif names != {
                "MouseFocusReason",
                "MenuBarFocusReason",
                "PopupFocusReason",
            }:
                violations.append(f"{path}:{node.lineno}: {sorted(names)}")
    assert not violations, "divergent reason-exception tuples:\n" + "\n".join(violations)


def test_no_active_window_special_case_outside_manager():
    violations: list[str] = []
    for path in _iter_src_modules():
        if path.name == "navigation_manager.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for _node, attr in _focus_reason_names(tree):
            if attr == "ActiveWindowFocusReason":
                violations.append(str(path))
                break
    assert not violations, "ActiveWindow special-case resurrected:\n" + "\n".join(violations)


def test_widget_last_input_reads_go_through_helper():
    """Widgets must not re-read ``last_input_was_keyboard`` directly."""
    allowed = {
        "navigation_manager.py",  # owner of the flag
        "nav_graph.py",  # reason generator (mouse/keyboard policy)
        "navigation_sections.py",  # reason generator (mouse/keyboard policy)
        "lifecycle.py",  # restore-reason generator (input → setFocus reason)
        "flyout_timer_service.py",  # backstop timer: no FocusReason exists,
        # only raw input modality (keep-open vs hover-governed)
        "test_focus_ring_resolver.py",
    }
    violations: list[str] = []
    for path in _iter_src_modules():
        if path.name in allowed:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "last_input_was_keyboard":
                violations.append(f"{path}:{node.lineno}")
    assert not violations, "direct last_input reads outside helper:\n" + "\n".join(violations)


def test_every_focus_in_event_uses_helper():
    """Every ``focusInEvent`` that interprets a reason uses the helper.

    Handlers without reason logic (``switch.py``, ``spinbox.py``,
    ``custom_line_edit.py`` — plain ``update()``/``selectAll()``) are out
    of scope; anything mentioning ``Qt.FocusReason`` must resolve via
    ``resolve_keyboard_focus`` / ``is_keyboard_focus``.
    """
    missing: list[str] = []
    for path in _iter_src_modules():
        if path.name == "navigation_manager.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "focusInEvent":
                reasons = {
                    n.attr
                    for n in ast.walk(node)
                    if isinstance(n, ast.Attribute)
                    and isinstance(n.value, ast.Attribute)
                    and n.value.attr == "FocusReason"
                    and isinstance(n.value.value, ast.Name)
                    and n.value.value.id == "Qt"
                }
                if not reasons:
                    continue
                used = {
                    n.attr
                    for n in ast.walk(node)
                    if isinstance(n, ast.Attribute)
                    and n.attr in {"resolve_keyboard_focus", "is_keyboard_focus"}
                } | {
                    n.id
                    for n in ast.walk(node)
                    if isinstance(n, ast.Name)
                    and n.id in {"resolve_keyboard_focus", "is_keyboard_focus"}
                }
                if not used:
                    missing.append(f"{path}:{node.lineno}")
    assert not missing, "focusInEvent not via helper:\n" + "\n".join(missing)
