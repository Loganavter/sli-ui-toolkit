"""SurfaceScrollArea paints its scroll surface from a theme token.

Stock ``QScrollArea`` viewports and ``setWidget``-flipped content widgets
auto-fill the QPalette ``Window`` role, which hosts keep darker than the
dialog surface token (dark ``Window`` ``#1e1e1e`` vs ``dialog.background``
``#2b2b2b``) — transparent content then renders on a near-black substrate.
``SurfaceScrollArea`` sets the surface as the scroll area's own
``background-color`` stylesheet (survives ``QStyle::polish``, re-tinted on
``theme_changed``) with the viewport + content pinned transparent via
attributes — a stylesheet on the viewport/content would force a full
repaint per scroll step instead of Qt's scroll blit, and a ``paintEvent``
fill is impossible on ``QAbstractScrollArea`` (inactive ``QPainter``). The
corner mask is disabled for the same reason. ``surface_token=None`` clears
the stylesheet so an ancestor paints the surface.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QVBoxLayout, QWidget

from sli_ui_toolkit import ThemeManager
from sli_ui_toolkit.widgets import SurfaceScrollArea

_LIGHT = {"Window": "#101010", "surface.background": "#202020"}
_DARK = {"Window": "#1e1e1e", "surface.background": "#2b2b2b"}


class _SolidHost(QWidget):
    """Paints a flat surface color — the transparent-mode ancestor."""

    def __init__(self, color: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._color = QColor(color)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), self._color)
        painter.end()


@pytest.fixture
def themed(qapp):
    tm = ThemeManager.get_instance()
    tm.register_palettes(_LIGHT, _DARK)
    tm.set_theme("light", qapp, await_ripples=False)
    tm._flush_pending_theme()  # type: ignore[attr-defined]
    yield tm
    tm.set_theme("light", qapp, await_ripples=False)
    tm._flush_pending_theme()  # type: ignore[attr-defined]


def _rendered(widget: QWidget, width: int, height: int, fill: str = "#ffffff") -> QImage:
    """Render *widget* into a pre-filled image (transparent areas keep the
    fill) — ``grab()`` would report transparent black for unpainted pixels."""
    img = QImage(width, height, QImage.Format.Format_RGB32)
    img.fill(QColor(fill))
    painter = QPainter(img)
    widget.render(painter, QPoint(0, 0))
    painter.end()
    return img


def _pixel(widget: QWidget, width: int, height: int, fill: str = "#ffffff") -> str:
    return _rendered(widget, width, height, fill).pixelColor(2, 2).name()


def _make_area(qtbot, *, token: str | None, host_color: str) -> tuple[_SolidHost, SurfaceScrollArea, QWidget]:
    host = _SolidHost(host_color)
    qtbot.addWidget(host)
    host.resize(300, 200)
    layout = QVBoxLayout(host)
    layout.setContentsMargins(0, 0, 0, 0)
    area = SurfaceScrollArea(surface_token=token)
    content = QWidget()
    area.setWidget(content)
    layout.addWidget(area)
    host.show()
    return host, area, content


def test_token_mode_paints_surface_from_token(qapp, qtbot, themed):
    host, area, content = _make_area(qtbot, token="dialog.background", host_color="#111111")
    qapp.processEvents()
    assert "background-color: #202020;" in area.styleSheet()
    assert area.viewport().styleSheet() == ""
    assert content.styleSheet() == ""
    assert not area.viewport().autoFillBackground()
    assert not content.autoFillBackground()
    assert _pixel(host, 300, 200) == "#202020"


def test_transparent_mode_shows_ancestor_paint(qapp, qtbot, themed):
    host, area, content = _make_area(qtbot, token=None, host_color="#111111")
    qapp.processEvents()
    assert area.styleSheet() == ""
    assert _pixel(host, 300, 200) == "#111111"
    assert not area.viewport().autoFillBackground()
    assert not content.autoFillBackground()


def test_transparent_pinning_survives_late_set_widget(qapp, qtbot, themed):
    host = _SolidHost("#111111")
    qtbot.addWidget(host)
    host.resize(300, 200)
    layout = QVBoxLayout(host)
    layout.setContentsMargins(0, 0, 0, 0)
    area = SurfaceScrollArea(surface_token=None)
    layout.addWidget(area)
    content = QWidget()
    area.setWidget(content)
    host.show()
    qapp.processEvents()
    assert not content.autoFillBackground()
    assert _pixel(host, 300, 200) == "#111111"


def test_surface_survives_unpolish_polish(qapp, qtbot, themed):
    host, area, _content = _make_area(qtbot, token="dialog.background", host_color="#111111")
    host.show()
    qapp.processEvents()
    area.style().unpolish(area)
    area.style().polish(area)
    qapp.processEvents()
    assert not area.viewport().autoFillBackground()
    assert _pixel(host, 300, 200) == "#202020"


def test_surface_re_tints_on_theme_switch(qapp, qtbot, themed):
    host, area, _content = _make_area(qtbot, token="dialog.background", host_color="#111111")
    qapp.processEvents()
    themed.set_theme("dark", qapp, await_ripples=False)
    themed._flush_pending_theme()  # type: ignore[attr-defined]
    qapp.processEvents()
    assert "background-color: #2b2b2b;" in area.styleSheet()
    assert _pixel(host, 300, 200) == "#2b2b2b"


def test_surface_switches_to_transparent_at_runtime(qapp, qtbot, themed):
    host, area, _content = _make_area(qtbot, token="dialog.background", host_color="#111111")
    qapp.processEvents()
    area.set_surface_token(None)
    qapp.processEvents()
    assert area.styleSheet() == ""
    assert _pixel(host, 300, 200) == "#111111"
    area.set_surface_token("dialog.background")
    qapp.processEvents()
    assert "background-color: #202020;" in area.styleSheet()
    assert _pixel(host, 300, 200) == "#202020"


def test_no_corner_mask(qapp, qtbot, themed):
    host, area, _content = _make_area(qtbot, token="dialog.background", host_color="#111111")
    qapp.processEvents()
    assert area.viewport().mask().isEmpty()