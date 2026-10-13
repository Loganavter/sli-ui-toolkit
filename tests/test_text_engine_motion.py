"""P2c: engine modules live under ``ui/widgets/text/engine``; old paths delegate."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.ui.widgets.composite.help_document import canvas as help_canvas_old
from sli_ui_toolkit.ui.widgets.composite.text_view import canvas as text_canvas_old
from sli_ui_toolkit.ui.widgets.composite.text_view import markdown as markdown_old
from sli_ui_toolkit.ui.widgets.composite.text_view.layout import paint as layout_paint_old
from sli_ui_toolkit.ui.widgets.text import Text
from sli_ui_toolkit.ui.widgets.text.engine import canvas as text_canvas_new
from sli_ui_toolkit.ui.widgets.text.engine import document_canvas as help_canvas_new
from sli_ui_toolkit.ui.widgets.text.engine import markdown as markdown_new
from sli_ui_toolkit.ui.widgets.text.engine.layout import paint as layout_paint_new


def _grab(widget: QWidget, width: int = 240, height: int = 80):
    widget.resize(width, height)
    widget.show()
    widget.repaint()
    image = widget.grab().toImage()
    widget.hide()
    return image


def test_old_text_canvas_is_thin_subclass_of_moved_core(qapp):
    assert issubclass(text_canvas_old.TextCanvas, text_canvas_new.TextCanvasCore)
    assert text_canvas_old.TextCanvas.__name__ == "TextCanvas"
    assert text_canvas_old.TextCanvas.__module__ == text_canvas_old.__name__
    assert text_canvas_old.__all__ == ["TextCanvas", "Position"]


def test_old_help_canvas_is_thin_subclass_of_moved_core(qapp):
    assert issubclass(help_canvas_old.HelpDocumentBodyCanvas, help_canvas_new.HelpDocumentBodyCore)
    assert help_canvas_old.HelpDocumentBodyCanvas.__name__ == "HelpDocumentBodyCanvas"


def test_old_module_functions_are_the_moved_objects(qapp):
    assert markdown_old.parse_help_blocks is markdown_new.parse_help_blocks
    assert markdown_old.spans_to_plain is markdown_new.spans_to_plain
    assert layout_paint_old.paint_layout is layout_paint_new.paint_layout
    assert help_canvas_old.markdown_for_selection is help_canvas_new.markdown_for_selection


def test_old_canvas_pixels_match_core(qapp):
    old = text_canvas_old.TextCanvas("print value\nsecond line")
    core = text_canvas_new.TextCanvasCore("print value\nsecond line")
    assert _grab(old) == _grab(core)


def test_text_code_mode_hosts_the_core(qapp):
    widget = Text("x = 1", mode="code", editable=True)
    assert type(widget._engine) is text_canvas_new.TextCanvasCore
    assert not isinstance(widget._engine, text_canvas_old.TextCanvas)


def test_text_document_mode_hosts_the_core(qapp):
    widget = Text("# Title\n\nBody", mode="document")
    assert type(widget._engine) is text_canvas_new.TextCanvasCore


def test_falsification_wrapper_is_not_the_core(qapp):
    # If the old name were re-bound to the core (no wrapper), the name check fails.
    assert text_canvas_old.TextCanvas is not text_canvas_new.TextCanvasCore
    assert help_canvas_old.HelpDocumentBodyCanvas is not help_canvas_new.HelpDocumentBodyCore
    assert text_canvas_old.TextCanvas.__name__ == "TextCanvas"
    assert text_canvas_new.TextCanvasCore.__name__ == "TextCanvasCore"
