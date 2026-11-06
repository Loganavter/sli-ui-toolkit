"""One gesture = one geometry recomputation and one commit (plan P4).

Counters, not prose. On the pre-fix tree (measured 2026-11-04, this base) one
zoom tick wrote the width once but placed the band TWICE — the first place ran
from ``resizeEvent`` inside the width pin, i.e. with the pre-commit zoom and the
pre-commit scroll (a stale place) — and a live resize of a FITTED view cost
THREE commits (``fitView`` + ``liveResize`` + the settle flush's no-change
``settle``) while a programmatic range change cost TWO (``hostScroll`` twice,
because ``rangeChanged`` was treated as a user scroll).

What this module pins:

1. one zoom tick (API centre anchor and wheel cursor anchor) -> exactly one
   ``setFixedWidth`` write, one band ``place``/``set_view``, one
   ``_commitState``;
2. one live resize turn of a fitted view -> exactly one ``_commitState``,
   including the settle-gate flush, and the view is STILL fitted (the
   load-bearing re-fit is not what was removed);
3. a programmatic range change -> zero ``_commitState`` (a range change is
   never a user scroll) and the deferred ingest fit is not retired;
4. the band never sees the pre-commit view: every recorded place carries the
   committed zoom, and the last one equals ``widget._zoom_level``.

The settle gate and the deferred ingest fit are load-bearing (HISTORY: the
120 ms settle-gated fit and the protected ingest fit) — only the duplicate
commits and the stale place are gone. Nothing here asserts timing.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QScrollArea

from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
    interaction as timeline_interaction,
)
from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
    viewport as timeline_viewport,
)
from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
    widget as timeline_widget_module,
)
from sli_ui_toolkit.ui.widgets.composite.timeline_widget.strip_band import StripBand


class CountingBand(StripBand):
    """Records every ``place``/``set_view`` the timeline pushes into the band."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.places: list[tuple[QRect, float]] = []
        self.views: list[tuple[int, float]] = []

    def place(self, rect) -> None:
        owner = self.parent()
        self.places.append((QRect(rect), float(owner._zoom_level)))
        return super().place(rect)

    def set_view(self, scroll_x: int, zoom: float) -> None:
        self.views.append((int(scroll_x), float(zoom)))
        return super().set_view(scroll_x, zoom)


class ProbeTimeline(timeline_widget_module.TimelineWidget):
    """Counts the commit funnel and the width writes (both are gesture costs)."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.commits: list[str] = []
        self.width_writes: list[int] = []

    def _commitState(self, nxt, source=""):
        self.commits.append(source)
        return super()._commitState(nxt, source=source)

    def setFixedWidth(self, width):  # noqa: N802 — Qt's name
        self.width_writes.append(int(width))
        return super().setFixedWidth(width)


def _snaps(n: int = 120):
    return [SimpleNamespace(timestamp=float(i)) for i in range(n)]


@pytest.fixture
def hosted(qapp, monkeypatch):
    """A fitted, hosted timeline with the GPU band replaced by a counting one."""
    monkeypatch.setattr(timeline_widget_module, "StripBand", CountingBand)
    area = QScrollArea()
    area.setWidgetResizable(False)
    widget = ProbeTimeline()
    widget.resize(800, 240)
    area.setWidget(widget)
    area.resize(800, 240)
    area.show()
    qapp.processEvents()
    widget.set_data(_snaps(), fps=30)
    widget._layout_settle.cancel()  # the ingest fit, run explicitly below
    widget.fit_view()
    widget._commitState(widget._current_state(), source="setup")
    qapp.processEvents()
    widget._layout_settle.cancel()
    band = widget.enable_strip_band(render=lambda _command_buffer, _band: None)
    assert isinstance(band, CountingBand)
    qapp.processEvents()
    _reset(widget, band)
    try:
        yield area, widget, band
    finally:
        area.close()
        area.deleteLater()
        qapp.processEvents()


def _reset(widget, band) -> None:
    widget.commits.clear()
    widget.width_writes.clear()
    band.places.clear()
    band.views.clear()


def _ctrl_wheel(widget, delta_y: int, x: float = 400.0) -> None:
    widget.wheelEvent(
        QWheelEvent(
            QPointF(x, 100.0),
            QPointF(x, 100.0),
            QPoint(0, 0),
            QPoint(0, int(delta_y)),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.ControlModifier,
            Qt.ScrollPhase.NoScrollPhase,
            False,
        )
    )


# --- 1. one zoom tick: one width write, one place, one commit ---------------


@pytest.mark.parametrize("driver", ["api", "wheel"])
def test_one_zoom_tick_is_one_width_write_one_place_one_commit(qapp, hosted, driver):
    area, widget, band = hosted
    zoom_before = widget._zoom_level
    scroll_before = widget._state.scroll_x

    if driver == "api":
        widget.set_zoom(min(1.0, zoom_before * 1.5), anchor="center")
    else:
        _ctrl_wheel(widget, 120)  # cursor-anchored: flushed on the next turn
    qapp.processEvents()
    qapp.processEvents()

    assert widget._zoom_level != pytest.approx(zoom_before)
    # exactly ONE width write, and it is the final content width
    assert widget.width_writes == [widget.width()], widget.width_writes
    # exactly ONE band place / view push
    assert len(band.places) == 1, band.places
    assert len(band.views) == 1, band.views
    # exactly ONE commit through the single funnel
    assert len(widget.commits) == 1, widget.commits
    assert widget.commits == ["apiSetZoom" if driver == "api" else "wheelZoom"]
    # the band was pushed the committed view, not the pre-commit one
    assert band.views[0] == (widget._state.scroll_x, widget._zoom_level)
    assert band.places[0][1] == pytest.approx(widget._zoom_level)
    # the scroll anchor actually moved, so the stale-place assert is not vacuous
    assert widget._state.scroll_x != scroll_before


# --- 2. one live resize turn on a fitted view: one commit -------------------


def _resize_event():
    return SimpleNamespace(type=lambda: QEvent.Type.Resize)


def test_one_fitted_live_resize_turn_is_one_commit(qapp, hosted):
    area, widget, band = hosted
    assert widget._zoom_level == pytest.approx(widget._fitted_zoom), "probe is not fitted"

    area.resize(1000, 240)
    qapp.processEvents()  # the viewport Resize reaches the installed filter
    # deliver the filter verdict explicitly too: one queued pass per turn
    timeline_interaction.event_filter(widget, area.viewport(), _resize_event())
    timeline_interaction.event_filter(widget, area.window(), _resize_event())
    qapp.processEvents()
    qapp.processEvents()
    # ... and the settle-gate flush of the same turn: it used to commit again
    widget._layout_settle.cancel()
    widget._on_layout_settle()
    qapp.processEvents()

    assert widget.commits == ["liveResize"], widget.commits
    # The re-fit is still load-bearing: a fitted view stays fitted.
    assert widget._zoom_level == pytest.approx(widget._fitted_zoom)
    assert widget._zoom_level == pytest.approx(
        timeline_viewport.calculate_min_zoom(widget)
    )
    # ... and no band place carries a pre-commit zoom
    assert band.places, "the live resize never placed the band"
    assert [zoom for _rect, zoom in band.places] == [
        pytest.approx(widget._zoom_level)
    ] * len(band.places)


# --- 3. a programmatic range change is not a user scroll --------------------


def test_programmatic_range_change_commits_nothing(qapp, hosted):
    area, widget, band = hosted
    bar = area.horizontalScrollBar()
    widget._needs_fit_view = True  # the protected ingest fit

    bar.setRange(int(bar.minimum()), int(bar.maximum()) + 100)
    qapp.processEvents()

    assert widget.commits == [], widget.commits
    assert widget._needs_fit_view is True, "a range change retired the ingest fit"
    assert band.views == [], band.views


# --- 4. the stale place: the band never sees the pre-commit view ------------


def test_the_band_never_sees_the_pre_commit_zoom_or_scroll(qapp, hosted):
    area, widget, band = hosted
    zoom_before = widget._zoom_level
    scroll_before = widget._state.scroll_x

    _ctrl_wheel(widget, 120, x=500.0)  # cursor anchor: scroll moves with it
    qapp.processEvents()
    qapp.processEvents()

    assert widget._zoom_level != pytest.approx(zoom_before)
    assert band.views, "the zoom tick never pushed a view into the band"
    # Every view the band received is the committed one: no call may carry the
    # pre-commit pair (that was the resizeEvent place inside the width pin).
    assert (scroll_before, zoom_before) not in band.views
    assert band.views == [(widget._state.scroll_x, widget._zoom_level)]
    # the last place's zoom is the live (committed) zoom
    assert band.places[-1][1] == pytest.approx(widget._zoom_level)
