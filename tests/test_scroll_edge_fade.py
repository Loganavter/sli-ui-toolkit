"""The clipped edge of a scroll area fades instead of cutting the content.

Google-pane behaviour the owner asked for (2026-11-22): the last pixels of a clipped line fade into the surface so the eye
reads "it continues" instead of "the text ends here". Four statements: the fade appears only on the side that continues,
it disappears when there is nothing more, it stays off unless the host enables it, and the colour is the host's.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.ui.widgets.atomic.minimalist_scrollbar import OverlayScrollArea


def _area(app, content_height: int):
    area = OverlayScrollArea()
    content = QWidget()
    content.setMinimumHeight(content_height)
    area.setWidget(content)
    area.resize(300, 200)
    area.show()
    for _ in range(6):
        app.processEvents()
    return area


def test_the_continuing_side_fades(qapp):
    area = _area(qapp, 900)
    area.set_edge_fade_enabled(True)
    for _ in range(4):
        qapp.processEvents()

    fade = area._edge_fade
    assert fade.isVisible()
    assert fade._top is False, "nothing is clipped above the first screen"
    assert fade._bottom is True, "the content continues below, so the bottom edge must fade"


def test_scrolling_to_the_end_moves_the_fade_to_the_top(qapp):
    area = _area(qapp, 900)
    area.set_edge_fade_enabled(True)
    bar = area.verticalScrollBar()
    bar.setValue(bar.maximum())
    for _ in range(4):
        qapp.processEvents()

    fade = area._edge_fade
    assert fade._top is True
    assert fade._bottom is False


def test_content_that_fits_has_no_fade(qapp):
    area = _area(qapp, 40)
    area.set_edge_fade_enabled(True)
    for _ in range(4):
        qapp.processEvents()
    assert not area._edge_fade.isVisible()


def test_the_fade_is_opt_in_and_takes_the_host_colour(qapp):
    area = _area(qapp, 900)
    assert area.edge_fade_enabled() is False
    assert not area._edge_fade.isVisible()

    area.set_edge_fade_enabled(True)
    area.set_edge_fade_colour(QColor("#123456"))
    assert area.edge_fade_colour() == QColor("#123456")
