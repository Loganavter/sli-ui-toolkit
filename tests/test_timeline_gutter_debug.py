"""Gutter debug traces: [timeline-gutter] lines fire with the gate open, stay
silent with it closed, and always format cleanly.

Diagnostic purpose: the gutter visibly lags zoom by ~1 frame. The traces
carry a monotonic tick so the order of zoom commit -> synchronous band
repaint -> async full paint -> host-scroll correction can be read off the
log: look for DRIFT (scrollbar moved between band-rect computation and the
sync repaint) and SKEW (overlay arg vs live scrollbar at paint time).
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

from PySide6.QtCore import QEvent, QPointF, QRect, Qt
from PySide6.QtGui import QMouseEvent

from sli_ui_toolkit.ui.widgets.composite.timeline_widget import debug as timeline_debug
from sli_ui_toolkit.ui.widgets.composite.timeline_widget.widget import (
    TimelineWidget,
)


def _snaps(n=40):
    return [
        SimpleNamespace(timestamp=float(i), channels={}) for i in range(n)
    ]


def _make(qapp) -> TimelineWidget:
    widget = TimelineWidget(snapshots=_snaps())
    widget.resize(800, 240)
    widget.show()
    qapp.processEvents()
    qapp.processEvents()
    widget._layout_settle.cancel()
    widget.fit_view()
    qapp.processEvents()
    return widget


class _Capture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records: list = []

    def emit(self, record):
        self.records.append(record)


def _press(x: float, y: float = 100.0) -> QMouseEvent:
    return QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(float(x), float(y)),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


def _move(x: float, y: float = 100.0) -> QMouseEvent:
    return QMouseEvent(
        QEvent.Type.MouseMove,
        QPointF(float(x), float(y)),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


def _release(x: float, y: float = 100.0) -> QMouseEvent:
    return QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        QPointF(float(x), float(y)),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )


def _drive(widget) -> None:
    widget.set_zoom(2.0)
    widget.mousePressEvent(_press(float(widget.LEFT_GUTTER)))
    assert widget._is_resizing_gutter
    widget.mouseMoveEvent(_move(float(widget.LEFT_GUTTER) + 20.0))
    widget.mouseReleaseEvent(_release(float(widget.LEFT_GUTTER) + 20.0))
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
        interaction as timeline_interaction,
    )

    timeline_interaction.host_scroll(widget)
    from PySide6.QtGui import QPainter

    painter = QPainter(widget)
    try:
        from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
            render as timeline_render,
        )

        timeline_render.paint_timeline(widget, painter, SimpleNamespace(rect=lambda: QRect(0, 0, 800, 240)))
    finally:
        painter.end()


def test_gutter_traces_fire_with_gate_open(qapp, monkeypatch):
    monkeypatch.setenv("SLI_TIMELINE_DEBUG", "1")
    assert timeline_debug._timeline_debug_enabled()
    logger = logging.getLogger("sli_ui_toolkit.timeline")
    handler = _Capture()
    old_level = logger.level
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    try:
        widget = _make(qapp)
        _drive(widget)
        widget.close()
    finally:
        logger.removeHandler(handler)
        logger.setLevel(old_level)
    gutter = [r for r in handler.records if "[timeline-gutter]" in r.getMessage()]
    assert gutter, "expected [timeline-gutter] records with the gate open"
    texts = [r.getMessage() for r in gutter]
    assert any("zoom-commit" in t for t in texts)
    assert any("zoom-band" in t for t in texts)
    assert any("paint-gutter" in t for t in texts)
    assert any("overlay" in t for t in texts)
    assert any("gutter-drag" in t or "host-scroll" in t for t in texts)
    for record in gutter:
        assert "tick=" in record.getMessage()


def test_gutter_traces_silent_with_gate_closed(qapp, monkeypatch):
    monkeypatch.delenv("SLI_TIMELINE_DEBUG", raising=False)
    monkeypatch.delenv("IMGSLI_TIMELINE_DEBUG", raising=False)
    monkeypatch.delenv("IMGSLI_VIDEO_EDITOR_DEBUG", raising=False)
    assert not timeline_debug._timeline_debug_enabled()
    logger = logging.getLogger("sli_ui_toolkit.timeline")
    handler = _Capture()
    old_level = logger.level
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    try:
        widget = _make(qapp)
        _drive(widget)
        widget.close()
    finally:
        logger.removeHandler(handler)
        logger.setLevel(old_level)
    assert not [r for r in handler.records if "[timeline-gutter]" in r.getMessage()]
