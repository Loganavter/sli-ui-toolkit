"""`RichTextView` — the scrolling rich-text pane a host uses where it had a read-only `QTextEdit`.

Hosts kept stock editors for three panes: release notes (`setMarkdown`), a system panel (`setText`), a video panel
(`setFontPointSize` + `setText` with HTML). The calls are pinned here, plus the property that makes it a *scrolling*
view: the label's height follows the wrapped content at the viewport width.
"""

from __future__ import annotations

from sli_ui_toolkit.widgets import RichTextView


def _view(qapp, size=(400, 120)) -> RichTextView:
    view = RichTextView()
    view.resize(*size)
    view.show()
    qapp.processEvents()
    return view


def test_plain_text_becomes_readable_lines(qapp):
    view = _view(qapp)
    view.setText("first\nsecond")
    assert "first" in view.toPlainText() and "second" in view.toPlainText()


def test_markdown_is_rendered(qapp):
    view = _view(qapp)
    view.setMarkdown("# Heading\n\nbody text")
    plain = view.toPlainText()
    assert "Heading" in plain and "body" in plain


def test_html_passes_through(qapp):
    view = _view(qapp)
    view.setHtml("<p><b>bold</b> and <i>italic</i></p>")
    assert "bold" in view.toPlainText()


def test_content_taller_than_the_viewport_scrolls(qapp):
    view = _view(qapp)
    before = view.label.height()
    view.setMarkdown("\n\n".join(f"line {index}" for index in range(200)))
    qapp.processEvents()
    assert view.label.height() > view.height()
    assert view.label.height() != before
    bar = view._scroll.verticalScrollBar()
    assert bar.maximum() > 0


def test_font_point_size_reaches_the_label(qapp):
    view = _view(qapp)
    view.setFontPointSize(10)
    assert view.label.font().pointSizeF() == 10.0


def test_no_stylesheet(qapp):
    view = _view(qapp)
    assert view.styleSheet() == ""
    assert view.label.styleSheet() == ""
