"""`RichTextView` — the scrolling rich-text pane a host uses where it had a read-only `QTextEdit`.

Hosts kept stock editors for three panes: release notes (`setMarkdown`), a system panel (`setText`), a video panel
(`setFontPointSize` + `setText` with HTML). The calls are pinned here, plus the two properties that make it a *rich*
view rather than a label: a real caret that blinks while focused and disappears on focus out, and a body height that
follows the engine's painted content at the viewport width (so a short body never scrolls at all).
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QFontInfo, QMouseEvent


def _view(qapp, size=(400, 120)):
    from sli_ui_toolkit.widgets import RichTextView

    view = RichTextView()
    view.resize(*size)
    view.show()
    qapp.processEvents()
    return view


def _canvas(view):
    canvas = view.label.canvas()
    assert canvas is not None
    return canvas


def _mouse(kind, point, *, button, buttons):
    return QMouseEvent(
        kind,
        QPointF(point),
        QPointF(point),  # global: the widget is the event target, no window offset needed
        button,
        buttons,
        Qt.KeyboardModifier.NoModifier,
    )


# -- content ------------------------------------------------------------


def test_plain_text_becomes_readable_lines(qapp):
    view = _view(qapp)
    view.setText("first\nsecond")
    assert "first" in view.toPlainText() and "second" in view.toPlainText()
    assert "\n" in view.toPlainText(), "a newline is a line break, not a space"


def test_markdown_is_rendered(qapp):
    view = _view(qapp)
    view.setMarkdown("# Heading\n\nbody text")
    plain = view.toPlainText()
    assert "Heading" in plain and "body" in plain


def test_html_passes_through(qapp):
    view = _view(qapp)
    view.setHtml("<p><b>bold</b> and <i>italic</i></p>")
    assert "bold" in view.toPlainText()
    assert "<" not in view.toPlainText()


def test_html_styling_survives_as_rich_text(qapp):
    """HTML is rendered by Qt's rich layout, not shown as tags or flattened to plain."""
    view = _view(qapp)
    view.setHtml('<p><span style="color:#ff0000">red</span> plain</p>')
    qapp.processEvents()
    image = view.label.grab().toImage()
    reds = sum(
        1
        for y in range(image.height())
        for x in range(image.width())
        if image.pixelColor(x, y).red() > 180 and image.pixelColor(x, y).green() < 90
    )
    assert reds > 20, "the inline colour of the HTML body must reach the painted surface"


def test_plain_text_reads_through_the_markup(qapp):
    # A structural dumper (and the host's own glue) asks for plain text; returning the stored HTML made a migrated pane
    # report its whole markup as content.
    view = _view(qapp)
    view.setHtml("<p><b>bold</b></p><p>second</p>")
    plain = view.toPlainText()
    assert "<" not in plain
    assert "bold" in plain and "second" in plain
    assert view.text() == plain


# -- caret and selection ------------------------------------------------


def test_caret_blinks_while_focused_and_is_gone_after_focus_out(qapp):
    """The caret is painted only while the surface has focus, and it toggles.

    Falsification: a `QLabel` pane had no caret at all — selected text sat
    in a static wash and nothing blinked.
    """
    view = _view(qapp)
    view.setText("alpha beta gamma delta")
    qapp.processEvents()
    canvas = _canvas(view)
    canvas.setFocus()
    qapp.processEvents()
    assert canvas.hasFocus()
    assert canvas._caret_blink.isActive(), "focus starts the 500 ms blink timer"
    assert canvas._caret_blink.interval() == 500

    canvas._caret_on = True
    canvas.update()
    qapp.processEvents()
    lit = canvas.grab().toImage()
    canvas._toggle_caret_blink()  # the timer's own tick, no wall-clock sleep
    assert canvas._caret_on is False
    qapp.processEvents()
    dark = canvas.grab().toImage()
    assert lit != dark, "blink-off must remove the caret pixels"
    canvas._toggle_caret_blink()

    canvas.clearFocus()
    qapp.processEvents()
    assert not canvas._caret_blink.isActive()
    canvas._caret_on = True
    canvas.update()
    qapp.processEvents()
    assert canvas.grab().toImage() == dark, "an unfocused pane paints no caret"


def test_mouse_drag_selects_text_and_ctrl_c_copies_it(qapp):
    view = _view(qapp)
    view.setText("alpha beta gamma delta")
    qapp.processEvents()
    canvas = _canvas(view)
    left, top, _right, _bottom = view.padding()
    start = QPoint(left + 3, top + 8)
    end = QPoint(left + 90, top + 8)
    canvas.mousePressEvent(_mouse(QEvent.Type.MouseButtonPress, start, button=Qt.MouseButton.LeftButton, buttons=Qt.MouseButton.LeftButton))
    canvas.mouseMoveEvent(_mouse(QEvent.Type.MouseMove, end, button=Qt.MouseButton.NoButton, buttons=Qt.MouseButton.LeftButton))
    canvas.mouseReleaseEvent(_mouse(QEvent.Type.MouseButtonRelease, end, button=Qt.MouseButton.LeftButton, buttons=Qt.MouseButton.NoButton))
    qapp.processEvents()
    assert canvas.selected_plain_text()
    assert canvas.selected_plain_text() in "alpha beta gamma delta"

    copied = canvas.copy_selection()
    assert copied is True
    from PySide6.QtWidgets import QApplication

    clipboard = QApplication.clipboard().text()
    assert clipboard and clipboard in "alpha beta gamma delta"


def test_double_click_selects_a_word(qapp):
    view = _view(qapp)
    view.setText("alpha beta")
    qapp.processEvents()
    canvas = _canvas(view)
    left, top, _right, _bottom = view.padding()
    canvas._rich_mouse_press(
        _mouse(
            QEvent.Type.MouseButtonPress,
            QPoint(left + 3, top + 8),
            button=Qt.MouseButton.LeftButton,
            buttons=Qt.MouseButton.LeftButton,
        ),
        word=True,
    )
    assert canvas.selected_plain_text().strip() in ("alpha", "beta")


# -- geometry -----------------------------------------------------------


def test_short_body_has_a_zero_scroll_range(qapp):
    """A body shorter than the viewport must not scroll it into emptiness."""
    view = _view(qapp, size=(400, 220))
    view.setText("one short line")
    qapp.processEvents()
    qapp.processEvents()
    bar = view.verticalScrollBar()
    assert bar.maximum() == 0, f"short body scrolled {bar.maximum()} px"
    assert view.label.height() < view._scroll.viewport().height()


def test_long_body_scrolls(qapp):
    view = _view(qapp)
    view.setMarkdown("\n\n".join(f"line {index}" for index in range(200)))
    qapp.processEvents()
    qapp.processEvents()
    assert view.label.height() > view.height()
    assert view.verticalScrollBar().maximum() > 0


def test_label_height_follows_the_painted_ink(qapp):
    """The fixed height IS the painted content height (the engine measures it).

    Falsification: a plain-text hint for a rich body claimed 2844 px where
    the pane painted 1776 px, so the pane scrolled through pages of nothing.
    """
    view = _view(qapp, size=(400, 120))
    view.setMarkdown("\n\n".join(f"line {index} of the body text" for index in range(40)))
    qapp.processEvents()
    qapp.processEvents()
    image = view.label.grab().toImage()
    background = image.pixelColor(1, 1)
    ink_rows = [
        y
        for y in range(image.height())
        if any(image.pixelColor(x, y) != background for x in range(image.width()))
    ]
    assert ink_rows, "the body painted nothing"
    empty_below = view.label.height() - (max(ink_rows) + 1)
    assert 0 <= empty_below <= view.padding()[3] + 4, (
        f"{empty_below} px of empty band below the last ink row"
    )


# -- API surface --------------------------------------------------------


def test_text_size_in_pixels_is_not_converted_through_dpi(qapp):
    # A host that states pixel sizes cannot use point sizes: `setFontPointSize(12)` rendered 16 px on a 96 dpi screen
    # and every line of a migrated pane grew.
    view = _view(qapp)
    view.setText("body")
    view.setTextPixelSize(12)
    assert QFontInfo(_canvas(view)._rich.font()).pixelSize() == 12
    view.setTextPixelSize(15)
    assert QFontInfo(_canvas(view)._rich.font()).pixelSize() == 15


def test_a_size_set_before_the_content_still_reaches_the_body(qapp):
    """A Designer sets the size before the glue sets the text; the size must survive that order."""
    view = _view(qapp)
    view.setTextPixelSize(13)
    view.setText("body")
    assert QFontInfo(_canvas(view)._rich.font()).pixelSize() == 13


def test_host_call_surface_still_answers(qapp):
    """Every call a migrated `QTextEdit` host makes keeps working."""
    view = _view(qapp)
    view.setHtml("<p>html</p>")
    view.setPlainText("plain")
    view.setText("text")
    view.setMarkdown("# md")
    view.append("appended")
    assert "appended" in view.text()
    view.clear()
    assert view.text() == ""
    view.setReadOnly(True)
    view.setSizeAdjustPolicy(0)
    view.setLineWrapMode(0)
    view.setFontPointSize(10.0)
    view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    assert view.verticalScrollBar() is not None
    assert view.toPlainText() == ""
    assert view.text() == ""
    assert view.padding() == (10, 5, 10, 5)
    view.set_padding((4, 4, 4, 4))
    assert view.padding() == (4, 4, 4, 4)
    # The pane's plate is the pane's own (`SurfacePanel`): the body must not
    # paint a surface over it.
    assert view.label.panel_fill is False


def test_no_stylesheet(qapp):
    view = _view(qapp)
    assert view.styleSheet() == ""
    assert view.label.styleSheet() == ""
    try:
        view.setStyleSheet("color: red")
    except ValueError:
        pass
    else:  # pragma: no cover - the refusal is the contract
        raise AssertionError("a pane stylesheet must be refused")
