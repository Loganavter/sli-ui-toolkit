"""One change channel for global UI metrics (typeface + scale) — the appearance bus.

``UiFont.font_changed`` and ``UiScale.scale_changed`` are two independent
process-wide signals, so every widget that derives geometry from either has
had to remember to subscribe to **both**. That asymmetry is the recurring bug
class this module closes (``plan-theme-refresh-systemic`` for colours, this
for metrics): the tab strip's derived bar height was refreshed on a scale
change but not when the UI font landed a beat after construction.

:class:`UiMetrics` folds the sources into a single :attr:`UiMetrics.changed`
signal; :func:`connect_ui_metrics` wires a widget's slot to it once,
idempotently, and returns the connections for teardown. Producers notify
the channel on a real change (existing single-signal connections keep
working — this is an addition, not a replacement).

**Appearance bus.** The channel carries *which axes changed* in its payload
— a ``frozenset`` drawn from ``{"theme", "scale", "font"}`` — so a consumer
subscribed to one axis is not woken by an unrelated change
(over-invalidation is the anti-pattern this bus exists to avoid).
``ThemeManager`` emits ``{"theme"}`` (its ``theme_changed`` stays a thin
alias — existing subscribers keep working), ``UiFont`` emits ``{"font"}``,
``UiScale`` emits ``{"scale"}``. :meth:`UiMetrics.begin_appearance` /
:meth:`UiMetrics.end_appearance` batch a group of producer notifications
into **one** emission carrying the union of the axes seen in between.

**Coalescing (the chosen strategy).** The host applies a scale change and a
font change together (e.g. Improve-ImgSLI's ``FontManager.apply_from_state``),
and a slot must run **once** for that one logical change, *after* both sources
have settled — running on the first signal alone would read the new scale with
the old font (or vice versa) and cache the wrong geometry. The source
notifications are therefore coalesced through a zero-timer: the first
notification of an event-loop turn schedules exactly one :attr:`changed`
emission on the next tick, and later notifications in the same turn are
absorbed by it. Slots run once per logical change with the final font *and*
scale both visible.
"""

from __future__ import annotations

import inspect
import weakref
from typing import Any, Callable, Iterable, Optional

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QWidget

#: Axes the appearance bus carries. Producers emit exactly one axis per
#: notification; consumers filter on the same names.
AXIS_THEME = "theme"
AXIS_SCALE = "scale"
AXIS_FONT = "font"

#: The payload domain of :attr:`UiMetrics.changed`.
APPEARANCE_AXES = frozenset({AXIS_THEME, AXIS_SCALE, AXIS_FONT})


def _normalize_axes(axes: Iterable[str]) -> frozenset[str]:
    """Coerce *axes* to a frozenset (a bare string is one axis, not five)."""
    if isinstance(axes, str):
        return frozenset({axes})
    return frozenset(axes)


def _slot_takes_payload(slot: Callable[..., Any]) -> bool:
    """True when *slot* can accept the axes payload positionally.

    Zero-arg slots (the T1 call style) are adapted by
    :func:`connect_ui_metrics` so existing call sites keep working
    unchanged.
    """
    try:
        signature = inspect.signature(slot)
    except (TypeError, ValueError):
        # Unintrospectable callable (some builtins / partials): pass the
        # payload through and let Python raise if it truly cannot take it.
        return True
    for parameter in signature.parameters.values():
        if parameter.kind is inspect.Parameter.VAR_POSITIONAL:
            return True
        if parameter.kind in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        ):
            return True
    return False


def _adapt_slot(
    slot: Callable[..., Any],
    filter_axes: frozenset[str] | None,
) -> Callable[[frozenset[str]], None]:
    """Wrap *slot* for the bus: apply the axes filter, adapt zero-arg slots.

    Every subscription goes through one of these wrappers (connected to
    ``UiMetrics.changed``) so granularity is enforced per subscription —
    Qt itself cannot filter per connection.
    """
    takes_payload = _slot_takes_payload(slot)

    def adapted(axes: frozenset[str]) -> None:
        if filter_axes is not None and not (axes & filter_axes):
            return
        if takes_payload:
            slot(axes)
        else:
            slot()

    return adapted


class UiMetrics(QObject):
    """Appearance bus: one coalesced channel for theme + scale + font.

    ``changed`` carries the axes that changed as a ``frozenset[str]``;
    :meth:`emit_appearance` is the coalesced producer entry point and
    :meth:`begin_appearance` / :meth:`end_appearance` batch a group of
    notifications into one emission with the union of the axes.
    """

    changed = Signal(object)  # payload: frozenset[str] ⊆ {"theme","scale","font"}

    _instance: Optional["UiMetrics"] = None

    def __init__(self) -> None:
        super().__init__()
        # Axes seen since the last flush; the zero-timer carries them all.
        self._pending_axes: set[str] = set()
        self._flush_scheduled = False
        # Batch state: while the depth is nonzero, producer notifications
        # accumulate in _batch_axes instead of scheduling a flush; the
        # matching end_appearance() merges them into one emission.
        self._batch_depth = 0
        self._batch_axes: set[str] = set()
        # Per-widget subscriptions, keyed weakly by widget; the inner dict
        # is keyed by (slot, axes filter) so connect_ui_metrics is
        # idempotent per (widget, slot, axes). Entries are dropped on
        # widget.destroyed.
        self._subscriptions: weakref.WeakKeyDictionary[
            QWidget,
            dict[
                tuple[Any, Optional[frozenset[str]]],
                tuple[list[tuple[Any, Any]], Callable[[frozenset[str]], None]],
            ],
        ] = weakref.WeakKeyDictionary()

    @classmethod
    def get_instance(cls) -> "UiMetrics":
        if cls._instance is None:
            cls._instance = UiMetrics()
        return cls._instance

    def emit_appearance(self, axes: Iterable[str]) -> None:
        """Producer entry point: notify the bus that *axes* changed.

        Coalesced — a same-turn group of notifications (from one logical
        change) reaches consumers as one :attr:`changed` emission. Inside a
        :meth:`begin_appearance` / :meth:`end_appearance` batch the axes
        are held for the batch's single union emission instead.
        """
        normalized = _normalize_axes(axes)
        if self._batch_depth > 0:
            self._batch_axes.update(normalized)
            return
        self._pending_axes.update(normalized)
        if self._pending_axes and not self._flush_scheduled:
            self._flush_scheduled = True
            QTimer.singleShot(0, self._flush)

    def begin_appearance(self) -> None:
        """Open an appearance batch: producer emits are held, not flushed."""
        self._batch_depth += 1

    def end_appearance(self) -> None:
        """Close the batch: flush ONCE with the union of the axes seen."""
        if self._batch_depth == 0:
            return
        self._batch_depth -= 1
        if self._batch_depth == 0 and self._batch_axes:
            self._pending_axes.update(self._batch_axes)
            self._batch_axes.clear()
            if not self._flush_scheduled:
                self._flush_scheduled = True
                QTimer.singleShot(0, self._flush)

    def _flush(self) -> None:
        self._flush_scheduled = False
        axes = frozenset(self._pending_axes)
        self._pending_axes.clear()
        if not axes:
            return
        self.changed.emit(axes)


def connect_ui_metrics(
    widget: QWidget,
    slot: Callable[..., Any],
    *,
    axes: frozenset[str] | None = None,
) -> list:
    """Wire ``slot`` to the appearance bus once (see module docstring).

    ``slot(axes)`` runs once per coalesced change with the changed axes as a
    ``frozenset[str]``; ``axes=None`` (default) subscribes to every axis, a
    ``frozenset`` like ``{"scale"}`` wakes the slot only when one of those
    axes changed. A zero-arg slot (the T1 call style) is adapted — called
    with no args — so existing call sites keep working.

    Idempotent per ``(widget, slot, axes)``: re-connecting the same bound
    method returns the existing connection instead of stacking a second one,
    so a widget that re-runs its constructor wiring still refreshes exactly
    once. Returns ``[(signal, connection), ...]`` for teardown; the
    connections are also dropped automatically when ``widget`` is destroyed,
    so a dead widget's slot can never run again.
    """
    metrics = UiMetrics.get_instance()
    filter_axes = None if axes is None else _normalize_axes(axes)
    key = (slot, filter_axes)
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
                for connections, _adapted in per_widget.values():
                    for signal, connection in connections:
                        try:
                            signal.disconnect(connection)
                        except (RuntimeError, TypeError):
                            pass
            metrics._subscriptions.pop(widget, None)

        widget.destroyed.connect(_cleanup)

    existing = per_widget.get(key)
    if existing is not None:
        connections, _adapted = existing
        return list(connections)

    adapted = _adapt_slot(slot, filter_axes)
    connection = metrics.changed.connect(adapted)
    connections = [(metrics.changed, connection)]
    per_widget[key] = (connections, adapted)
    return list(connections)


__all__ = [
    "APPEARANCE_AXES",
    "AXIS_FONT",
    "AXIS_SCALE",
    "AXIS_THEME",
    "UiMetrics",
    "connect_ui_metrics",
]
