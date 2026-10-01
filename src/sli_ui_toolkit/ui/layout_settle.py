"""Synchronous settle for self-sizing widgets (one-frame geometry transients).

A widget that constrains its own size from a child's current size
(``setFixedHeight`` / ``setFixedSize`` / min+max clamps) while its children
are placed by a ``QLayout`` is only correct if the layout re-runs
**synchronously** after the change: the size setter merely posts the
widget's own ``Resize`` event, so a layout left to the next event-loop turn
paints one frame with stale child geometry — and ``QBoxLayout`` splits the
delta into the wrong child when a cached hint is stale (growing exposes it,
shrinking hides it). See ``docs/dev/QT_LAYOUT_PITFALLS.md`` in
improve-imgsli-internal-docs.

Rule: call :func:`settle_layout` at the end of the explicit rebuild or
mutation that changed a self-derived size — never inside a child's own
``resizeEvent`` (settling too early can freeze a mid-scale value; some paths
must re-sync after the children finish rescaling).
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget


def settle_layout(widget: QWidget, *children: QWidget | None) -> None:
    """Refresh children hints and re-run ``widget.layout()`` synchronously.

    For each child (``None`` entries are skipped) calls
    ``child.updateGeometry()`` to drop stale ``sizeHint`` caches, then
    invalidates and activates the widget's own layout so the widget and
    its contents agree in the same call — no ``processEvents()``, no
    posted re-run. A widget without a layout is a no-op (children are
    still refreshed).
    """
    for child in children:
        if child is None:
            continue
        child.updateGeometry()
    root = widget.layout()
    if root is not None:
        root.invalidate()
        root.activate()
