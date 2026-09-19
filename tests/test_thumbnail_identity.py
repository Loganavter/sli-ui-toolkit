"""Thumbnail identity contracts for the timeline strip (Phase 1 T-paint).

Every strip block must show EXACTLY its own representative frame or a
theme-token placeholder — never a neighbor pixmap, never ``idx[0]``.

Covered:

- N indices with N distinguishable payloads: ``payload(i) == content(i)``
  per block (sampled at the block center, off the seam).
- sparse store: a block whose rep is absent shows the placeholder.
- evicted neighbor: after removal the block shows the placeholder, not the
  surviving neighbor.
- zoom / base_tile change: reps re-resolve against the same store, no
  cross-binding.
- degenerate (zero-width) block: skipped via ``continue``, never aborts the
  rest of the strip.
- 1:1 overdraw: no ``+1.0px`` overwrite of the next frame.
- lookup hygiene: no ``bisect`` / ``_thumb_indices`` fallback in the strip
  lookup path.
"""

from __future__ import annotations

import inspect
import math

from PySide6.QtGui import QColor, QImage, QPainter, QPixmap

from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
    render as timeline_render,
)
from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
    theme as timeline_theme,
)
from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
    viewport as timeline_viewport,
)
from sli_ui_toolkit.widgets import TimelineWidget

# Eight mutually distinguishable solid payloads — none collides with the
# placeholder (track_bg) or canvas (Window) tokens in either theme.
COLORS = [
    QColor(255, 0, 0),
    QColor(0, 255, 0),
    QColor(0, 0, 255),
    QColor(255, 255, 0),
    QColor(255, 0, 255),
    QColor(0, 255, 255),
    QColor(255, 136, 0),
    QColor(136, 0, 255),
]

_TOTAL_FRAMES = 9  # span 8: 8 blocks at 1:1, reps {0..7}; reps {0, 4} collapsed


def _make_strip_widget(qtbot, *, zoom: float = 1.0) -> TimelineWidget:
    """Bare strip widget: no model, no fit_view.

    ``_state`` is cleared after show so ``prune_thumbnails`` is a no-op and
    the store under test is exactly what the test put there (feed/prune
    coherence is T-state/A-feed scope; paint identity must not depend on
    it). Zoom is written directly after show because the show-settle would
    otherwise clamp it to min_zoom.
    """
    tl = TimelineWidget()
    tl._fps = 10
    tl._duration = 0.8
    tl._total_frames = _TOTAL_FRAMES
    qtbot.addWidget(tl)
    tl.resize(1200, 400)
    tl.show()
    tl._state = None
    tl._zoom_level = float(zoom)
    return tl


def _pixmap(color: QColor) -> QPixmap:
    px = QPixmap(64, 36)
    px.fill(color)
    return px


def _render_strip(tl: TimelineWidget) -> QImage:
    """Paint the full-content strip into an image via the real draw path."""
    base = timeline_viewport.get_base_tile_width(tl)
    logical = timeline_viewport.get_logical_width(tl)
    slot = timeline_viewport.get_slot_width(tl)
    csx = float(tl.LEFT_GUTTER)
    colors = timeline_theme.build_theme_colors(tl)
    width_px = int(math.ceil(csx + logical)) + 2
    height_px = int(tl.STRIP_HEIGHT) + 2
    img = QImage(width_px, height_px, QImage.Format.Format_ARGB32)
    img.fill(colors["canvas_bg"])
    painter = QPainter(img)
    timeline_render.draw_thumbnail_strip(
        tl,
        painter,
        canvas_bg=colors["canvas_bg"],
        content_start_x=csx,
        strip_top=0.0,
        width=csx + logical,
        start_x=csx,
        end_x=csx + logical,
        logical_width=logical,
        slot_width=slot,
    )
    painter.end()
    assert base > 0
    return img


def _strip_blocks(tl: TimelineWidget):
    csx = float(tl.LEFT_GUTTER)
    logical = timeline_viewport.get_logical_width(tl)
    return timeline_viewport.strip_block_layout(
        tl, content_start_x=csx, start_x=csx, end_x=csx + logical
    )


def _center(block, *, y: int = 36) -> tuple[int, int]:
    bx, bw, _rep = block
    return int(bx + bw / 2.0), y


def _placeholder_rgb(tl: TimelineWidget) -> int:
    return timeline_theme.build_theme_colors(tl)["track_bg"].rgb()


def test_exact_match_per_block(qtbot):
    """payload(i) == content(i): every 1:1 block shows its own rep color."""
    tl = _make_strip_widget(qtbot, zoom=1.0)
    tl.set_thumbnails({i: _pixmap(COLORS[i]) for i in range(8)})
    blocks = _strip_blocks(tl)
    assert [rep for _, _, rep in blocks] == list(range(8)), blocks
    img = _render_strip(tl)
    for (bx, bw, rep), color in zip(blocks, COLORS):
        x, y = _center((bx, bw, rep))
        assert img.pixelColor(x, y).rgb() == color.rgb(), (rep, bx, bw)


def test_sparse_store_shows_placeholder_never_neighbor(qtbot):
    """A rep absent from the store paints the placeholder, not a neighbor."""
    tl = _make_strip_widget(qtbot, zoom=0.25)
    blocks = _strip_blocks(tl)
    assert [rep for _, _, rep in blocks] == [0, 4], blocks
    tl.set_thumbnails({0: _pixmap(COLORS[0])})
    img = _render_strip(tl)
    placeholder = _placeholder_rgb(tl)
    assert placeholder != COLORS[0].rgb()
    x0, y0 = _center(blocks[0])
    assert img.pixelColor(x0, y0).rgb() == COLORS[0].rgb()
    x1, y1 = _center(blocks[1])
    assert img.pixelColor(x1, y1).rgb() == placeholder, "missing rep must not borrow rep 0"
    assert img.pixelColor(x1, y1).rgb() != COLORS[0].rgb()


def test_evicted_neighbor_shows_placeholder(qtbot):
    """After eviction the orphaned block fails closed to the placeholder."""
    tl = _make_strip_widget(qtbot, zoom=0.25)
    blocks = _strip_blocks(tl)
    assert [rep for _, _, rep in blocks] == [0, 4], blocks
    tl.set_thumbnails({0: _pixmap(COLORS[0]), 4: _pixmap(COLORS[2])})
    img = _render_strip(tl)
    x1, y1 = _center(blocks[1])
    assert img.pixelColor(x1, y1).rgb() == COLORS[2].rgb()
    # Simulate eviction of the neighbor (index-addressed store shape kept).
    del tl._thumbnails[4]
    tl._thumb_indices.remove(4)
    img = _render_strip(tl)
    placeholder = _placeholder_rgb(tl)
    assert img.pixelColor(x1, y1).rgb() == placeholder
    assert img.pixelColor(x1, y1).rgb() not in (COLORS[0].rgb(), COLORS[2].rgb())
    x0, y0 = _center(blocks[0])
    assert img.pixelColor(x0, y0).rgb() == COLORS[0].rgb()


def test_zoom_change_does_not_cross_bind(qtbot):
    """Reps re-resolve against the same store across zoom changes."""
    tl = _make_strip_widget(qtbot, zoom=1.0)
    store = {i: _pixmap(COLORS[i]) for i in range(8)}
    tl.set_thumbnails(store)
    img = _render_strip(tl)
    for (bx, bw, rep), color in zip(_strip_blocks(tl), COLORS):
        x, y = _center((bx, bw, rep))
        assert img.pixelColor(x, y).rgb() == color.rgb(), ("1:1", rep)
    # Collapse: two blocks, reps {0, 4} — each keeps its own payload.
    tl._zoom_level = 0.25
    blocks = _strip_blocks(tl)
    assert [rep for _, _, rep in blocks] == [0, 4], blocks
    img = _render_strip(tl)
    assert img.pixelColor(*_center(blocks[0])).rgb() == COLORS[0].rgb()
    assert img.pixelColor(*_center(blocks[1])).rgb() == COLORS[4].rgb()
    # And back to 1:1: all eight exact again.
    tl._zoom_level = 1.0
    img = _render_strip(tl)
    for (bx, bw, rep), color in zip(_strip_blocks(tl), COLORS):
        x, y = _center((bx, bw, rep))
        assert img.pixelColor(x, y).rgb() == color.rgb(), ("restored", rep)


def test_degenerate_block_does_not_abort_strip(qtbot, monkeypatch):
    """A zero-width block is skipped (continue), later blocks still paint."""
    tl = _make_strip_widget(qtbot, zoom=1.0)
    tl.set_thumbnails({3: _pixmap(COLORS[1]), 5: _pixmap(COLORS[0])})
    csx = float(tl.LEFT_GUTTER)
    monkeypatch.setattr(
        timeline_viewport,
        "strip_block_layout",
        lambda _w, **_kw: [(csx, 0.0, 5), (csx, 128.0, 3)],
    )
    img = _render_strip(tl)
    # The real layout is patched away, so sample the injected block's center
    # directly: it must show rep 3's payload despite the leading degenerate.
    assert img.pixelColor(int(csx + 64), 36).rgb() == COLORS[1].rgb()


def test_no_overdraw_at_one_to_one(qtbot):
    """At 1:1 a block's first pixel is its own frame, never the neighbor's."""
    tl = _make_strip_widget(qtbot, zoom=1.0)
    tl.set_thumbnails({i: _pixmap(COLORS[i]) for i in range(8)})
    blocks = _strip_blocks(tl)
    assert len(blocks) == 8, blocks
    img = _render_strip(tl)
    for index, (bx, bw, rep) in enumerate(blocks):
        first = img.pixelColor(int(bx), 36).rgb()
        assert first == COLORS[index].rgb(), (index, rep, "overwritten by left neighbor")
        last = img.pixelColor(int(bx + bw) - 1, 36).rgb()
        assert last == COLORS[index].rgb(), (index, rep)


def test_no_bisect_fallback_in_strip_lookup():
    """The strip lookup path carries no nearest-neighbor fallback."""
    for fn in (
        timeline_render.draw_thumbnail_strip,
        timeline_render._lookup_thumbnail,
    ):
        source = inspect.getsource(fn)
        assert "bisect" not in source, fn.__name__
        assert "_thumb_indices" not in source, fn.__name__


def test_lookup_returns_none_when_absent(qtbot):
    """Exact-match lookup: hit returns the pixmap, miss returns None."""
    tl = _make_strip_widget(qtbot, zoom=1.0)
    tl.set_thumbnails({2: _pixmap(COLORS[2])})
    hit = timeline_render._lookup_thumbnail(tl, 2)
    assert hit is not None and not hit.isNull()
    assert timeline_render._lookup_thumbnail(tl, 3) is None
    assert timeline_render._lookup_thumbnail(tl, 0) is None
