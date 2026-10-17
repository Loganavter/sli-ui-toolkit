"""Adjacent tooltips show instantly; a fresh hover re-pays the wake-up delay.

Regression: moving the cursor a couple of pixels from one tooltip target to its
neighbour hid the bubble (``Leave``) and the next ``ToolTip`` event re-paid the
whole delay (~Qt hover wake-up + ``PathTooltip`` 500 ms). A short "session"
keeps the next tooltip instant while the cursor travels.
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
    t._session_until_ms = 2000.0  # a tooltip was just shown
    assert t.session_active() is True
    t.show_tooltip(QPoint(0, 0), "B")
    assert not t._show_timer.isActive()  # no re-delay


def test_hide_keeps_the_session_alive_for_travel(qapp, monkeypatch) -> None:
    t = _fresh()
    monkeypatch.setattr(t, "_now_ms", lambda: 1000.0)
    t.show_tooltip(QPoint(0, 0), "A")
    t._session_until_ms = 2000.0
    t.hide_tooltip()
    assert t._session_until_ms >= 1000.0 + PathTooltip.SESSION_IDLE_MS
    assert t.session_active() is True


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
