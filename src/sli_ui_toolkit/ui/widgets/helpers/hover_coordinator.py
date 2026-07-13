from __future__ import annotations

from weakref import WeakKeyDictionary, ref

from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, Qt
from PySide6.QtGui import QCursor, QMouseEvent
from PySide6.QtWidgets import QApplication, QWidget


_HOVER_EVENT_TYPES = {
    QEvent.Type.HoverEnter,
    QEvent.Type.HoverMove,
    QEvent.Type.Enter,
    QEvent.Type.MouseMove,
}

_CLEAR_EVENT_TYPES = {
    QEvent.Type.Leave,
    QEvent.Type.Hide,
    QEvent.Type.WindowDeactivate,
    QEvent.Type.EnabledChange,
}


class HoverCoordinator(QObject):
    """Keeps custom-painted hover state consistent across related widgets.

    Qt delivers enter/leave per widget. Fast pointer motion over dense child
    controls can leave a custom hover animation active when the expected child
    leave never reaches that widget. The coordinator periodically reconciles
    registered widgets against the current global cursor position and clears
    descendants when a containing widget/window leaves or hides.
    """

    def __init__(self) -> None:
        super().__init__()
        # Value is (has_hoverHitTest, has_setHoverActive), resolved once at
        # registration instead of via hasattr() on every reconcile — these
        # are fixed per widget class and reconcile() runs on every MouseMove
        # in the whole application.
        self._widgets: WeakKeyDictionary[QWidget, tuple[bool, bool]] = (
            WeakKeyDictionary()
        )
        self._installed_app: QApplication | None = None

    def register(self, widget: QWidget) -> None:
        self._install()
        self._widgets[widget] = (
            hasattr(widget, "hoverHitTest"),
            hasattr(widget, "setHoverActive"),
        )
        widget.setMouseTracking(True)
        widget.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        widget_ref = ref(widget)
        widget.destroyed.connect(lambda *_: self._discard_ref(widget_ref))

    def unregister(self, widget: QWidget) -> None:
        self._widgets.pop(widget, None)

    def _discard_ref(self, widget_ref) -> None:
        widget = widget_ref()
        if widget is not None:
            self._widgets.pop(widget, None)

    def reconcile(
        self,
        global_pos: QPoint | None = None,
        source_window: QWidget | None = None,
    ) -> None:
        pos = global_pos or QCursor.pos()
        # One widgetAt() hit-test for the whole reconcile pass, not one per
        # registered widget: with N hover-tracked buttons in a window, doing
        # a per-widget mapFromGlobal()+rect-contains()+widgetAt() on every
        # single MouseMove event (fired continuously during any drag,
        # including ones with nothing to do with these buttons) made hover
        # tracking O(N) expensive-Qt-call work per mouse pixel moved.
        top_widget = QApplication.widgetAt(pos)
        for widget, (has_hit_test, has_set_hover) in list(self._widgets.items()):
            if source_window is not None and widget.window() is not source_window:
                self._set_hover(widget, has_set_hover, False)
                continue
            self._reconcile_widget(widget, pos, top_widget, has_hit_test, has_set_hover)

    def clear_all(self) -> None:
        for widget, (_, has_set_hover) in list(self._widgets.items()):
            self._set_hover(widget, has_set_hover, False)

    def clear_descendants(self, root: QWidget) -> None:
        for widget, (_, has_set_hover) in list(self._widgets.items()):
            if widget is root or root.isAncestorOf(widget):
                self._set_hover(widget, has_set_hover, False)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        event_type = event.type()
        if event_type in _HOVER_EVENT_TYPES:
            source_window = (
                watched.window() if isinstance(watched, QWidget) else None
            )
            self.reconcile(
                self._global_pos_from_event(event),
                source_window=source_window,
            )
        elif event_type in _CLEAR_EVENT_TYPES:
            if isinstance(watched, QWidget):
                self.clear_descendants(watched)
            else:
                self.clear_all()
        elif event_type == QEvent.Type.ApplicationDeactivate:
            self.clear_all()
        return False

    def _install(self) -> None:
        app = QApplication.instance()
        if app is None or app is self._installed_app:
            return
        if self._installed_app is not None:
            self._installed_app.removeEventFilter(self)
        app.installEventFilter(self)
        self._installed_app = app

    def _reconcile_widget(
        self,
        widget: QWidget,
        global_pos: QPoint,
        top_widget: QWidget | None,
        has_hit_test: bool,
        has_set_hover: bool,
    ) -> None:
        if not self._is_reconcilable(widget):
            self._set_hover(widget, has_set_hover, False)
            return

        active = top_widget is not None and (
            top_widget is widget or widget.isAncestorOf(top_widget)
        )
        if active and has_hit_test:
            local = widget.mapFromGlobal(global_pos)
            active = bool(widget.hoverHitTest(QPointF(local)))  # type: ignore[attr-defined]
        self._set_hover(widget, has_set_hover, active)

    @staticmethod
    def _is_reconcilable(widget: QWidget) -> bool:
        return bool(widget.isVisible() and widget.isEnabled())

    @staticmethod
    def _set_hover(widget: QWidget, has_set_hover: bool, active: bool) -> None:
        if has_set_hover:
            widget.setHoverActive(active)  # type: ignore[attr-defined]

    @staticmethod
    def _global_pos_from_event(event: QEvent) -> QPoint | None:
        if isinstance(event, QMouseEvent):
            return event.globalPosition().toPoint()
        return QCursor.pos()


_COORDINATOR = HoverCoordinator()


def hover_coordinator() -> HoverCoordinator:
    return _COORDINATOR


def register_hover_widget(widget: QWidget) -> None:
    _COORDINATOR.register(widget)


def unregister_hover_widget(widget: QWidget) -> None:
    _COORDINATOR.unregister(widget)
