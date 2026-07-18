"""Unified help document body surface (paint + selection)."""

from __future__ import annotations

import re
from collections.abc import Callable

from PySide6.QtCore import QElapsedTimer, QPoint, QPointF, Qt, QSize, Signal
from PySide6.QtGui import QGuiApplication, QKeySequence, QMouseEvent, QPaintEvent, QPainter
from PySide6.QtWidgets import QApplication, QSizePolicy, QWidget

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.composite.help_document.blocks import HelpBlock
from sli_ui_toolkit.ui.widgets.composite.help_document.layout.builder import (
    layout_document,
)
from sli_ui_toolkit.ui.widgets.composite.help_document.layout.hit_test import (
    hit_test_link,
    hit_test_pixmap,
    hit_test_text_offset,
)
from sli_ui_toolkit.ui.widgets.composite.help_document.layout.paint import paint_layout
from sli_ui_toolkit.ui.widgets.composite.help_document.layout.types import (
    AssetResolver,
    LayoutResult,
)
from sli_ui_toolkit.ui.widgets.composite.help_document.text_index import (
    DocumentTextIndex,
    build_text_index,
    segment_bounds_at_offset,
    word_bounds_at_offset,
)

_DRAG_THRESHOLD_PX = 4
# Triple-click needs more slack than OS double-click: the third press comes after
# the user has already seen the word selection.
_MULTI_CLICK_INTERVAL_MIN_MS = 900
_MULTI_CLICK_INTERVAL_SCALE = 2.5
_MULTI_CLICK_DISTANCE_SCALE = 2


class _AnchorMarker(QWidget):
    """Zero-height scroll target for ``ensureWidgetVisible``."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(1)
        self.setMaximumWidth(1)


class HelpDocumentBodyCanvas(QWidget):
    """Painted help body with unified text selection."""

    linkActivated = Signal(str)
    imageActivated = Signal(str)
    textContextMenuRequested = Signal(QPoint)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("HelpDocumentBodyCanvas")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(0)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        self._theme = ThemeManager.get_instance()
        self._resolve_asset: AssetResolver | None = None
        self._blocks: tuple[HelpBlock, ...] = ()
        self._text_index = DocumentTextIndex("", (), ())
        self._layout = LayoutResult(1.0, 1.0, (), (), {})
        self._sel_anchor: int | None = None
        self._sel_focus: int | None = None
        self._press_pos: QPointF | None = None
        self._press_offset: int | None = None
        self._dragging = False
        # After double-click, keep the button-down state and extend by words on drag.
        self._word_selecting = False
        self._word_anchor: tuple[int, int] | None = None
        # After triple-click, extend by paragraph/segment on drag.
        self._paragraph_selecting = False
        self._paragraph_anchor: tuple[int, int] | None = None
        self._click_timer = QElapsedTimer()
        self._click_count = 0
        self._click_last_pos: QPoint | None = None
        self._anchor_markers: dict[str, _AnchorMarker] = {}
        self._last_layout_width: int = 0

        self._theme.theme_changed.connect(self._relayout)
        self.customContextMenuRequested.connect(self._emit_context_menu)

    def set_asset_resolver(self, resolver: AssetResolver | None) -> None:
        self._resolve_asset = resolver
        self._relayout()

    def set_blocks(self, blocks: tuple[HelpBlock, ...]) -> None:
        self._blocks = tuple(blocks)
        self._text_index = build_text_index(self._blocks)
        self.clear_selection()
        self._relayout()

    def text_index(self) -> DocumentTextIndex:
        return self._text_index

    def plain_text(self) -> str:
        return self._text_index.text

    def selected_plain_text(self) -> str:
        start, end = self._selection_range()
        if start is None or end is None or start == end:
            return ""
        return self._text_index.slice_plain(start, end)

    def selected_markdown(self, source_markdown: str) -> str:
        selected = self.selected_plain_text()
        return markdown_for_selection(selected, source_markdown)

    def select_all_text(self) -> None:
        if not self._text_index.text:
            self.clear_selection()
            return
        self._sel_anchor = 0
        self._sel_focus = len(self._text_index.text)
        self.update()

    def anchor_widget(self, anchor: str) -> QWidget | None:
        return self._anchor_markers.get(anchor)

    def minimumSizeHint(self) -> QSize:
        return QSize(0, max(1, int(self._layout.height)))

    def sizeHint(self) -> QSize:
        width = self.width() if self.width() > 1 else max(1, int(self._layout.width))
        return QSize(width, max(1, int(self._layout.height)))

    def relayout(self) -> None:
        """Re-measure body content for the current widget width."""
        self._relayout()
        self.updateGeometry()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        width = self._content_width()
        if width != self._last_layout_width:
            self._relayout()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        start, end = self._selection_range()
        paint_layout(
            painter,
            self._layout,
            selection_start=start,
            selection_end=end,
            theme=self._theme,
        )

    def clear_selection(self) -> None:
        self._sel_anchor = None
        self._sel_focus = None
        self._word_selecting = False
        self._word_anchor = None
        self._paragraph_selecting = False
        self._paragraph_anchor = None
        self.update()

    def _multi_click_interval_ms(self) -> int:
        hints = QApplication.styleHints()
        return max(
            _MULTI_CLICK_INTERVAL_MIN_MS,
            int(hints.mouseDoubleClickInterval() * _MULTI_CLICK_INTERVAL_SCALE),
        )

    def _multi_click_distance(self) -> int:
        hints = QApplication.styleHints()
        return max(1, int(hints.mouseDoubleClickDistance() * _MULTI_CLICK_DISTANCE_SCALE))

    def _arm_click_chain(self, pos: QPointF, count: int) -> None:
        """Keep a multi-click chain alive from *pos* with the given press count."""
        self._click_count = count
        self._click_timer.restart()
        self._click_last_pos = pos.toPoint()

    def _update_click_count(self, pos: QPointF) -> int:
        """Count rapid same-spot presses (Qt has no public clickCount on QMouseEvent)."""
        interval = self._multi_click_interval_ms()
        distance = self._multi_click_distance()
        local = pos.toPoint()
        if (
            self._click_timer.isValid()
            and self._click_timer.elapsed() <= interval
            and self._click_last_pos is not None
            and (local - self._click_last_pos).manhattanLength() <= distance
        ):
            self._click_count += 1
        else:
            self._click_count = 1
        self._click_timer.restart()
        self._click_last_pos = local
        return self._click_count

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        pos = QPointF(event.position())
        click_count = self._update_click_count(pos)
        self._press_pos = pos
        self._press_offset = hit_test_text_offset(self._layout, pos)
        self._dragging = False
        self._word_selecting = False
        self._word_anchor = None
        self._paragraph_selecting = False
        self._paragraph_anchor = None
        if click_count >= 3 and self._press_offset is not None:
            bounds = segment_bounds_at_offset(self._text_index, self._press_offset)
            if bounds is not None and bounds[0] != bounds[1]:
                self._sel_anchor, self._sel_focus = bounds
                self._paragraph_anchor = bounds
                self._paragraph_selecting = True
                # Allow a following click to keep extending the chain if needed.
                self._arm_click_chain(pos, 3)
                self.update()
                self.setFocus()
                event.accept()
                return
        if self._press_offset is not None:
            self._sel_anchor = self._press_offset
            self._sel_focus = self._press_offset
            self.update()
        else:
            self.clear_selection()
        self.setFocus()
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        pos = QPointF(event.position())
        self._update_hover_cursor(pos)
        if self._press_pos is None:
            event.accept()
            return
        if not self._dragging:
            delta = pos - self._press_pos
            if delta.manhattanLength() >= _DRAG_THRESHOLD_PX:
                self._dragging = True
        if self._dragging:
            offset = hit_test_text_offset(self._layout, pos)
            if offset is not None and self._sel_anchor is not None:
                if self._paragraph_selecting and self._paragraph_anchor is not None:
                    self._extend_paragraph_selection(offset)
                elif self._word_selecting and self._word_anchor is not None:
                    self._extend_word_selection(offset)
                else:
                    self._sel_focus = offset
                self.update()
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mouseReleaseEvent(event)
        pos = QPointF(event.position())
        self._update_hover_cursor(pos)
        if not self._dragging:
            href = hit_test_link(self._layout, pos)
            if href:
                self.linkActivated.emit(href)
                self._clear_press_state()
                event.accept()
                return
            image_path = hit_test_pixmap(self._layout, pos)
            if image_path:
                self.imageActivated.emit(image_path)
                self._clear_press_state()
                event.accept()
                return
        self._clear_press_state()
        event.accept()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mouseDoubleClickEvent(event)
        pos = QPointF(event.position())
        offset = hit_test_text_offset(self._layout, pos)
        if offset is not None:
            bounds = word_bounds_at_offset(self._text_index.text, offset)
            if bounds is not None and bounds[0] != bounds[1]:
                self._sel_anchor, self._sel_focus = bounds
                self._word_anchor = bounds
                self._word_selecting = True
            else:
                self._sel_anchor = offset
                self._sel_focus = offset
                self._word_anchor = None
                self._word_selecting = False
            # Keep press state so a held drag after double-click can extend.
            self._press_pos = pos
            self._press_offset = offset
            self._dragging = False
            # Restart the multi-click window from the double-click so the third
            # press has a full generous interval (not the leftover of the pair).
            self._arm_click_chain(pos, 2)
            self.update()
        else:
            self.clear_selection()
            self._clear_press_state()
        self.setFocus()
        event.accept()

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.unsetCursor()
        super().leaveEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.matches(QKeySequence.StandardKey.SelectAll):
            self.select_all_text()
            event.accept()
            return
        if event.matches(QKeySequence.StandardKey.Copy):
            text = self.selected_plain_text()
            if text:
                QGuiApplication.clipboard().setText(text)
            event.accept()
            return
        super().keyPressEvent(event)

    def _emit_context_menu(self, pos: QPoint) -> None:
        # Do not auto-select on right-click: copy actions stay disabled until
        # the user has a real selection (double-click word / drag / select all).
        self.textContextMenuRequested.emit(self.mapToGlobal(pos))

    def _clear_press_state(self) -> None:
        self._press_pos = None
        self._press_offset = None
        self._dragging = False
        # Keep word/paragraph selecting only while the button is down;
        # release ends the gesture but leaves the selection painted.
        self._word_selecting = False
        self._word_anchor = None
        self._paragraph_selecting = False
        self._paragraph_anchor = None

    def _extend_word_selection(self, offset: int) -> None:
        """Grow the double-click selection word-by-word toward *offset*."""
        assert self._word_anchor is not None
        wa, wb = self._word_anchor
        text = self._text_index.text
        bounds = word_bounds_at_offset(text, offset)
        if bounds is None:
            self._sel_anchor = wa
            self._sel_focus = wb
            return
        ca, cb = bounds
        if ca == cb:
            # Between words / punctuation: still extend toward the caret.
            if offset >= wb:
                self._sel_anchor = wa
                self._sel_focus = max(wb, offset)
            elif offset < wa:
                self._sel_anchor = wb
                self._sel_focus = min(wa, offset)
            else:
                self._sel_anchor = wa
                self._sel_focus = wb
            return
        if ca >= wa:
            self._sel_anchor = wa
            self._sel_focus = max(wb, cb)
        else:
            self._sel_anchor = wb
            self._sel_focus = min(wa, ca)

    def _extend_paragraph_selection(self, offset: int) -> None:
        """Grow the triple-click selection segment-by-segment toward *offset*."""
        assert self._paragraph_anchor is not None
        pa, pb = self._paragraph_anchor
        bounds = segment_bounds_at_offset(self._text_index, offset)
        if bounds is None:
            self._sel_anchor = pa
            self._sel_focus = pb
            return
        ca, cb = bounds
        if ca >= pa:
            self._sel_anchor = pa
            self._sel_focus = max(pb, cb)
        else:
            self._sel_anchor = pb
            self._sel_focus = min(pa, ca)

    def _update_hover_cursor(self, pos: QPointF) -> None:
        if hit_test_link(self._layout, pos) or hit_test_pixmap(self._layout, pos):
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        elif hit_test_text_offset(self._layout, pos) is not None:
            self.setCursor(Qt.CursorShape.IBeamCursor)
        else:
            self.unsetCursor()

    def _selection_range(self) -> tuple[int | None, int | None]:
        if self._sel_anchor is None or self._sel_focus is None:
            return None, None
        if self._sel_anchor <= self._sel_focus:
            return self._sel_anchor, self._sel_focus
        return self._sel_focus, self._sel_anchor

    def _relayout(self, *_args) -> None:
        width = self._content_width()
        self._last_layout_width = width
        self._layout = layout_document(
            self._blocks,
            self._text_index,
            float(width),
            self._theme,
            self._resolve_asset,
        )
        self.setMinimumHeight(max(1, int(self._layout.height)))
        self._sync_anchor_markers()
        self.update()

    def _content_width(self) -> int:
        width = self.width()
        if width > 1:
            return width
        parent = self.parentWidget()
        if parent is not None:
            margins = 0
            if parent.layout() is not None:
                m = parent.layout().contentsMargins()
                margins = m.left() + m.right()
            parent_w = parent.width()
            if parent_w > margins + 1:
                return max(1, parent_w - margins)
        return max(1, width)

    def _sync_anchor_markers(self) -> None:
        for anchor, marker in list(self._anchor_markers.items()):
            if anchor not in self._layout.anchors:
                marker.deleteLater()
                del self._anchor_markers[anchor]
        for anchor, y in self._layout.anchors.items():
            marker = self._anchor_markers.get(anchor)
            if marker is None:
                marker = _AnchorMarker(self)
                self._anchor_markers[anchor] = marker
            marker.move(0, int(y))
            marker.show()


def _normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def markdown_for_selection(selection: str, markdown: str) -> str:
    """Best-effort map of a plain selection back to a markdown substring."""
    needle = selection.strip()
    if not needle:
        return markdown
    if needle in markdown:
        return needle
    norm_needle = _normalize_ws(needle)
    if not norm_needle:
        return markdown
    if norm_needle in markdown:
        return norm_needle
    pattern = re.escape(norm_needle).replace(r"\ ", r"\s+")
    match = re.search(pattern, markdown, flags=re.MULTILINE)
    if match is not None:
        return match.group(0)
    return markdown
