"""The text engine lives under ``ui/widgets/text/engine`` — and only there.

The old ``composite/text_view`` + ``composite/help_document`` packages are
deleted (text-unification wave C); the engine classes are the single
implementation, and ``Text`` hosts them. These tests guard both facts: a
re-created old path fails the import gate, and the hosted surface is the
engine class itself (no second wrapper implementation).
"""

from __future__ import annotations

import importlib.util

from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.ui.widgets.text import Text
from sli_ui_toolkit.ui.widgets.text.engine import canvas as text_canvas


def _grab(widget: QWidget, width: int = 240, height: int = 80):
    widget.resize(width, height)
    widget.show()
    widget.repaint()
    image = widget.grab().toImage()
    widget.hide()
    return image


def test_old_text_composite_packages_are_gone():
    """No compatibility package may come back 'for later'."""
    assert (
        importlib.util.find_spec("sli_ui_toolkit.ui.widgets.composite.text_view")
        is None
    )
    assert (
        importlib.util.find_spec("sli_ui_toolkit.ui.widgets.composite.help_document")
        is None
    )


def test_text_code_mode_pixels_match_the_engine(qapp):
    """The hosted surface must not repaint differently from the bare engine."""
    widget = Text("print value\nsecond line", mode="code")
    core = text_canvas.TextCanvasCore("print value\nsecond line")
    assert _grab(widget) == _grab(core)


def test_text_code_mode_hosts_the_core(qapp):
    widget = Text("x = 1", mode="code", editable=True)
    assert type(widget._engine) is text_canvas.TextCanvasCore
    assert widget.canvas() is widget._engine


def test_text_document_mode_hosts_the_core(qapp):
    widget = Text("# Title\n\nBody", mode="document")
    assert type(widget._engine) is text_canvas.TextCanvasCore
    assert widget.canvas() is widget._engine
