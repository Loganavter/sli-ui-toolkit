"""Shared visual-row grouping for keyboard navigation.

One implementation of "what counts as a row" — used by both the flyout
traversal (``BaseFlyout._navigable_rows``) and the ``NavigationSection``
implementations that drive toolbars and dialogs
(``AutoNavigationSection``). Before this module the flyout had its own
copy of the centre-y banding logic; the sections kept an older, separate
approximation, so the same "navigation follows x order instead of visual
rows" defect lived on in the section path after it was fixed in the flyout
(owner report 2026-10-19: a colour-picker dialog's ``AutoNavigationSection``
was not traversable, and its single reachable row walked by x only).
"""

from __future__ import annotations

from collections.abc import Iterable

import shiboken6
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QWidget


def group_visual_rows(
    widgets: Iterable[QWidget],
    *,
    tolerance: float | None = None,
) -> list[list[QWidget]]:
    """Group *widgets* into VISUAL rows (centre-y bands), x-sorted inside a row.

    Grouping is by the global centre **y**: widgets whose centre is within
    *tolerance* of the current row's first centre belong to that row, so a
    taller control (a ``Switch`` next to a button) does not split its row.
    Rows come out ordered by y and each row is sorted by x, which makes the
    flat sequence a reading order — Up/Down can then step rows and Left/Right
    step inside a row.

    *tolerance* defaults to half the median widget height (floored at 4 px),
    the value the flyout traversal has used since the 2026-10-19 fix. Pass an
    explicit number to override it.

    Dead (C++-deleted) widgets and widgets whose geometry cannot be read are
    dropped rather than raising: navigation runs from an app-wide event filter
    and a stale child must never take arrow keys down with it.
    """
    live: list[QWidget] = []
    for widget in widgets:
        if not isinstance(widget, QWidget):
            continue
        try:
            if not shiboken6.isValid(widget):  # type: ignore[attr-defined]
                continue
        except Exception:
            continue
        live.append(widget)
    if not live:
        return []

    centers: dict[QWidget, QPoint] = {}
    for widget in live:
        try:
            centers[widget] = widget.mapToGlobal(widget.rect().center())
        except Exception:
            centers[widget] = QPoint(0, 0)

    if tolerance is None:
        heights = sorted(max(1, widget.height()) for widget in live)
        tolerance = max(4, heights[len(heights) // 2] // 2)

    rows: list[list[QWidget]] = []
    for widget in sorted(live, key=lambda w: (centers[w].y(), centers[w].x())):
        if rows and abs(centers[widget].y() - centers[rows[-1][0]].y()) <= tolerance:
            rows[-1].append(widget)
        else:
            rows.append([widget])
    for row in rows:
        row.sort(key=lambda w: centers[w].x())
    return rows


__all__ = ["group_visual_rows"]
