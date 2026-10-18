"""AST contract: raw per-source metrics signals stay off-limits outside the bus.

A module that connects ``UiFont.font_changed`` / ``UiScale.scale_changed``
directly (the two independent global signals every widget once had to
subscribe to separately — the asymmetry behind the recurring stale-geometry
bug class) must either go through the unified channel —
``connect_ui_metrics`` / ``MetricsContainer`` — or be recorded in
``EXEMPTIONS`` below with a reason. The list is the not-yet-migrated offender
inventory from ``plan-ui-metrics-systemic``; it ratchets down as each file
moves to the bus (never grow it without a recorded reason).
"""

from __future__ import annotations

import ast
from pathlib import Path

_PACKAGE_ROOT = Path(__file__).resolve().parent.parent / "src" / "sli_ui_toolkit"

#: Not-yet-migrated raw-signal subscribers (plan offender inventory, 2026-10-18
#: audit). Each entry must carry a reason; removing one means the file now
#: uses the bus. Ratchet: never grow this list without a recorded reason.
EXEMPTIONS: dict[str, str] = {
    # --- scale-only subscribers (plan inventory A; T2b migration pending) ---
    "ui/widgets/atomic/custom_group_widget.py": (
        "scale-only subscriber; T2b migration pending"
    ),
    "ui/widgets/atomic/custom_line_edit.py": (
        "scale-only subscriber; T2b migration pending"
    ),
    "ui/widgets/atomic/loading_spinner.py": (
        "scale-only subscriber; T2b migration pending"
    ),
    "ui/widgets/atomic/slider.py": "scale-only subscriber; T2b migration pending",
    "ui/widgets/atomic/spinbox.py": "scale-only subscriber; T2b migration pending",
    "ui/widgets/atomic/switch.py": "scale-only subscriber; T2b migration pending",
    "ui/widgets/comboboxes/combo_box.py": (
        "scale-only subscriber; T2b migration pending"
    ),
    "ui/widgets/composite/base_flyout/widget.py": (
        "scale-only subscriber; T2b migration pending"
    ),
    "ui/widgets/composite/console_view.py": (
        "scale-only subscriber; T2b migration pending"
    ),
    "ui/widgets/composite/dialog_shell.py": (
        "scale-only subscriber; T2b migration pending"
    ),
    "ui/widgets/composite/icon_action_flyout.py": (
        "scale-only subscriber; T2b migration pending"
    ),
    "ui/widgets/composite/indexed_toggle_flyout.py": (
        "scale-only subscriber; T2b migration pending"
    ),
    "ui/widgets/composite/list_panel/widget.py": (
        "scale-only subscriber; T2b migration pending"
    ),
    "ui/widgets/composite/process_console_widget.py": (
        "scale-only subscriber; T2b migration pending"
    ),
    "ui/widgets/composite/sidebar_nav_list/widget.py": (
        "scale-only subscriber; T2b migration pending"
    ),
    "ui/widgets/composite/simple_options_flyout/row.py": (
        "scale-only subscriber; T2b migration pending"
    ),
    "ui/widgets/composite/simple_options_flyout/widget.py": (
        "scale-only subscriber; T2b migration pending"
    ),
    "ui/widgets/composite/timeline_widget/interaction.py": (
        "scale-only subscriber; T2b migration pending"
    ),
    "ui/widgets/composite/timeline_widget/widget.py": (
        "scale-only subscriber; T2b migration pending"
    ),
    "ui/widgets/composite/toast/notification.py": (
        "scale-only subscriber; T2b migration pending"
    ),
    "ui/widgets/composite/top_tab_bar/bar.py": (
        "scale-only subscriber; T2b migration pending"
    ),
    "ui/widgets/text/engine/canvas.py": (
        "scale-only subscriber; T2b migration pending"
    ),
    "ui/widgets/text/engine/document_canvas.py": (
        "scale-only subscriber; T2b migration pending"
    ),
    "ui/windows/custom_title_bar/widget.py": (
        "scale-only subscriber; T2b migration pending"
    ),
    "ui/windows/window_chrome.py": (
        "scale-only subscriber; T2b migration pending"
    ),
    # --- internal plumbing (managers, not widget geometry consumers) ---
    "ui/managers/theme_manager.py": (
        "internal: re-scales host QSS px literals on a scale change; "
        "singleton lifetime, not a derived-geometry consumer"
    ),
    "ui/managers/ui_font.py": (
        "internal: apply() live-resync wiring connects both raw signals to "
        "one closure"
    ),
    # --- both raw signals, still direct (T2b migration pending) ---
    "ui/widgets/atomic/text_labels.py": (
        "connects font_changed + scale_changed directly; T2b migration pending"
    ),
    "ui/widgets/buttons/button.py": (
        "connects theme+font+scale with its own destroyed-hook teardown "
        "(documented stale-slot crash class); T2b migration pending"
    ),
    "ui/widgets/text/text.py": (
        "connects font_changed + scale_changed directly; T2b migration pending"
    ),
}

_RAW_SIGNAL_NAMES = frozenset({"font_changed", "scale_changed"})


def _raw_signal_connects(tree: ast.AST) -> list[int]:
    """Line numbers of ``…font_changed.connect(`` / ``…scale_changed.connect(``."""
    hits: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr != "connect":
            continue
        target = func.value
        if isinstance(target, ast.Attribute) and target.attr in _RAW_SIGNAL_NAMES:
            hits.append(node.lineno)
    return hits


def _references_name(tree: ast.AST, name: str) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == name:
            return True
        if isinstance(node, ast.Attribute) and node.attr == name:
            return True
    return False


def _subclasses(tree: ast.AST, class_name: str) -> bool:
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for base in node.bases:
            if isinstance(base, ast.Name) and base.id == class_name:
                return True
            if isinstance(base, ast.Attribute) and base.attr == class_name:
                return True
    return False


def _uses_bus(tree: ast.AST) -> bool:
    """True when the AST subscribes through the unified channel."""
    return _references_name(tree, "connect_ui_metrics") or _subclasses(
        tree, "MetricsContainer"
    )


def _module_findings(rel: str, tree: ast.Module) -> list[str]:
    findings: list[str] = []
    # Per class: a class that connects a raw signal must itself be on the
    # bus (a module-level bus reference must not excuse an off-bus class).
    for cls in (n for n in tree.body if isinstance(n, ast.ClassDef)):
        if _raw_signal_connects(cls) and not (
            _uses_bus(cls) or _subclasses(cls, "MetricsContainer")
        ):
            findings.append(
                f"{rel}: class {cls.name} connects a raw metrics signal "
                "off the bus (use connect_ui_metrics / MetricsContainer "
                "or record an exemption)"
            )
    # Module-level connects (outside every top-level class).
    class_spans = [
        (n.lineno, n.end_lineno or n.lineno)
        for n in tree.body
        if isinstance(n, ast.ClassDef)
    ]
    module_connects = [
        lineno
        for lineno in _raw_signal_connects(tree)
        if not any(lo <= lineno <= hi for lo, hi in class_spans)
    ]
    if module_connects and not _uses_bus(tree):
        findings.append(
            f"{rel}: module-level raw metrics signal connect "
            f"(line {module_connects[0]}) off the bus"
        )
    return findings


def _findings() -> list[str]:
    findings: list[str] = []
    for path in sorted(_PACKAGE_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        rel = path.relative_to(_PACKAGE_ROOT).as_posix()
        if rel in EXEMPTIONS:
            continue  # recorded exemption — see the ratchet list above
        findings.extend(_module_findings(rel, tree))
    return findings


def test_no_raw_metrics_signal_connections_off_the_bus() -> None:
    """0 findings: every raw per-source connect is on the bus or exempt."""
    findings = _findings()
    assert findings == [], "raw per-source metrics signals must go through the bus:\n" + "\n".join(
        findings
    )


def test_exemption_list_is_recorded_and_current() -> None:
    """The ratchet list: every entry exists, carries a reason, and the
    plan's offender inventory is actually recorded.
    """
    assert len(EXEMPTIONS) == 30, (
        f"expected the 30 not-yet-migrated offenders recorded, got "
        f"{len(EXEMPTIONS)} — migrate files to the bus (and drop their "
        "entry) instead of letting the list drift"
    )
    for rel, reason in EXEMPTIONS.items():
        assert (_PACKAGE_ROOT / rel).is_file(), f"exempt file missing: {rel}"
        assert reason.strip(), f"exemption without a recorded reason: {rel}"
    for rel in (
        "ui/widgets/atomic/switch.py",
        "ui/widgets/composite/timeline_widget/widget.py",
        "ui/widgets/buttons/button.py",
        "ui/managers/theme_manager.py",
        "ui/managers/ui_font.py",
    ):
        assert rel in EXEMPTIONS, f"plan offender not recorded in the exemption list: {rel}"


def test_detector_flags_a_raw_connect_outside_the_bus() -> None:
    tree = ast.parse(
        "UiScale.get_instance().scale_changed.connect(widget._on_scale_changed)"
    )
    assert _raw_signal_connects(tree) == [1]
    assert _uses_bus(tree) is False


def test_detector_accepts_bus_usage() -> None:
    tree = ast.parse(
        "from sli_ui_toolkit.ui.managers.ui_metrics import connect_ui_metrics\n"
        "connect_ui_metrics(self, self._on_metrics_changed)\n"
    )
    assert _uses_bus(tree) is True
    tree = ast.parse("class Foo(MetricsContainer):\n    pass\n")
    assert _uses_bus(tree) is True


def test_detector_ignores_unrelated_signals() -> None:
    tree = ast.parse("self.theme_manager.theme_changed.connect(self.update)\n")
    assert _raw_signal_connects(tree) == []
