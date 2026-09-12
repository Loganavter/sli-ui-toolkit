"""CustomTitleBar drag surface — window moving via system move or manual.

The whole bar is draggable except registered exclusions (window controls,
zone widgets the host added) and any interactive ``Button``. On Wayland
the drag is handed to ``startSystemMove``; on X11 it falls back to manual
``window.move`` delta tracking.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.ui.widgets.buttons import Button


class _TitleBarDragApi:
    """Mixin: drag exclusion registry + mouse drag handling.

    Not a QWidget itself — mixed into CustomTitleBar; relies on instance
    attributes assigned in ``CustomTitleBar.__init__`` (``_drag_enabled``,
    ``_drag_exclusions``, ``_drag_start_global``, ``_balance_spacer``,
    ``_left_balance``, ``_controls``, ``_title_label``,
    ``_target_window``) and on QWidget methods (childAt, parentWidget,
    isEnabled, isVisible, testAttribute). Calls the window-controls mixin's
    ``_toggle_maximize``.
    """

    # Declared here only so mypy can resolve them across the mixin split —
    # the real assignments live in CustomTitleBar.__init__ (widget.py), the
    # sibling mixins, or QWidget itself. Plain annotations only (no
    # `= value`); QWidget-provided names are ``Any``.
    _drag_enabled: bool
    _drag_exclusions: set[int]
    _drag_start_global: QPoint | None
    _balance_spacer: QWidget
    _left_balance: QWidget
    _controls: QWidget
    _title_label: Any
    _target_window: Any
    childAt: Any
    parentWidget: Any
    _toggle_maximize: Any

    def set_drag_enabled(self, enabled: bool) -> None:
        self._drag_enabled = enabled

    def register_drag_exclusion(self, widget: QWidget) -> None:
        self._drag_exclusions.add(id(widget))

    def _is_draggable_at(self, pos: QPoint) -> bool:
        if not self._drag_enabled or self._target_window is None:
            return False
        child = self.childAt(pos)
        if child is None:
            return True
        widget: QWidget | None = child
        while widget is not None and widget is not self:
            if id(widget) in self._drag_exclusions:
                return False
            if isinstance(widget, Button) and widget.isEnabled() and widget.isVisible():
                return False
            if (
                widget is not self._balance_spacer
                and widget is not self._left_balance
                and not widget.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
                and widget.isEnabled()
                and widget.isVisible()
                and widget.parentWidget() is not self._controls
                and widget is not self._title_label
            ):
                if widget.objectName() != "TitleBarZoneHost":
                    return False
            widget = widget.parentWidget()
        return True

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._is_draggable_at(event.position().toPoint())
        ):
            self._drag_start_global = event.globalPosition().toPoint()
            # Title-bar drag must not become a navigation click-anchor:
            # NavigationManager's MouseButtonPress filter already stamped
            # last_click_pos / realign_pending on the QApplication level
            # before this widget handler runs.  Clear it so the next arrow
            # does NOT realign to the drag surface (which would land on the
            # bar's first button and show the ring after a pure window move,
            # especially noticeable after Ctrl+drag).
            try:
                from sli_ui_toolkit.ui.managers.navigation_manager import (
                    NavigationManager,
                )

                mgr = NavigationManager.get_instance()
                mgr._realign.realign_pending = False
                mgr._realign.last_click_pos = None
            except Exception:
                pass
        else:
            self._drag_start_global = None
        QWidget.mousePressEvent(self, event)  # type: ignore[arg-type]

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        w = self._target_window
        if (
            self._drag_start_global is not None
            and event.buttons() & Qt.MouseButton.LeftButton
            and w is not None
        ):
            handle = w.windowHandle()
            if handle is not None:
                try:
                    handle.startSystemMove()
                    self._drag_start_global = None
                    return
                except Exception:
                    pass

            drag_start = self._drag_start_global
            assert drag_start is not None
            current = event.globalPosition().toPoint()
            delta = current - drag_start
            self._drag_start_global = current
            if w.isMaximized():
                w.showNormal()
            w.move(w.pos() + delta)
        QWidget.mouseMoveEvent(self, event)  # type: ignore[arg-type]

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_start_global = None
        QWidget.mouseReleaseEvent(self, event)  # type: ignore[arg-type]

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._target_window is not None
            and self._is_draggable_at(event.position().toPoint())
        ):
            self._toggle_maximize(self._target_window)
        QWidget.mouseDoubleClickEvent(self, event)  # type: ignore[arg-type]
