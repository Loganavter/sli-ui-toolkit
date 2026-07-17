"""HelpDocumentView canvas renderer tests."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtWidgets import QApplication, QFrame

from sli_ui_toolkit.ui.widgets.composite.help_document.blocks import (
    parse_help_blocks,
)
from sli_ui_toolkit.ui.widgets.composite.help_document.canvas import HelpDocumentBodyCanvas
from sli_ui_toolkit.ui.widgets.composite.help_document.layout.hit_test import hit_test_link
from sli_ui_toolkit.ui.widgets.composite.help_document.text_index import (
    assert_index_matches_blocks,
    build_text_index,
)
from sli_ui_toolkit.ui.widgets.composite.help_document.view import _LinkLabel
from sli_ui_toolkit.widgets import HelpDocumentView


@pytest.fixture
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _canvas(view: HelpDocumentView) -> HelpDocumentBodyCanvas:
    canvas = view.findChild(HelpDocumentBodyCanvas)
    assert canvas is not None
    return canvas


def test_text_index_matches_blocks_to_plain_text():
    blocks = parse_help_blocks(
        "## Title\n\n"
        "Paragraph.\n\n"
        "- one\n"
        "- two\n\n"
        ":::figure{side=right}\n"
        "![alt](x.png)\n"
        "Caption\n"
        ":::\n"
    )
    index = build_text_index(blocks)
    assert_index_matches_blocks(blocks, index)


def test_help_document_view_renders_and_emits_links(qapp, qtbot):
    view = HelpDocumentView(show_toc=True, toc_title="On this page")
    qtbot.addWidget(view)
    view.resize(640, 480)
    received: list[str] = []
    view.linkActivated.connect(received.append)

    view.set_markdown(
        "## Title\n\n"
        "### One {#one}\n\n"
        "### Two {#two}\n\n"
        "Open [docs](help://magnifier#freeze) and press `F1`.\n"
    )
    qapp.processEvents()

    assert view.scroll_to_anchor("one") is not None
    assert view.scroll_to_anchor("two") is not None
    assert view.findChild(QFrame, "HelpDocumentToc") is not None
    root = view.layout()
    assert root is not None
    toc = view.findChild(QFrame, "HelpDocumentToc")
    canvas = _canvas(view)
    assert root.indexOf(toc) < root.indexOf(canvas)

    toc_links = view.findChildren(_LinkLabel)
    assert toc_links

    canvas = _canvas(view)
    frag = canvas._layout.text_fragments[-1]
    assert frag.links
    pos = frag.rect.topLeft() + frag.links[0].rect.center()
    assert hit_test_link(canvas._layout, QPointF(pos)) == "help://magnifier#freeze"
    view.linkActivated.emit("help://magnifier#freeze")
    assert received == ["help://magnifier#freeze"]
    view.deleteLater()


def test_help_document_toc_link_heights_are_even(qapp, qtbot):
    """TOC must not insert uneven vertical gaps between h3 links."""
    view = HelpDocumentView(show_toc=True, toc_title="On this page")
    qtbot.addWidget(view)
    view.resize(640, 480)
    view.set_markdown(
        "## Title\n\n"
        "Intro paragraph for layout width.\n\n"
        "### Short {#short}\n\n"
        "Body.\n\n"
        "### A much longer section title that would wrap if allowed {#long}\n\n"
        "Body.\n\n"
        "### Mid {#mid}\n\n"
        "Body.\n\n"
        "### Also mid length title {#mid2}\n\n"
        "Body.\n\n"
        "### Last {#last}\n\n"
        "Body.\n"
    )
    view.show()
    qapp.processEvents()

    toc = view.findChild(QFrame, "HelpDocumentToc")
    assert toc is not None
    links = toc.findChildren(_LinkLabel)
    assert len(links) == 5
    heights = [link.height() for link in links]
    assert max(heights) - min(heights) <= 4, heights
    ys = sorted(link.y() for link in links)
    gaps = [ys[i + 1] - ys[i] - heights[i] for i in range(len(ys) - 1)]
    assert all(0 <= g <= 8 for g in gaps), gaps
    view.deleteLater()


def test_help_document_view_side_figure_row(qapp, qtbot):
    view = HelpDocumentView(show_toc=False)
    qtbot.addWidget(view)
    view.resize(640, 400)
    view.set_markdown(
        "Intro beside the figure.\n\n"
        ":::figure{side=right width=120}\n"
        "![x](missing.png)\n"
        "Caption\n"
        ":::\n"
    )
    qapp.processEvents()
    canvas = _canvas(view)
    assert canvas._layout.pixmaps
    assert len(canvas._layout.text_fragments) >= 2
    view.deleteLater()


def test_help_document_figure_caption_parses_inline_markdown(qapp, qtbot):
    view = HelpDocumentView(show_toc=False)
    qtbot.addWidget(view)
    view.resize(640, 400)
    view.set_markdown(
        ":::figure{side=right width=120}\n"
        "![x](missing.png)\n"
        "**Toolbar → Export / Video** (placeholder).\n"
        ":::\n"
    )
    qapp.processEvents()
    canvas = _canvas(view)
    caption_frags = [f for f in canvas._layout.text_fragments if f.global_end > f.global_start]
    assert caption_frags
    text = canvas._text_index.text
    assert "Toolbar → Export / Video" in text or "**Toolbar" in text
    view.deleteLater()


def test_help_document_figure_center_aligns(qapp, qtbot):
    view = HelpDocumentView(show_toc=False)
    qtbot.addWidget(view)
    view.resize(640, 480)
    view.show()
    qtbot.waitExposed(view)
    view.set_markdown(
        "## T\n\n"
        "### Cap {#cap}\n\n"
        ":::figure{side=center width=120}\n"
        "![x](missing.png)\n"
        "Centered caption\n"
        ":::\n"
    )
    qapp.processEvents()
    canvas = _canvas(view)
    assert canvas._layout.pixmaps
    pix = canvas._layout.pixmaps[0]
    assert pix.rect.x() > 0
    view.deleteLater()


def test_help_document_select_all_text(qapp, qtbot):
    view = HelpDocumentView(show_toc=False)
    qtbot.addWidget(view)
    view.resize(640, 400)
    view.set_markdown("**Bold** and [link](help://x).\n\nSecond paragraph.\n")
    qapp.processEvents()
    view.select_all_text()
    selected = view.selected_plain_text()
    assert "Bold" in selected
    assert "link" in selected
    assert "Second paragraph" in selected
    assert selected == view.plain_text()
    view.deleteLater()


def test_help_document_cross_block_selection(qapp, qtbot):
    view = HelpDocumentView(show_toc=False)
    qtbot.addWidget(view)
    view.resize(640, 480)
    view.set_markdown(
        "## Heading\n\n"
        "First paragraph.\n\n"
        "- list item\n"
    )
    qapp.processEvents()
    canvas = _canvas(view)
    canvas._sel_anchor = 0
    canvas._sel_focus = len(canvas.plain_text())
    selected = view.selected_plain_text()
    assert "Heading" in selected
    assert "First paragraph" in selected
    assert "list item" in selected
    view.deleteLater()


def test_help_document_canvas_requests_app_context_menu(qapp, qtbot):
    view = HelpDocumentView(show_toc=False)
    qtbot.addWidget(view)
    view.resize(640, 400)
    view.set_markdown("Copy this paragraph text.\n")
    qapp.processEvents()
    canvas = _canvas(view)
    assert canvas.contextMenuPolicy() == Qt.ContextMenuPolicy.CustomContextMenu

    received: list[QPoint] = []
    view.textContextMenuRequested.connect(received.append)
    canvas.customContextMenuRequested.emit(canvas.rect().center())
    assert len(received) == 1
    assert isinstance(received[0], QPoint)
    # Right-click must not invent a selection for copy actions.
    assert canvas.selected_plain_text() == ""
    view.deleteLater()


def test_help_document_double_click_selects_word(qapp, qtbot):
    from PySide6.QtCore import QPoint, Qt

    view = HelpDocumentView(show_toc=False)
    qtbot.addWidget(view)
    view.resize(640, 200)
    view.show()
    view.set_markdown("Hello world paragraph.\n")
    qapp.processEvents()
    canvas = _canvas(view)
    qtbot.mouseDClick(canvas, Qt.MouseButton.LeftButton, pos=QPoint(40, 20))
    qapp.processEvents()
    selected = canvas.selected_plain_text()
    assert selected in ("Hello", "world", "paragraph.")
    view.deleteLater()


def test_help_document_single_click_does_not_select_word(qapp, qtbot):
    from PySide6.QtCore import QPoint, Qt

    view = HelpDocumentView(show_toc=False)
    qtbot.addWidget(view)
    view.resize(640, 200)
    view.show()
    view.set_markdown("Hello world paragraph.\n")
    qapp.processEvents()
    canvas = _canvas(view)
    qtbot.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=QPoint(40, 20))
    qapp.processEvents()
    assert canvas.selected_plain_text() == ""
    view.deleteLater()


def test_help_document_selection_includes_kbd_shortcut(qapp, qtbot):
    """KBD spans (`Ctrl+V`) must be part of the selection model and paint pass."""
    from PySide6.QtGui import QImage, QPainter

    from sli_ui_toolkit.theme import ThemeManager
    from sli_ui_toolkit.ui.widgets.composite.help_document.layout.paint import paint_layout

    view = HelpDocumentView(show_toc=False)
    qtbot.addWidget(view)
    view.resize(640, 200)
    view.set_markdown(
        "Перетаскивание файлов. `Ctrl+V` вставляет изображение.\n"
    )
    qapp.processEvents()
    canvas = _canvas(view)
    text = canvas.plain_text()
    start = text.index("Ctrl+V")
    end = start + len("Ctrl+V")
    canvas._sel_anchor = start
    canvas._sel_focus = end
    assert canvas.selected_plain_text() == "Ctrl+V"

    img = QImage(640, 120, QImage.Format.Format_ARGB32)
    img.fill(0xFFFFFFFF)
    painter = QPainter(img)
    paint_layout(
        painter,
        canvas._layout,
        selection_start=start,
        selection_end=end,
        theme=ThemeManager.get_instance(),
    )
    painter.end()
    view.deleteLater()


def test_help_document_hit_test_spans_wrapped_lines(qapp, qtbot):
    from PySide6.QtCore import QPointF

    from sli_ui_toolkit.ui.widgets.composite.help_document.layout.hit_test import (
        hit_test_text_offset,
    )

    view = HelpDocumentView(show_toc=False)
    qtbot.addWidget(view)
    view.resize(260, 600)
    view.show()
    qtbot.waitExposed(view)
    view.set_markdown(
        "Это длинный абзац, который должен переноситься на несколько строк "
        "при узкой колонке справки.\n"
    )
    qapp.processEvents()
    canvas = _canvas(view)
    frag = canvas._layout.text_fragments[0]
    assert frag.layout.lineCount() >= 2
    start = frag.rect.topLeft() + QPointF(2, 2)
    end = QPointF(frag.rect.right() - 2, frag.rect.bottom() - 2)
    start_off = hit_test_text_offset(canvas._layout, start)
    end_off = hit_test_text_offset(canvas._layout, end)
    assert start_off is not None
    assert end_off is not None
    assert end_off > start_off
    canvas._sel_anchor = start_off
    canvas._sel_focus = end_off
    selected = view.selected_plain_text()
    assert len(selected) > 20
    assert "длинный абзац" in selected
    view.deleteLater()


def test_help_document_select_all_matches_plain_text(qapp, qtbot):
    view = HelpDocumentView(show_toc=False)
    qtbot.addWidget(view)
    view.resize(260, 600)
    view.show()
    qtbot.waitExposed(view)
    view.set_markdown(
        "## Заголовок\n\n"
        "Первый абзац с достаточно длинным текстом для переноса на новую строку.\n\n"
        "- пункт списка\n"
        "- второй пункт\n"
    )
    qapp.processEvents()
    view.select_all_text()
    assert view.selected_plain_text() == view.plain_text()
    view.deleteLater()


def test_help_document_figure_caption_sits_below_image(qapp, qtbot):
    view = HelpDocumentView(show_toc=False)
    qtbot.addWidget(view)
    view.resize(640, 480)
    view.show()
    qtbot.waitExposed(view)
    view.set_markdown(
        ":::figure{side=block width=120}\n"
        "![x](missing.png)\n"
        "Caption under image\n"
        ":::\n\n"
        "Next paragraph.\n"
    )
    qapp.processEvents()
    canvas = _canvas(view)
    assert canvas._layout.pixmaps
    pix = canvas._layout.pixmaps[0]
    caption_frags = [
        frag
        for frag in canvas._layout.text_fragments
        if "Caption under image" in canvas._text_index.text[frag.global_start : frag.global_end]
    ]
    assert caption_frags
    cap = caption_frags[0]
    gap = cap.rect.y() - (pix.rect.y() + pix.rect.height())
    assert 0 <= gap <= 12, gap
    next_frags = [
        frag
        for frag in canvas._layout.text_fragments
        if "Next paragraph" in canvas._text_index.text[frag.global_start : frag.global_end]
    ]
    assert next_frags
    next_gap = next_frags[0].rect.y() - (cap.rect.y() + cap.rect.height())
    assert next_gap < 30, next_gap
    view.deleteLater()


def test_help_document_reflows_when_window_narrows(qapp, qtbot):
    view = HelpDocumentView(show_toc=False)
    qtbot.addWidget(view)
    view.resize(640, 480)
    view.show()
    qtbot.waitExposed(view)
    view.set_markdown(
        "This paragraph should wrap to more lines when the help column becomes narrow.\n"
    )
    qapp.processEvents()
    canvas = _canvas(view)
    wide_lines = canvas._layout.text_fragments[0].layout.lineCount()
    wide_height = canvas._layout.height
    view.resize(220, 720)
    qapp.processEvents()
    canvas = _canvas(view)
    narrow_lines = canvas._layout.text_fragments[0].layout.lineCount()
    narrow_height = canvas._layout.height
    assert narrow_lines > wide_lines
    assert narrow_height > wide_height
    view.deleteLater()


def test_help_document_wrapped_paragraphs_do_not_overlap(qapp, qtbot):
    view = HelpDocumentView(show_toc=False)
    qtbot.addWidget(view)
    view.resize(220, 600)
    view.set_markdown(
        "This is a long paragraph that should wrap across several lines "
        "when the help column is narrow enough to force word wrapping.\n"
    )
    qapp.processEvents()
    canvas = _canvas(view)
    frags = canvas._layout.text_fragments
    assert len(frags) == 1
    assert frags[0].layout.lineCount() >= 3
    assert frags[0].rect.height() >= 60.0
    view.deleteLater()


def test_help_document_figure_left_floats_with_text(qapp, qtbot):
    view = HelpDocumentView(show_toc=False)
    qtbot.addWidget(view)
    view.resize(640, 480)
    view.set_markdown(
        "## T\n\n"
        "Beside the panel.\n\n"
        ":::figure{side=left width=120}\n"
        "![x](missing.png)\n"
        "Left cap\n"
        ":::\n"
    )
    qapp.processEvents()
    canvas = _canvas(view)
    assert canvas._layout.pixmaps
    assert canvas._layout.text_fragments
    view.deleteLater()
