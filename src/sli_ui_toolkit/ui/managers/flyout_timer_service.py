from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, QPoint, QTimer

from sli_ui_toolkit.config import get_flyout_timings

class DelayedActionTimer(QObject):
    def __init__(self, callback: Callable[[], None], parent=None, interval_ms: int = 0):
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(callback)
        if interval_ms > 0:
            self._timer.setInterval(interval_ms)

    def start(self, ms: int | None = None):
        if ms is not None:
            self._timer.start(ms)
        else:
            self._timer.start()

    def stop(self):
        self._timer.stop()

    def is_active(self) -> bool:
        return self._timer.isActive()

    def interval(self) -> int:
        return self._timer.interval()

    def set_interval(self, ms: int):
        self._timer.setInterval(ms)

class AnchoredFlyoutAutoHide(QObject):
    def __init__(
        self,
        *,
        flyout,
        anchor_getter: Callable[[], object | None],
        parent=None,
        retry_ms: int | None = None,
    ):
        super().__init__(parent)
        self._flyout = flyout
        self._anchor_getter = anchor_getter
        timings = get_flyout_timings()
        self._retry_ms = (
            timings.transient_auto_hide_delay_ms
            if retry_ms is None
            else int(retry_ms)
        )
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_timeout)

    def schedule(self, ms: int):
        if ms <= 0:
            self._timer.stop()
            return
        self._timer.start(ms)

    def cancel(self):
        self._timer.stop()

    def _on_timeout(self):
        if self._flyout is None:
            return
        try:
            if not self._flyout.isVisible():
                return
        except RuntimeError:
            return

        from PySide6.QtGui import QCursor

        cursor_pos = QCursor.pos()

        try:
            if self._flyout.contains_global(cursor_pos):
                self.schedule(self._retry_ms)
                return
        except Exception:
            pass

        anchor = self._anchor_getter()
        if anchor is not None:
            try:
                button_global_pos = anchor.mapToGlobal(QPoint(0, 0))
                button_rect = anchor.rect()
                button_global_rect = button_rect.translated(button_global_pos)
                if button_global_rect.contains(cursor_pos):
                    self.schedule(self._retry_ms)
                    return
            except Exception:
                pass

        if self._cursor_in_linked_child(cursor_pos):
            self.schedule(self._retry_ms)
            return

        try:
            self._flyout.hide()
        except Exception:
            pass

    def _cursor_in_linked_child(self, cursor_pos) -> bool:
        """True if the cursor is over a ``FlyoutManager.link()``-ed child.

        E.g. an options dropdown opened from a combo box that lives inside
        this (hover-driven) flyout's own content: the dropdown is its own
        top-level-ish overlay widget, spatially outside both this flyout's
        own rect and its anchor's rect, so without this check the cursor
        moving onto it during a pick would read as "left both safe zones"
        and auto-hide the parent flyout out from under the dropdown.
        """
        try:
            from sli_ui_toolkit.managers import FlyoutManager
        except Exception:
            return False
        manager = FlyoutManager.get_instance()
        for child in manager.linked_children(self._flyout):
            try:
                if child.isVisible() and child.contains_global(cursor_pos):
                    return True
            except Exception:
                continue
        return False
