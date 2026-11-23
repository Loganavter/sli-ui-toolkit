"""``settle_layout(deep=True)`` activates the layout of every descendant, parents first.

Why the flag exists (2026-11-23): activating a layout resizes its children, and a child that is *already* the right size
receives no ``Resize`` - so Qt never re-runs that child's own layout and its children keep the geometry of the box it had
before. Measured in RVE's settings page: the scroll area's content widget was already at its final 1026x852 while the tab
host inside it stayed 1000x766 for one event-loop turn, i.e. one frame of the previous geometry; the owner saw it as
content moving by the page inset when a page was first touched.

The pins below are about the contract, not about that host: a deep settle must reach nested layouts even when no widget in
the subtree changes size, and a shallow settle must stay shallow (an existing caller cannot be silently given extra work).
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QVBoxLayout, QWidget  # noqa: E402

from sli_ui_toolkit.ui.layout_settle import settle_layout  # noqa: E402


class _CountingBox(QVBoxLayout):
    """A layout that records whether it was asked to activate."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.activations = 0

    def activate(self):  # noqa: N802 - Qt spelling
        self.activations += 1
        return super().activate()


def _tree() -> tuple[QWidget, dict[str, _CountingBox]]:
    root = QWidget()
    root.resize(400, 300)
    layouts: dict[str, _CountingBox] = {}

    def branch(parent: QWidget, name: str, *, fixed: bool = False) -> QWidget:
        child = QWidget(parent)
        if fixed:
            # Already final: the parent's layout activation cannot resize it, which is exactly the stale case.
            child.setFixedSize(320, 200)
        box = _CountingBox(child)
        layouts[name] = box
        leaf = QWidget(child)
        box.addWidget(leaf)
        return child

    root_box = _CountingBox(root)
    layouts["root"] = root_box
    first = branch(root, "middle", fixed=True)
    root_box.addWidget(first)
    branch(first, "inner")
    return root, layouts


def test_a_deep_settle_activates_nested_layouts_even_without_a_resize():
    root, layouts = _tree()
    settle_layout(root, deep=True)
    assert layouts["root"].activations >= 1
    assert layouts["middle"].activations >= 1, "a child that is already the right size still needs its own layout run"
    assert layouts["inner"].activations >= 1, "the deep settle must reach a grandchild layout"


def test_a_shallow_settle_leaves_the_nested_layouts_alone():
    root, layouts = _tree()
    settle_layout(root)
    assert layouts["root"].activations >= 1
    assert layouts["inner"].activations == 0, "the default call must not grow extra work for existing hosts"
