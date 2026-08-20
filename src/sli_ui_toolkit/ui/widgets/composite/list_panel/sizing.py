"""ListPanel height/sizing policy — split out of ``widget.py`` to keep the
facade thin. Functions take the panel as their first argument."""

from __future__ import annotations

from PySide6.QtCore import QTimer


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


def recalculate_and_set_height(panel, max_height: int | None = None):
    """Size the panel: natural height up to 8 rows, else MAX_VISIBLE_ITEMS.

    The virtual-list controller owns the content height and row
    positioning; this only clamps the panel/scroll-area viewport height.
    """
    num_items = panel._controller.count

    if num_items <= 0:
        row_h = panel.item_height if panel.item_height > 0 else 36
        final_height = constrained_height(row_h, max_height)
        panel._container_height = final_height
        panel.setMinimumHeight(0)
        panel.setMaximumHeight(final_height)
        panel.scroll_area.setMinimumHeight(0)
        panel.scroll_area.setMaximumHeight(final_height)
        panel._deferred_scrollbar_sync()
        return final_height

    pitch = panel._row_pitch()

    if num_items <= 8:
        natural_h = num_items * pitch + 10
        final_h = constrained_height(natural_h, max_height)
        panel._container_height = final_h
        panel.setMinimumHeight(0 if final_h < natural_h else final_h)
        panel.setMaximumHeight(final_h)
        panel.scroll_area.setMinimumHeight(0 if final_h < natural_h else final_h)
        panel.scroll_area.setMaximumHeight(final_h)
    else:
        visible_items = min(num_items, panel.MAX_VISIBLE_ITEMS)
        max_h = visible_items * pitch + 10
        final_h = constrained_height(max_h, max_height)
        panel._container_height = final_h
        panel.setMinimumHeight(0)
        panel.setMaximumHeight(final_h)
        panel.scroll_area.setMinimumHeight(0)
        panel.scroll_area.setMaximumHeight(final_h)

    panel._deferred_scrollbar_sync()
    return final_h
