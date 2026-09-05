"""ListPanel height/sizing policy — split out of ``widget.py`` to keep the
facade thin. Functions take the panel as their first argument."""

from __future__ import annotations

from PySide6.QtCore import QTimer

from sli_ui_toolkit.ui.managers.ui_scale import scaled_px


def constrained_height(height: int, max_height: int | None) -> int:
    if max_height is None:
        return height
    return max(1, min(height, int(max_height)))


def deferred_scrollbar_sync(panel) -> None:
    # The viewport height settles on the next layout pass; re-derive the
    # visible window + scrollbar range after it does. The singleShot is
    # not cancelled by widget destruction — guard against it (same
    # pattern as SimpleOptionsFlyout._deferred_update_size).
    def _rebind():
        try:
            import shiboken6  # type: ignore[attr-defined]

            if not shiboken6.Shiboken.isValid(panel):
                return
        except Exception:
            pass
        controller = panel._controller
        if controller is not None:
            try:
                controller.rebind()
            except RuntimeError:
                pass

    QTimer.singleShot(20, _rebind)


def _panel_chrome_height(panel) -> int:
    """Vertical chrome the panel adds around the scroll area (own layout
    margins, top + bottom)."""
    try:
        margins = panel.layout_outer.contentsMargins()
        return int(margins.top() + margins.bottom())
    except (AttributeError, RuntimeError):
        return 2


def _symmetric_content_height(panel, num_items: int) -> int:
    """Content height with mirrored top/bottom insets (same math as
    ``VirtualListController._content_height``): the last row contributes
    its widget height, not a full pitch — inter-row spacing is not
    duplicated after the list."""
    pitch = panel._row_pitch()
    row_h = panel.item_height if panel.item_height > 0 else 36
    y_margin = scaled_px(panel._content_margin_px)
    return 2 * y_margin + max(0, num_items - 1) * pitch + max(1, row_h)


def recalculate_and_set_height(panel, max_height: int | None = None):
    """Size the panel: natural height up to 8 rows, else MAX_VISIBLE_ITEMS.

    The virtual-list controller owns the content height and row
    positioning; this only clamps the panel/scroll-area viewport height.
    Heights here are *panel* heights (content + panel chrome); the scroll
    area gets the chrome subtracted so the viewport lands exactly on the
    content — no stretch, no dead band at the bottom.
    """
    num_items = panel._controller.count
    chrome = _panel_chrome_height(panel)

    if num_items <= 0:
        row_h = panel.item_height if panel.item_height > 0 else 36
        final_height = constrained_height(row_h, max_height)
        panel._container_height = final_height
        panel.setMinimumHeight(0)
        panel.setMaximumHeight(final_height)
        panel.scroll_area.setMinimumHeight(0)
        panel.scroll_area.setMaximumHeight(max(0, final_height - chrome))
        panel._deferred_scrollbar_sync()
        return final_height

    if num_items <= 8:
        natural_h = _symmetric_content_height(panel, num_items) + chrome
        final_h = constrained_height(natural_h, max_height)
        panel._container_height = final_h
        panel.setMinimumHeight(0 if final_h < natural_h else final_h)
        panel.setMaximumHeight(final_h)
        scroll_h = max(0, final_h - chrome)
        panel.scroll_area.setMinimumHeight(0 if final_h < natural_h else scroll_h)
        panel.scroll_area.setMaximumHeight(scroll_h)
    else:
        visible_items = min(num_items, panel.MAX_VISIBLE_ITEMS)
        max_h = _symmetric_content_height(panel, visible_items) + chrome
        final_h = constrained_height(max_h, max_height)
        panel._container_height = final_h
        panel.setMinimumHeight(0)
        panel.setMaximumHeight(final_h)
        panel.scroll_area.setMinimumHeight(0)
        panel.scroll_area.setMaximumHeight(max(0, final_h - chrome))

    panel._deferred_scrollbar_sync()
    return final_h
