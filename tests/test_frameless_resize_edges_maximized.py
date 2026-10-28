"""A window with no room left must not offer edge resizing.

Owner report 2026-10-28: on Wayland **every dialog except the main window**
still showed the resize cursor at its borders while maximized — and the edges
could be grabbed. The main window was fine, which named the layer: the CSD
resize filter gates on ``isMaximized()/isFullScreen()``, and a transient
dialog stretched to the screen by the compositor often carries neither state
(Qt keeps ``isMaximized()`` false while the geometry says maximized).

Telegram Desktop does not have this class of bug because on Linux it does not
own edge hit-testing at all (``desktop-app/lib_ui``,
``ui/platform/linux/ui_window_linux.cpp``: ``CreateSpecialWindowHelper``
returns nullptr and ``NativeWindowFrameSupported()`` is true); where it does
own it (Windows, ``ui/platform/win/ui_window_win.cpp``) the gate is exactly
``nativeResize() && !maximized`` with ``maximized = isMaximized() ||
isFullScreen()``.

So the gate learns the third signal — geometry: a window that fills the
screen's available area is maximized-like even when no flag says so.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.ui.windows.frameless.resize_filter import _maximized_like


def _available(widget):
    screen = widget.screen()
    assert screen is not None
    return screen.availableGeometry()


def test_normal_window_is_not_maximized_like(qapp):
    widget = QWidget()
    widget.resize(400, 300)
    qapp.processEvents()
    assert _maximized_like(widget) is False


def test_window_stretched_to_the_screen_is_maximized_like(qapp):
    """The Wayland dialog shape: screen-sized, ``isMaximized()`` still false."""
    widget = QWidget()
    available = _available(widget)
    widget.resize(available.width(), available.height())
    qapp.processEvents()
    assert widget.isMaximized() is False, "precondition: no state flag to rely on"
    assert _maximized_like(widget) is True, (
        "a window that fills the available area still offered edge resizing — "
        "this is the Wayland dialog report"
    )


def test_wide_but_short_window_keeps_its_bottom_edge(qapp):
    """Only BOTH axes at the available size count; a wide window is normal."""
    widget = QWidget()
    available = _available(widget)
    widget.resize(available.width(), 300)
    qapp.processEvents()
    assert _maximized_like(widget) is False


def test_the_filter_consults_the_maximized_like_gate(qapp, monkeypatch):
    """Wiring half: the filter must ASK the gate, on every window event.

    The behavioural press probe this replaced was green with AND without the
    fix (the synthetic press never reached ``_edges_for_pos``), i.e. it proved
    nothing. This one fails on the pre-fix code by construction: the old gate
    called ``target.isMaximized()`` directly and never consulted the helper.
    """
    import sli_ui_toolkit.ui.windows.frameless.resize_filter as rf_module

    widget = QWidget()
    widget.setWindowFlag(Qt.WindowType.Window)
    widget.resize(400, 300)
    widget.show()
    qapp.processEvents()

    asked: list[int] = []

    def _spy(target) -> bool:
        asked.append(1)
        return True

    # apply_frameless is what INSTALLS the filter (a bare _ResizeFilter object
    # is never consulted); the existing resize stand looks it up the same way.
    from sli_ui_toolkit.ui.windows.frameless.lifecycle import apply_frameless

    apply_frameless(widget, resizable=True)
    qapp.processEvents()
    monkeypatch.setattr(rf_module, "_maximized_like", _spy)
    resize_filter = widget.findChild(rf_module._ResizeFilter)
    assert resize_filter is not None, "apply_frameless did not install the filter"

    local = QPoint(widget.width() - 1, widget.height() - 1)
    press = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        local.toPointF(),
        widget.mapToGlobal(local).toPointF(),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.instance().sendEvent(widget, press)
    qapp.processEvents()

    assert asked, (
        "the resize filter decided without asking _maximized_like — the gate "
        "still trusts isMaximized() alone"
    )
    assert resize_filter._manual_edges == 0
