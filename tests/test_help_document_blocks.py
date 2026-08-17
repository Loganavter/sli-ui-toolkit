"""Help document block parser — controlled markdown subset for HelpDocumentView."""

from __future__ import annotations

from sli_ui_toolkit.ui.widgets.composite.help_document import (
    CodeBlock,
    FigureBlock,
    HeadingBlock,
    ImageBlock,
    InlineKind,
    ListBlock,
    ParagraphBlock,
    TableBlock,
    blocks_to_plain_text,
    collect_heading_anchors,
    parse_help_blocks,
    parse_inline,
    spans_to_plain,
)
from sli_ui_toolkit.ui.widgets.composite.text_view.text_index import (
    assert_index_matches_blocks,
    build_text_index,
)


SAMPLE = """
## Magnifier

Enable the tool, then drag on the canvas.

### Enabling {#enabling}

- Toggle **Use Magnifier**
- Press `M` or `Ctrl+Shift+P`

### Capture {#capture}

:::figure{side=right width=280}
![Toolbar](assets/magnifier/toolbar.png)
Magnifier button on the toolbar
:::

See [Comparison](help://comparison#split) for the divider.
"""


def test_parse_headings_lists_and_links():
    blocks = parse_help_blocks(SAMPLE)
    assert isinstance(blocks[0], HeadingBlock)
    assert blocks[0].level == 2
    assert blocks[0].text == "Magnifier"

    headings = [b for b in blocks if isinstance(b, HeadingBlock) and b.level == 3]
    assert headings[0].anchor == "enabling"
    assert headings[1].anchor == "capture"

    lists = [b for b in blocks if isinstance(b, ListBlock)]
    assert len(lists) == 1
    assert lists[0].ordered is False
    assert len(lists[0].items) == 2

    figures = [b for b in blocks if isinstance(b, FigureBlock)]
    assert len(figures) == 1
    assert figures[0].path == "assets/magnifier/toolbar.png"
    assert figures[0].side == "right"
    assert figures[0].width == 280
    assert "toolbar" in figures[0].caption.lower()


def test_parse_inline_kbd_and_link():
    spans = parse_inline("Press `Ctrl+S` or [Help](help://introduction)")
    kinds = [s.kind for s in spans]
    assert InlineKind.KBD in kinds
    assert InlineKind.LINK in kinds
    link = next(s for s in spans if s.kind == InlineKind.LINK)
    assert link.href == "help://introduction"
    kbd = next(s for s in spans if s.kind == InlineKind.KBD)
    assert kbd.text == "Ctrl+S"


def test_standalone_image_block():
    blocks = parse_help_blocks("![Alt](foo.png)\n")
    assert len(blocks) == 1
    assert isinstance(blocks[0], ImageBlock)
    assert blocks[0].path == "foo.png"


def test_collect_heading_anchors():
    blocks = parse_help_blocks("### A {#a}\n\n### B {#b}\n")
    assert collect_heading_anchors(blocks) == (("a", "A"), ("b", "B"))


def test_paragraph_between_structures():
    blocks = parse_help_blocks("Hello **world**.\n\n- one\n")
    assert isinstance(blocks[0], ParagraphBlock)
    assert any(s.kind == InlineKind.BOLD for s in blocks[0].spans)
    assert isinstance(blocks[1], ListBlock)


def test_parse_figure_side_center_and_left():
    blocks = parse_help_blocks(
        ":::figure{side=center width=240}\n"
        "![a](a.png)\n"
        "Mid\n"
        ":::\n\n"
        ":::figure{side=left width=200}\n"
        "![b](b.png)\n"
        "Left\n"
        ":::\n"
    )
    figures = [b for b in blocks if isinstance(b, FigureBlock)]
    assert figures[0].side == "center"
    assert figures[0].width == 240
    assert figures[1].side == "left"


def test_parse_figure_width_percent():
    blocks = parse_help_blocks(
        ":::figure{side=block width=75%}\n"
        "![a](a.png)\n"
        "Wide\n"
        ":::\n"
    )
    figures = [b for b in blocks if isinstance(b, FigureBlock)]
    assert len(figures) == 1
    assert figures[0].side == "block"
    assert figures[0].width is None
    assert figures[0].width_percent == 75.0
    assert figures[0].height is None


def test_parse_figure_height_px():
    blocks = parse_help_blocks(
        ":::figure{side=block height=160}\n"
        "![a](a.png)\n"
        "Tall\n"
        ":::\n"
    )
    figures = [b for b in blocks if isinstance(b, FigureBlock)]
    assert len(figures) == 1
    assert figures[0].height == 160
    assert figures[0].width is None
    assert figures[0].width_percent is None


def test_group_side_figures_ignores_center():
    from sli_ui_toolkit.ui.widgets.composite.text_view.structure import (
        SideFigureGroup,
        group_side_figures,
    )

    blocks = parse_help_blocks(
        "Intro.\n\n"
        ":::figure{side=center width=200}\n"
        "![x](a.png)\n"
        "Cap\n"
        ":::\n"
    )
    grouped = group_side_figures(blocks)
    assert not any(isinstance(g, SideFigureGroup) for g in grouped)
    assert any(isinstance(b, FigureBlock) and b.side == "center" for b in grouped)


def test_level_one_headings():
    blocks = parse_help_blocks(
        "# Title\n\n#### Deep {#deep}\n\nParagraph.\n"
    )
    assert blocks[0].level == 1
    assert blocks[0].text == "Title"
    assert blocks[1].level == 4
    assert blocks[1].anchor == "deep"
    assert isinstance(blocks[2], ParagraphBlock)


def test_fenced_code_blocks():
    blocks = parse_help_blocks(
        "Before.\n\n"
        "```python\n"
        "from sli_ui_toolkit.widgets import Button\n"
        "# comment stays in the block\n"
        "```\n\n"
        "After.\n"
    )
    assert isinstance(blocks[0], ParagraphBlock)
    code = blocks[1]
    assert isinstance(code, CodeBlock)
    assert code.language == "python"
    assert code.lines == (
        "from sli_ui_toolkit.widgets import Button",
        "# comment stays in the block",
    )
    assert isinstance(blocks[2], ParagraphBlock)
    assert blocks_to_plain_text(blocks) == (
        "Before.\n\n"
        "from sli_ui_toolkit.widgets import Button\n"
        "# comment stays in the block\n\n"
        "After."
    )


def test_fenced_code_without_language_and_unclosed():
    blocks = parse_help_blocks("```\nvalue = 42\n```\n\nafter\n")
    assert isinstance(blocks[0], CodeBlock)
    assert blocks[0].language == ""
    assert blocks[0].lines == ("value = 42",)
    unclosed = parse_help_blocks("```\nleft open\n")
    assert isinstance(unclosed[0], CodeBlock)
    assert unclosed[0].lines == ("left open",)


def test_parse_pipe_table_with_header():
    blocks = parse_help_blocks(
        "| Param | Meaning |\n"
        "|---|---|\n"
        "| `alpha` | allow alpha editing |\n"
        "| hover | keep hover overlays |\n"
    )
    tables = [b for b in blocks if isinstance(b, TableBlock)]
    assert len(tables) == 1
    table = tables[0]
    assert [spans_to_plain(c) for c in table.header] == ["Param", "Meaning"]
    assert len(table.rows) == 2
    assert spans_to_plain(table.rows[0][0]) == "alpha"
    assert table.rows[0][0][0].kind == InlineKind.CODE
    assert spans_to_plain(table.rows[1][1]) == "keep hover overlays"


def test_parse_pipe_table_without_header():
    blocks = parse_help_blocks("| a | b |\n| c | d |\n")
    tables = [b for b in blocks if isinstance(b, TableBlock)]
    assert len(tables) == 1
    assert tables[0].header == ()
    assert len(tables[0].rows) == 2


def test_parse_pipe_table_pads_short_rows():
    blocks = parse_help_blocks(
        "| A | B | C |\n|---|---|---|\n| 1 | 2 |\n"
    )
    table = next(b for b in blocks if isinstance(b, TableBlock))
    assert len(table.header) == 3
    assert len(table.rows[0]) == 3
    assert spans_to_plain(table.rows[0][2]) == ""


def test_parse_pipe_table_escaped_pipe():
    blocks = parse_help_blocks("| a | b\\|c |\n")
    table = next(b for b in blocks if isinstance(b, TableBlock))
    assert [spans_to_plain(c) for c in table.rows[0]] == ["a", "b|c"]


def test_pipe_table_does_not_swallow_following_paragraph():
    blocks = parse_help_blocks(
        "| a | b |\n|---|---|\n| 1 | 2 |\n\nTrailing paragraph.\n"
    )
    tables = [b for b in blocks if isinstance(b, TableBlock)]
    paragraphs = [b for b in blocks if isinstance(b, ParagraphBlock)]
    assert len(tables) == 1
    assert len(paragraphs) == 1
    assert spans_to_plain(paragraphs[0].spans) == "Trailing paragraph."


def test_pipe_table_plain_text_matches_index():
    blocks = parse_help_blocks(
        "| Param | Meaning |\n|---|---|\n| `alpha` | allow |\n| b | keep |\n"
    )
    index = build_text_index(blocks)
    assert_index_matches_blocks(blocks, index)
