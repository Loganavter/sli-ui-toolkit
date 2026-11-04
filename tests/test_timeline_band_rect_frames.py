"""The band's rectangle lives in ONE coordinate frame (owner report 2026-11-04).

The band is a child of the timeline widget, which the host scrolls, so its rect
is in CONTENT coordinates: both edges carry the scroll offset. Before this fix
the left edge was the gutter in content coords and the right edge was
``scroll + viewport`` in viewport coords, so the width became ``visible +
scroll`` (measured: scroll 8236 -> width 9140 for a 904-wide area) — the cells
stretched up to 10x (the owner's "~350 px cells") and the band slid under the
sticky gutter.

The invariant pinned here is the SCREEN one: at any scroll, the band's on-screen
left edge is the gutter and its width is the visible content width.
"""

from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtWidgets import QScrollArea


def _zoom_host(qapp, *, zoom: float = 0.02, vw: int = 1100):
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget.widget import (
        TimelineWidget,
    )

    snaps = [SimpleNamespace(timestamp=float(i)) for i in range(120)]
    area = QScrollArea()
    area.setWidgetResizable(False)
    widget = TimelineWidget()
    widget.resize(vw, 240)
    area.setWidget(widget)
    area.resize(vw, 240)
    area.show()
    qapp.processEvents()
    widget.set_data(snaps, fps=30)
    widget.fit_view()
    widget._commitState(widget._current_state(), source="test")
    qapp.processEvents()
    widget.set_zoom(zoom)
    qapp.processEvents()
    return area, widget


def test_the_band_stays_at_the_gutter_and_keeps_its_width(qapp):
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
        viewport as timeline_viewport,
    )

    area, widget = _zoom_host(qapp)
    try:
        bar = area.horizontalScrollBar()
        assert bar.maximum() > 0, "the probe needs a scrolled view"
        gutter = int(widget.LEFT_GUTTER)
        widths, on_screen_x = [], []
        for value in (0, 500, bar.maximum() // 2, bar.maximum()):
            bar.setValue(value)
            qapp.processEvents()
            rect = timeline_viewport.strip_band_rect(widget)
            widths.append(rect.width())
            on_screen_x.append(rect.x() - bar.value())
        assert len(set(widths)) == 1, (
            f"the band width followed the scroll position: {widths}"
        )
        assert set(on_screen_x) == {gutter}, (
            f"the band left the gutter on screen: {on_screen_x} (gutter {gutter})"
        )
        visible = int(timeline_viewport.get_viewport_width(widget)) - gutter
        assert widths[0] <= visible + 1, (
            f"the band is wider than the visible content: {widths[0]} > {visible}"
        )
    finally:
        area.close()
        area.deleteLater()


def test_a_range_change_does_not_retire_the_deferred_fit(qapp):
    """``rangeChanged`` is wired to host_scroll; our own width write fires it."""
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
        interaction as timeline_interaction,
    )

    area, widget = _zoom_host(qapp)
    try:
        widget._needs_fit_view = True
        # a range change (min, max) — not a user scroll
        timeline_interaction.host_scroll(widget, 0, 300)
        assert widget._needs_fit_view is True, (
            "a range change retired the protected ingest fit"
        )
        # a real scroll step still retires it (the value must actually move:
        # a no-op step returns early, which is correct)
        area.horizontalScrollBar().setValue(area.horizontalScrollBar().maximum() // 2)
        qapp.processEvents()
        timeline_interaction.host_scroll(widget)
        assert widget._needs_fit_view is False
    finally:
        area.close()
        area.deleteLater()
