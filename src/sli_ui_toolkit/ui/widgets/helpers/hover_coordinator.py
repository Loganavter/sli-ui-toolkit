from __future__ import annotations

from weakref import WeakSet, ref

from PyQt6.QtCore import QEvent, QObject, QPoint, QPointF, QRect, Qt
from PyQt6.QtGui import QCursor, QMouseEvent
from PyQt6.QtWidgets import QApplication, QWidget


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
        self._widgets: WeakSet[QWidget] = WeakSet()
        self._installed_app: QApplication | None = None

    def register(self, widget: QWidget) -> None:
        self._install()
        self._widgets.add(widget)
        widget.setMouseTracking(True)
        widget.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        widget_ref = ref(widget)
        widget.destroyed.connect(lambda *_: self._discard_ref(widget_ref))

    def unregister(self, widget: QWidget) -> None:
        self._widgets.discard(widget)

    def _discard_ref(self, widget_ref) -> None:
        widget = widget_ref()
        if widget is not None:
            self._widgets.discard(widget)

    def reconcile(
        self,
        global_pos: QPoint | None = None,
        source_window: QWidget | None = None,
    ) -> None:
        pos = global_pos or QCursor.pos()
        for widget in list(self._widgets):
            if source_window is not None and widget.window() is not source_window:
                self._set_hover(widget, False)
                continue
            self._reconcile_widget(widget, pos)

    def clear_all(self) -> None:
        for widget in list(self._widgets):
            self._set_hover(widget, False)

    def clear_descendants(self, root: QWidget) -> None:
        for widget in list(self._widgets):
            if widget is root or root.isAncestorOf(widget):
                self._set_hover(widget, False)

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

    def _reconcile_widget(self, widget: QWidget, global_pos: QPoint) -> None:
        if not self._is_reconcilable(widget):
            self._set_hover(widget, False)
            return

        local = widget.mapFromGlobal(global_pos)
        active = QRect(QPoint(0, 0), widget.size()).contains(local)
        if active:
            top_widget = QApplication.widgetAt(global_pos)
            if top_widget is None or (
                top_widget is not widget and not widget.isAncestorOf(top_widget)
            ):
                active = False
        if active and hasattr(widget, "hoverHitTest"):
            active = bool(widget.hoverHitTest(QPointF(local)))  # type: ignore[attr-defined]
        self._set_hover(widget, active)

    @staticmethod
    def _is_reconcilable(widget: QWidget) -> bool:
        return bool(widget.isVisible() and widget.isEnabled())

    @staticmethod
    def _set_hover(widget: QWidget, active: bool) -> None:
        if hasattr(widget, "setHoverActive"):
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
