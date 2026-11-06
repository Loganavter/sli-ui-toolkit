"""One owner of the timeline geometry (plan-timeline-event-synchrony P1/P2).

``viewport.content_geometry(widget)`` is the single entry point: it names every
rectangle the timeline uses, in CONTENT coordinates (the host scrolls the
content widget, so on-screen x == content x - ``scroll``), and
``to_viewport_x`` / ``to_viewport_rect`` are the only place that subtraction
happens. Two properties are pinned here:

1. **Every consumer follows the entry point.** Patch the geometry and the
   band, the gutter band, the inner-scrollbar strip, the footer top and the
   playhead inputs all move with it — nobody re-derives ``scroll + viewport``.
2. **The P0 screen invariant.** At any scroll value the band's on-screen left
   edge is the gutter and its width is the visible content width.

Plus the P2 defect itself: ``get_viewport_width`` no longer falls back to the
container's width, so a timeline WITHOUT a ``QScrollArea`` keeps its host-given
visible width and can zoom out (it used to report its own fixed content width
back and freeze ``min_zoom`` at the current zoom, ~0.5 in the report).
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QRect
from PySide6.QtWidgets import QScrollArea, QVBoxLayout, QWidget

from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
    primitives as timeline_primitives,
)
from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
    render as timeline_render,
)
from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
    viewport as timeline_viewport,
)
from sli_ui_toolkit.ui.widgets.composite.timeline_widget.widget import TimelineWidget



def _snaps(n: int = 120):
    return [SimpleNamespace(timestamp=float(i)) for i in range(n)]


def _hosted(qapp, *, zoom: float = 0.02, vw: int = 800, vh: int = 240):
    """Timeline inside a host ``QScrollArea`` with a scrolled view."""
    area = QScrollArea()
    area.setWidgetResizable(False)
    widget = TimelineWidget()
    widget.resize(vw, vh)
    area.setWidget(widget)
    area.resize(vw, vh)
    area.show()
    qapp.processEvents()
    widget.set_data(_snaps(), fps=30)
    widget.fit_view()
    widget._commitState(widget._current_state(), source="test")
    qapp.processEvents()
    widget.set_zoom(zoom)
    qapp.processEvents()
    return area, widget


def _bare(qapp):
    """Timeline with NO scroll host, inside a container laid out around it."""
    parent = QWidget()
    layout = QVBoxLayout(parent)
    layout.setContentsMargins(0, 0, 0, 0)
    widget = TimelineWidget()
    layout.addWidget(widget)
    parent.resize(700, 240)
    parent.show()
    qapp.processEvents()
    return parent, widget


# --- 1. every consumer follows the single entry point -----------------------


def test_the_geometry_is_the_one_owner_of_the_rects(qapp):
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
        viewport as vp,
    )

    area, widget = _hosted(qapp)
    try:
        geo = vp.content_geometry(widget)
        assert geo.scroll == area.horizontalScrollBar().value() > 0
        assert geo.width == widget.width()
        assert geo.gutter == int(widget.LEFT_GUTTER)
        assert geo.footer_top == widget.height() - vp.footer_height(widget)
        assert geo.content_rect.x() == geo.scroll
        assert geo.visible_width == area.viewport().width()

        assert vp.strip_band_rect(widget) == geo.band_rect
        assert vp.gutter_band_rect(widget) == geo.gutter_rect
        sb = vp.sb_strip_rect(widget)
        assert sb.x() == geo.scroll + geo.gutter
        assert sb.width() == geo.content_rect.width() - geo.gutter
        assert sb.y() == geo.footer_top

        # Viewport conversion is the single subtraction site.
        assert vp.to_viewport_x(geo, geo.scroll + geo.gutter) == geo.gutter
        assert vp.to_viewport_rect(geo, geo.band_rect) == geo.band_rect.translated(
            -geo.scroll, 0
        )
    finally:
        area.close()
        area.deleteLater()


def test_every_consumer_moves_when_the_geometry_moves(qapp, monkeypatch):
    """Patch the entry point: all derived rects shift with it, none recompute."""
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
        viewport as vp,
    )

    area, widget = _hosted(qapp)
    real = vp.content_geometry
    try:
        base = real(widget)
        shift = 137
        patched = replace(
            base,
            scroll=base.scroll + shift,
            content_rect=base.content_rect.translated(shift, 0),
            band_rect=base.band_rect.translated(shift, 0),
            gutter_rect=base.gutter_rect.translated(shift, 0),
        )
        monkeypatch.setattr(vp, "content_geometry", lambda w: patched)

        assert vp.strip_band_rect(widget) == patched.band_rect
        assert vp.gutter_band_rect(widget) == patched.gutter_rect
        sb = vp.sb_strip_rect(widget)
        assert sb.x() == patched.scroll + patched.gutter
        assert sb.y() == patched.footer_top

        # A field that a consumer previously re-derived is now read from here.
        monkeypatch.setattr(
            vp,
            "content_geometry",
            lambda w: replace(
                patched,
                footer_top=99,
                gutter_rect=QRect(patched.gutter_rect.x(), 0, patched.gutter_rect.width(), 99),
            ),
        )
        assert vp.sb_strip_rect(widget).y() == 99
        assert vp.gutter_band_rect(widget).height() == 99
    finally:
        area.close()
        area.deleteLater()


def test_paint_takes_footer_and_playhead_from_the_geometry(qapp, monkeypatch):
    """The paint pass reads the geometry: footer top, playhead width, sb strip."""
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
        viewport as vp,
    )

    area, widget = _hosted(qapp)
    real = vp.content_geometry
    playhead_moves: list[dict] = []
    sb_rects: list = []
    try:
        base = real(widget)
        patched = replace(
            base,
            scroll=base.scroll + 211,
            footer_top=base.footer_top - 17,
            content_rect=base.content_rect.translated(211, 0),
            band_rect=base.band_rect.translated(211, 0),
            gutter_rect=base.gutter_rect.translated(211, 0),
        )
        monkeypatch.setattr(vp, "content_geometry", lambda w: patched)
        original_playhead = timeline_primitives.draw_playhead

        def _spy_playhead(widget_, painter_, **kwargs):
            playhead_moves.append(kwargs)
            return original_playhead(widget_, painter_, **kwargs)

        original_sb = vp.draw_inner_scrollbar

        def _spy_sb(widget_, painter_, sb_rect, *args, **kwargs):
            sb_rects.append(sb_rect)
            return original_sb(widget_, painter_, sb_rect, *args, **kwargs)

        monkeypatch.setattr(timeline_primitives, "draw_playhead", _spy_playhead)
        monkeypatch.setattr(vp, "draw_inner_scrollbar", _spy_sb)
        widget.paintEvent(_paint_event(widget))
        assert playhead_moves, "the playhead pass did not run"
        assert playhead_moves[0]["footer_top"] == patched.footer_top
        assert playhead_moves[0]["width"] == patched.scroll + patched.content_rect.width()
        assert sb_rects and sb_rects[0].x() == patched.scroll + patched.gutter
        assert sb_rects[0].y() == patched.footer_top
    finally:
        area.close()
        area.deleteLater()


def _paint_event(widget):
    from PySide6.QtGui import QPaintEvent

    return QPaintEvent(QRect(0, 0, widget.width(), widget.height()))


# --- 2. the P0 screen invariant, through the entry point --------------------


def test_the_band_screen_invariant_at_three_scroll_values(qapp):
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
        viewport as vp,
    )

    area, widget = _hosted(qapp)
    try:
        bar = area.horizontalScrollBar()
        assert bar.maximum() > 0, "the probe needs a scrolled view"
        gutter = int(widget.LEFT_GUTTER)
        widths, screen_x = [], []
        for value in (0, bar.maximum() // 2, bar.maximum()):
            bar.setValue(value)
            qapp.processEvents()
            geo = vp.content_geometry(widget)
            screen = vp.to_viewport_rect(geo, geo.band_rect)
            widths.append(screen.width())
            screen_x.append(screen.x())
            # both edges are content-frame: on screen the band starts at the
            # gutter and never grows with the scroll
            assert vp.to_viewport_x(geo, geo.band_rect.x()) == gutter
            assert screen.width() == geo.content_rect.width() - geo.gutter
        assert len(set(widths)) == 1, f"the band width followed the scroll: {widths}"
        assert set(screen_x) == {gutter}, screen_x
    finally:
        area.close()
        area.deleteLater()


# --- 3. the P2 defect: no container-width fallback --------------------------


def test_get_viewport_width_is_the_widgets_own_width_without_a_host(qapp):
    """No host scroll area -> the widget's own width, never the parent's."""
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
        viewport as vp,
    )

    parent = QWidget()
    parent.resize(700, 240)
    widget = TimelineWidget(parent=parent)
    widget.resize(900, 240)
    parent.show()
    qapp.processEvents()
    try:
        assert vp.get_scroll_area(widget) is None
        assert widget.parent() is parent
        assert vp.get_viewport_width(widget) == widget.width() == 900
    finally:
        parent.close()
        parent.deleteLater()


def test_a_timeline_without_a_scroll_area_keeps_zooming_out(qapp):
    """A bare timeline keeps its host-given width, so ``min_zoom`` stays put.

    Without a host nothing may pin the width to the content: a fitted view of
    a 700-px host must keep the same fitted zoom after a zoom-in, i.e. zooming
    back out is still possible (the pre-fix tree widened the widget to the
    content width, and ``min_zoom`` followed it).
    """
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
        viewport as vp,
    )

    parent, widget = _bare(qapp)
    try:
        host_width = widget.width()
        assert host_width > 0
        widget.set_data(_snaps(), fps=30)
        widget._layout_settle.cancel()
        widget.fit_view()
        qapp.processEvents()
        fit_zoom = widget._zoom_level
        assert fit_zoom < 1.0

        widget.set_zoom(min(1.0, fit_zoom * 8.0))
        qapp.processEvents()

        assert widget.width() == host_width, (
            f"a bare timeline pinned its width to the content: "
            f"{host_width} -> {widget.width()}"
        )
        assert vp.get_viewport_width(widget) == host_width
        assert vp.calculate_min_zoom(widget) == pytest.approx(fit_zoom, rel=0.05), (
            "min_zoom followed the content width: zooming out is blocked"
        )
        assert vp.calculate_min_zoom(widget) < widget._zoom_level
    finally:
        parent.close()
        parent.deleteLater()


# --- 4. the rg invariant, as a source gate ---------------------------------


def test_the_scroll_offset_is_read_only_by_the_geometry_module():
    """No ``scroll + viewport`` / ``x - scroll`` arithmetic outside the owner."""
    viewport_src = Path(timeline_viewport.__file__).read_text()
    render_src = Path(timeline_render.__file__).read_text()
    widget_src = Path(
        Path(timeline_render.__file__).resolve().parent / "widget.py"
    ).read_text()

    assert "def content_geometry(" in viewport_src
    assert "def to_viewport_x(" in viewport_src
    assert "def to_viewport_rect(" in viewport_src
    # The host scroll offset is read in exactly one function.
    assert viewport_src.count("horizontalScrollBar().value()") == 1, (
        viewport_src.count("horizontalScrollBar().value()")
    )
    for source, name in ((render_src, "render.py"), (widget_src, "widget.py")):
        assert "scroll_offset" not in source, f"{name} still names the scroll offset"
    # render.py must not read the host bar at all (it used to compute
    # ``scroll + viewport`` per pass). widget.py reads it only to detect that
    # the host scrolled (old_h/new_h change detection for the wheel path),
    # which is host-scroll semantics, not geometry.
    assert "horizontalScrollBar" not in render_src
