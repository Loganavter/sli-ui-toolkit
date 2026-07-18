"""Help document block parser — controlled markdown subset for HelpDocumentView."""

from __future__ import annotations

from sli_ui_toolkit.ui.widgets.composite.help_document import (
    FigureBlock,
    HeadingBlock,
    ImageBlock,
    InlineKind,
    ListBlock,
    ParagraphBlock,
    collect_heading_anchors,
    parse_help_blocks,
    parse_inline,
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
    from sli_ui_toolkit.ui.widgets.composite.help_document.structure import (
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
