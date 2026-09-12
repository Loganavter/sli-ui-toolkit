"""Static scan: every painted text in the toolkit must be scale-resolved.

Two failure classes this guards against (both found live in Improve-ImgSLI):

* **Unscaled text** — a paint function draws with the raw painter font
  (design-sized) instead of a `ui_font()`/`paint_font()`-resolved one. At
  UI scale > 1.0 the label stays small (timeline lane labels, help fallback
  alt text).
* **Double-scaled text** — a paint function runs `paint_font()`/`rebase()`
  over a font that is *already* scale-resolved (the row font set by the
  menu's `_relayout_widths`), multiplying the factor a second time and
  painting ~factor² (context menu row labels).

Rule A: any function containing `drawText(` must either call `setFont(`
itself, reference a scale-resolving font helper (`ui_font`, `paint_font`,
`rebase_family`, `rebase_font`, `apply_ui_font`) in the same function, or be
listed in ``_TEXT_WITHOUT_SET_FONT`` (with the reason why its inherited font
is already scale-resolved).

Rule B: any function containing `drawText(` may only call `paint_font` /
`rebase_font` if listed in ``_PAINT_FONT_ALLOWED`` — those helpers multiply
the factor, so they are only safe on widgets whose own font is the
design-sized application font (never on widgets whose font was set to a
scale-resolved one, e.g. context-menu rows).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_TOOLKIT_ROOT = Path(__file__).resolve().parent.parent / "src" / "sli_ui_toolkit"

_SCALE_FONT_HELPERS = ("ui_font", "paint_font", "rebase_family", "rebase_font", "apply_ui_font")
_PAINT_FONT_HELPERS = ("paint_font", "rebase_font")

# (relative path, function name) -> reason. These paint functions draw text
# without setting a font themselves because the widget's inherited font is
# already scale-resolved (apply_ui_font pinned in __init__) or the painter
# font was set by the caller.
_TEXT_WITHOUT_SET_FONT: dict[tuple[str, str], str] = {
    ("ui/widgets/atomic/switch.py", "paintEvent"): (
        "paints widget.font(); Switch.__init__ pins apply_ui_font(self)"
    ),
    ("ui/widgets/composite/adaptive_tab_strip/tab_bar.py", "_paint_tab"): (
        "paints self.font(); the tab strip pins apply_ui_font(self) in __init__"
    ),
    ("ui/widgets/helpers/marquee_text.py", "draw_marquee_text"): (
        "paints the caller-set font; callers do painter.setFont(label.font()) "
        "with a scale-resolved label font"
    ),
}

# (relative path, function name) -> reason. paint_font()/rebase_font()
# multiply the UiScale factor, which is only correct when the source widget
# font is the *design-sized* application font — never on widgets whose font
# is already scale-resolved.
_PAINT_FONT_ALLOWED: dict[tuple[str, str], str] = {
    ("ui/widgets/atomic/custom_group_widget.py", "_paint_top_caption"): (
        "paints with paint_font(self) over the widget's design-sized font"
    ),
    ("ui/widgets/atomic/checkbox.py", "draw"): (
        "CheckBox is now a Button subclass (rebased off QCheckBox, no more "
        "apply_ui_font pin) -- paints with paint_font(widget) over the "
        "design-sized font, same as the rest of the button pipeline"
    ),
    ("ui/widgets/atomic/radio.py", "draw"): (
        "RadioButton is now a Button subclass (rebased off QRadioButton, no "
        "more apply_ui_font pin) -- paints with paint_font(widget) over the "
        "design-sized font, same as the rest of the button pipeline"
    ),
    ("ui/widgets/buttons/content.py", "_draw_row"): (
        "button text layers paint with paint_font(ctx.widget); buttons keep "
        "the design-sized app font (no apply_ui_font)"
    ),
    ("ui/widgets/buttons/content.py", "draw"): (
        "button text layers paint with paint_font(ctx.widget); buttons keep "
        "the design-sized app font (no apply_ui_font)"
    ),
    ("ui/widgets/buttons/layers/badge.py", "draw"): (
        "badge digits paint with the painter font of the button pipeline, "
        "which is the design-sized app font"
    ),
    ("ui/widgets/comboboxes/_overlay.py", "draw"): (
        "dropdown slot text paints with paint_font(widget) over the "
        "combobox's design-sized font"
    ),
    ("ui/widgets/comboboxes/_layers.py", "draw"): (
        "field text paints with paint_font(widget) over the design-sized font"
    ),
    ("ui/widgets/comboboxes/scrollable_combobox.py", "draw"): (
        "slot text paints with widget.getItemFont() -> paint_font(self) over "
        "the design-sized font"
    ),
    ("ui/widgets/composite/top_tab_bar/tab_button.py", "draw"): (
        "tab text paints with paint_font(widget) over the design-sized font"
    ),
    ("ui/widgets/overlays/drag_drop_overlay.py", "paintEvent"): (
        "paints with paint_font(self, pixel_size=20) over the design-sized font"
    ),
}


def _paint_functions() -> list[tuple[Path, ast.FunctionDef]]:
    found: list[tuple[Path, ast.FunctionDef]] = []
    for path in sorted(_TOOLKIT_ROOT.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            calls = [c for c in ast.walk(node) if isinstance(c, ast.Call)]
            has_text = any(
                isinstance(c.func, ast.Attribute) and c.func.attr == "drawText"
                for c in calls
            )
            if has_text:
                found.append((path, node))
    return found


def _calls(fn: ast.FunctionDef, names: set[str]) -> list[ast.Call]:
    out = []
    for c in ast.walk(fn):
        if not isinstance(c, ast.Call):
            continue
        if isinstance(c.func, ast.Attribute) and c.func.attr in names:
            out.append(c)
        elif isinstance(c.func, ast.Name) and c.func.id in names:
            out.append(c)
    return out


def _rel_path(path: Path) -> str:
    return str(path.relative_to(_TOOLKIT_ROOT)).replace("\\", "/")


def test_every_painted_text_has_a_scale_resolved_font():
    """Rule A: drawText requires setFont / scale helper / documented reason."""
    violations: list[str] = []
    for path, fn in _paint_functions():
        key = (_rel_path(path), fn.name)
        if _calls(fn, {"setFont"}):
            continue
        if _calls(fn, set(_SCALE_FONT_HELPERS)):
            continue
        if key in _TEXT_WITHOUT_SET_FONT:
            continue
        violations.append(
            f"{key[0]}::{key[1]} draws text but never calls setFont() or a "
            f"scale-resolving helper ({', '.join(_SCALE_FONT_HELPERS)}) — add "
            "a setFont(ui_font(...))/paint_font(...) call, or an entry in "
            "_TEXT_WITHOUT_SET_FONT with the reason the inherited font is "
            "already scale-resolved"
        )
    assert not violations, "\n".join(violations)


def test_paint_font_only_on_design_sized_fonts():
    """Rule B: paint_font()/rebase_font() near drawText needs an allowance."""
    violations: list[str] = []
    for path, fn in _paint_functions():
        key = (_rel_path(path), fn.name)
        if not _calls(fn, set(_PAINT_FONT_HELPERS)):
            continue
        if key in _PAINT_FONT_ALLOWED:
            continue
        violations.append(
            f"{key[0]}::{key[1]} calls {_PAINT_FONT_HELPERS} while drawing "
            "text — these multiply the UiScale factor, so they are only safe "
            "on design-sized fonts; use rebase_family() (size-preserving) for "
            "already scale-resolved fonts, or add an entry in "
            "_PAINT_FONT_ALLOWED with the reason"
        )
    assert not violations, "\n".join(violations)


def test_scan_catalogue_stays_current():
    """Allowlists must not rot: every entry must still exist and still draw text."""
    functions = {( _rel_path(p), fn.name) for p, fn in _paint_functions()}
    for key in list(_TEXT_WITHOUT_SET_FONT) + list(_PAINT_FONT_ALLOWED):
        assert key in functions, (
            f"allowlist entry {key} no longer matches any drawText function — "
            "remove it"
        )
