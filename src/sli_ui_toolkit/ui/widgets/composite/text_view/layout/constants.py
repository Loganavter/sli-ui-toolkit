"""Layout spacing and typography for help document body."""

from __future__ import annotations

BLOCK_SPACING = 10.0
SIDE_FIGURE_SPACING = 16.0
SIDE_FIGURE_V_MARGIN = 4.0
CAPTION_SPACING = 6.0
LIST_INDENT = 8.0
CAPTION_FONT_PX = 13
BODY_FONT_PX = 14
# Heading scale (design px, scaled by UiScale) — monotonically decreasing
# so every ``#``…``######`` level is visually distinct.
H1_FONT_PX = 26
H2_FONT_PX = 22
H3_FONT_PX = 18
H4_FONT_PX = 16
H5_FONT_PX = 14
H6_FONT_PX = 13

# Fenced code blocks: shaded rounded box (``help.code.background`` token),
# text inset by the padding; a fence language label occupies the header row.
CODE_PAD_X = 12.0
CODE_PAD_Y = 8.0
CODE_HEADER_H = 20.0
CODE_RADIUS = 6.0
CODE_LABEL_FONT_PX = 11

# A literal "\t" in paragraph text lands on this column — lets programmatic
# callers line up like a table without a dedicated grid block type.
PARAGRAPH_TAB_STOP_PX = 140.0

# TableBlock cell padding (border-to-text, in both directions).
TABLE_CELL_PAD_X = 10.0
TABLE_CELL_PAD_Y = 6.0
