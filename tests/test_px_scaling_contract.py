"""AST contract: geometry must re-derive through ``scaled_px()``, not be baked.

Two shapes produced the live-scale breakage (a widget/geometry that keeps its
import-time or literal design px after the user changes UI scale):

(a) ``scaled_px(...)`` evaluated into an **import-time constant** — a
    module-level or class-body assignment, or a function default. ``UiScale``
    is a process-wide singleton whose factor changes at runtime, so a value
    computed at import is frozen at whatever factor was active then; the
    app-side precedents are ``plugins/export/layout_geometry.py``,
    ``ui/widgets/color/picker_dialog.py`` and
    ``tabs/image_compare/plugins/video_editor/layout_geometry.py``.
(b) a ``setFixed*`` / ``setMinimum*`` / ``setMaximum*`` / ``resize(`` /
    ``QSize(`` call in chrome code (``ui/widgets``, ``ui/windows``) whose
    geometry arguments are *all* raw numeric literals — an obvious
    design-space value that skips the scale path entirely.

``0`` and ``16777215`` (``QWIDGETSIZE_MAX``) are excluded from (b): they are
structural sentinels (collapse / unbounded), not design px. Everything else is
gated. Offenders that are intentional or merely not yet migrated live in
``tests/px_scaling_allowlist.py`` with a reason; that list is a ratchet and
carries a per-file site count so an already-exempt file cannot silently gain
another offender. See the module docstring there for the ratchet rules.
"""

from __future__ import annotations

import ast
from pathlib import Path

from tests.px_scaling_allowlist import EXEMPTED_SITES, EXEMPTIONS

_PACKAGE_ROOT = Path(__file__).resolve().parent.parent / "src" / "sli_ui_toolkit"

#: Chrome code: widget/window surfaces whose geometry is user-scale sensitive.
#: Painters/managers elsewhere in the package are out of scope for shape (b).
_CHROME_PREFIXES = ("ui/widgets/", "ui/windows/")

#: Calls that stamp fixed geometry onto a widget or a size.
_GEOMETRY_CALLS = frozenset(
    {
        "setFixedWidth",
        "setFixedHeight",
        "setFixedSize",
        "setMinimumWidth",
        "setMinimumHeight",
        "setMinimumSize",
        "setMaximumWidth",
        "setMaximumHeight",
        "setMaximumSize",
        "resize",
        "QSize",
    }
)

#: Structural, not design px: 0 = collapsed, 16777215 = QWIDGETSIZE_MAX.
_STRUCTURAL_SENTINELS = frozenset({0, 16777215})

_NUMERIC_BINOPS = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod)


def _call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    if isinstance(node.func, ast.Name):
        return node.func.id
    return None


def _contains_scaled_px(node: ast.AST) -> bool:
    """True when *node* references ``scaled_px`` (bare or as an attribute)."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name) and sub.id == "scaled_px":
            return True
        if isinstance(sub, ast.Call) and _call_name(sub) == "scaled_px":
            return True
    return False


class _ImportTimePxScanner(ast.NodeVisitor):
    """Lines where ``scaled_px(...)`` is frozen at import time.

    Descends through module and class bodies (both execute at import) and
    through function decorators/defaults (also import-time), but never into a
    function body — those re-run per call and are the *correct* place to
    resolve the factor.
    """

    def __init__(self) -> None:
        self.lines: list[int] = []

    def _scan_defaults(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        defaults = [*node.args.defaults, *node.args.kw_defaults]
        candidates = [d for d in defaults if d is not None]
        candidates.extend(node.decorator_list)
        if any(_contains_scaled_px(candidate) for candidate in candidates):
            self.lines.append(node.lineno)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._scan_defaults(node)  # body intentionally not visited

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._scan_defaults(node)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        return  # body runs per call

    def visit_Assign(self, node: ast.Assign) -> None:
        if _contains_scaled_px(node.value):
            self.lines.append(node.lineno)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None and _contains_scaled_px(node.value):
            self.lines.append(node.lineno)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        if _contains_scaled_px(node.value):
            self.lines.append(node.lineno)


def detect_baked_px_constants(tree: ast.AST) -> list[int]:
    """Line numbers of import-time constants baked from ``scaled_px()``."""
    scanner = _ImportTimePxScanner()
    scanner.visit(tree)
    return sorted(set(scanner.lines))


def _literal_values(node: ast.AST) -> list[float] | None:
    """Numeric values of a pure-literal expression, or ``None`` if not one.

    ``None`` means the expression depends on runtime state (a name, a call, an
    attribute) and therefore cannot be judged a skipped scale path.
    """
    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
    ):
        return [float(node.value)]
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        inner = _literal_values(node.operand)
        if inner is None:
            return None
        return [-value for value in inner] if isinstance(node.op, ast.USub) else inner
    if isinstance(node, ast.BinOp) and isinstance(node.op, _NUMERIC_BINOPS):
        left = _literal_values(node.left)
        right = _literal_values(node.right)
        if left is None or right is None:
            return None
        return left + right
    return None


def _geometry_hits(tree: ast.AST) -> list[tuple[int, str]]:
    """``(line, source)`` of geometry calls whose args are all raw literals."""
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        if _call_name(node) not in _GEOMETRY_CALLS:
            continue
        values: list[float] = []
        literal = True
        for arg in node.args:
            got = _literal_values(arg)
            if got is None:
                literal = False
                break
            values.extend(got)
        if not literal or not values:
            continue
        if all(value in _STRUCTURAL_SENTINELS for value in values):
            continue
        hits.append((node.lineno, ast.unparse(node)))
    return sorted(hits)


def detect_unscaled_px_geometry(tree: ast.AST) -> list[int]:
    """Line numbers of all-literal geometry calls (shape (b) sites)."""
    return [line for line, _ in _geometry_hits(tree)]


def _is_chrome(rel: str) -> bool:
    return rel.startswith(_CHROME_PREFIXES)


def _raw_findings() -> dict[str, list[str]]:
    """``relative_path -> messages`` for every current offender, exemptions
    ignored (the inventory the allowlist is calibrated against)."""
    findings: dict[str, list[str]] = {}
    for path in sorted(_PACKAGE_ROOT.rglob("*.py")):
        rel = path.relative_to(_PACKAGE_ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        messages: list[str] = []
        for line in detect_baked_px_constants(tree):
            messages.append(
                f"{rel}:{line} scaled_px() baked into an import-time constant "
                "— resolve it at the use site instead"
            )
        if _is_chrome(rel):
            for line, source in _geometry_hits(tree):
                messages.append(
                    f"{rel}:{line} {source} — fixed geometry from a raw literal "
                    "that skips scaled_px()"
                )
        if messages:
            findings[rel] = messages
    return findings


def _findings() -> list[str]:
    raw = _raw_findings()
    out: list[str] = []
    for rel, messages in raw.items():
        if rel in EXEMPTIONS:
            continue  # recorded offender — see tests/px_scaling_allowlist.py
        out.extend(messages)
    return out


def test_no_import_time_baked_scaled_px_constants() -> None:
    """0 findings: ``scaled_px`` is never frozen at import time."""
    findings = _findings()
    assert findings == [], (
        "UI-scale geometry must be resolved at use time, never baked at "
        "import:\n" + "\n".join(findings)
    )


def test_offender_inventory_matches_the_allowlist() -> None:
    """The ratchet, site by site: every offender file is exempted, no
    exemption is stale, and no exempt file has gained (or lost) a finding
    without the allowlist being updated."""
    raw = _raw_findings()
    assert set(raw) == set(EXEMPTIONS), (
        "offender inventory drifted: unexempted files "
        f"{sorted(set(raw) - set(EXEMPTIONS))} / stale exemptions "
        f"{sorted(set(EXEMPTIONS) - set(raw))}"
    )
    assert set(EXEMPTIONS) == set(EXEMPTED_SITES), (
        "EXEMPTIONS and EXEMPTED_SITES must list the same files"
    )
    drifting = {
        rel: (EXEMPTED_SITES[rel], len(raw[rel]))
        for rel in raw
        if EXEMPTED_SITES[rel] != len(raw[rel])
    }
    assert not drifting, (
        "exempt file finding counts changed (recorded, actual): "
        f"{drifting} — update EXEMPTED_SITES in tests/px_scaling_allowlist.py "
        "(a fix lowers the number and eventually drops the EXEMPTIONS entry)"
    )


def test_detector_is_not_blind_on_the_current_tree() -> None:
    """Self-falsification: ignoring the allowlist, the detector must still see
    today's whole offender inventory (15 sites in 10 files). If a refactor
    makes the contract "green" by making the detector see nothing, this fails."""
    raw = _raw_findings()
    assert len(raw) == 10, f"detector found {len(raw)} offender files, expected 10"
    assert sum(len(messages) for messages in raw.values()) == 15
    assert "ui/widgets/buttons/style_api.py" in raw
    assert "ui/widgets/composite/calendar_widget/day_button.py" in raw


def test_exemption_list_is_recorded_and_justified() -> None:
    """Every entry exists, carries a reason, and is genuinely needed."""
    assert len(EXEMPTIONS) == 10, (
        f"expected today's 10 offender files recorded, got {len(EXEMPTIONS)} "
        "— fix an offender (and drop its entry) instead of letting the list "
        "drift"
    )
    for rel, reason in EXEMPTIONS.items():
        assert (_PACKAGE_ROOT / rel).is_file(), f"exempt file missing: {rel}"
        assert reason.strip(), f"exemption without a recorded reason: {rel}"
    for rel, reason in EXEMPTIONS.items():
        assert "by design" in reason or "offender" in reason, (
            f"{rel} must say whether the exemption is 'by design' or a real "
            "'offender' awaiting a fix"
        )


def test_detector_flags_a_module_level_scaled_px_constant() -> None:
    tree = ast.parse("from sli_ui_toolkit.ui.managers.ui_scale import scaled_px\nPAD = scaled_px(8)\n")
    assert detect_baked_px_constants(tree) == [2]
    assert detect_unscaled_px_geometry(tree) == []


def test_detector_flags_class_body_and_default_arg_baking() -> None:
    class_body = ast.parse(
        "class Card:\n"
        "    GAP = scaled_px(6)\n"
        "    PAD: int = scaled_px(4) + 1\n"
    )
    assert detect_baked_px_constants(class_body) == [2, 3]

    default_arg = ast.parse("def paint(self, radius=scaled_px(4)):\n    return radius\n")
    assert detect_baked_px_constants(default_arg) == [1]

    use_site = ast.parse("def paint(self):\n    return scaled_px(4)\n")
    assert detect_baked_px_constants(use_site) == []


def test_detector_flags_literal_geometry_in_a_scale_aware_class() -> None:
    tree = ast.parse(
        "class Chrome:\n"
        "    def relayout(self):\n"
        "        self.setFixedHeight(24)\n"
        "        self.setMinimumSize(28, 36)\n"
        "        self.resize(800, 600)\n"
        "        self.updateGeometry()\n"
    )
    assert detect_unscaled_px_geometry(tree) == [3, 4, 5]


def test_detector_accepts_scaled_geometry_and_structural_sentinels() -> None:
    scaled = ast.parse(
        "self.setFixedHeight(scaled_px(24))\n"
        "self.resize(scaled_px(800), scaled_px(600))\n"
        "self.setFixedSize(scaled_px(size), size + scaled_px(2))\n"
        "self.setMinimumWidth(0)\n"
        "self.setMaximumWidth(16777215)\n"
        "w = self.width()\n"
        "self.setFixedWidth(w)\n"
        "return QSize(w, h)\n"
    )
    assert detect_unscaled_px_geometry(scaled) == []


def test_detector_accepts_literal_arithmetic_only_when_it_is_actually_px() -> None:
    """Raw arithmetic still counts as a design literal (shape (b)); sentinels
    mixed in do not excuse a real design value."""
    tree = ast.parse("self.setFixedHeight(12 * 2)\nself.setMinimumHeight(max(0, 1))\n")
    assert detect_unscaled_px_geometry(tree) == [1]


def test_shape_b_scope_is_chrome_only() -> None:
    assert _is_chrome("ui/widgets/atomic/slider.py") is True
    assert _is_chrome("ui/windows/window_chrome.py") is True
    assert _is_chrome("ui/managers/ui_scale.py") is False
    assert _is_chrome("config.py") is False
