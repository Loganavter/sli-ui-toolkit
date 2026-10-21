"""Copy-as-Markdown: a selection maps to ITS source slice, never the page.

Falsification (owner report 2026-10-21): selecting the two labels of a help
list and choosing "Copy as Markdown" put the WHOLE page on the clipboard.
Mechanism: ``markdown_for_selection`` searched the flattened selection text
inside the source and returned the full markdown whenever the search failed —
which it always does for more than one block, because the text index strips
the markup (``-``/``**``/``##``) and inserts ``\\n\\n`` between blocks. These
tests pin the block-geometry mapping that replaced it: every case below
returns the selected fragment on the pre-change tree's fallback (the page).
"""

from __future__ import annotations

from sli_ui_toolkit.ui.widgets.text.engine.markdown import (
    ParagraphBlock,
    parse_help_blocks,
    parse_inline,
)
from sli_ui_toolkit.ui.widgets.text.engine.markdown_copy import markdown_for_range
from sli_ui_toolkit.ui.widgets.text.engine.text_index import build_text_index

MD = (
    "# Заголовок {#top}\n"
    "\n"
    "Текст **жирный** и `код`, а также [ссылка](help://x).\n"
    "\n"
    "- **Файл** — имя.\n"
    "- **Изображение** — размер.\n"
    "\n"
    "| Param | Meaning |\n"
    "|---|---|\n"
    "| `alpha` | allow alpha |\n"
    "\n"
    "```python\n"
    "print('x')\n"
    "```\n"
)


def _index(markdown: str = MD):
    blocks = parse_help_blocks(markdown)
    return blocks, build_text_index(blocks)


def _copy(index, start: int, end: int, markdown: str = MD) -> str:
    return markdown_for_range(index, markdown, start, end)


def _needle(index, needle: str, occurrence: int = 0) -> tuple[int, int]:
    position = -1
    for _ in range(occurrence + 1):
        position = index.text.index(needle, position + 1)
    return position, position + len(needle)


def test_two_list_labels_copy_their_two_lines_not_the_page():
    """The reported case: two bullet labels → exactly those two source lines."""
    _blocks, index = _index()
    start, _ = _needle(index, "• Файл")
    _, end = _needle(index, "• Изображение — размер.")
    copied = _copy(index, start, end)
    assert copied == "- **Файл** — имя.\n- **Изображение** — размер."
    assert copied.strip() != MD.strip()


def test_heading_and_paragraph_keep_their_block_markup():
    _blocks, index = _index()
    _, end = _needle(index, "Текст жирный и код, а также ссылка.")
    copied = _copy(index, 0, end)
    # The invisible {#top} anchor is a rendering directive, not content.
    assert copied == (
        "# Заголовок\n\nТекст **жирный** и `код`, а также [ссылка](help://x)."
    )


def test_whole_inline_span_keeps_its_delimiters():
    _blocks, index = _index()
    for needle, expected in (
        ("жирный", "**жирный**"),
        ("код", "`код`"),
        ("ссылка", "[ссылка](help://x)"),
    ):
        start, end = _needle(index, needle)
        assert _copy(index, start, end) == expected


def test_partial_inline_span_copies_plain_text_not_half_markup():
    """Half a bold run must not emit a dangling ``**``."""
    _blocks, index = _index()
    start, _ = _needle(index, "жирный")
    copied = _copy(index, start, start + len("жир"))
    assert copied == "жир"
    assert "**" not in copied


def test_partial_start_and_end_do_not_widen_to_neighbouring_blocks():
    _blocks, index = _index()
    start, _ = _needle(index, "Текст")
    _, end = _needle(index, "• Изображение — размер.")
    copied = _copy(index, start + len("Текст "), end)
    assert copied.startswith("**жирный**")
    assert copied.endswith("**Изображение** — размер.")
    assert "Заголовок" not in copied


def test_table_cells_copy_as_pipe_cells():
    _blocks, index = _index()
    start, _ = _needle(index, "Param")
    _, end = _needle(index, "Meaning")
    assert _copy(index, start, end) == "Param | Meaning"


def test_code_block_selection_copies_the_whole_fence():
    _blocks, index = _index()
    start, end = _needle(index, "print('x')")
    # The document's own trailing newline is preserved (the fence is last).
    assert _copy(index, start, end) == "```python\nprint('x')\n```\n"


def test_select_all_reproduces_the_source():
    _blocks, index = _index()
    copied = _copy(index, 0, len(index.text))
    # Everything verbatim except the invisible heading anchor directive.
    assert "#top" not in copied
    assert copied.strip() == MD.replace(" {#top}", "").strip()


def test_host_built_blocks_without_geometry_fall_back_to_plain_text():
    """A host that hands ``set_blocks`` hand-built blocks has no source map:
    the copy is the plain selection, never the whole source."""
    blocks = (ParagraphBlock(spans=parse_inline("Hello **world**.")),)
    index = build_text_index(blocks)
    copied = _copy(index, 0, len(index.text), MD)
    assert copied == "Hello world."
    assert MD.strip() not in copied


def test_empty_source_markdown_falls_back_to_plain_text():
    _blocks, index = _index()
    start, end = _needle(index, "жирный")
    assert _copy(index, start, end, "") == "жирный"


def test_crlf_source_maps_the_same_way():
    markdown = "## Заголовок\r\n\r\n- **Файл** — имя.\r\n- **Изображение** — размер.\r\n"
    _blocks, index = _index(markdown)
    start, _ = _needle(index, "• Файл")
    _, end = _needle(index, "• Изображение — размер.")
    assert _copy(index, start, end, markdown) == (
        "- **Файл** — имя.\n- **Изображение** — размер.\n"
    )


def test_empty_range_copies_nothing():
    _blocks, index = _index()
    assert _copy(index, 5, 5) == ""


def test_text_widget_copies_a_two_label_selection(qapp, qtbot):
    """Widget-level wiring: ``Text.selected_markdown`` maps the live selection."""
    from sli_ui_toolkit.widgets import Text

    widget = Text("", mode="document")
    qtbot.addWidget(widget)
    widget.set_blocks(parse_help_blocks(MD))
    canvas = widget.canvas()
    text = widget.plain_text()
    start = text.index("• Файл")
    end = text.index("• Изображение — размер.") + len("• Изображение — размер.")
    canvas._doc_selection.set_range(start, end)
    assert widget.selected_markdown(MD) == (
        "- **Файл** — имя.\n- **Изображение** — размер."
    )
