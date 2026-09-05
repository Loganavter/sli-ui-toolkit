"""Unified help document body surface (paint + selection)."""

from __future__ import annotations

import logging
import re
import unicodedata
from collections.abc import Callable

from PySide6.QtCore import QPoint, QPointF, Qt, QSize, Signal
from PySide6.QtGui import QGuiApplication, QKeySequence, QMouseEvent, QPaintEvent, QPainter
from PySide6.QtWidgets import QSizePolicy, QWidget

from sli_ui_toolkit.core.debug_flags import any_flag

# [nav-help-text] trace lines fire on help-doc scroll edges. Gated on the
# opt-in nav flag at call time (off by default even under the host's
# --debug) — host-app ``docs/dev/LOGGING.md`` unique-prefix convention;
# same vars as ``ui.managers.navigation_debug`` (``SLI_NAV_DEBUG``,
# legacy alias ``UI_NAV_DEBUG``).
logger = logging.getLogger(__name__)


def _help_debug_enabled() -> bool:
    return any_flag("SLI_NAV_DEBUG", "UI_NAV_DEBUG")


def _help_debug(message: str, *args) -> None:
    if _help_debug_enabled():
        logger.debug(message, *args)

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.managers.ui_scale import UiScale
from sli_ui_toolkit.ui.widgets.composite.text_view.markdown import HelpBlock
from sli_ui_toolkit.ui.widgets.composite.text_view.layout.builder import (
    layout_document,
)
from sli_ui_toolkit.ui.widgets.composite.text_view.layout.constants import (
    PARAGRAPH_TAB_STOP_PX,
)
from sli_ui_toolkit.ui.widgets.composite.text_view.layout.hit_test import (
    hit_test_link,
    hit_test_pixmap,
    hit_test_text_offset,
)
from sli_ui_toolkit.ui.widgets.composite.text_view.layout.paint import paint_layout
from sli_ui_toolkit.ui.widgets.composite.text_view.layout.types import (
    AssetResolver,
    LayoutResult,
)
from sli_ui_toolkit.ui.widgets.composite.text_view.selection import (
    DocumentSelection,
)
from sli_ui_toolkit.ui.widgets.composite.text_view.text_index import (
    DocumentTextIndex,
    build_text_index,
)


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
        #: the unified document selection state (shared with the text view's
        #: document mode): offset anchor/focus, multi-click chain (double =
        #: word, triple = paragraph), drag threshold, word/paragraph extend.
        self._selection = DocumentSelection()
        self._anchor_markers: dict[str, _AnchorMarker] = {}
        self._last_layout_width: int = 0
        self._tab_stop_px: float = PARAGRAPH_TAB_STOP_PX
        #: search-highlight scroll target, reused across queries (not part of
        #: the anchor map — anchors are rebuilt on every relayout)
        self._search_marker: _AnchorMarker | None = None

        self._theme.theme_changed.connect(self._relayout)
        # Document fonts resolve through ui_font() per layout pass; re-layout
        # on UiScale changes so text, headings and captions grow live with
        # the interface scale.
        UiScale.get_instance().scale_changed.connect(self._relayout)
        self.customContextMenuRequested.connect(self._emit_context_menu)

    def set_asset_resolver(self, resolver: AssetResolver | None) -> None:
        self._resolve_asset = resolver
        self._relayout()

    def set_tab_stop_px(self, px: float) -> None:
        """Column position a literal ``\\t`` in paragraph text lands on.

        Callers that build label/value rows (e.g. Image Properties) measure
        their widest label and pass it here so the tab column always clears
        it — a fixed constant would break under larger UI font scales.
        """
        px = max(1.0, float(px))
        if px == self._tab_stop_px:
            return
        self._tab_stop_px = px
        self._relayout()

    def set_blocks(self, blocks: tuple[HelpBlock, ...]) -> None:
        self._blocks = tuple(blocks)
        self._text_index = build_text_index(self._blocks)
        self._selection.index = self._text_index
        self.clear_selection()
        self._relayout()

    def text_index(self) -> DocumentTextIndex:
        return self._text_index

    def plain_text(self) -> str:
        return self._text_index.text

    def selected_plain_text(self) -> str:
        rng = self._selection.range()
        if rng is None:
            return ""
        start, end = rng
        return self._text_index.slice_plain(start, end)

    def selected_markdown(self, source_markdown: str) -> str:
        selected = self.selected_plain_text()
        return markdown_for_selection(selected, source_markdown)

    def select_all_text(self) -> None:
        if not self._text_index.text:
            self.clear_selection()
            return
        self._selection.select_all(len(self._text_index.text))
        self.update()

    def anchor_widget(self, anchor: str) -> QWidget | None:
        return self._anchor_markers.get(anchor)

    def scroll_to_text(self, query: str) -> QWidget | None:
        """Highlight the first normalized occurrence of ``query``.

        Uses the same normalization as the toolkit search scorers
        (``normalize_for_search``), so anything a non-fuzzy ``match_score``
        accepted is locatable here. Sets the document selection (painted as
        an accent wash) over the match and returns a zero-height
        scroll-target widget, or ``None`` when the query is absent.
        """
        from sli_ui_toolkit.ui.widgets.comboboxes._search import (
            find_normalized,
            normalize_for_search,
        )

        if not query:
            self.clear_selection()
            self._hide_search_marker()
            return None
        hit = find_normalized(
            normalize_for_search(query), self._text_index.text
        )
        if hit is None:
            self.clear_selection()
            self._hide_search_marker()
            return None
        raw_start, raw_end, _norm_pos = hit
        self._selection.set_range(raw_start, raw_end)
        self.update()
        return self._search_marker_at(raw_start)

    def _search_marker_at(self, offset: int) -> QWidget | None:
        """Reuse the dedicated search marker at the fragment containing offset."""
        fragment = None
        for frag in self._layout.text_fragments:
            if frag.global_start <= offset <= frag.global_end:
                fragment = frag
                break
        if fragment is None:
            return None
        marker = self._search_marker
        if marker is None:
            marker = _AnchorMarker(self)
            self._search_marker = marker
        marker.move(0, int(fragment.rect.top()))
        marker.show()
        return marker

    def _hide_search_marker(self) -> None:
        marker = self._search_marker
        if marker is not None:
            marker.hide()

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
        self._selection.reset()
        self._hide_search_marker()
        self.update()

    def _doc_press(self, event: QMouseEvent) -> None:
        """One press path for mousePressEvent and mouseDoubleClickEvent: the
        unified selection's chain counter resolves double = word, triple =
        paragraph."""
        pos = QPointF(event.position())
        offset = hit_test_text_offset(self._layout, pos)
        self._selection.press(offset, pos.toPoint())
        self.update()
        self.setFocus()
        event.accept()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        self._doc_press(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mouseDoubleClickEvent(event)
        self._doc_press(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        pos = QPointF(event.position())
        self._update_hover_cursor(pos)
        sel = self._selection
        if sel.press_point is None:
            event.accept()
            return
        if not sel.dragged:
            if not sel.should_drag(pos):
                event.accept()
                return
            sel.dragged = True
        offset = hit_test_text_offset(self._layout, pos)
        if offset is not None and sel.anchor is not None:
            sel.extend(offset)
            self.update()
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mouseReleaseEvent(event)
        pos = QPointF(event.position())
        self._update_hover_cursor(pos)
        sel = self._selection
        if not sel.dragged:
            href = hit_test_link(self._layout, pos)
            if href:
                self.linkActivated.emit(href)
                sel.end_gesture()
                event.accept()
                return
            image_path = hit_test_pixmap(self._layout, pos)
            if image_path:
                self.imageActivated.emit(image_path)
                sel.end_gesture()
                event.accept()
                return
        sel.end_gesture()
        event.accept()

    def leaveEvent(self, event) -> None:  # noqa: N802
        self.unsetCursor()
        super().leaveEvent(event)

    def _find_scroll_area(self):
        from PySide6.QtWidgets import QScrollArea

        w = self.parentWidget()
        while w is not None:
            if isinstance(w, QScrollArea):
                return w
            w = w.parentWidget()
        return None

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
        # In text sections (single-row AutoNavigation) Up/Down should scroll
        # through the document, not jump to another row. Accept the key so
        # NavigationManager's trial-dispatch sees it as handled and keeps focus
        # on the canvas while we scroll the parent QScrollArea.
        key = event.key()
        if key in (
            Qt.Key.Key_Up,
            Qt.Key.Key_Down,
            Qt.Key.Key_PageUp,
            Qt.Key.Key_PageDown,
            Qt.Key.Key_Home,
            Qt.Key.Key_End,
        ):
            area = self._find_scroll_area()
            if area is not None:
                bar = area.verticalScrollBar()
                if bar is not None:
                    before = bar.value()
                    at_top = before == bar.minimum()
                    at_bottom = before == bar.maximum()
                    # Library-level scroll handling for text sections — debug when nowhere to scroll
                    if _help_debug_enabled():
                        if (key == Qt.Key.Key_Up and at_top) or (
                            key == Qt.Key.Key_PageUp and at_top
                        ) or (key == Qt.Key.Key_Home and at_top):
                            _help_debug(
                                "[nav-help-text] %s at top (value=%s min=%s) — nowhere to scroll up",
                                key,
                                before,
                                bar.minimum(),
                            )
                        if (key == Qt.Key.Key_Down and at_bottom) or (
                            key == Qt.Key.Key_PageDown and at_bottom
                        ) or (key == Qt.Key.Key_End and at_bottom):
                            _help_debug(
                                "[nav-help-text] %s at bottom (value=%s max=%s) — nowhere to scroll down",
                                key,
                                before,
                                bar.maximum(),
                            )
                    if key == Qt.Key.Key_Up:
                        bar.setValue(bar.value() - 40)
                    elif key == Qt.Key.Key_Down:
                        bar.setValue(bar.value() + 40)
                    elif key == Qt.Key.Key_PageUp:
                        bar.setValue(bar.value() - bar.pageStep())
                    elif key == Qt.Key.Key_PageDown:
                        bar.setValue(bar.value() + bar.pageStep())
                    elif key == Qt.Key.Key_Home:
                        bar.setValue(bar.minimum())
                    elif key == Qt.Key.Key_End:
                        bar.setValue(bar.maximum())
                    # Even when at the edge and value doesn't change we still
                    # accept so NavigationManager doesn't try to move focus to
                    # another row — text scroll is the intended action for this
                    # single-row AutoNavigation section.
                    if _help_debug_enabled() and bar.value() == before and key in (
                        Qt.Key.Key_Up,
                        Qt.Key.Key_Down,
                        Qt.Key.Key_PageUp,
                        Qt.Key.Key_PageDown,
                    ):
                        _help_debug(
                            "[nav-help-text] scroll blocked at edge key=%s value=%s",
                            key,
                            before,
                        )
                    event.accept()
                    return
        super().keyPressEvent(event)

    def _emit_context_menu(self, pos: QPoint) -> None:
        # Do not auto-select on right-click: copy actions stay disabled until
        # the user has a real selection (double-click word / drag / select all).
        self.textContextMenuRequested.emit(self.mapToGlobal(pos))

    def _update_hover_cursor(self, pos: QPointF) -> None:
        if hit_test_link(self._layout, pos) or hit_test_pixmap(self._layout, pos):
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        elif hit_test_text_offset(self._layout, pos) is not None:
            self.setCursor(Qt.CursorShape.IBeamCursor)
        else:
            self.unsetCursor()

    def _selection_range(self) -> tuple[int | None, int | None]:
        rng = self._selection.range()
        return rng if rng is not None else (None, None)

    def _relayout(self, *_args) -> None:
        width = self._content_width()
        self._last_layout_width = width
        self._layout = layout_document(
            self._blocks,
            self._text_index,
            float(width),
            self._theme,
            self._resolve_asset,
            tab_stop_px=self._tab_stop_px,
        )
        self.setMinimumHeight(max(1, int(self._layout.height)))
        self._sync_anchor_markers()
        # Keep the search highlight's scroll marker on the fragment after a
        # theme/font/width relayout moved everything.
        rng = self._selection.range()
        if rng is not None and self._search_marker is not None:
            self._search_marker_at(rng[0])
        self.update()

    def _content_width(self) -> int:
        width = self.width()
        if width > 1:
            return width
        parent = self.parentWidget()
        if parent is not None:
            margins = 0
            parent_layout = parent.layout()
            if parent_layout is not None:
                m = parent_layout.contentsMargins()
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
            anchor_marker = self._anchor_markers.get(anchor)
            if anchor_marker is None:
                anchor_marker = _AnchorMarker(self)
                self._anchor_markers[anchor] = anchor_marker
            anchor_marker.move(0, int(y))
            anchor_marker.show()


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
