"""PendingSettle runs a coalesced reflow at the paint boundary (mechanism C).

``PendingSettle`` exists for the "first presented frame is not the settled
frame" class whose cause is a DEFERRED reflow: the consumer coalesces several
change notifications into one pass, but the pass is armed on a 0-timer, so the
frame that is already being composed paints the *previous* state once.

These tests drive a real widget whose ``paintEvent`` records the value it
painted. ``repaint()`` is used for the paint-boundary cases on purpose: it
paints synchronously, without an event-loop turn, so the 0-timer fallback
cannot run first and hide the stale frame the falsification test observes.
"""

from __future__ import annotations

import shiboken6
from PySide6.QtGui import QPaintEvent
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.ui.pending_settle import PendingSettle, settle_on_paint


class _PaintRecorder(QWidget):
    """Paints (and records) the value its ``value_of`` callable returns."""

    def __init__(self, value_of) -> None:
        super().__init__()
        self._value_of = value_of
        self.painted: list[str] = []

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        self.painted.append(self._value_of())


def _shown(qapp, widget: _PaintRecorder) -> _PaintRecorder:
    widget.resize(48, 24)
    widget.show()
    qapp.processEvents()
    widget.painted.clear()
    return widget


def test_settle_on_paint_first_paint_sees_the_new_value(qapp):
    state = {"value": "old"}
    widget = _shown(qapp, _PaintRecorder(lambda: state["value"]))
    pending = PendingSettle()
    settle_on_paint(widget, pending)

    pending.schedule(widget, lambda: state.update(value="new"))
    widget.repaint()

    assert widget.painted == ["new"]


def test_without_settle_on_paint_the_first_paint_is_stale(qapp):
    """Falsification: the same harness without the filter paints one frame late."""
    state = {"value": "old"}
    widget = _shown(qapp, _PaintRecorder(lambda: state["value"]))
    pending = PendingSettle()

    pending.schedule(widget, lambda: state.update(value="new"))
    widget.repaint()

    assert widget.painted == ["old"]
    assert state["value"] == "old", "the reflow must not run at schedule() time"

    # The 0-timer fallback still runs it — on a later turn, i.e. a frame late.
    qapp.processEvents()
    assert state["value"] == "new"


def test_repeated_schedules_run_the_reflow_once_with_the_last_fn(qapp):
    calls: list[int] = []
    widget = _PaintRecorder(lambda: "")
    pending = PendingSettle()

    for index in range(5):
        pending.schedule(widget, lambda index=index: calls.append(index))
    assert calls == []

    qapp.processEvents()

    assert calls == [4], "one coalesced reflow, last fn wins"
    assert not pending.is_pending()


def test_settle_now_runs_immediately_and_a_second_call_is_a_no_op(qapp):
    calls: list[int] = []
    widget = _PaintRecorder(lambda: "")
    pending = PendingSettle()

    pending.schedule(widget, lambda: calls.append(1))
    assert pending.is_pending()

    pending.settle_now()
    assert calls == [1]
    assert not pending.is_pending()

    pending.settle_now()
    assert calls == [1]


def test_destroyed_widget_never_runs_the_reflow(qapp):
    calls: list[int] = []
    widget = _PaintRecorder(lambda: "")
    pending = PendingSettle()
    settle_on_paint(widget, pending)

    pending.schedule(widget, lambda: calls.append(1))
    shiboken6.delete(widget)
    assert not shiboken6.isValid(widget)

    # The armed fallback fires with the widget already gone: it must drop the
    # reflow instead of running it against a dead receiver.
    qapp.processEvents()
    qapp.processEvents()

    assert calls == []
    assert not pending.is_pending()
