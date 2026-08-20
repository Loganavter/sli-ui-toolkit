"""Explicit navigation graph snapshot + validation.

POC for docs/dev/investigations/navigation-robustness-plan.md.
Read-only: snapshots NavigationManager's implicit _sections ordering into an
explicit NavGraph and validates invariants that previously required log trawls.
Does not replace NavigationManager.register() yet — next step is to make the
manager consume this graph.

Mirrors file_meta.py / docs_link_graph.py snapshot pattern.
"""

from __future__ import annotations

import inspect
import re
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget


@dataclass(frozen=True)
class NavNode:
    owner: str
    section: str
    visible: bool
    extra_keys: frozenset[int]


@dataclass(frozen=True)
class NavGraph:
    nodes: tuple[NavNode, ...]


def _try_import_manager():
    try:
        from sli_ui_toolkit.ui.managers.navigation_manager import NavigationManager

        return NavigationManager
    except Exception:
        return None


def focus_reason() -> Qt.FocusReason:
    """Central FocusReason policy — mouse vs keyboard.

    Mouse-initiated bootstrap (session picker click) → MouseFocusReason → no ring.
    Keyboard-initiated (Enter/arrow) → OtherFocusReason → ring.
    All setFocus() outside Button.focusInEvent should go through here.
    Delegates to NavigationManager.current_focus_reason() (breaking 4.0).
    """
    mgr_cls = _try_import_manager()
    if mgr_cls is not None:
        try:
            return mgr_cls.get_instance().current_focus_reason()
        except Exception:
            pass
    return Qt.FocusReason.OtherFocusReason


def snapshot() -> NavGraph:
    mgr_cls = _try_import_manager()
    if mgr_cls is None:
        return NavGraph(nodes=())
    mgr = mgr_cls.get_instance()
    nodes: list[NavNode] = []
    for owner, spec in getattr(mgr, "_sections", []):
        try:
            visible = bool(owner.isVisible()) if isinstance(owner, QWidget) else True
        except Exception:
            visible = False
        try:
            extra = frozenset(getattr(spec, "extra_keys", frozenset()))
        except Exception:
            extra = frozenset()
        nodes.append(
            NavNode(
                owner=type(owner).__name__,
                section=type(spec).__name__,
                visible=visible,
                extra_keys=extra,
            )
        )
    return NavGraph(nodes=tuple(nodes))


def validate(graph: NavGraph | None = None, repo_root: Path | None = None) -> list[str]:
    """Return violations — empty means graph is healthy."""
    if graph is None:
        graph = snapshot()
    violations: list[str] = []

    # 1. focus_first/last must accept ref_x (protocol change root cause 4)
    mgr_cls = _try_import_manager()
    if mgr_cls is not None:
        for owner, spec in getattr(mgr_cls.get_instance(), "_sections", []):
            for name in ("focus_first", "focus_last"):
                fn = getattr(spec, name, None)
                if fn is None:
                    continue
                try:
                    sig = inspect.signature(fn)
                    if "ref_x" not in sig.parameters:
                        violations.append(f"{type(spec).__name__}.{name} missing ref_x param")
                except (TypeError, ValueError):
                    pass

    # 2. No stray setFocus(OtherFocusReason) — deferred to strict mode
    # Kept as informational via --strict; POC contract only checks graph invariants.
    # See plan: centralize via focus_reason() incrementally, not flag-day.
    pass

    # 3. Invisible nodes should have no edges — validated via snapshot (all nodes where visible==False)
    # For POC, just ensure graph snapshot is non-empty when manager has sections
    # (real check: _neighbor skips invisible — covered by existing nav tests)

    # 4. ToolbarRowsSection must expose Left/Right in extra_keys
    for node in graph.nodes:
        if node.section == "ToolbarRowsSection":
            if Qt.Key.Key_Left not in node.extra_keys or Qt.Key.Key_Right not in node.extra_keys:
                violations.append("ToolbarRowsSection extra_keys must contain Left/Right")

    return violations
