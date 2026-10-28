"""Window-level event-filter pass-through for ``TimelineWidget``.

The timeline installs itself as an event filter on its TOP-LEVEL window
(``interaction.show_event`` -> ``install_filter_once(widget, window)``) to
notice fullscreen / OS resizes where its own width stays fixed. That is a
*listening* role: pinging the settle gate is a side effect, the event itself
is not consumed.

Returning ``True`` from the filter stopped Qt's filter chain for that object,
so a sibling filter installed on the same window — the CSD chrome
``TitleBarGeometryFilter`` (``ui/windows/csd_helpers.py``) — never saw the
resize and the painted chrome froze at the previous size. Measured live by the
supervisor on the video editor: window 1216x933 -> 1620x1040, content relaid
out (QSplitter 1604x988) while ``CsdRoundedBackground`` stayed [1200x917] and
``CustomTitleBar`` [1200x36]. Settings/Help (no timeline) resized correctly —
the working-sibling diff that names this filter as the owner.

Pinned here (Qt walks event filters newest-installed-first):

* a filter installed on the window BEFORE the timeline's own still receives
  ``Resize`` (the timeline's filter runs first and used to swallow it);
* a filter installed AFTER the timeline's own receives it too;
* the timeline's own verdict is ``False`` for the window (and for the host
  viewport) while the settle gate is still pinged.

The companion ``test_timeline_settle_ping_passthrough.py`` pins that the
ping still flushes the fit — the behaviour the old ``True`` was paid for.
"""

from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import QVBoxLayout, QWidget


def _snaps(n: int):
    return [SimpleNamespace(timestamp=float(i)) for i in range(n)]


class _WindowEventRecorder(QObject):
    """Plain third-party filter: records window-scoped geometry events."""

    def __init__(self, target: QWidget) -> None:
        super().__init__()
        self._target = target
        self.window_events: list[QEvent.Type] = []

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 - Qt API
        if obj is self._target and event.type() in (
            QEvent.Type.Resize,
            QEvent.Type.WindowStateChange,
        ):
            self.window_events.append(event.type())
        return False


def _hosted_timeline(qapp, *, recorder_first: bool):
    """Top-level window + scroll area + timeline; returns (window, widget, recorder).

    The scroll area mirrors the host layout, so the viewport filter target
    (``interaction.show_event`` installs on ``scroll_area.viewport()``) is real.
    """
    from PySide6.QtWidgets import QScrollArea

    from sli_ui_toolkit.ui.widgets.composite.timeline_widget.widget import (
        TimelineWidget,
    )

    window = QWidget()
    layout = QVBoxLayout(window)
    area = QScrollArea()
    area.setWidgetResizable(True)
    widget = TimelineWidget(snapshots=_snaps(30))
    area.setWidget(widget)
    layout.addWidget(area)
    window.resize(700, 420)

    recorder = _WindowEventRecorder(window)
    if recorder_first:
        # Older filter: Qt calls it AFTER the timeline's own (installed on the
        # first showEvent), so a swallowed event never reaches it.
        window.installEventFilter(recorder)
        window.show()
        qapp.processEvents()
        # The timeline must really be filtering this window for the assertion
        # below to mean anything.
        assert any(target is window for target in widget._filter_targets)
    else:
        window.show()
        qapp.processEvents()
        assert any(target is window for target in widget._filter_targets)
        # Newer filter: called BEFORE the timeline's, so this order proves the
        # event reaches the tail of the chain rather than the head.
        window.installEventFilter(recorder)
    widget._layout_settle.cancel()
    # Drop what the show-time resize delivered (that one lands before the
    # timeline filter exists in the older-first order) so the assertion below
    # speaks only about the post-settle resize under test.
    recorder.window_events.clear()
    return window, widget, recorder


def test_window_resize_reaches_filter_installed_before_timeline(qapp):
    """A sibling filter older than the timeline's still sees the window Resize."""
    window, widget, recorder = _hosted_timeline(qapp, recorder_first=True)
    try:
        window.resize(940, 560)
        qapp.processEvents()
        assert QEvent.Type.Resize in recorder.window_events, (
            "timeline swallowed the window Resize — the CSD chrome filter "
            "never runs and the title bar/background freeze at the old size"
        )
    finally:
        window.close()


def test_window_resize_reaches_filter_installed_after_timeline(qapp):
    """The event also survives both ends of the chain (not consumed at all)."""
    window, widget, recorder = _hosted_timeline(qapp, recorder_first=False)
    try:
        window.resize(940, 560)
        qapp.processEvents()
        assert QEvent.Type.Resize in recorder.window_events
    finally:
        window.close()


def test_event_filter_verdict_is_false_and_still_pings(qapp):
    """Window + viewport geometry events: verdict False, settle gate pinged."""
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
        interaction as timeline_interaction,
        viewport as timeline_viewport,
    )

    window, widget, _recorder = _hosted_timeline(qapp, recorder_first=True)
    try:
        for obj in (window, timeline_viewport.get_scroll_area(widget).viewport()):
            widget._layout_settle.cancel()
            assert not widget._layout_settle._timer.isActive()
            event = QEvent(QEvent.Type.Resize)
            # Both the interaction body and the widget's own override agree.
            assert timeline_interaction.event_filter(widget, obj, event) is False
            assert widget.eventFilter(obj, event) is False
            assert widget._layout_settle._timer.isActive(), (
                "the ping is the whole point of handling the event — it must "
                "survive the verdict flip"
            )
    finally:
        window.close()
