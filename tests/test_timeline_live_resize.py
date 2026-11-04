"""A live window resize must move the timeline with it (owner report 2026-11-04).

Two symptoms, one cause: the fixed width is derived from the VIEWPORT width, and
a viewport-only resize used to do nothing but ping the settle gate — so until
the drag stopped the content kept the old width. Widening left the strip stale;
narrowing left the widget wider than the shrunken viewport, i.e. a horizontal
scrollbar for as long as the drag lasted.
"""

from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import QScrollArea

from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
    interaction as timeline_interaction,
)
from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
    viewport as timeline_viewport,
)


def _snaps(n: int):
    return [SimpleNamespace(timestamp=float(i)) for i in range(n)]


def _host(qapp, vw: int, vh: int = 240):
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget.widget import (
        TimelineWidget,
    )

    area = QScrollArea()
    area.setWidgetResizable(False)
    widget = TimelineWidget()
    widget.resize(vw, 240)
    area.setWidget(widget)
    area.resize(vw, vh)
    area.show()
    qapp.processEvents()
    widget.set_data(_snaps(120), fps=30)
    widget.fit_view()
    widget._commitState(widget._current_state(), source="test")
    qapp.processEvents()
    return area, widget


def _resize_event():
    return SimpleNamespace(type=lambda: QEvent.Type.Resize)


def _filter(qapp, area, widget):
    """Deliver a viewport-resize event exactly as the installed filter sees it."""
    return timeline_interaction.event_filter(
        widget, area.viewport(), _resize_event()
    )


def test_widening_moves_the_timeline_without_waiting_for_the_settle(qapp):
    area, widget = _host(qapp, 800)
    try:
        before = widget.width()
        area.resize(1100, 240)
        qapp.processEvents()
        _filter(qapp, area, widget)
        qapp.processEvents()

        assert widget.width() != before, (
            "the timeline kept its pre-resize width until the settle flush"
        )
        # it must fill the wider viewport, not stay short of it
        assert widget.width() >= timeline_viewport.get_viewport_width(widget)
    finally:
        area.close()
        area.deleteLater()


def test_narrowing_does_not_leave_a_horizontal_scrollbar(qapp):
    area, widget = _host(qapp, 1100)
    try:
        area.resize(700, 240)
        qapp.processEvents()
        _filter(qapp, area, widget)
        qapp.processEvents()

        bar = area.horizontalScrollBar()
        assert bar.maximum() == 0 or not bar.isVisible(), (
            f"a horizontal scrollbar appeared during a narrowing drag "
            f"(max={bar.maximum()}, value={bar.value()}, "
            f"widget={widget.width()} viewport={timeline_viewport.get_viewport_width(widget)})"
        )
    finally:
        area.close()
        area.deleteLater()
