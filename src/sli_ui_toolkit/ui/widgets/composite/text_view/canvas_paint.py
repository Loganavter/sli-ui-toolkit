"""Rendering pipeline for ``TextCanvas`` — one frame, code and document mode.

``_CanvasPaintApi`` owns ``paintEvent`` and everything it calls: the
document-mode paint path, the code-mode gutter/fold-arrow/line painters.
Mixin preceding ``QWidget`` in ``TextCanvas``'s MRO so its ``paintEvent``
override wins, same trick as ``base_flyout``.
"""

from __future__ import annotations

import logging
import os
import time

from PySide6.QtCore import QRect
from PySide6.QtGui import QColor, QPainter

from sli_ui_toolkit.theme import ThemeManager

from . import constants
from .document import paint_layout
from .highlight import python_line_spans, python_span_colors
from .painter import _cached_advance, draw_text_line

_logger = logging.getLogger(__name__)
# Re-evaluated per paint so `SLI_TEXTVIEW_DEBUG=1` works even if set after import.
# Use WARNING so it shows with default host logging (DEBUG is filtered).
def _debug_enabled() -> bool:
    return os.getenv("SLI_TEXTVIEW_DEBUG") == "1" or os.getenv("IMGSLI_TRACE") == "1"

_DEBUG_PAINT_EVERY = 1  # log every paint while debugging — zero useful info means throttle hid the storm
_paint_counter = 0
_slow_threshold_ms = 0  # log everything when debug on
_last_paint_ts = 0.0
_burst_start = 0.0
_burst_count = 0


class _CanvasPaintApi:
    _FOLD_ARROW = "▸"  # ▸

    def paintEvent(self, event) -> None:  # noqa: N802
        # Debug probe: use WARNING + file so it is visible even with default
        # host log level (DEBUG is filtered → "НОЛЬ полезной информации").
        dbg = _debug_enabled()
        t0 = time.perf_counter() if dbg else 0
        global _paint_counter
        if self._document_layout is not None:
            self._paint_document()
            if dbg:
                dt = (time.perf_counter() - t0) * 1000
                _paint_counter += 1
                from .highlight import python_line_spans as _pls

                info = _pls.cache_info() if hasattr(_pls, "cache_info") else None
                msg = (
                    f"TextCanvas paint doc paint#{_paint_counter} lines={len(self._lines)} "
                    f"h={self.height()} clip={getattr(event, 'rect', lambda: self.rect())()} dt={dt:.2f}ms cache={info}"
                )
                _logger.warning(msg)
                # Also to /tmp for headless runs where log.txt is overwritten
                try:
                    with open("/tmp/textview_debug.log", "a", encoding="utf-8") as f:
                        f.write(msg + "\n")
                except Exception:
                    pass
            return
        painter = QPainter(self)
        tm = ThemeManager.get_instance()
        foreground = tm.try_get_color("WindowText")
        if foreground is None or not foreground.isValid():
            foreground = QColor(0, 0, 0)
        self._paint_gutter(painter, foreground, clip_rect=getattr(event, "rect", lambda: self.rect())())
        colors = python_span_colors(tm)
        selection_color = QColor(tm.try_get_color("accent") or QColor(0, 0, 0))
        selection_color.setAlpha(70)
        # Clip to the exposed rect — painting every line for a 2k-line file
        # on every scroll tick is O(N) and makes the Code view lag badly.
        # The QScrollArea moves the canvas; only the viewport slice is exposed.
        clip = getattr(event, "rect", lambda: self.rect())() if event is not None else self.rect()
        first = max(0, (clip.y() - constants.PAD) // max(1, self._line_height))
        last = min(
            len(self._lines) - 1,
            (clip.y() + clip.height() - constants.PAD) // max(1, self._line_height) + 1,
        )
        # gutter already paints its own visible slice, but fold arrows are
        # cheap — still draw them (few lines). Lines: only the visible span.
        y0 = constants.PAD + self._metrics.ascent() + first * self._line_height
        y = y0
        for line_index in range(first, last + 1):
            line = self._lines[line_index]
            self._paint_line(
                painter, y, line, line_index, foreground, colors, selection_color
            )
            y += self._line_height
        self._paint_fold_arrows(painter, foreground)
        if dbg:
            dt = (time.perf_counter() - t0) * 1000
            _paint_counter += 1
            from .highlight import python_line_spans as _pls

            info = _pls.cache_info() if hasattr(_pls, "cache_info") else None
            # Detect repaint storm: >10 paints in <200ms with same clip
            global _last_paint_ts, _burst_start, _burst_count
            now = time.perf_counter()
            if now - _burst_start > 0.2:
                _burst_start = now
                _burst_count = 0
            _burst_count += 1
            interval = (now - _last_paint_ts) * 1000 if _last_paint_ts else 0
            _last_paint_ts = now
            msg = (
                f"TextCanvas paint code paint#{_paint_counter} N={len(self._lines)} "
                f"visible=[{first}..{last}] ({max(0, last-first+1)}) h={self.height()} clip={clip} dt={dt:.2f}ms interval={interval:.1f}ms burst={_burst_count} cache={info}"
            )
            _logger.warning(msg)
            try:
                with open("/tmp/textview_debug.log", "a", encoding="utf-8") as f:
                    f.write(msg + "\n")
                    # On storm, dump stack to locate trigger (update() caller)
                    if _burst_count > 5 and interval < 20:
                        import traceback

                        stack = "".join(traceback.format_stack()[-6:-2])
                        f.write(f"  STACK burst#{_burst_count} interval {interval:.1f}ms:\n{stack}\n")
                        _logger.warning("TextCanvas burst stack:\n%s", stack)
            except Exception:
                pass

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

    def _paint_gutter(self, painter: QPainter, foreground: QColor, clip_rect=None) -> None:
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
        clip = clip_rect if clip_rect is not None else self.rect()
        first = max(0, (clip.y() - constants.PAD) // max(1, self._line_height))
        last = min(
            len(self._lines) - 1,
            (clip.y() + clip.height() - constants.PAD) // max(1, self._line_height) + 1,
        )
        y = constants.PAD + self._metrics.ascent() + first * self._line_height
        for index in range(first, last + 1):
            number = self._gutter_text(index)
            num_width = self._metrics.horizontalAdvance(number)
            painter.setPen(text_color)
            painter.drawText(width - constants.GUTTER_PAD - num_width, y, number)
            y += self._line_height
        painter.setPen(separator)
        # Separator previously spanned the whole 80k widget — clipped to viewport
        painter.drawLine(width - 1, clip.y(), width - 1, clip.y() + clip.height())

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
        # Selection highlight — debug must fire even in read-only Code
        # (Edit not pressed) where _editing==False, otherwise 2-char drag
        # never logs → "не работает твой дебаг".
        sel_lo, sel_hi = self._selection_range_for_line(line_index, line)
        dbg_sel = os.getenv("SLI_TEXTVIEW_DEBUG") == "1" and 0 < sel_hi - sel_lo <= 5
        if dbg_sel:
            t0 = time.perf_counter()
            x0_dbg = self._text_x() + _cached_advance(self._metrics, line[:sel_lo], False)
            x1_dbg = self._text_x() + _cached_advance(self._metrics, line[:sel_hi], False)
            dt = (time.perf_counter() - t0) * 1000
            msg = f"selection paint line={line_index} sel=[{sel_lo}:{sel_hi}] len={len(line)} dt_adv={dt:.3f}ms editing={self._editing} cursor={self._cursor}"
            _logger.warning(msg)
            try:
                with open("/tmp/textview_debug.log", "a", encoding="utf-8") as f:
                    f.write(msg + "\n")
            except Exception:
                pass
        if self._editing and sel_lo < sel_hi:
            x0 = self._text_x() + _cached_advance(self._metrics, line[:sel_lo], False)
            x1 = self._text_x() + _cached_advance(self._metrics, line[:sel_hi], False)
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
            cx = self._text_x() + _cached_advance(self._metrics, line[: self._cursor[1]], False)
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
