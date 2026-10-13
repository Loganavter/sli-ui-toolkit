from __future__ import annotations

from typing import Any, cast
from weakref import WeakKeyDictionary, ref

import shiboken6
from PySide6.QtCore import QCoreApplication, QEvent, QObject, Qt, QTimer
from PySide6.QtWidgets import QApplication, QWidget


def _is_alive(widget: QWidget | None) -> bool:
    """True while the shiboken wrapper still owns a live C++ QWidget."""
    if widget is None:
        return False
    try:
        return bool(shiboken6.isValid(widget))  # type: ignore[attr-defined]
    except Exception:
        return False


class _EditableTextKeyFilter(QObject):
    """Per-widget: Return/Enter clears focus; preset Tab-adopt.

    Installed on the widget itself, not the app — Qt already only delivers
    this one widget's own key events here, so there is nothing to share.
    Applies to any widget opted into ``apply_editable_text_behavior``.

    The Tab branch must live here, not only in the widget's
    ``keyPressEvent``: ``QWidget.event()`` diverts Tab to focus travel
    before ``keyPressEvent`` ever runs (in-flyout fields lose Tab to the
    next button), while an event filter runs first and can still accept
    it. Gated on the submit preset + empty field, so plain fields keep
    native Tab travel.
    """

    def __init__(self, widget: QWidget) -> None:
        super().__init__(widget)
        self._widget = widget

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.KeyPress and watched is self._widget:
            key = getattr(event, "key", lambda: None)()
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                QTimer.singleShot(0, watched.clearFocus)  # type: ignore[attr-defined]
            elif key == Qt.Key.Key_Tab and self._adopt_tab(event):
                return True
        return False

    def _adopt_tab(self, event: QEvent) -> bool:
        """Submit-preset Tab-adopt: placeholder becomes starting text."""
        widget = self._widget
        try:
            preset = getattr(widget, "isSubmitPreset", None)
            if not callable(preset) or not preset():
                return False
            edit = cast(Any, widget)
            if edit.isReadOnly():
                return False
            if (edit.text() or "").strip():
                return False
            placeholder = edit.placeholderText() or ""
            if not placeholder:
                return False
            modifiers_fn = getattr(event, "modifiers", None)
            modifiers = (
                modifiers_fn()
                if callable(modifiers_fn)
                else Qt.KeyboardModifier.NoModifier
            )
            if modifiers & (
                Qt.KeyboardModifier.ControlModifier
                | Qt.KeyboardModifier.AltModifier
                | Qt.KeyboardModifier.MetaModifier
            ):
                return False
            edit.setText(placeholder)
            try:
                edit.deselect()
            except Exception:
                pass
            try:
                edit.setCursorPosition(len(placeholder))
            except Exception:
                pass
            return True
        except Exception:
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
