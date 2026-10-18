"""UiMetrics — one coalesced change channel for font + scale.

``UiFont.font_changed`` and ``UiScale.scale_changed`` are two independent
global signals; ``connect_ui_metrics`` wires a slot to the unified
``UiMetrics.changed`` once, and a same-turn font+scale pair must reach the
slot exactly once (after both have settled).
"""

from __future__ import annotations

import shiboken6
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.ui.managers.ui_font import UiFont
from sli_ui_toolkit.ui.managers.ui_metrics import UiMetrics, connect_ui_metrics
from sli_ui_toolkit.ui.managers.ui_scale import UiScale


def test_singleton() -> None:
    assert UiMetrics.get_instance() is UiMetrics.get_instance()


def test_slot_fires_on_font_change(qapp):
    widget = QWidget()
    calls: list[int] = []
    connect_ui_metrics(widget, lambda: calls.append(1))
    UiFont.get_instance().sync_from_application()
    qapp.processEvents()
    assert calls == [1], "slot did not fire on a UI font change"


def test_slot_fires_on_scale_change(qapp):
    scale = UiScale.get_instance()
    previous = scale.factor()
    try:
        scale.set_factor(1.0)
        widget = QWidget()
        calls: list[int] = []
        connect_ui_metrics(widget, lambda: calls.append(1))
        scale.set_factor(1.5)
        qapp.processEvents()
        assert calls == [1], "slot did not fire on a UI scale change"
    finally:
        scale.set_factor(previous)
        qapp.processEvents()


def test_slot_fires_once_when_font_and_scale_change_together(qapp):
    """The host applies scale + font in one turn: exactly one slot call."""
    scale = UiScale.get_instance()
    previous = scale.factor()
    try:
        scale.set_factor(1.0)
        widget = QWidget()
        calls: list[int] = []
        connect_ui_metrics(widget, lambda: calls.append(1))
        scale.set_factor(1.5)
        UiFont.get_instance().sync_from_application()
        qapp.processEvents()
        assert calls == [1], f"coalesced slot ran {len(calls)} times, want 1"
    finally:
        scale.set_factor(previous)
        qapp.processEvents()


def test_connect_is_idempotent_per_widget_and_slot(qapp):
    widget = QWidget()
    calls: list[int] = []

    def slot() -> None:
        calls.append(1)

    first = connect_ui_metrics(widget, slot)
    second = connect_ui_metrics(widget, slot)
    assert first == second
    assert len(first) == 1
    UiFont.get_instance().sync_from_application()
    qapp.processEvents()
    assert calls == [1], "re-connecting the same slot stacked a second call"


def test_teardown_disconnects_returned_connections(qapp):
    widget = QWidget()
    calls: list[int] = []
    connections = connect_ui_metrics(widget, lambda: calls.append(1))
    UiFont.get_instance().sync_from_application()
    qapp.processEvents()
    assert calls == [1]
    for signal, connection in connections:
        signal.disconnect(connection)
    UiFont.get_instance().sync_from_application()
    qapp.processEvents()
    assert calls == [1], "slot ran after its connections were dropped"


def test_destroyed_widget_stops_receiving_changes(qapp):
    widget = QWidget()
    calls: list[int] = []
    connect_ui_metrics(widget, lambda: calls.append(1))
    UiFont.get_instance().sync_from_application()
    qapp.processEvents()
    assert calls == [1]
    shiboken6.delete(widget)
    UiFont.get_instance().sync_from_application()
    qapp.processEvents()
    assert calls == [1], "a destroyed widget's slot still ran"
