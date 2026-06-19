from __future__ import annotations

from PySide6.QtCore import QObject, QEvent, Qt, QTimer
from PySide6.QtWidgets import QApplication, QLineEdit, QWidget

class _EditableTextEventFilter(QObject):
    def __init__(self, widget: QWidget):
        super().__init__(widget)
        self._widget = widget

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.KeyPress and watched is self._widget:
            key = getattr(event, "key", lambda: None)()
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and isinstance(watched, QLineEdit):
                QTimer.singleShot(0, watched.clearFocus)
                return False

        if event.type() == QEvent.Type.MouseButtonPress and isinstance(watched, QWidget):
            widget = self._widget
            if (
                widget.hasFocus()
                and watched is not widget
                and not widget.isAncestorOf(watched)
            ):
                QTimer.singleShot(0, widget.clearFocus)

        return super().eventFilter(watched, event)

def apply_editable_text_behavior(widget: QWidget) -> QWidget:
    if getattr(widget, "_editable_text_behavior_installed", False):
        return widget

    behavior = _EditableTextEventFilter(widget)
    widget.installEventFilter(behavior)
    app = QApplication.instance()
    if app is not None:
        app.installEventFilter(behavior)
        widget.destroyed.connect(lambda: app.removeEventFilter(behavior))
    widget._editable_text_behavior = behavior
    widget._editable_text_behavior_installed = True
    return widget
