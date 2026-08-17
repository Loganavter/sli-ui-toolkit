from __future__ import annotations

from weakref import WeakKeyDictionary, ref

import shiboken6
from PySide6.QtCore import QCoreApplication, QEvent, QObject, Qt, QTimer
from PySide6.QtWidgets import QApplication, QLineEdit, QWidget


def _is_alive(widget: QWidget | None) -> bool:
    """True while the shiboken wrapper still owns a live C++ QWidget."""
    if widget is None:
        return False
    try:
        return bool(shiboken6.isValid(widget))  # type: ignore[attr-defined]
    except Exception:
        return False


class _EditableTextKeyFilter(QObject):
    """Per-widget: Return/Enter clears focus.

    Installed on the widget itself, not the app — Qt already only delivers
    this one widget's own key events here, so there is nothing to share.
    """

    def __init__(self, widget: QWidget) -> None:
        super().__init__(widget)
        self._widget = widget

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.KeyPress and watched is self._widget:
            key = getattr(event, "key", lambda: None)()
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and isinstance(watched, QLineEdit):
                QTimer.singleShot(0, watched.clearFocus)
        return False


class _OutsideClickCoordinator(QObject):
    """Clears focus on click-outside for every registered editable-text widget.

    One shared ``QApplication`` filter for every widget that opts in, instead
    of one filter per widget instance (the previous shape: each
    ``CustomLineEdit`` installed its own app-wide filter, so N text fields
    meant N filters re-inspecting every single app event — the same
    per-instance duplication ``HoverCoordinator`` already exists to avoid
    for hover state; this mirrors that pattern).
    """

    def __init__(self) -> None:
        super().__init__()
        self._widgets: WeakKeyDictionary[QWidget, None] = WeakKeyDictionary()
        self._installed_app: QCoreApplication | None = None

    def register(self, widget: QWidget) -> None:
        self._install()
        self._widgets[widget] = None
        widget_ref = ref(widget)
        widget.destroyed.connect(lambda *_: self._discard_ref(widget_ref))

    def _discard_ref(self, widget_ref) -> None:
        widget = widget_ref()
        if widget is not None:
            self._widgets.pop(widget, None)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.MouseButtonPress and isinstance(watched, QWidget):
            for widget in list(self._widgets.keys()):
                if not _is_alive(widget):
                    self._widgets.pop(widget, None)
                    continue
                if (
                    widget.hasFocus()
                    and watched is not widget
                    and not widget.isAncestorOf(watched)
                ):
                    QTimer.singleShot(0, widget.clearFocus)
        return False

    def _install(self) -> None:
        app = QApplication.instance()
        if app is None or app is self._installed_app:
            return
        if self._installed_app is not None:
            self._installed_app.removeEventFilter(self)
        app.installEventFilter(self)
        self._installed_app = app


_OUTSIDE_CLICK = _OutsideClickCoordinator()


def apply_editable_text_behavior(widget: QWidget) -> QWidget:
    if getattr(widget, "_editable_text_behavior_installed", False):
        return widget

    key_filter = _EditableTextKeyFilter(widget)
    widget.installEventFilter(key_filter)
    _OUTSIDE_CLICK.register(widget)
    setattr(widget, "_editable_text_behavior", key_filter)
    setattr(widget, "_editable_text_behavior_installed", True)
    return widget
