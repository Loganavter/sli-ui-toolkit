"""Layout/Constructor tree walking for ``InspectorController`` — split out to
keep that class down to event dispatch + selection state, mirroring the
thin-owner pattern already used in ``code/apply.py``. ``_layout_nodes_for``
and ``_constructor_nodes_for`` used to carry two copies of the same nested
``walk()`` helper (one walking from the widget's window, one from the widget
itself); collapsed into the single ``_walk_widget_tree`` below.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget


def _walk_widget_tree(controller, root: QWidget, *, depth: int = 0) -> list[tuple[str, object, int]]:
    nodes: list[tuple[str, object, int]] = []

    def walk(current: QWidget, current_depth: int) -> None:
        nodes.append((type(current).__name__, current, current_depth))
        for child in current.findChildren(
            QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly
        ):
            if controller._is_inspector_widget(child):
                continue
            walk(child, current_depth + 1)

    walk(root, depth)
    return nodes


def layout_nodes_for(controller, widget: QWidget) -> None:
    if not controller._is_valid_widget(widget):
        return
    nodes = _walk_widget_tree(controller, widget.window())
    controller._window.set_layout_nodes(tuple(nodes))


def constructor_nodes_for(controller, widget: QWidget) -> None:
    """Every widget inside the selected widget (its own subtree)."""
    if not controller._is_valid_widget(widget):
        return
    nodes = _walk_widget_tree(controller, widget)
    controller._window.set_constructor_nodes(tuple(nodes))
