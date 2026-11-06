"""The playhead/selection overlay above the GPU filmstrip band (plan P5).

Structural fact under test (``strip_band.py``): a child widget composites
ABOVE every ``QPainter`` pass of its parent, so a visible band hides the
playhead line and the selection wash that the parent paints across the strip
row. The answer is one more paint-only child raised over the band
(``overlay.TimelineOverlay``) that re-draws exactly those two things — with
the parent's own ``render.paint_playhead`` / ``render.paint_selection_wash``,
not a copy of them.

What is provable offscreen (and pinned here):

1. the widget tree: the overlay exists, is the timeline's child, is visible
   while the band is visible, and is the TOPMOST child after
   ``sync_strip_band`` (``raise_`` after ``band.place``);
2. input: it is transparent to mouse events and takes no focus, and a click
   at the band's y still lands on the timeline's scrub path;
3. geometry: it tracks the band's rect — the single owner's rect — after a
   scroll and after a zoom;
4. paint: it calls the shared selection/playhead functions with the band's
   content span, in the CONTENT frame (``x_head + dx == x_head - scroll -
   gutter``), and the pixels land at the geometry-derived x;
5. fallback: with the band disabled the overlay is gone/hidden and the parent
   pass still draws both — no visual regression without a band.

The composited result (an overlay pixel on top of the band's GPU texture) is
not observable here: that is the live capture.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QImage, QPaintEvent
from PySide6.QtWidgets import QApplication, QScrollArea

from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
    interaction as timeline_interaction,
)
from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
    overlay as timeline_overlay,
)
from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
    render as timeline_render,
)
from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
    viewport as timeline_viewport,
)
from sli_ui_toolkit.widgets import StripBand, TimelineWidget


def _snaps(n: int = 120):
    return [SimpleNamespace(timestamp=float(i)) for i in range(n)]


def _hosted(qapp, *, zoom: float = 0.02, vw: int = 800, vh: int = 240):
    """Timeline inside a host ``QScrollArea`` with a genuinely scrolled view.

    The band's rect carries the host's scroll offset (content coordinates), so
    the overlay's placement and paint only mean something in a scrolled host.
    """
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


def _banded(qapp):
    area, widget = _hosted(qapp)
    band = widget.enable_strip_band(render=lambda command_buffer, b: None)
    qapp.processEvents()
    overlay = widget.strip_band_overlay()
    assert overlay is not None, "enabling the band must create its overlay"
    return area, widget, band, overlay


def _playhead_frame_inside_the_band(widget) -> int:
    """A frame whose playhead sits ~100 px into the band, not at an edge."""
    geo = timeline_viewport.content_geometry(widget)
    return int(timeline_viewport.pos_to_frame(widget, geo.band_rect.left() + 100))


# --- 1. the widget tree ----------------------------------------------------


def test_overlay_is_a_visible_child_above_the_band(qapp):
    area, widget, band, overlay = _banded(qapp)
    try:
        assert isinstance(overlay, timeline_overlay.TimelineOverlay)
        assert overlay.parent() is widget
        assert widget.strip_band_overlay() is overlay
        # Visible exactly while the band is on screen.
        assert band.isVisible()
        assert overlay.isVisible()

        # The stacking order IS the parent's children() order for widgets;
        # raise_() must have put the overlay after the band.
        order = list(widget.children())
        assert order.index(overlay) > order.index(band), [type(c).__name__ for c in order]

        # Re-syncing keeps the overlay on top (the raise happens after place).
        band.raise_()
        widget.sync_strip_band()
        order = list(widget.children())
        assert order.index(overlay) > order.index(band)
        assert overlay.isVisible()
    finally:
        area.close()
        area.deleteLater()


# --- 2. input --------------------------------------------------------------


def test_overlay_is_paint_only_and_does_not_take_a_click(qapp):
    area, widget, band, overlay = _banded(qapp)
    presses: list = []
    original = timeline_interaction.mouse_press_event

    def _spy(target, event):
        presses.append((target is widget, event.position().toPoint()))
        return original(target, event)

    timeline_interaction.mouse_press_event = _spy
    try:
        assert overlay.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        assert overlay.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        assert overlay.focusPolicy() == Qt.FocusPolicy.NoFocus

        # Qt's own hit-testing, at the band's y: the overlay (and the band,
        # also transparent) are skipped, the timeline underneath gets the
        # event. childAt() returns None when nothing wants the point.
        point = band.geometry().center()
        assert widget.childAt(point) is not overlay
        target = QApplication.widgetAt(widget.mapToGlobal(point))
        assert target is widget, target

        from PySide6.QtTest import QTest

        QTest.mouseClick(target, Qt.MouseButton.LeftButton, pos=target.mapFrom(widget, point))
        assert presses, "the click at the band's y never reached the timeline"
        assert presses[0][0] is True
    finally:
        timeline_interaction.mouse_press_event = original
        area.close()
        area.deleteLater()


# --- 3. geometry -----------------------------------------------------------


def test_overlay_tracks_the_band_rect_on_scroll_and_zoom(qapp):
    area, widget, band, overlay = _banded(qapp)
    try:
        bar = area.horizontalScrollBar()
        assert bar.maximum() > 0, "the probe needs a scrolled view"
        for value in (bar.minimum(), bar.maximum() // 2, bar.maximum()):
            bar.setValue(value)
            qapp.processEvents()
            widget.sync_strip_band()
            expected = timeline_viewport.strip_band_rect(widget)
            assert overlay.band_rect() == expected
            assert overlay.geometry() == expected
            assert overlay.geometry() == band.geometry()

        before = QRect(overlay.geometry())
        widget.set_zoom(0.05)
        qapp.processEvents()
        expected = timeline_viewport.strip_band_rect(widget)
        assert overlay.geometry() == expected == band.geometry()
        assert overlay.geometry() != before, "the zoom did not move the band"
    finally:
        area.close()
        area.deleteLater()


# --- 4. the shared paint functions, in the content frame -------------------


def test_overlay_paints_through_the_shared_functions(qapp):
    area, widget, band, overlay = _banded(qapp)
    calls: list[tuple] = []
    original_wash = timeline_render.paint_selection_wash
    original_head = timeline_render.paint_playhead
    original_primitive = timeline_render.timeline_primitives.draw_playhead

    def _spy_wash(target, painter, geo, **kwargs):
        calls.append(("wash", geo, kwargs, painter.transform().dx()))
        return original_wash(target, painter, geo, **kwargs)

    def _spy_head(target, painter, geo, **kwargs):
        calls.append(("playhead", geo, kwargs, painter.transform().dx()))
        return original_head(target, painter, geo, **kwargs)

    def _spy_primitive(target, painter, **kwargs):
        calls.append(("primitive", kwargs, painter.transform().dx()))
        return original_primitive(target, painter, **kwargs)

    timeline_render.paint_selection_wash = _spy_wash
    timeline_render.paint_playhead = _spy_head
    timeline_render.timeline_primitives.draw_playhead = _spy_primitive
    try:
        frame = _playhead_frame_inside_the_band(widget)
        widget._visual_index = float(frame)
        widget._scrub_visual_index = None
        widget._has_selection = True
        widget._anchor_index = frame - 10
        widget._drag_index = frame + 10
        widget.sync_strip_band()
        qapp.processEvents()

        geo = timeline_viewport.content_geometry(widget)
        band_rect = geo.band_rect
        image = QImage(overlay.size(), QImage.Format.Format_ARGB32)
        image.fill(0)
        calls.clear()
        overlay.render(image)

        kinds = [call[0] for call in calls]
        assert kinds == ["wash", "playhead", "primitive"], kinds

        wash, playhead, primitive = calls
        for kind, geo_arg, kwargs, _dx in (wash, playhead):
            assert kind in ("wash", "playhead")
            assert geo_arg == geo
            # The overlay's span IS the band's content span: one owner.
            assert kwargs["start_x"] == band_rect.left()
            assert kwargs["end_x"] == band_rect.right()
            # Content frame -> local frame, by exactly the band offset.
            assert _dx == -band_rect.left()

        # The geometry-derived x: the playhead's content x, placed on screen at
        # the same x the parent pass uses (content x - scroll), i.e.
        # content x == local x + gutter + scroll.
        _kind, head_kwargs, head_dx = primitive
        x_head = head_kwargs["x_head"]
        assert x_head == pytest.approx(
            timeline_viewport.visual_pos_from_index(widget, frame)
        )
        local_x = x_head + head_dx
        assert x_head == pytest.approx(local_x + geo.gutter + geo.scroll)

        # And the pixels agree: the playhead column carries ink in the
        # rendered overlay image (the band rect starts at the gutter, so the
        # line is INSIDE the overlay — this is the part the band used to hide).
        column = int(round(local_x))
        assert 0 <= column < image.width()
        alphas = [
            image.pixelColor(x, 30).alpha()
            for x in range(max(0, column - 3), min(image.width(), column + 4))
        ]
        assert max(alphas) > 0, (column, alphas)
    finally:
        timeline_render.paint_selection_wash = original_wash
        timeline_render.paint_playhead = original_head
        timeline_render.timeline_primitives.draw_playhead = original_primitive
        area.close()
        area.deleteLater()


# --- 5. without a band: hidden overlay, unchanged parent pass --------------


def test_parent_pass_still_draws_both_without_a_band(qapp):
    area, widget, band, overlay = _banded(qapp)
    calls: list[str] = []
    original_wash = timeline_render.paint_selection_wash
    original_head = timeline_render.paint_playhead

    def _spy_wash(target, painter, geo, **kwargs):
        calls.append("wash")
        return original_wash(target, painter, geo, **kwargs)

    def _spy_head(target, painter, geo, **kwargs):
        calls.append("playhead")
        return original_head(target, painter, geo, **kwargs)

    timeline_render.paint_selection_wash = _spy_wash
    timeline_render.paint_playhead = _spy_head
    try:
        widget._has_selection = True
        widget._anchor_index = 10
        widget._drag_index = 40
        widget._visual_index = 25.0
        widget.sync_strip_band()
        qapp.processEvents()

        widget.disable_strip_band()
        qapp.processEvents()
        assert widget.strip_band() is None
        assert widget.strip_band_overlay() is None
        assert not overlay.isVisible()

        calls.clear()
        widget.paintEvent(QPaintEvent(QRect(0, 0, widget.width(), widget.height())))
        assert calls == ["wash", "playhead"], calls
    finally:
        timeline_render.paint_selection_wash = original_wash
        timeline_render.paint_playhead = original_head
        area.close()
        area.deleteLater()


# --- the docstring obligation is gone --------------------------------------


def test_strip_band_no_longer_asks_the_renderer_to_draw_the_chrome():
    """The old obligation was prose nothing enforced; the overlay is the fact."""
    source = Path(
        Path(timeline_overlay.__file__).resolve().parent / "strip_band.py"
    ).read_text(encoding="utf-8")
    assert "the renderer draws those itself" not in source
    assert "TimelineOverlay" in source
    overlay_source = Path(timeline_overlay.__file__).read_text(encoding="utf-8")
    # The overlay reads geometry from the one owner, never the host bar.
    assert "content_geometry(" in overlay_source
    assert "horizontalScrollBar" not in overlay_source


def test_overlay_module_owns_no_timer_or_readback():
    source = Path(timeline_overlay.__file__).read_text(encoding="utf-8")
    for forbidden in ("QTimer", "singleShot", "grabFramebuffer", "QImage"):
        assert forbidden not in source, forbidden


def test_overlay_is_not_a_strip_band():
    """Guard the seam: two children, two jobs (tiles vs chrome)."""
    assert not issubclass(timeline_overlay.TimelineOverlay, StripBand)
