"""The band's rectangle lives in ONE coordinate frame (owner report 2026-11-04).

Measured before this fix, on a zoomed view (host range 0..8236, 904-px visible
content): ``strip_band_rect`` grew with the scroll position —
``scroll 8236 -> width 9140`` — because ``left`` was the gutter in CONTENT
coordinates while the right edge was ``scroll_offset + viewport`` in VIEWPORT
coordinates. The band then painted over the gutter and the pass stretched every
cell by that ratio (the owner's "~350 px cells" is exactly it).
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


def test_the_band_width_does_not_grow_with_the_scroll(qapp):
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
        viewport as timeline_viewport,
    )

    area, widget = _zoom_host(qapp)
    try:
        bar = area.horizontalScrollBar()
        assert bar.maximum() > 0, "the probe needs a scrolled view"
        widths = []
        for value in (0, 500, bar.maximum() // 2, bar.maximum()):
            bar.setValue(value)
            qapp.processEvents()
            rect = timeline_viewport.strip_band_rect(widget)
            widths.append(rect.width())
            assert rect.x() == int(widget.LEFT_GUTTER)
        assert len(set(widths)) == 1, (
            f"the band width followed the scroll position: {widths}"
        )
        visible = int(timeline_viewport.get_viewport_width(widget)) - int(
            widget.LEFT_GUTTER
        )
        assert widths[0] <= visible + 1, (
            f"the band is wider than the visible content: {widths[0]} > {visible}"
        )
    finally:
        area.close()
        area.deleteLater()
