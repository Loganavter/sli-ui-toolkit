"""A closed tooltip ends the session; the next hover pays the full delay again.

Rule (product owner): instant showing is a hand-over aid only — while one
tooltip is still up and the cursor travels to a neighbouring target (Qt
delivers ``Leave(old)`` then ``Enter(new)`` in one mouse-move dispatch).
A completed close ends the session, so the next tooltip pays the configured
show delay (``DEFAULT_SHOW_DELAY_MS`` / ``set_show_delay_ms``) again.

Regression: ``hide_tooltip`` used to *extend* the session by
``SESSION_IDLE_MS`` (1500 ms), so after the first tooltip every later tooltip in
that window opened instantly, even after the bubble had closed.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.ui.widgets.atomic.tooltips import (
    PathTooltip,
    _ApplicationTooltipInterceptor,
)


def _fresh() -> PathTooltip:
    t = PathTooltip.get_instance()
    t.hide_tooltip()
    t._session_until_ms = 0.0
    t.set_show_delay_ms(500)
    return t


def test_show_tooltip_is_delayed_without_a_session(qapp, monkeypatch) -> None:
    t = _fresh()
    monkeypatch.setattr(t, "_now_ms", lambda: 1000.0)
    assert t.session_active() is False
    t.show_tooltip(QPoint(0, 0), "A")
    assert t._show_timer.isActive()  # a fresh hover pays the delay
    t.hide_tooltip()


def test_show_tooltip_is_instant_inside_a_session(qapp, monkeypatch) -> None:
    t = _fresh()
    monkeypatch.setattr(t, "_now_ms", lambda: 1000.0)
    t._session_until_ms = 2000.0  # a tooltip is still up
    assert t.session_active() is True
    t.show_tooltip(QPoint(0, 0), "B")
    assert not t._show_timer.isActive()  # no re-delay
    assert t._pending_delay_ms == 0


def test_close_ends_the_session_and_next_tooltip_repays_the_delay(
    qapp, monkeypatch
) -> None:
    """The reported bug: a closed tooltip must not make the next one instant."""
    t = _fresh()
    monkeypatch.setattr(t, "_now_ms", lambda: 1000.0)

    t.show_tooltip(QPoint(0, 0), "A")  # default delay -> deferred, not shown
    assert t._pending_delay_ms == 500
    assert t._show_timer.isActive()

    t.hide_tooltip()  # the close
    assert t.session_active() is False

    t.show_tooltip(QPoint(0, 0), "B")  # default delay again
    assert t._pending_delay_ms == 500  # NOT instant
    assert t._show_timer.isActive()
    t.hide_tooltip()


def test_close_after_a_shown_tooltip_ends_the_session(qapp, monkeypatch) -> None:
    """Even a close of a *shown* tooltip (session armed) ends the session."""
    t = _fresh()
    monkeypatch.setattr(t, "_now_ms", lambda: 1000.0)
    t._session_until_ms = 1000.0 + PathTooltip.SESSION_IDLE_MS  # tooltip is up
    assert t.session_active() is True

    t.hide_tooltip()

    assert t.session_active() is False
    t.show_tooltip(QPoint(0, 0), "B")
    assert t._pending_delay_ms == 500
    assert t._show_timer.isActive()
    t.hide_tooltip()


def test_session_expires_after_the_idle_window(qapp, monkeypatch) -> None:
    t = _fresh()
    monkeypatch.setattr(t, "_now_ms", lambda: 5000.0)
    t._session_until_ms = 4000.0
    assert t.session_active() is False
    t.show_tooltip(QPoint(0, 0), "C")
    assert t._show_timer.isActive()  # the delay is paid again
    t.hide_tooltip()


def test_enter_does_not_swallow_and_is_instant_in_a_session(qapp) -> None:
    interceptor = _ApplicationTooltipInterceptor()
    widget = QWidget()
    widget.setToolTip("hello")
    t = PathTooltip.get_instance()
    t._session_until_ms = t._now_ms() + PathTooltip.SESSION_IDLE_MS
    # Enter must never be consumed (it only refreshes the bubble).
    assert interceptor.eventFilter(widget, QEvent(QEvent.Type.Enter)) is False
    t.hide_tooltip()
    widget.deleteLater()


def test_handover_leave_then_enter_in_one_dispatch_is_instant(qapp) -> None:
    """The hand-over survives the fix — with the real Qt event order.

    Qt's ``dispatchEnterLeave`` sends ``Leave(old)`` *before* ``Enter(new)`` in
    the same mouse-move dispatch, so the ``Leave`` only schedules the close; the
    ``Enter`` in the same dispatch still finds the tooltip up and shows
    instantly.
    """
    t = _fresh()
    t._session_until_ms = t._now_ms() + PathTooltip.SESSION_IDLE_MS  # A is up
    interceptor = _ApplicationTooltipInterceptor()
    a = QWidget()
    a.setToolTip("A")
    b = QWidget()
    b.setToolTip("B")

    interceptor.eventFilter(a, QEvent(QEvent.Type.Leave))
    assert t.session_active() is True  # the close is deferred, not completed

    interceptor.eventFilter(b, QEvent(QEvent.Type.Enter))
    assert not t._show_timer.isActive()  # hand-over is instant
    assert t._pending_delay_ms == 0

    # With no neighbour to hand over to, the same Leave completes the close.
    t.hide_tooltip()
    assert t.session_active() is False
    a.deleteLater()
    b.deleteLater()


def test_leave_then_show_repays_the_delay_once_the_close_completes(qapp) -> None:
    """A Leave with no following Enter completes the close on the next tick."""
    t = _fresh()
    t._session_until_ms = t._now_ms() + PathTooltip.SESSION_IDLE_MS  # tooltip up
    interceptor = _ApplicationTooltipInterceptor()
    a = QWidget()
    a.setToolTip("A")

    interceptor.eventFilter(a, QEvent(QEvent.Type.Leave))
    qapp.processEvents()  # let the deferred close run

    assert t.session_active() is False
    t.show_tooltip(QPoint(0, 0), "B")
    assert t._pending_delay_ms == 500
    assert t._show_timer.isActive()
    t.hide_tooltip()
    a.deleteLater()
