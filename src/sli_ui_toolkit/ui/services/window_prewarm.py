from __future__ import annotations

from typing import Protocol, runtime_checkable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QWidget

@runtime_checkable
class OffscreenPrewarmAware(Protocol):
    def begin_offscreen_prewarm(self) -> None: ...
    def end_offscreen_prewarm(self) -> None: ...

def prewarm_widget_window(
    app: QApplication,
    widget: QWidget,
    *,
    name: str | None = None,
) -> None:
    aware = widget if isinstance(widget, OffscreenPrewarmAware) else None
    if aware is not None:
        aware.begin_offscreen_prewarm()

    # A prewarm must never change the visible state it found: show()/hide()
    # below exists only to realize the native window offscreen. Without the
    # guard, prewarming an already-visible window would hide it out from
    # under the host (observed as chrome flicker on late-attached dialogs).
    was_visible = False
    try:
        was_visible = bool(widget.isVisible())
    except RuntimeError:
        return
    widget.ensurePolished()
    widget.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    try:
        widget.show()
        widget.repaint()
        if not was_visible:
            widget.hide()
    finally:
        widget.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, False)
        if aware is not None:
            aware.end_offscreen_prewarm()

def prewarm_widget_window_once(
    app: QApplication,
    widget: QWidget,
    *,
    name: str | None = None,
) -> bool:
    if bool(widget.property("_offscreen_prewarmed")):
        return False
    prewarm_widget_window(app, widget, name=name)
    try:
        widget.setProperty("_offscreen_prewarmed", True)
    except RuntimeError:
        return True
    return True


def reset_prewarm_once(widget: QWidget) -> None:
    """Clear the once-flag so the next ``prewarm_widget_window_once`` re-runs.

    The flag is sticky for the widget's lifetime (reconfigure paths such as
    theme/scale changes that need a fresh native-window realization call
    this); the property itself dies with the widget, so no destroyed-signal
    bookkeeping is needed.
    """
    try:
        widget.setProperty("_offscreen_prewarmed", False)
    except RuntimeError:
        pass

