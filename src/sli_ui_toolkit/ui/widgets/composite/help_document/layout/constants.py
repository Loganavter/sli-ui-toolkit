"""Layout spacing and typography for help document body."""

from __future__ import annotations

BLOCK_SPACING = 10.0
SIDE_FIGURE_SPACING = 16.0
SIDE_FIGURE_V_MARGIN = 4.0
CAPTION_SPACING = 6.0
LIST_INDENT = 8.0
CAPTION_FONT_PX = 13
BODY_FONT_PX = 14
H2_FONT_PX = 22
H3_FONT_PX = 16

# A literal "\t" in paragraph text lands on this column — lets programmatic
# callers line up like a table without a dedicated grid block type.
PARAGRAPH_TAB_STOP_PX = 140.0

# TableBlock cell padding (border-to-text, in both directions).
TABLE_CELL_PAD_X = 10.0
TABLE_CELL_PAD_Y = 6.0
