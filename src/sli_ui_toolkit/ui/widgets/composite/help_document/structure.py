"""Layout-level grouping of parsed help blocks."""

from __future__ import annotations

from dataclasses import dataclass

from sli_ui_toolkit.ui.widgets.composite.help_document.blocks import (
    FigureBlock,
    HelpBlock,
    ParagraphBlock,
)


@dataclass(frozen=True, slots=True)
class SideFigureGroup:
    figure: FigureBlock
    paragraphs: tuple[ParagraphBlock, ...]


LayoutItem = HelpBlock | SideFigureGroup


def group_side_figures(blocks: tuple[HelpBlock, ...]) -> list[LayoutItem]:
    """Pair side figures with adjacent paragraphs for Blender-like layout."""
    out: list[LayoutItem] = []
    i = 0
    n = len(blocks)
    while i < n:
        block = blocks[i]
        if isinstance(block, FigureBlock) and block.side in {"left", "right"}:
            paras_before: list[ParagraphBlock] = []
            if out and isinstance(out[-1], ParagraphBlock):
                paras_before.append(out.pop())  # type: ignore[arg-type]
            paras_after: list[ParagraphBlock] = []
            j = i + 1
            while j < n and isinstance(blocks[j], ParagraphBlock):
                paras_after.append(blocks[j])  # type: ignore[arg-type]
                j += 1
            out.append(
                SideFigureGroup(
                    figure=block,
                    paragraphs=tuple(paras_before + paras_after),
                )
            )
            i = j
            continue
        out.append(block)
        i += 1
    return out
