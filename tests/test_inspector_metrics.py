"""The inspector subtree re-derives its design-px geometry on a LIVE metrics change.

Falsification story (measured against the pre-change tree): the inspector had
**no** appearance-bus subscription at all. Building an ``InspectorWindow`` at
factor 1.0 and then calling ``UiScale.set_factor(1.25)`` left every cached
value frozen:

- the tree row stayed **26 px** — the raw ``setFixedHeight(26)`` at the end of
  ``_TreeNodeRow.__init__`` overwrote the fixed height ``Button`` had already
  resolved through ``scaled_px``;
- the tree indent stayed 14 px, the page content margins ``(8,8,8,8)`` and
  spacing 4, the toolbar margins ``(8,6,8,2)`` and spacing 6;
- an already-built preview kept ``maximumHeight() == 144`` /
  ``minimumHeight() == 48``;
- a rendered color swatch kept its 14×14 fixed size.

After the fix one subscription on the inspector chrome root (the window)
re-derives those constants through ``scaled_px()`` at the live factor. Every
assertion below is the exact scaled number, not merely "it changed".
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QRect
from PySide6.QtTest import QTest

from sli_ui_toolkit.managers import UiFont, UiScale
from sli_ui_toolkit.ui.inspector.contract import FieldKind, InspectField
from sli_ui_toolkit.ui.inspector.fields import _Swatch
from sli_ui_toolkit.ui.inspector.tree import _TreeNodeRow
from sli_ui_toolkit.ui.inspector.view import InspectorWindow
from sli_ui_toolkit.widgets import Switch

from tests.inspector_helpers import _open_probe

_PROBE_SOURCE = (
    "from PySide6.QtWidgets import QWidget\n"
    "\n"
    "class Probe(QWidget):\n"
    "    def __init__(self, parent=None):\n"
    "        super().__init__(parent)\n"
)


@pytest.fixture(autouse=True)
def _reset_live_metrics():
    """Every test starts and ends at the design factor / face."""
    UiScale.get_instance().set_factor(1.0)
    UiFont.get_instance().set_family(None)
    yield
    UiScale.get_instance().set_factor(1.0)
    UiFont.get_instance().set_family(None)


def _drain_metrics_bus() -> None:
    """Let the coalesced zero-timer emit (and its slots run)."""
    QTest.qWait(50)


def _row_indent_left(row: _TreeNodeRow) -> float:
    """Left edge of the row's twist region — the scaled depth indent."""
    rects = row._split.compute(
        QRect(0, 0, 400, row.height()), row._controller.regions
    )
    return rects[0].left()


def _build_inspector(qapp, tmp_path_factory, monkeypatch):
    """Real window + Layout tree + Code/Preview + a rendered color swatch."""
    win = InspectorWindow()
    root = Switch()
    child = Switch()
    win.set_layout_nodes((("Switch", root, 0), ("Switch", child, 1)))

    pane, _source_file, _written = _open_probe(
        win,
        _PROBE_SOURCE,
        tmp_path_factory,
        monkeypatch,
        source_start=3,
    )
    pane._code_section._preview_btn.click()
    assert pane._code_section._preview_widget is not None

    # A page that survives the Code section: an extra section keeps the
    # rendered swatch alive while the preview panel is open.
    extra = pane.add_section("Probe")
    pane._add_field_row(
        extra,
        InspectField(name="background", value="#ff0000", kind=FieldKind.COLOR),
    )
    swatches = extra.content_widget.findChildren(_Swatch)
    assert swatches
    swatch = swatches[0]

    win.resize(900, 700)
    win.show()
    QTest.qWait(20)

    rows = pane.pages["Layout"].content_widget.findChildren(_TreeNodeRow)
    depth_one = next(row for row in rows if row._depth == 1)
    return win, pane, depth_one, swatch


def test_inspector_re_derives_geometry_on_a_live_scale_change(
    qapp, tmp_path_factory, monkeypatch
):
    win, pane, row, swatch = _build_inspector(qapp, tmp_path_factory, monkeypatch)
    preview = pane._code_section._preview_widget
    tree_page = pane.pages["Layout"]

    # ---- design baseline, factor 1.0 ----
    assert row.height() == 26
    assert _row_indent_left(row) == 14  # depth-1 leaf: one indent step
    margins = tree_page.content_layout.contentsMargins()
    assert (margins.left(), margins.top(), margins.right(), margins.bottom()) == (
        8,
        8,
        8,
        8,
    )
    assert tree_page.content_layout.spacing() == 4
    toolbar = win.toolbar_layout
    toolbar_margins = toolbar.contentsMargins()
    assert (
        toolbar_margins.left(),
        toolbar_margins.top(),
        toolbar_margins.right(),
        toolbar_margins.bottom(),
    ) == (8, 6, 8, 2)
    assert toolbar.spacing() == 6
    assert preview.maximumHeight() == 144
    assert preview.minimumHeight() == 48
    assert swatch.size().width() == 14

    # ---- live change, through the public lever ----
    UiScale.get_instance().set_factor(1.25)
    _drain_metrics_bus()

    # The raw 26 px write is gone: Button's scaled fixed height survives.
    assert row.height() == UiScale.get_instance().scaled_px(26)
    assert row.height() != 26
    # ... and a row CONSTRUCTED at the new factor must not be stamped back to
    # 26 by the deleted ``setFixedHeight`` (the raw write landed after Button
    # had already applied the scaled design size).
    late_row = _TreeNodeRow(
        "Late", Switch(), has_children=False, expanded=False, depth=0
    )
    assert late_row.minimumHeight() == UiScale.get_instance().scaled_px(26)
    assert late_row.maximumHeight() == UiScale.get_instance().scaled_px(26)
    assert late_row.minimumHeight() != 26
    # Indent re-derived at use time.
    assert _row_indent_left(row) == UiScale.get_instance().scaled_px(14)
    assert _row_indent_left(row) > 14
    margins = tree_page.content_layout.contentsMargins()
    assert (margins.left(), margins.top(), margins.right(), margins.bottom()) == (
        UiScale.get_instance().scaled_px(8),
    ) * 4
    assert tree_page.content_layout.spacing() == UiScale.get_instance().scaled_px(4)
    toolbar_margins = win.toolbar_layout.contentsMargins()
    assert (
        toolbar_margins.left(),
        toolbar_margins.top(),
        toolbar_margins.right(),
        toolbar_margins.bottom(),
    ) == tuple(UiScale.get_instance().scaled_px(v) for v in (8, 6, 8, 2))
    assert win.toolbar_layout.spacing() == UiScale.get_instance().scaled_px(6)
    assert preview.maximumHeight() == UiScale.get_instance().scaled_px(144)
    assert preview.minimumHeight() == UiScale.get_instance().scaled_px(48)
    assert swatch.size().width() == UiScale.get_instance().scaled_px(14)

    win.close()


def test_font_axis_wakes_the_inspector_subtree(qapp):
    """A font-only emission must reach the inspector's one subscription.

    Row height is scale-derived (a font change does not change it), so the
    observable proof is that the pane's metrics pass runs — the pre-change
    inspector had no subscriber at all (``refresh_metrics`` did not exist).
    """
    win = InspectorWindow()
    win.set_layout_nodes((("Switch", Switch(), 0),))
    pane = win.active_pane()
    assert pane is not None

    calls: list[int] = []
    original = pane.refresh_metrics

    def _spy() -> None:
        calls.append(1)
        original()

    pane.refresh_metrics = _spy  # type: ignore[method-assign]

    UiFont.get_instance().set_family("DejaVu Sans")
    _drain_metrics_bus()

    assert calls, "a font-axis change never reached the inspector subtree"
    win.close()
