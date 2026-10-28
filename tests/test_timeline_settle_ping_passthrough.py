"""The settle ping survives the pass-through verdict.

Companion to ``test_timeline_window_filter_passthrough.py``: the timeline's
window/viewport filter no longer consumes ``Resize``/``WindowStateChange``,
and this file pins that the debounced fit it used to "buy" with ``True`` still
happens. The verdict and the ping are independent — ``install_filter_once``
only makes the widget a listener, ``_layout_settle.ping()`` owns the follow-up
(``interaction.layout_settle`` -> ``fit_view`` / ``viewport_geometry_changed``
on the ``"settle"`` flush).

Guarantees pinned here:

* a real window resize arms the settle gate even though the filter returns
  ``False`` (the timeline stays installed as a filter and keeps observing);
* the armed gate still runs the deferred fit when it flushes — the fit is not
  contingent on the event being reported as "handled".
"""

from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QVBoxLayout, QWidget


def _snaps(n: int):
    return [SimpleNamespace(timestamp=float(i)) for i in range(n)]


def _hosted_timeline(qapp, n: int = 60):
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget.widget import (
        TimelineWidget,
    )

    window = QWidget()
    layout = QVBoxLayout(window)
    widget = TimelineWidget(snapshots=_snaps(n))
    layout.addWidget(widget)
    window.resize(700, 420)
    window.show()
    qapp.processEvents()
    # Drain the show-time ping so the test observes only its own resize.
    widget._layout_settle.cancel()
    widget.fit_view()
    widget._commitState(widget._current_state(), source="test")
    widget._layout_settle.cancel()
    return window, widget


def test_window_resize_arms_gate_through_the_filter(qapp):
    """A real window resize reaches the filter and pings the gate."""
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
        interaction as timeline_interaction,
    )

    window, widget = _hosted_timeline(qapp)
    try:
        assert any(target is window for target in widget._filter_targets)
        assert not widget._layout_settle._timer.isActive()
        window.resize(940, 560)
        qapp.processEvents()
        assert widget._layout_settle._timer.isActive(), (
            "resize reached the widget earlier in this suite but not here — "
            "the gate must be pinged from the filter's window branch"
        )
        # Same verdict through the explicit interaction entry (no commit).
        widget._layout_settle.cancel()
        assert (
            timeline_interaction.event_filter(
                widget, window, QEvent(QEvent.Type.WindowStateChange)
            )
            is False
        )
        assert widget._layout_settle._timer.isActive()
    finally:
        window.close()


def test_armed_gate_still_runs_the_deferred_fit(qapp, qtbot):
    """The ping is not lost: the settle flush still calls ``fit_view``."""
    window, widget = _hosted_timeline(qapp)
    try:
        calls: list[int] = []
        original_fit = widget.fit_view

        def _spy_fit(*args, **kwargs):
            calls.append(widget.width())
            return original_fit(*args, **kwargs)

        widget.fit_view = _spy_fit
        try:
            # The deferred-fit path is taken only while the flag is set; the
            # filter's ping is what schedules it.
            widget._needs_fit_view = True
            window.resize(980, 580)
            qapp.processEvents()
            assert widget._layout_settle._timer.isActive()
            qtbot.wait(300)  # settle interval is 120 ms
            assert widget._needs_fit_view is False
            assert calls, "settle flush never reached fit_view"
            assert widget._layout_settle._timer.isActive() is False
        finally:
            widget.fit_view = original_fit
    finally:
        window.close()
