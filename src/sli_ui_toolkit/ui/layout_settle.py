"""Synchronous settle for self-sizing widgets (one-frame geometry transients).

A widget that constrains its own size from a child's current size
(``setFixedHeight`` / ``setFixedSize`` / min+max clamps) while its children
are placed by a ``QLayout`` is only correct if the layout re-runs
**synchronously** after the change: the size setter merely posts the
widget's own ``Resize`` event, so a layout left to the next event-loop turn
paints one frame with stale child geometry — and ``QBoxLayout`` splits the
delta into the wrong child when a cached hint is stale (growing exposes it,
shrinking hides it). See the :func:`settle_layout` rule below.

Rule: call :func:`settle_layout` at the end of the explicit rebuild or
mutation that changed a self-derived size — never inside a child's own
``resizeEvent`` (settling too early can freeze a mid-scale value; some paths
must re-sync after the children finish rescaling).
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget


def _depth(widget: QWidget) -> int:
    depth = 0
    node = widget.parentWidget()
    while node is not None:
        depth += 1
        node = node.parentWidget()
    return depth


def settle_layout(widget: QWidget, *children: QWidget | None, deep: bool = False) -> None:
    """Refresh children hints and re-run ``widget.layout()`` synchronously.

    For each child (``None`` entries are skipped) calls
    ``child.updateGeometry()`` to drop stale ``sizeHint`` caches, then
    invalidates and activates the widget's own layout so the widget and
    its contents agree in the same call — no ``processEvents()``, no
    posted re-run. A widget without a layout is a no-op (children are
    still refreshed).

    ``deep=True`` also activates the layout of every descendant, parents
    before children. Why it is sometimes required: activating a layout
    resizes its children, and a child that was *already* the right size
    gets no ``Resize`` — so Qt never re-runs that child's layout and its
    own children keep the geometry of the box it had before (measured on
    RVE's settings page: the scroll area's content widget was already
    1026x852 while the tab host inside it stayed at 1000x766 until the
    next event-loop turn, showing one frame of the previous geometry).
    """
    targets = [widget]
    if deep:
        # Parents first: activating a parent resizes its children, and the
        # child's own layout must then run against the new size.
        targets.extend(sorted(widget.findChildren(QWidget), key=_depth))
    for target in targets:
        target.updateGeometry()
    for child in children:
        if child is None:
            continue
        child.updateGeometry()
    for target in targets:
        layout = target.layout()
        if layout is not None:
            layout.invalidate()
            layout.activate()
