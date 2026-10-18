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

#: Raw-signal subscribers that genuinely cannot use the bus (T2b swept the
#: 25 migratable offenders from the plan's 2026-10-18 inventory to
#: ``connect_ui_metrics``; see ``MIGRATED_OFFENDERS``). Each entry below must
#: carry a reason. Ratchet: never grow this list without a recorded reason.
EXEMPTIONS: dict[str, str] = {
    "ui/managers/theme_manager.py": (
        "internal: re-scales host QSS px literals on a scale change; a QObject "
        "singleton (never a QWidget), so the bus's widget-keyed wiring does not "
        "apply"
    ),
    "ui/managers/ui_font.py": (
        "internal: apply()'s live-resync wiring; the two raw connects ARE the "
        "resync hook (the producer side of the bus, not a consumer)"
    ),
    "ui/widgets/buttons/button.py": (
        "connects theme+font+scale with its own destroyed-hook teardown "
        "(documented stale-slot crash class: a dead Button's slot once fired as "
        "a QSpacerItem); the theme connect cannot go through the metrics bus"
    ),
    "ui/widgets/composite/timeline_widget/interaction.py": (
        "the raw connect/disconnect pair is the close->reshow transient "
        "teardown hook; the bus's per-(widget, slot) idempotency cache returns "
        "the same (already dropped) connection on rebind, so it cannot express "
        "unbind/rebind"
    ),
    "ui/widgets/composite/timeline_widget/widget.py": (
        "the __init__ raw connect is the counterpart of the transient "
        "bind/unbind pair in timeline_widget/interaction.py"
    ),
}

#: The plan-inventory offenders T2b migrated to the bus. Recorded so the
#: ratchet is two-sided: a migrated file must NOT come back into EXEMPTIONS.
MIGRATED_OFFENDERS: tuple[str, ...] = (
    "ui/widgets/atomic/custom_group_widget.py",
    "ui/widgets/atomic/custom_line_edit.py",
    "ui/widgets/atomic/loading_spinner.py",
    "ui/widgets/atomic/slider.py",
    "ui/widgets/atomic/spinbox.py",
    "ui/widgets/atomic/switch.py",
    "ui/widgets/atomic/text_labels.py",
    "ui/widgets/comboboxes/combo_box.py",
    "ui/widgets/composite/base_flyout/widget.py",
    "ui/widgets/composite/console_view.py",
    "ui/widgets/composite/dialog_shell.py",
    "ui/widgets/composite/icon_action_flyout.py",
    "ui/widgets/composite/indexed_toggle_flyout.py",
    "ui/widgets/composite/list_panel/widget.py",
    "ui/widgets/composite/process_console_widget.py",
    "ui/widgets/composite/sidebar_nav_list/widget.py",
    "ui/widgets/composite/simple_options_flyout/row.py",
    "ui/widgets/composite/simple_options_flyout/widget.py",
    "ui/widgets/composite/toast/notification.py",
    "ui/widgets/composite/top_tab_bar/bar.py",
    "ui/widgets/text/engine/canvas.py",
    "ui/widgets/text/engine/document_canvas.py",
    "ui/widgets/text/text.py",
    "ui/windows/custom_title_bar/widget.py",
    "ui/windows/window_chrome.py",
)

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
    assert len(EXEMPTIONS) == 5, (
        f"expected the 5 non-migratable raw subscribers recorded, got "
        f"{len(EXEMPTIONS)} — migrate files to the bus (and drop their "
        "entry) instead of letting the list drift"
    )
    for rel, reason in EXEMPTIONS.items():
        assert (_PACKAGE_ROOT / rel).is_file(), f"exempt file missing: {rel}"
        assert reason.strip(), f"exemption without a recorded reason: {rel}"
    for rel in (
        "ui/widgets/buttons/button.py",
        "ui/managers/theme_manager.py",
        "ui/managers/ui_font.py",
    ):
        assert rel in EXEMPTIONS, f"plan offender not recorded in the exemption list: {rel}"


def test_migrated_offenders_stay_off_the_exemption_list() -> None:
    """The 25 T2b-migrated offenders must never come back into EXEMPTIONS."""
    assert len(MIGRATED_OFFENDERS) == 25
    for rel in MIGRATED_OFFENDERS:
        assert (_PACKAGE_ROOT / rel).is_file(), f"migrated file missing: {rel}"
        assert rel not in EXEMPTIONS, (
            f"{rel} was migrated to the bus in T2b — do not re-exempt it"
        )


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
