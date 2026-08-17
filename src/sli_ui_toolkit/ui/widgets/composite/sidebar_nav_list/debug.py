"""Layout debug dump for IconListWidget (SLI_UI_NAVLIST_DEBUG=1).

Dumps host/viewport/row geometry after a layout pass to diagnose rows
being clipped ("eaten") at non-1.0 UI scale factors — off by default.
The functions take the widget explicitly (they read ``_rows``/``_scroll``/
``_host``/``_host_layout``) so the panel just delegates; no shared state.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from PySide6.QtCore import QPoint, QTimer

from sli_ui_toolkit.ui.managers.ui_scale import UiScale

_navlist_logger = logging.getLogger("sli_ui_toolkit.sidebar_nav_list")


def _navlist_debug_enabled() -> bool:
    return os.environ.get("SLI_UI_NAVLIST_DEBUG", "").strip().lower() not in (
        "",
        "0",
        "false",
        "no",
        "off",
    )


def _navlist_debug(message: str, *args) -> None:
    if _navlist_debug_enabled():
        _navlist_logger.debug("[navlist] " + message, *args)


def schedule_layout_debug(widget: Any, reason: str) -> None:
    """Dump geometry after the current layout pass (the synchronous
    state right after set_items/scale_changed is mid-rebuild and shows
    stale rects — the live "eaten rows" symptoms only show post-layout).
    """
    if not _navlist_debug_enabled():
        return
    QTimer.singleShot(0, lambda: log_layout_state(widget, reason))


def log_layout_state(widget: Any, reason: str) -> None:
    """Dump host/viewport/row geometry to diagnose top rows being
    clipped ("eaten") at non-1.0 UI scale factors.

    Expected healthy state at any factor: every row's rect is fully
    inside ``host``, ``host`` height <= viewport height OR the scroll
    value is within range with row 0 visible at value == 0.

    When the list lives inside a CSD-decorated window (``_csd_title_bar``),
    the dump also prints the bar's height and the window-layout top
    margin that compensates for it — a mismatch here means the first
    row sits underneath the title bar.
    """
    _rows = widget._rows
    _scroll = widget._scroll
    _host = widget._host
    _host_layout = widget._host_layout

    _navlist_debug(
        "reason=%s factor=%.2f widget=%dx%d scrollbar_value=%d/%d page=%d",
        reason,
        UiScale.get_instance().factor(),
        widget.width(),
        widget.height(),
        _scroll.verticalScrollBar().value(),
        _scroll.verticalScrollBar().maximum(),
        _scroll.verticalScrollBar().pageStep(),
    )
    top_level = widget.window()
    in_window = widget.mapTo(top_level, QPoint(0, 0)) if top_level is not None else None
    _navlist_debug(
        "  in_window=%s (window=%dx%d)",
        (in_window.x(), in_window.y()) if in_window is not None else None,
        top_level.width(),
        top_level.height(),
    )
    title_bar = getattr(top_level, "_csd_title_bar", None)
    if title_bar is not None:
        _navlist_debug(
            "  csd_title_bar height=%d visible=%s geometry=%s",
            title_bar.height(),
            title_bar.isVisible(),
            (title_bar.x(), title_bar.y(), title_bar.width(), title_bar.height()),
        )
    layout = top_level.layout() if top_level is not None else None
    if layout is not None:
        ml, mt, mr, mb = layout.getContentsMargins()
        _navlist_debug(
            "  window_layout_margins=(%d, %d, %d, %d)",
            ml,
            mt,
            mr,
            mb,
        )
    vp = _scroll.viewport()
    _navlist_debug(
        "  viewport=%dx%d@(%d,%d) host=%dx%d@(%d,%d) host_sizehint=%dx%d margins=%s spacing=%d",
        vp.width(),
        vp.height(),
        vp.x(),
        vp.y(),
        _host.width(),
        _host.height(),
        _host.x(),
        _host.y(),
        _host.sizeHint().width(),
        _host.sizeHint().height(),
        (_host_layout.contentsMargins().left(),
         _host_layout.contentsMargins().top(),
         _host_layout.contentsMargins().right(),
         _host_layout.contentsMargins().bottom()),
        _host_layout.spacing(),
    )
    total_h = 0
    for index, row in enumerate(_rows):
        btn = row.button
        total_h += btn.height()
        _navlist_debug(
            "  row[%d] text=%r height=%d min_h=%d max_h=%d sizehint=%dx%d "
            "visible=%s rect=%dx%d@(%d,%d)",
            index,
            row.text[:24],
            btn.height(),
            btn.minimumHeight(),
            btn.maximumHeight(),
            btn.sizeHint().width(),
            btn.sizeHint().height(),
            btn.isVisible(),
            btn.width(),
            btn.height(),
            btn.x(),
            btn.y(),
        )
    _navlist_debug(
        "  rows_total_h=%d content_h=sizehint=%d vs viewport=%d",
        total_h,
        _host.sizeHint().height(),
        vp.height(),
    )
