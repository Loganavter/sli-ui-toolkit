"""Rendering pipeline for ``TextCanvas`` — one frame, code and document mode.

``_CanvasPaintApi`` owns ``paintEvent`` and everything it calls: the
document-mode paint path, the code-mode gutter/fold-arrow/line painters.
Mixin preceding ``QWidget`` in ``TextCanvas``'s MRO so its ``paintEvent``
override wins, same trick as ``base_flyout``.
"""

from __future__ import annotations

from PySide6.QtCore import QRect
from PySide6.QtGui import QColor, QPainter

from sli_ui_toolkit.theme import ThemeManager

from . import constants
from .document import paint_layout
from .highlight import python_line_spans, python_span_colors
from .painter import draw_text_line


class _CanvasPaintApi:
    _FOLD_ARROW = "▸"  # ▸

    def paintEvent(self, _event) -> None:  # noqa: N802
        if self._document_layout is not None:
            self._paint_document()
            return
        painter = QPainter(self)
        tm = ThemeManager.get_instance()
        foreground = tm.try_get_color("WindowText")
        if foreground is None or not foreground.isValid():
            foreground = QColor(0, 0, 0)
        self._paint_gutter(painter, foreground)
        colors = python_span_colors(tm)
        selection_color = QColor(tm.try_get_color("accent") or QColor(0, 0, 0))
        selection_color.setAlpha(70)
        y = constants.PAD + self._metrics.ascent()
        for line_index, line in enumerate(self._lines):
            self._paint_line(
                painter, y, line, line_index, foreground, colors, selection_color
            )
            y += self._line_height
        self._paint_fold_arrows(painter, foreground)

    def _paint_document(self) -> None:
        painter = QPainter(self)  # type: ignore[call-overload]
        painter.translate(constants.PAD, constants.PAD)
        selection_start = selection_end = None
        rng = self._doc_selection.paint_range()
        if rng is not None:
            selection_start, selection_end = rng
        paint_layout(
            painter,
            self._document_layout,  # type: ignore[arg-type]
            selection_start=selection_start,
            selection_end=selection_end,
            theme=ThemeManager.get_instance(),
        )

    def _fold_arrow_reserve(self) -> int:
        """Constant gutter space for the fold arrow (0 when folding is
        disabled). Reserved for the whole view — the text's left offset
        never moves when rows expand/collapse."""
        if self._fold_lines is None:
            return 0
        return self._metrics.horizontalAdvance(self._FOLD_ARROW) + 4

    def _paint_fold_arrows(self, painter: QPainter, foreground: QColor) -> None:
        """VS Code-style disclosure arrows: in the gutter, left of the line
        number, inside the reserved constant offset."""
        if not self._fold_lines:
            return
        color = QColor(foreground)
        color.setAlpha(150)
        painter.setPen(color)
        painter.setFont(self._font)
        y = constants.PAD + self._metrics.ascent()
        for index in sorted(self._fold_lines):
            if 0 <= index < len(self._lines):
                painter.drawText(
                    constants.GUTTER_PAD,
                    y + index * self._line_height,
                    self._FOLD_ARROW,
                )

    def _paint_gutter(self, painter: QPainter, foreground: QColor) -> None:
        """VS Code-style line-number gutter (only when a start is set):
        right-aligned muted numbers + a thin separator on its right edge."""
        if self._line_number_start is None:
            return
        width = self._gutter_width()
        text_color = QColor(foreground)
        text_color.setAlpha(120)
        separator = QColor(foreground)
        separator.setAlpha(50)
        painter.setFont(self._font)
        y = constants.PAD + self._metrics.ascent()
        for index, _line in enumerate(self._lines):
            number = self._gutter_text(index)
            num_width = self._metrics.horizontalAdvance(number)
            painter.setPen(text_color)
            painter.drawText(width - constants.GUTTER_PAD - num_width, y, number)
            y += self._line_height
        painter.setPen(separator)
        painter.drawLine(width - 1, 0, width - 1, self.height())

    def _paint_line(
        self,
        painter: QPainter,
        y: int,
        line: str,
        line_index: int,
        base_color: QColor,
        colors,
        selection_color: QColor,
    ) -> None:
        if self._editing:
            sel_lo, sel_hi = self._selection_range_for_line(line_index, line)
            if sel_lo < sel_hi:
                x0 = self._text_x() + self._metrics.horizontalAdvance(line[:sel_lo])
                x1 = self._text_x() + self._metrics.horizontalAdvance(line[:sel_hi])
                painter.fillRect(
                    QRect(x0, y - self._metrics.ascent(), x1 - x0, self._line_height),
                    selection_color,
                )
        draw_text_line(
            painter,
            self._text_x(),
            y,
            line,
            python_line_spans(line),
            base_color,
            colors,
            self._font,
        )
        # The caret is hidden while a selection is active: during a drag
        # the cursor rides the mouse inside the selected range, and after
        # release the caret would sit at the selection's focus edge — the
        # highlight alone should read as the selection.
        if (
            self._editing
            and self.hasFocus()
            and not self._selection.active()
            and self._cursor[0] == line_index
        ):
            cx = self._text_x() + self._metrics.horizontalAdvance(
                line[:self._cursor[1]]
            )
            painter.fillRect(
                QRect(cx, y - self._metrics.ascent(), 2, self._line_height),
                base_color,
            )

    def _selection_range_for_line(self, line_index: int, line: str) -> tuple[int, int]:
        rng = self._selection_bounds()
        if rng is None:
            return (0, 0)
        (lo_line, lo_col), (hi_line, hi_col) = rng
        if lo_line > line_index or hi_line < line_index:
            return (0, 0)
        start = lo_col if lo_line == line_index else 0
        end = hi_col if hi_line == line_index else len(line)
        return (start, end)
