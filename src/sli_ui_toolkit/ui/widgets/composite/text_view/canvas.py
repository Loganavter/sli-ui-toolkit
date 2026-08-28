"""TextCanvas — the painted text surface that IS the editor.

The same painted widget switches between read and edit modes, so both look
identical by construction. Edit mode adds a caret, selection, and
keyboard/mouse input; the host ``TextView`` scrolls it and draws the rounded
frame around the visible area.

The class keeps only construction, state, document-mode delegation glue, and
Qt-required method names it doesn't delegate; the concerns live in sibling
mixin modules (same pattern as ``base_flyout``/``buttons``):

- ``editing.py``      — ``_CanvasEditingApi``  buffer/cursor/undo/selection mutation
- ``events.py``        — ``_CanvasEventsApi``   mouse/keyboard/IME event handling
- ``canvas_paint.py``  — ``_CanvasPaintApi``     paintEvent + gutter/fold/line rendering
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QFontDatabase, QFontMetrics, QKeySequence, QGuiApplication
from PySide6.QtWidgets import QSizePolicy, QWidget

import logging
import os
import time
import traceback

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.managers.ui_scale import UiScale
from . import constants
from .document import build_text_index, layout_document, parse_help_blocks
from .selection import DocumentSelection, TextSelection
from sli_ui_toolkit.ui.widgets.composite.text_view.layout.hit_test import (
    hit_test_link,
    hit_test_pixmap,
    hit_test_text_offset,
)
from .canvas_paint import _CanvasPaintApi
from .editing import Position, _CanvasEditingApi
from .events import _CanvasEventsApi

_canvas_logger = logging.getLogger(__name__)
_update_counter = 0
_last_update_ts = 0.0

__all__ = ["TextCanvas", "Position"]


class TextCanvas(_CanvasPaintApi, _CanvasEventsApi, _CanvasEditingApi, QWidget):
    """Painted monospace text surface with a line-based editing model."""

    changed = Signal()
    #: document mode: a link was clicked (href)
    linkActivated = Signal(str)
    #: document mode: an image was clicked (source asset path)
    imageActivated = Signal(str)

    def __init__(self, text: str):
        super().__init__()
        self._lines = text.split("\n") if text else [""]
        self._editing = False
        self._cursor: Position = (0, 0)
        self._selection = TextSelection()
        self._undo: list[tuple[str, Position]] = []
        self._chain_selecting: str | None = None
        self._press_point = None
        self._drag_extending = False
        self._line_number_start: int | None = None
        self._line_number_map: dict[int, str] | None = None
        self._fold_lines: set[int] | None = None
        self._font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
        self._font.setPixelSize(constants.FONT_PIXEL_SIZE)
        self._metrics = QFontMetrics(self._font)
        self._line_height = self._metrics.lineSpacing()
        self._char_width = self._metrics.horizontalAdvance("0") or self._metrics.averageCharWidth() or 1
        # theme cache generation for canvas_paint invalidation
        self._theme_generation = 0
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._document_blocks: Any = None
        self._document_index: Any = None
        self._document_layout: Any = None
        self._document_asset_resolver: Any = None
        self._doc_selection = DocumentSelection()
        self._sync_height()
        try:
            ThemeManager.get_instance().theme_changed.connect(
                self._on_theme_changed
            )
        except Exception:
            pass
        try:
            UiScale.get_instance().scale_changed.connect(
                self._on_scale_changed
            )
        except Exception:
            pass

    def _on_theme_changed(self, *_args) -> None:
        # Invalidate theme color cache in canvas_paint
        try:
            import sli_ui_toolkit.ui.widgets.composite.text_view.canvas_paint as _cp

            _cp._cached_foreground = None
            _cp._cached_span_colors = None
            _cp._cached_selection_color = None
        except Exception:
            pass
        if self._document_blocks is not None:
            self._relayout_document()
        else:
            self.update()

    def _on_scale_changed(self, *_args) -> None:
        # Scale may affect font metrics; refresh cached widths
        try:
            self._metrics = QFontMetrics(self._font)
            self._line_height = self._metrics.lineSpacing()
            self._char_width = self._metrics.horizontalAdvance("0") or self._metrics.averageCharWidth() or 1
        except Exception:
            pass
        if self._document_blocks is not None:
            # The singleton connections outlive the widget: a canvas whose
            # C++ side is already deleted (GC'd wrapper, scale test teardown)
            # must not raise from the signal into the emitting test.
            try:
                self._relayout_document()
            except RuntimeError:
                pass
        else:
            self._sync_height()
            self.update()

    # -- state --------------------------------------------------------------

    def text(self) -> str:
        return "\n".join(self._lines)

    def plain_text(self) -> str:
        """Full plain text of the current content (document or code)."""
        if self._document_index is not None:
            return self._document_index.text
        return self.text()

    def set_text(self, text: str) -> None:
        self._lines = text.split("\n") if text else [""]
        self._cursor = (0, 0)
        self._selection.clear()
        self._chain_selecting = None
        self._document_blocks = None
        self._document_index = None
        self._document_layout = None
        self._document_asset_resolver = None
        self._doc_selection.reset()
        self._sync_height()
        self.update()

    def is_document(self) -> bool:
        return self._document_blocks is not None


    def set_document(
        self, markdown: str, *, resolve_asset=None
    ) -> None:
        """Switch to read-only document mode (markdown blocks)."""
        self._lines = []
        self._cursor = (0, 0)
        self._selection.clear()
        self._chain_selecting = None
        self._editing = False
        self._document_blocks = parse_help_blocks(markdown) if markdown else ()
        self._document_index = build_text_index(self._document_blocks)
        self._doc_selection.index = self._document_index
        self._document_asset_resolver = resolve_asset
        self._document_layout = None
        self._doc_selection.reset()
        self.unsetCursor()
        self._relayout_document()

    def _doc_layout_pos(self, point) -> QPointF:
        return QPointF(point) - QPointF(constants.PAD, constants.PAD)

    def _doc_offset_at(self, event) -> int | None:
        if self._document_layout is None:
            return None
        return hit_test_text_offset(
            self._document_layout, self._doc_layout_pos(event.position().toPoint())
        )

    def _document_mouse_press(self, event) -> None:
        """Press/double-click in document mode: one handler for both, the
        unified chain counter resolves double = word, triple = segment."""
        self._doc_selection.press(
            self._doc_offset_at(event), event.position().toPoint()
        )
        self.setFocus()
        self.update()

    def _document_mouse_move(self, event) -> None:
        sel = self._doc_selection
        if (
            event.buttons() & Qt.MouseButton.LeftButton
            and sel.press_offset is not None
            and sel.selection is not None
        ):
            if not sel.dragged:
                if not sel.should_drag(event.position().toPoint()):
                    return
                sel.dragged = True
            offset = self._doc_offset_at(event)
            if offset is not None:
                sel.extend(offset)
                self.update()

    def _document_mouse_release(self, event) -> None:
        sel = self._doc_selection
        if sel.dragged:
            sel.end_gesture()
            return
        if self._document_layout is None:
            sel.end_gesture()
            return
        pos = self._doc_layout_pos(event.position().toPoint())
        href = hit_test_link(self._document_layout, pos)
        if href:
            self.linkActivated.emit(href)
            sel.end_gesture()
            return
        path = hit_test_pixmap(self._document_layout, pos)
        if path:
            self.imageActivated.emit(path)
        sel.end_gesture()

    def _document_key(self, event) -> bool:
        """Handle keys in document mode; True if consumed."""
        if event.matches(QKeySequence.StandardKey.SelectAll):
            if self._document_index is not None:
                self._doc_selection.select_all(len(self._document_index.text))
                self.update()
            return True
        if event.matches(QKeySequence.StandardKey.Copy):
            rng = self._doc_selection.copy_range()
            if rng is not None and self._document_index is not None:
                lo, hi = rng
                QGuiApplication.clipboard().setText(
                    self._document_index.slice_plain(lo, hi)
                )
            return True
        return False

    def _relayout_document(self) -> None:
        """(Re)build the document layout for the current width."""
        if self._document_blocks is None:
            return
        width = max(1, self.width() - 2 * constants.PAD)
        self._document_layout = layout_document(
            self._document_blocks,
            self._document_index,
            width,
            ThemeManager.get_instance(),
            resolve_asset=self._document_asset_resolver,
        )
        self._sync_height()
        self.update()

    def is_editing(self) -> bool:
        return self._editing

    def set_line_number_start(self, start: int | None) -> None:
        """VS Code-style line-number gutter: the number of the first
        visible line (e.g. the class's line in its source file); ``None``
        disables the gutter. Code mode only — document mode never shows it.
        """
        self._line_number_start = start
        self.update()

    def set_line_number_map(self, mapping: dict[int, str] | None) -> None:
        """Explicit gutter text per display line (e.g. real file line
        numbers in a view with collapsed gaps). Lines not in the map fall
        back to ``start + index``. ``None`` clears the override."""
        self._line_number_map = dict(mapping) if mapping else None
        self.update()

    def set_fold_lines(self, lines: set[int] | None) -> None:
        """Display lines that carry a gutter disclosure arrow (collapsed
        code regions, VS Code style — arrow left of the line number). An
        empty set keeps folding enabled (the constant arrow offset stays
        reserved); ``None`` disables it entirely."""
        self._fold_lines = set(lines) if lines is not None else None
        self.update()

    def line_at(self, y: int) -> int:
        """Display line index for a y coordinate in widget space."""
        return max(
            0,
            min(
                len(self._lines) - 1,
                (int(y) - constants.PAD) // max(1, self._line_height),
            ),
        )

    def _gutter_text(self, index: int) -> str:
        if self._line_number_map is not None and index in self._line_number_map:
            return self._line_number_map[index]
        start = self._line_number_start
        return str(start + index) if start is not None else ""

    def _gutter_width(self) -> int:
        """Width of the line-number gutter (0 when disabled).

        Sized from the widest label — with numeric labels (file line
        numbers, gap boundary numbers) the width is identical in every
        collapse state, so the text's left offset never jumps."""
        if self._line_number_start is None:
            return 0
        digits = 2
        if self._line_number_map is not None:
            for label in self._line_number_map.values():
                digits = max(digits, len(label))
        else:
            last = self._line_number_start + max(1, len(self._lines)) - 1
            digits = max(digits, len(str(last)))
        return (
            digits * self._metrics.horizontalAdvance("0")
            + 2 * constants.GUTTER_PAD
            + self._fold_arrow_reserve()
        )

    def _text_x(self) -> int:
        """Left edge of the code text: page padding + line-number gutter."""
        return constants.PAD + self._gutter_width()

    def set_editing(self, editing: bool) -> None:
        if editing == self._editing:
            return
        self._editing = editing
        if editing:
            self.setCursor(Qt.CursorShape.IBeamCursor)
            self.setFocus()
            # Register as a real text-input client (QLineEdit/QTextEdit do
            # this by default; custom painted widgets must opt in): the
            # platform input context then treats the widget as an editor
            # — IME hotkeys and keyboard-layout switching keep working
            # while it has focus.
            self.setAttribute(
                Qt.WidgetAttribute.WA_InputMethodEnabled, True
            )
        else:
            self._selection.clear()
            self._chain_selecting = None
            self._drag_extending = False
            self.unsetCursor()
            self.setAttribute(
                Qt.WidgetAttribute.WA_InputMethodEnabled, False
            )
        self.update()

    def update(self, *args, **kwargs) -> None:  # noqa: N802  # debug probe for repaint storm
        # Single getenv per update, logger only — no file IO on hot path
        if os.getenv("SLI_TEXTVIEW_DEBUG") == "1" or os.getenv("IMGSLI_TRACE") == "1":
            global _update_counter, _last_update_ts
            _update_counter += 1
            now = time.perf_counter()
            interval = (now - _last_update_ts) * 1000 if _last_update_ts else 0
            _last_update_ts = now
            if _update_counter % 10 == 0 or (interval < 20 and interval != 0):
                stack = "".join(traceback.format_stack()[-7:-3])
                msg = f"TextCanvas update#{_update_counter} interval={interval:.1f}ms stack:\n{stack}"
                _canvas_logger.warning(msg)
        super().update(*args, **kwargs)

    def repaint(self, *args, **kwargs) -> None:  # noqa: N802
        if os.getenv("SLI_TEXTVIEW_DEBUG") == "1":
            stack = "".join(traceback.format_stack()[-6:-2])
            _canvas_logger.warning("TextCanvas repaint stack:\n%s", stack)
        super().repaint(*args, **kwargs)

    def _sync_height(self) -> None:
        # The content height is a MINIMUM, not a fixed size: the host scroll
        # area stretches the canvas to its viewport (the text view fills the
        # window and only scrolls when the content exceeds it) — a fixed
        # height forced the renderer to expand to the whole document.
        _dbg = os.getenv("SLI_TEXTVIEW_DEBUG") == "1"
        t0 = time.perf_counter() if _dbg else 0
        if self._document_layout is not None:
            h = int(self._document_layout.height) + 2 * constants.PAD
            self.setMinimumHeight(h)
        else:
            lines = max(1, len(self._lines))
            h = self._line_height * lines + 2 * constants.PAD
            self.setMinimumHeight(h)
            if _dbg and lines > 1000:
                _canvas_logger.warning(
                    "TextCanvas _sync_height N=%d h=%d line_h=%d", lines, h, self._line_height
                )
        self.updateGeometry()
        if _dbg and t0:
            dt = (time.perf_counter() - t0) * 1000
            if dt > 5:
                _canvas_logger.warning("TextCanvas _sync_height dt=%.2fms", dt)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self._document_blocks is not None:
            self._relayout_document()
