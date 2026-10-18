"""UiMetrics — one coalesced change channel for font + scale (the appearance bus).

``UiFont.font_changed`` and ``UiScale.scale_changed`` are two independent
global signals; ``connect_ui_metrics`` wires a slot to the unified
``UiMetrics.changed`` once, and a same-turn font+scale pair must reach the
slot exactly once (after both have settled). P3: the payload carries the axes
that changed, per-subscription ``axes`` filters wake a slot only for the axes
it subscribes to, and ``begin_appearance`` / ``end_appearance`` coalesce a
batch of producer notifications into one emission with the union.
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


def test_changed_payload_carries_the_axes_that_changed(qapp):
    """P3: ``changed`` carries the frozenset of axes that changed, per source."""
    widget = QWidget()
    payloads: list[frozenset[str]] = []
    connect_ui_metrics(widget, lambda axes: payloads.append(axes))

    UiFont.get_instance().sync_from_application()
    qapp.processEvents()
    assert payloads == [frozenset({"font"})]

    payloads.clear()
    scale = UiScale.get_instance()
    previous = scale.factor()
    try:
        scale.set_factor(1.0)
        scale.set_factor(1.5)
        qapp.processEvents()
        assert payloads == [frozenset({"scale"})]
    finally:
        scale.set_factor(previous)
        qapp.processEvents()


def test_axes_subscriber_not_woken_by_other_axes(qapp):
    """Granularity: a ``{"scale"}`` subscriber is not called for a font
    change, and a ``{"font"}`` subscriber is not called for a scale change.
    """
    widget = QWidget()
    scale_calls: list[frozenset[str]] = []
    font_calls: list[frozenset[str]] = []
    connect_ui_metrics(
        widget, lambda axes: scale_calls.append(axes), axes=frozenset({"scale"})
    )
    connect_ui_metrics(
        widget, lambda axes: font_calls.append(axes), axes=frozenset({"font"})
    )

    UiFont.get_instance().sync_from_application()
    qapp.processEvents()
    assert scale_calls == []
    assert font_calls == [frozenset({"font"})]

    scale = UiScale.get_instance()
    previous = scale.factor()
    try:
        scale.set_factor(1.0)
        scale.set_factor(1.5)
        qapp.processEvents()
        assert scale_calls == [frozenset({"scale"})]
        assert font_calls == [frozenset({"font"})]
    finally:
        scale.set_factor(previous)
        qapp.processEvents()


def test_connect_is_idempotent_per_widget_slot_and_axes(qapp):
    widget = QWidget()
    calls: list[frozenset[str]] = []

    def slot(axes: frozenset[str]) -> None:
        calls.append(axes)

    first = connect_ui_metrics(widget, slot, axes=frozenset({"scale"}))
    second = connect_ui_metrics(widget, slot, axes=frozenset({"scale"}))
    assert first == second
    assert len(first) == 1
    scale = UiScale.get_instance()
    previous = scale.factor()
    try:
        scale.set_factor(1.0)
        scale.set_factor(1.5)
        qapp.processEvents()
        assert calls == [frozenset({"scale"})]
    finally:
        scale.set_factor(previous)
        qapp.processEvents()


def test_batch_emits_once_with_the_union(qapp):
    """``begin_appearance()`` … ``end_appearance()`` emits ONCE with the
    union of the axes seen in between.
    """
    widget = QWidget()
    calls: list[frozenset[str]] = []
    connect_ui_metrics(widget, lambda axes: calls.append(axes))
    metrics = UiMetrics.get_instance()
    metrics.begin_appearance()
    metrics.emit_appearance({"theme"})
    metrics.emit_appearance({"scale"})
    metrics.emit_appearance({"font"})
    metrics.end_appearance()
    qapp.processEvents()
    assert calls == [frozenset({"theme", "scale", "font"})]


def test_batch_merges_with_a_same_turn_direct_emit(qapp):
    """A direct emit plus a batch in the same turn still coalesce into one
    emission carrying the union.
    """
    widget = QWidget()
    calls: list[frozenset[str]] = []
    connect_ui_metrics(widget, lambda axes: calls.append(axes))
    metrics = UiMetrics.get_instance()
    metrics.emit_appearance({"font"})
    metrics.begin_appearance()
    metrics.emit_appearance({"theme"})
    metrics.end_appearance()
    qapp.processEvents()
    assert calls == [frozenset({"font", "theme"})]


def test_zero_arg_slot_gets_exactly_one_call_per_batch(qapp):
    """A zero-arg slot (the T1 call style) is adapted: one call per coalesced
    change, never handed the payload.
    """
    widget = QWidget()
    calls: list[int] = []
    connect_ui_metrics(widget, lambda: calls.append(1))
    metrics = UiMetrics.get_instance()
    metrics.begin_appearance()
    metrics.emit_appearance({"theme"})
    metrics.emit_appearance({"scale"})
    metrics.end_appearance()
    qapp.processEvents()
    assert calls == [1]
