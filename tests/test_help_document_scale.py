"""Help document text scales with the UiScale factor (live re-layout).

Regression: the help/Image Properties bodies built their fonts from raw
``QFont()`` + fixed px constants and never subscribed to
``UiScale.scale_changed``, so the whole document stayed at design size
when the interface scale was raised. Fonts now resolve through
``ui_font(pixel_size=...)`` (scaled exactly once) and the canvas
re-layouts on every factor change.
"""

from __future__ import annotations

import pytest

from sli_ui_toolkit.managers import UiScale
from sli_ui_toolkit.ui.widgets.composite.help_document.canvas import HelpDocumentBodyCanvas
from sli_ui_toolkit.widgets import HelpDocumentView


@pytest.fixture(autouse=True)
def _reset_ui_scale():
    yield
    UiScale.get_instance().set_factor(1.0)


def _canvas(view: HelpDocumentView) -> HelpDocumentBodyCanvas:
    canvas = view.findChild(HelpDocumentBodyCanvas)
    assert canvas is not None
    return canvas


def test_help_document_reflows_and_grows_with_ui_scale(qapp, qtbot):
    view = HelpDocumentView(show_toc=True, toc_title="On this page")
    qtbot.addWidget(view)
    view.resize(640, 480)
    view.set_markdown("## Big Title\n\nSome paragraph text.\n")
    qtbot.wait(10)
    canvas = _canvas(view)

    height_1 = canvas.minimumHeight()
    text_height_1 = canvas._layout.height

    UiScale.get_instance().set_factor(2.0)
    qtbot.wait(10)

    assert canvas._layout.height > text_height_1
    assert canvas.minimumHeight() > height_1

    UiScale.get_instance().set_factor(1.0)
    qtbot.wait(10)
    assert canvas._layout.height == pytest.approx(text_height_1, abs=2)
