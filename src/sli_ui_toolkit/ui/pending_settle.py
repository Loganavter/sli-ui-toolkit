"""Paint-boundary settle for a coalesced reflow (the deferred-reflow transient).

Three mechanisms produce the recurring "the first presented frame is not the
settled frame" class:

* **A** — a value derived from font/scale/theme before those sources settled:
  owned by ``UiMetrics`` /
  :func:`~sli_ui_toolkit.ui.managers.ui_metrics.connect_ui_metrics`.
* **B** — a self-derived size versus a POSTED layout re-run: owned by
  :func:`~sli_ui_toolkit.ui.layout_settle.settle_layout`.
* **C** — a DEFERRED reflow (a 0-timer that coalesces several change
  notifications into one pass). It has no owner, and "coalesce into the next
  event-loop turn" is exactly what paints the *previous* state once. This
  module owns mechanism C.

Qt delivers a widget's ``Paint`` event **after** the layout pass and after the
event that invalidated the geometry, so the paint boundary is the last safe
place to run a coalesced reflow: the frame being composed is the one the user
sees. :class:`PendingSettle` is the coalescing slot — the consumer schedules the
reflow instead of arming its own timer — and :func:`settle_on_paint` runs it
from the widget's ``Paint`` event, before the widget paints.

Companion: :func:`~sli_ui_toolkit.ui.layout_settle.settle_layout` handles
mechanism B by re-running the layout synchronously at the end of the mutation.
This module handles the case where the reflow itself must be coalesced (several
notifications per turn) and therefore cannot run in the setter that caused it;
do not duplicate ``settle_layout`` here — call it from the reflow if the reflow
also changes a self-derived size.
"""

from __future__ import annotations

import weakref
from typing import Callable

import shiboken6
from PySide6.QtCore import QEvent, QObject, QTimer
from PySide6.QtWidgets import QWidget


class PendingSettle:
    """One coalesced reflow, run at the widget's paint boundary.

    Only one reflow is held at a time. Repeated :meth:`schedule` calls in one
    event-loop turn replace each other (the last ``fn`` wins), so N change
    notifications run the reflow exactly once with the final state — the same
    coalescing a zero-timer gives, but with the run moved to the paint, where
    the result is guaranteed to be visible in the frame being composed.

    The 0-timer in :meth:`schedule` is only a fallback for a widget that is not
    being painted (hidden, or no paint is queued): whoever gets there first,
    :meth:`settle_now` clears the pending entry, so the other path is a no-op
    and the reflow still runs at most once per schedule.

    The pending widget is held weakly and its C++ lifetime is checked before
    running, so a widget destroyed with a reflow still queued drops the reflow
    instead of running it against a dead receiver.
    """

    def __init__(self) -> None:
        self._widget: weakref.ReferenceType[QWidget] | None = None
        self._fn: Callable[[], None] | None = None
        self._fallback_armed = False

    # -- host API ---------------------------------------------------------

    def schedule(self, widget: QWidget, fn: Callable[[], None]) -> None:
        """Queue *fn* to run before *widget*'s next paint; coalesces repeats.

        A previous pending reflow is replaced (last ``fn`` wins) — idempotent
        while pending. Requests the repaint that will carry the settled frame
        (``widget.update()``) and arms a single 0-timer as the fallback for a
        widget that never paints; neither the repaint nor the timer is
        duplicated by a repeated call.
        """
        self._widget = weakref.ref(widget)
        self._fn = fn
        if not self._fallback_armed:
            self._fallback_armed = True
            QTimer.singleShot(0, self._fallback)
        widget.update()

    def settle_now(self) -> None:
        """Run the pending reflow synchronously, if any, and clear it.

        At most one reflow runs per call: the pending entry is cleared *before*
        ``fn()`` is invoked, so a reflow that schedules another one (a state
        change inside the reflow) leaves the new entry pending for the next
        paint instead of recursing, and a nested :meth:`settle_now` (from the
        reflow, or from another watched widget's paint) is a no-op. A call with
        nothing pending — the second of the paint/timer pair — does nothing.
        """
        fn = self._fn
        if fn is None:
            return
        widget = self._widget() if self._widget is not None else None
        # Clear first: re-entrancy safety, and the reflow must not be retried
        # against a receiver that is going away.
        self._fn = None
        self._widget = None
        if widget is None or not _is_alive(widget):
            return
        fn()

    def is_pending(self) -> bool:
        """True while a reflow is queued (scheduled and not yet run)."""
        return self._fn is not None

    # -- fallback timer ---------------------------------------------------

    def _fallback(self) -> None:
        self._fallback_armed = False
        self.settle_now()


class _PaintSettleFilter(QObject):
    """Event filter that settles *pending* before the watched widget paints."""

    def __init__(self, widget: QWidget, pending: PendingSettle) -> None:
        # Parented to the widget: the filter is owned by it and Qt drops the
        # installed filter when the widget is destroyed, so it outlives
        # neither the widget nor holds a dangling reference to it.
        super().__init__(widget)
        self._pending = pending

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Paint:
            self._pending.settle_now()
        return False


def settle_on_paint(widget: QWidget, pending: PendingSettle) -> None:
    """Run *pending*'s reflow on *widget*'s ``Paint`` event, before painting.

    The filter returns ``False``, so painting continues with the reflow's
    result already applied — the first frame a widget presents is the settled
    one. The filter object is parented to *widget*, which ties its lifetime to
    the widget (Qt removes event filters of a destroyed receiver) and keeps a
    Python reference on the widget so it is not collected while installed;
    *widget* itself is never kept alive.
    """
    existing = getattr(widget, "_pending_settle_filter", None)
    if isinstance(existing, _PaintSettleFilter) and existing._pending is pending:
        return
    event_filter = _PaintSettleFilter(widget, pending)
    widget.installEventFilter(event_filter)
    # Keep the Python wrapper reachable: the C++ parent owns it, but the
    # attribute makes the install idempotent and readable in a debugger.
    setattr(widget, "_pending_settle_filter", event_filter)


def _is_alive(widget: QWidget) -> bool:
    """False for a C++-deleted widget (its wrapper outlives the object)."""
    try:
        return bool(shiboken6.isValid(widget))  # type: ignore[attr-defined]
    except Exception:
        return False


__all__ = ["PendingSettle", "settle_on_paint"]
