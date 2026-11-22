"""Document (markdown) mode carries a visible caret, like the rich body does.

The body is read-only, but a click still has to show where it landed: the selection highlight appears only after the drag
threshold, so a plain click on a character used to look like a dead click (owner, 2026-11-22: "document mode still has no
caret"). Three statements:

* a click places the caret (``DocumentSelection.caret()``) and starts the blink timer;
* ``caret_rect`` maps that offset into the layout's own coordinates, inside the fragment that holds it;
* the caret actually reaches the pixels - the render differs between the two blink phases.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.text.engine.layout.caret import caret_rect
from sli_ui_toolkit.widgets import Text


def _theme(app):
    manager = ThemeManager.get_instance()
    manager.register_palettes(
        {"dialog.text": "#dddddd", "accent": "#0078ff"},
        {"dialog.text": "#dddddd", "accent": "#0078ff"},
    )
    manager.set_theme("dark", app)
    return manager


def _document(app, markup: str = "Hello caret world."):
    widget = Text(markup, mode="document")
    widget.resize(600, 200)
    widget.show()
    for _ in range(6):
        app.processEvents()
    return widget, widget._engine


def _click(app, widget, engine, at: QPoint) -> None:
    event = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPointF(at),
        QPointF(widget.mapToGlobal(at)),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    app.sendEvent(engine, event)
    for _ in range(6):
        app.processEvents()


def test_a_click_in_a_document_places_a_blinking_caret(qapp):
    app = qapp or QApplication.instance() or QApplication([])
    _theme(app)
    widget, engine = _document(app)
    assert engine._doc_selection.caret() is None, "a fresh document has no caret"

    _click(app, widget, engine, QPoint(14, 12))
    assert engine.hasFocus(), "the click must focus the body, or the caret is gated off"
    assert engine._doc_selection.caret() is not None
    assert engine._caret_blink.isActive(), "the caret must blink while the body owns focus"


def test_caret_rect_lands_inside_the_fragment_that_holds_the_offset(qapp):
    app = qapp or QApplication.instance() or QApplication([])
    _theme(app)
    _widget, engine = _document(app)
    layout = engine._document_layout
    assert layout is not None and layout.text_fragments
    frag = layout.text_fragments[0]

    for offset in (frag.global_start, (frag.global_start + frag.global_end) // 2, frag.global_end):
        rect = caret_rect(layout, offset)
        assert rect is not None, f"no caret rect for offset {offset}"
        assert frag.rect.top() <= rect.top() <= frag.rect.bottom(), (offset, rect, frag.rect)
        assert rect.width() > 0 and rect.height() > 0


def test_the_caret_reaches_the_pixels(qapp):
    app = qapp or QApplication.instance() or QApplication([])
    _theme(app)
    widget, engine = _document(app)
    _click(app, widget, engine, QPoint(14, 12))

    engine._caret_on = True
    on = engine.grab().toImage()
    engine._caret_on = False
    off = engine.grab().toImage()
    assert on != off, "the caret phase does not change a single pixel - nothing was painted"
