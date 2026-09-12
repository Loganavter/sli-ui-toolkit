"""Virtual list engine: bounded row-pool virtualization for any list host.

Public API (also re-exported from ``sli_ui_toolkit.widgets``):

- :class:`VirtualListController` — wire a row pool + window math to an
  ``OverlayScrollArea`` (scrollbar sync, rebind on scroll/resize/filter).
- :func:`visible_window` / :func:`max_scroll_px` — pure window math for fixed
  row heights.
- :class:`MeasuredHeights` — variable-height cache with prefix sums.
- :class:`RowPool` — bounded reusable row-widget pool.
"""

from __future__ import annotations

from .controller import VirtualListController
from .pool import BindFn, RowFactory, RowPool
from .window import MeasuredHeights, max_scroll_px, visible_window

__all__ = [
    "BindFn",
    "MeasuredHeights",
    "RowFactory",
    "RowPool",
    "VirtualListController",
    "max_scroll_px",
    "visible_window",
]