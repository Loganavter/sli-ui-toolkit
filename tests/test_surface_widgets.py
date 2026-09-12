"""Surface regressions: CalendarWidget and TextView.

Both widgets used to render their background on the QPalette ``Window``
role (darker than the ``dialog.background`` token hosts paint); now
``CalendarWidget`` paints its own surface from the resolved token and
``TextView`` pins viewport + canvas transparent so the host surface shows
behind the frame overlay.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QVBoxLayout, QWidget

from sli_ui_toolkit import ThemeManager
from sli_ui_toolkit.widgets import CalendarWidget, TextView

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
    img = QImage(width, height, QImage.Format.Format_RGB32)
    img.fill(QColor(fill))
    painter = QPainter(img)
    widget.render(painter, QPoint(0, 0))
    painter.end()
    return img


def test_calendar_widget_paints_surface_from_bg_token(qapp, qtbot, themed):
    cal = CalendarWidget()
    qtbot.addWidget(cal)
    cal.resize(400, 300)
    cal.show()
    qapp.processEvents()
    img = cal.grab().toImage()
    center = img.pixelColor(cal.width() // 2, cal.height() // 2).name()
    assert center == "#202020"


def test_text_view_viewport_shows_host_background_by_default(qapp, qtbot, themed):
    host = _SolidHost("#111111")
    qtbot.addWidget(host)
    host.resize(300, 200)
    layout = QVBoxLayout(host)
    layout.setContentsMargins(0, 0, 0, 0)
    view = TextView("")
    layout.addWidget(view)
    host.show()
    qapp.processEvents()
    img = _rendered(host, 300, 200)
    assert img.pixelColor(2, 2).name() == "#111111"
    assert img.pixelColor(30, 30).name() == "#111111"


def test_text_view_panel_fill_still_paints_raised_well(qapp, qtbot, themed):
    host = _SolidHost("#111111")
    qtbot.addWidget(host)
    host.resize(300, 200)
    layout = QVBoxLayout(host)
    layout.setContentsMargins(0, 0, 0, 0)
    view = TextView("")
    layout.addWidget(view)
    host.show()
    qapp.processEvents()

    view.set_panel_fill(QColor("#202020"))
    qapp.processEvents()
    img = _rendered(host, 300, 200)
    # Inside the rounded well the fill paints…
    assert img.pixelColor(30, 30).name() == "#202020"
    # …while the masked corner keeps the host surface.
    assert img.pixelColor(1, 1).name() == "#111111"

    view.set_panel_fill(None)
    qapp.processEvents()
    img = _rendered(host, 300, 200)
    assert img.pixelColor(30, 30).name() == "#111111"