"""One change channel for global UI metrics (typeface + scale).

``UiFont.font_changed`` and ``UiScale.scale_changed`` are two independent
process-wide signals, so every widget that derives geometry from either has
had to remember to subscribe to **both**. That asymmetry is the recurring bug
class this module closes (``plan-theme-refresh-systemic`` for colours, this
for metrics): the tab strip's derived bar height was refreshed on a scale
change but not when the UI font landed a beat after construction.

:class:`UiMetrics` folds the two sources into a single
:attr:`UiMetrics.changed` signal; :func:`connect_ui_metrics` wires a widget's
slot to it once, idempotently, and returns the connections for teardown.
``UiFont._emit_changed()`` and ``UiScale.set_factor()`` notify the channel on
a real change (existing single-signal connections keep working — this is an
addition, not a replacement).

**Coalescing (the chosen strategy).** The host applies a scale change and a
font change together (e.g. Improve-ImgSLI's ``FontManager.apply_from_state``),
and a slot must run **once** for that one logical change, *after* both sources
have settled — running on the first signal alone would read the new scale with
the old font (or vice versa) and cache the wrong geometry. The two source
notifications are therefore coalesced through a zero-timer: the first
notification of an event-loop turn schedules exactly one
:attr:`changed` emission on the next tick, and later notifications in the same
turn are absorbed by it. Slots run once per logical change with the final font
*and* scale both visible.
"""

from __future__ import annotations

import weakref
from typing import Any, Callable, Optional

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QWidget


class UiMetrics(QObject):
    """Combined font+scale change channel (see module docstring)."""

    changed = Signal()

    _instance: Optional["UiMetrics"] = None

    def __init__(self) -> None:
        super().__init__()
        self._pending = False
        # Per-widget subscriptions, keyed weakly by widget; the inner dict is
        # keyed by the exact slot object so connect_ui_metrics is idempotent
        # per (widget, slot). Entries are dropped on widget.destroyed.
        self._subscriptions: weakref.WeakKeyDictionary[
            QWidget, dict[Any, list[tuple[Any, Any]]]
        ] = weakref.WeakKeyDictionary()

    @classmethod
    def get_instance(cls) -> "UiMetrics":
        if cls._instance is None:
            cls._instance = UiMetrics()
        return cls._instance

    def _on_source_changed(self) -> None:
        """Source managers call this on a real font/scale change.

        Coalesces a same-turn font+scale pair into one :attr:`changed`.
        """
        if self._pending:
            return
        self._pending = True
        QTimer.singleShot(0, self._flush)

    def _flush(self) -> None:
        self._pending = False
        self.changed.emit()


def connect_ui_metrics(widget: QWidget, slot: Callable[[], None]) -> list:
    """Wire ``slot`` to :attr:`UiMetrics.changed` once (see module docstring).

    Idempotent per ``(widget, slot)``: re-connecting the same bound method
    returns the existing connection instead of stacking a second one, so a
    widget that re-runs its constructor wiring still refreshes exactly once.
    Returns ``[(signal, connection), ...]`` for teardown; the connections are
    also dropped automatically when ``widget`` is destroyed, so a dead widget's
    slot can never run again.
    """
    metrics = UiMetrics.get_instance()
    per_widget = metrics._subscriptions.get(widget)
    if per_widget is None:
        per_widget = {}
        metrics._subscriptions[widget] = per_widget

        def _cleanup(_obj: Any = None) -> None:
            # The widget died: drop every connection so its slots never run
            # again (and the singleton stops keeping the widget alive). At
            # shutdown the connection may already be gone (sender destroyed
            # first) and shiboken emits a RuntimeWarning instead of raising —
            # silence the harmless noise, as UiFont.apply does.
            import warnings

            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                for connections in per_widget.values():
                    for signal, connection in connections:
                        try:
                            signal.disconnect(connection)
                        except (RuntimeError, TypeError):
                            pass
            metrics._subscriptions.pop(widget, None)

        widget.destroyed.connect(_cleanup)

    existing = per_widget.get(slot)
    if existing is not None:
        return list(existing)
    connection = metrics.changed.connect(slot)
    connections: list[tuple[Any, Any]] = [(metrics.changed, connection)]
    per_widget[slot] = connections
    return list(connections)


__all__ = ["UiMetrics", "connect_ui_metrics"]
