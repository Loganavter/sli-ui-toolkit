"""ConsoleView — painted, read-only multi-line console surface.

The console's glyphs are shaped and drawn by the toolkit's text engine: one
``QTextLayout`` per source line (``build_text_layout``, wrapped at the content
width, the line's colour/bold/italic baked into its ``QTextCharFormat``
spans), painted through the engine's ``paint_layout``. What the widget owns is
the console: the line model, max-lines trimming, a ``MinimalistScrollBar``,
follow-the-tail auto-scroll, the selection state, clipboard copy and a themed
right-click menu (Copy / Select all / Clear) through ``ContextMenuMixin``.

The widget owns its own surface (background/border read from
``ThemeManager``), so it needs no QSS. Hosts append :class:`ConsoleLine`
objects through :meth:`ConsoleView.append`; the log/process consoles layer
their level semantics on top.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterable

from PySide6.QtCore import QPointF, QRect, QRectF, QSize, Qt
from PySide6.QtGui import (
    QTextOption,
    QColor,
    QLinearGradient,
    QFont,
    QFontMetrics,
    QGuiApplication,
    QKeyEvent,
    QKeySequence,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QResizeEvent,
    QShowEvent,
    QTextLayout,
    QWheelEvent,
)
from PySide6.QtWidgets import QSizePolicy, QWidget

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.managers.ui_font import apply_ui_font, pin_font_size
from sli_ui_toolkit.ui.managers.ui_metrics import (
    AXIS_FONT,
    AXIS_SCALE,
    connect_ui_metrics,
)
from sli_ui_toolkit.ui.managers.ui_scale import scaled_px
from sli_ui_toolkit.ui.widgets.atomic.minimalist_scrollbar import (
    MINIMAL_SCROLLBAR_WIDTH,
    MinimalistScrollBar,
)
from sli_ui_toolkit.ui.widgets.helpers.context_menu import (
    ContextMenuMixin,
    TriggeredCallback,
)

if TYPE_CHECKING:
    from sli_ui_toolkit.ui.widgets.composite.context_menu.models import (
        ContextMenuEntry,
    )

#: Context-menu action ids (stable for hosts that bind their own translator).
CONSOLE_COPY_ACTION_ID = "console.copy"
CONSOLE_SELECT_ALL_ACTION_ID = "console.select_all"
CONSOLE_CLEAR_ACTION_ID = "console.clear"
from sli_ui_toolkit.ui.widgets.text.engine.layout.coords import (
    fragment_layout_to_index,
    line_for_y,
)
from sli_ui_toolkit.ui.widgets.text.engine.layout.hit_test import (
    hit_test_text_offset,
)
from sli_ui_toolkit.ui.widgets.text.engine.layout.paint import paint_layout
from sli_ui_toolkit.ui.widgets.text.engine.layout.text_layout import (
    build_text_layout,
)
from sli_ui_toolkit.ui.widgets.text.engine.layout.types import (
    LayoutResult,
    TextFragment,
)
from sli_ui_toolkit.ui.widgets.text.engine.markdown import InlineKind
from sli_ui_toolkit.ui.widgets.text.engine.text_index import (
    CharStyle,
    TextRole,
    TextRoleKind,
)

#: Design-px surface metrics (scaled through ``UiScale`` at read time).
_RADIUS = 6
_PADDING = 6
_BOTTOM_TOLERANCE = 2
#: Height of the clipped-edge ramp, design px - enough to read as a fade, short enough not to hide a text line.
_EDGE_FADE_HEIGHT = 24
#: Alpha of the selection wash (the engine's document bodies use 80; the
#: console shipped 90 and a log's low-contrast rows need it).
_SELECTION_ALPHA = 90
#: Bound on the prepared-line layouts. A trimmed log keeps the layouts of
#: lines it no longer holds, so past this the cache is dropped whole.
_ROW_CACHE_LIMIT = 4096


@dataclass(frozen=True)
class ConsoleLine:
    """One logical console line (a source line, before word-wrap).

    ``color`` is the resolved paint color for the whole line (``None`` means
    "use the view's default text token"). ``bold``/``italic`` carry per-line
    emphasis — the consoles use them for errors/commands.
    """

    text: str
    color: QColor | None = None
    bold: bool = False
    italic: bool = False


@dataclass(frozen=True)
class VisualLine:
    """A wrapped visual row: a slice of its source line.

    ``start``/``end`` are character offsets into the source line's text, so
    a visual row maps back to an exact character range (selection, copy and
    identity checks all use this).
    """

    text: str
    source_index: int
    start: int
    end: int


def _build_console_menu(
    view: "ConsoleView",
) -> tuple[tuple[ContextMenuEntry, ...], TriggeredCallback]:
    """Copy / Select all / Clear entries for the console's right-click menu.

    Consumed by :class:`~sli_ui_toolkit.ui.widgets.helpers.context_menu.ContextMenuMixin`
    (and through it the toolkit ``ContextMenu`` composite, never a raw
    ``QMenu``), so the popup paints in the active theme and keeps the platform
    placement the other toolkit menus use.
    """
    # Imported here, not at module scope: importing the submodule runs
    # ``context_menu/__init__``, which pulls the flyout stack and cycles back
    # through ``composite`` — the console must stay importable on its own.
    from sli_ui_toolkit.ui.widgets.composite.context_menu.models import (
        ContextMenuAction,
    )

    def on_triggered(action_id: str, _data: object) -> None:
        if action_id == CONSOLE_COPY_ACTION_ID:
            view.copy()
        elif action_id == CONSOLE_SELECT_ALL_ACTION_ID:
            view.select_all()
        elif action_id == CONSOLE_CLEAR_ACTION_ID:
            view.clear()

    has_lines = bool(view.lines())
    entries: tuple[ContextMenuEntry, ...] = (
        ContextMenuAction(
            CONSOLE_COPY_ACTION_ID,
            "Copy",
            enabled=bool(view.selected_text()),
        ),
        ContextMenuAction(
            CONSOLE_SELECT_ALL_ACTION_ID,
            "Select all",
            enabled=has_lines,
        ),
        ContextMenuAction(
            CONSOLE_CLEAR_ACTION_ID,
            "Clear",
        ),
    )
    return entries, on_triggered


class ConsoleView(ContextMenuMixin, QWidget):
    """Painted, read-only console surface (no stock text widget)."""

    def __init__(self, parent: QWidget | None = None, *, max_lines: int | None = None) -> None:
        super().__init__(parent)
        self.theme_manager = ThemeManager.get_instance()
        self._lines: list[ConsoleLine] = []
        self._max_lines: int | None = None if max_lines is None else max(0, int(max_lines))
        self._font = apply_ui_font(self)
        self._font_external = False
        self._row_height = 1
        self._pad = scaled_px(_PADDING)
        self._scroll_reserve = scaled_px(MINIMAL_SCROLLBAR_WIDTH)
        self._layout_dirty = True
        self._plain_text_cache: str | None = None
        self._wrap_width: int | None = None
        # Every glyph is shaped and drawn by the text engine: one prepared
        # QTextLayout per source line (wrapped at the content width), cached
        # per (text, colour, emphasis) for the life of one wrap width. `_rows`
        # is the engine's own geometry table - paint and hit-testing build
        # `TextFragment`s from it on demand, no second painter exists here.
        self._rows: list[tuple[float, float, int, int, QTextLayout]] = []
        self._frag_tops: list[float] = []
        self._line_offsets: list[int] = []
        self._row_count = 0
        #: key -> (layout, wrapped rows, layout ascent); the rows/ascent are
        #: read on every layout pass, so they ride with the layout.
        self._row_cache: dict[tuple[str, int, bool, bool], tuple[QTextLayout, int, float]] = {}
        #: per-character style runs are identical for every line of the same
        #: length/emphasis; a log has a few distinct lengths, not thousands.
        self._span_cache: dict[tuple[int, bool, bool], tuple[tuple, tuple]] = {}

        self._readonly_requested = True
        self._v_scroll_policy = None
        self._h_scroll_policy = None
        # Follow-the-tail state: True while the view sits at the bottom, so new lines pin it there. Scrolling away turns
        # it off and coming back turns it on again - one rule, no separate "user scrolled" bookkeeping to get wrong.
        self._follow = True
        self._edge_fade = False
        self._edge_fade_colour: QColor | None = None
        self._sel_anchor: tuple[int, int] | None = None
        self._sel_cursor: tuple[int, int] | None = None
        self._dragging = False

        self._bg_color = QColor("#000000")
        self._border_color = QColor("#000000")
        self._text_color = QColor("#ffffff")

        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setAutoFillBackground(False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.IBeamCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._vbar = MinimalistScrollBar(Qt.Orientation.Vertical, self)
        self._vbar.setVisible(False)
        self._vbar.valueChanged.connect(self._on_scroll_value_changed)

        self._refresh_theme()
        try:
            self.theme_manager.theme_changed.connect(self._on_theme_changed)
        except Exception:
            pass
        try:
            # Pads/scroll reserve are design px (``scaled_px``); the painted
            # font follows the appearance bus until a host takes it over via
            # ``set_font`` (``_font_external``) — the bus is the only way a
            # later face/scale change reaches this widget.
            connect_ui_metrics(
                self,
                self._on_metrics_changed,
                axes=frozenset({AXIS_FONT, AXIS_SCALE}),
            )
        except Exception:
            pass

    # -- model API ----------------------------------------------------------

    def append(
        self,
        text: str,
        *,
        color: QColor | None = None,
        bold: bool = False,
        italic: bool = False,
    ) -> ConsoleLine:
        """Append a line, following the tail while the view is at the bottom."""
        following = self._should_follow()
        line = ConsoleLine(
            str(text),
            QColor(color) if color is not None else None,
            bool(bold),
            bool(italic),
        )
        self._plain_text_cache = None
        self._lines.append(line)
        self._trim()
        self._mark_dirty()
        self._update_scroll_range()
        if following:
            self.scroll_to_bottom()
        self.update()
        return line

    def append_lines(self, lines: Iterable[str]) -> int:
        """Append many lines with ONE layout invalidation - the path for a log that arrives in batches.

        `append` per line invalidates (and therefore lays the whole console out) once per line; a render log delivers
        several lines per tick, which is what turned the panel into a freeze.
        """
        texts = [str(line) for line in lines]
        if not texts:
            return 0
        following = self._should_follow()
        self._plain_text_cache = None
        for text in texts:
            self._lines.append(ConsoleLine(text))
        self._trim()
        self._mark_dirty()
        self._update_scroll_range()
        if following:
            self.scroll_to_bottom()
        return len(texts)

    def append_console_lines(self, lines: Iterable[ConsoleLine]) -> int:
        """Append already-classified lines in one batch (colour/bold per line, one layout invalidation).

        The host's log filter decides what a line is - an error, a warning, a phase marker - and this is how that
        decision reaches the paint: `append_lines` takes plain text and paints every row the same.
        """
        pending = list(lines)
        if not pending:
            return 0
        following = self._should_follow()
        self._plain_text_cache = None
        self._lines.extend(pending)
        self._trim()
        self._mark_dirty()
        self._update_scroll_range()
        if following:
            self.scroll_to_bottom()
        return len(pending)

    def set_lines(self, lines: Iterable[ConsoleLine]) -> None:
        """Replace the whole model (theme recolor / bulk rebuild).

        The scroll position is preserved unless the view was already at the
        bottom, in which case it stays pinned there.
        """
        following = self._should_follow()
        prev_value = self._vbar.value()
        self._plain_text_cache = None
        self._lines = list(lines)
        self._trim()
        self._clear_selection()
        self._mark_dirty()
        self._update_scroll_range()
        if following:
            self.scroll_to_bottom()
        else:
            self._vbar.setValue(min(prev_value, self._vbar.maximum()))
        self.update()

    def clear(self) -> None:
        self._plain_text_cache = None
        self._lines.clear()
        self._clear_selection()
        self._mark_dirty()
        self._update_scroll_range()
        self._vbar.setValue(0)
        self.update()

    def set_max_lines(self, max_lines: int | None) -> None:
        """Cap the retained lines, trimming oldest first (``None`` = unbounded)."""
        self._max_lines = None if max_lines is None else max(0, int(max_lines))
        self._trim()
        self._mark_dirty()
        self._update_scroll_range()
        self.update()

    def set_font(self, font: QFont) -> None:
        """Host-owned face override (see ``_font_external``).

        The host's font is pinned (size asserted into the resolve mask) so
        the console does not pick the size up from its ancestor chain — the
        same trap ``apply_ui_font`` closes for the default path.
        """
        self._font = pin_font_size(QFont(font))
        self._font_external = True
        self._reset_layout_cache()
        # The BASE class on purpose: `setFont` below routes through here, so calling the override would recurse.
        QWidget.setFont(self, font)
        self._mark_dirty()
        self._update_scroll_range()
        self.update()

    def setFont(self, font: QFont) -> None:  # noqa: N802 - Qt spelling
        """A host that sets the font the Qt way (`apply(widget, pt)`, `widget.setFont(...)`) gets the same pinned face.

        The console paints from its own `_font`, so a plain inherited setFont would change nothing visible - the trap
        the toolkit already paid for once with `QLabel`-shaped labels.

        The constructor's own font application arrives HERE before the fields exist (`apply_ui_font` calls `setFont`
        while `_pad` is still unset), so an early call goes to the base class: routing it into `set_font` marked the
        layout dirty and read `self._pad` - measured as the host crashing on boot, with every test still green.
        """
        if not hasattr(self, "_pad"):
            QWidget.setFont(self, font)
            return
        self.set_font(font)

    # -- QTextEdit-compatible surface (a host migrating a log keeps its calls) ---------------------------

    def setPlainText(self, text: str) -> None:  # noqa: N802 - QTextEdit spelling
        """Replace the whole content with `text` (one console line per source line).

        Re-setting the SAME text is a no-op: a host that refreshes its pane on a timer used to pay a full re-wrap of the
        whole log every tick.
        """
        body = str(text)
        if body == getattr(self, "_plain_text_cache", None):
            return
        self._plain_text_cache = body
        self.set_lines([ConsoleLine(line) for line in body.split("\n")])

    def setHtml(self, html: str) -> None:  # noqa: N802
        """Accept a QTextEdit `setHtml` call and show its PLAIN text.

        A painted console has no rich-text engine: a log pane's HTML is the Designer's empty paragraph, and a host that
        passed real markup would lose its formatting here rather than at paint time. Stated in the docstring, not
        silently truncated.
        """
        from PySide6.QtGui import QTextDocument

        document = QTextDocument()
        document.setHtml(str(html))
        self.setPlainText(document.toPlainText())

    def setReadOnly(self, read_only: bool) -> None:  # noqa: N802
        """No-op: a console is always read-only. Present so a migrated `QTextEdit` keeps its call."""
        self._readonly_requested = bool(read_only)

    def setVerticalScrollBarPolicy(self, policy) -> None:  # noqa: N802
        """No-op: the console owns its scrollbar (it appears only when the content overflows)."""
        self._v_scroll_policy = policy

    def setHorizontalScrollBarPolicy(self, policy) -> None:  # noqa: N802
        """No-op: the console wraps lines and never scrolls horizontally."""
        self._h_scroll_policy = policy

    def verticalScrollBar(self) -> "_ConsoleScrollBar":  # noqa: N802
        """A `QScrollBar`-shaped facade over the console's own scroll.

        Hosts pin a log to the bottom with `verticalScrollBar().setValue(maximum())`; without this the call fails on a
        migrated pane. Only the surface a log host uses is provided - value, setValue, maximum, minimum.
        """
        return _ConsoleScrollBar(self)

    def lines(self) -> tuple[ConsoleLine, ...]:
        return tuple(self._lines)

    def text(self, *, separator: str = "\n") -> str:
        return separator.join(line.text for line in self._lines)

    # -- scrolling ----------------------------------------------------------

    def scroll_to_bottom(self) -> None:
        self._vbar.setValue(self._vbar.maximum())
        self._follow = True

    def is_at_bottom(self) -> bool:
        return self._vbar.value() >= self._vbar.maximum() - _BOTTOM_TOLERANCE

    def scroll_value(self) -> int:
        return self._vbar.value()

    def set_scroll_value(self, value: int) -> None:
        self._vbar.setValue(int(value))

    def set_auto_follow(self, enabled: bool) -> None:
        """Pin new lines to the bottom (``True``) or leave the scroll where the user put it (``False``).

        This is the sticky-scroll contract the owner asked for (2026-11-22): while the view sits at the bottom it keeps
        itself there as the log grows; scrolling up detaches it, scrolling back to the bottom re-attaches it. The state is
        DERIVED from the scroll position (``_should_follow``), so no separate flag can drift out of sync with what the
        user sees.
        """
        self._follow = bool(enabled)
        if self._follow:
            self.scroll_to_bottom()

    def auto_follow(self) -> bool:
        return bool(self._follow)

    def _should_follow(self) -> bool:
        """Follow when the view is at the bottom AND has not been detached by a scroll away."""
        if not self._follow:
            return False
        if self._vbar.maximum() <= 0:
            return True
        return self.is_at_bottom()

    # -- clipped-edge fade --------------------------------------------------

    def set_edge_fade_enabled(self, enabled: bool) -> None:
        """Fade the content that continues past the top/bottom edge (``False`` by default).

        A painted 24 px gradient in the SURFACE colour, drawn over the rows - not a ``QGraphicsEffect``: an effect
        renders the whole widget into an offscreen pixmap on every paint, which a log pane cannot afford (it froze the
        GUI thread, see `_EdgeFade` in `minimalist_scrollbar`). One ``fillRect`` per edge keeps it free.
        """
        enabled = bool(enabled)
        if enabled == self._edge_fade:
            return
        self._edge_fade = enabled
        self.update()

    def edge_fade_enabled(self) -> bool:
        return bool(self._edge_fade)

    def set_edge_fade_colour(self, colour) -> None:
        """Override the ramp colour; ``None`` restores the console's own surface colour."""
        self._edge_fade_colour = QColor(colour) if colour is not None else None
        self.update()

    def edge_fade_sides(self) -> tuple[bool, bool]:
        """(top, bottom) - the edges where content continues past the viewport."""
        bar = self._vbar
        return (bar.value() > bar.minimum(), bar.value() < bar.maximum())

    # -- geometry / introspection (used by the widget and by tests) ---------

    def visual_lines(self) -> list[VisualLine]:
        """Wrapped visual rows, in paint order, each bound to its source line.

        Derived from the engine layouts (the console no longer keeps its own
        wrap table): every ``QTextLine`` is one painted row, and its character
        range is the slice of the source line it shows.
        """
        self._ensure_layout()
        rows: list[VisualLine] = []
        for source_index, row in enumerate(self._rows):
            layout = row[4]
            text = layout.text()
            for index in range(layout.lineCount()):
                line = layout.lineAt(index)
                start = max(0, int(line.textStart()))
                end = min(len(text), start + int(line.textLength()))
                rows.append(VisualLine(text[start:end], source_index, start, end))
        return rows

    def line_index_at(self, y: int) -> int:
        """Source line index whose row contains pixel ``y`` (-1 when none)."""
        self._ensure_layout()
        if not self._rows:
            return -1
        if y < self._pad:
            return -1
        return self._fragment_at_row(self._row_at(float(y)))

    # -- selection / clipboard ---------------------------------------------

    def select_all(self) -> None:
        if not self._lines:
            return
        last = len(self._lines) - 1
        self._sel_anchor = (0, 0)
        self._sel_cursor = (last, len(self._lines[last].text))
        self.update()

    def selected_text(self) -> str:
        bounds = self._selection_bounds()
        if bounds is None:
            return ""
        (start_line, start_char), (end_line, end_char) = bounds
        end_line = min(end_line, len(self._lines) - 1)
        parts: list[str] = []
        for index in range(start_line, end_line + 1):
            source = self._lines[index].text
            start = start_char if index == start_line else 0
            end = end_char if index == end_line else len(source)
            start = max(0, min(len(source), start))
            end = max(start, min(len(source), end))
            parts.append(source[start:end])
        return "\n".join(parts)

    def copy(self) -> None:
        selected = self.selected_text()
        if selected:
            QGuiApplication.clipboard().setText(selected)

    # -- event overrides ----------------------------------------------------

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        was_bottom = self.is_at_bottom()
        self._pad = scaled_px(_PADDING)
        self._scroll_reserve = scaled_px(MINIMAL_SCROLLBAR_WIDTH)
        self._mark_dirty()
        self._update_scroll_range()
        if was_bottom:
            self.scroll_to_bottom()

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        """Re-validate the layout and the scroll range whenever the console becomes visible.

        A pane that lived on a hidden page laid itself out against the width it had while hidden, and a bar shown while
        the ancestor chain is unmapped is never positioned (``_position_scrollbar`` skips it) — the reported first show
        of the Logs tab: a range for a viewport that was gone, the bar at its default rect over the first rows, all of
        it cured only by the next appended line. Qt usually hands a hidden widget its resize event at show time, but not
        every path into a shown page does, so the show itself is the guard.
        """
        super().showEvent(event)
        self._mark_dirty()
        self._update_scroll_range()

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        bar = self._vbar
        if bar.minimum() == bar.maximum():
            event.ignore()
            return
        if not event.pixelDelta().isNull():
            delta = event.pixelDelta().y()
        else:
            delta = event.angleDelta().y() // 2
        if delta:
            bar.setValue(bar.value() - delta)
        event.accept()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        point = self._point_at(event.position().x(), event.position().y())
        self._dragging = point is not None
        self._sel_anchor = point
        self._sel_cursor = point
        self.update()
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._dragging and (event.buttons() & Qt.MouseButton.LeftButton):
            point = self._point_at(event.position().x(), event.position().y())
            if point is not None:
                self._sel_cursor = point
                self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._dragging = False
        super().mouseReleaseEvent(event)

    def build_context_menu(
        self,
    ) -> tuple[tuple[ContextMenuEntry, ...], TriggeredCallback]:
        """Right-click menu: Copy (with a selection) / Select all / Clear.

        The console had no menu at all (owner report 2026-11-28); it is the
        first consumer of the shared :class:`ContextMenuMixin`, so a second
        toolkit widget only has to return its entries instead of re-copying
        the popup plumbing ``Text`` already had.
        """
        return _build_console_menu(self)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.matches(QKeySequence.StandardKey.Copy) or (
            event.key() == Qt.Key.Key_Insert
            and bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        ):
            self.copy()
            event.accept()
            return
        if event.matches(QKeySequence.StandardKey.SelectAll):
            self.select_all()
            event.accept()
            return
        super().keyPressEvent(event)

    # -- painting -----------------------------------------------------------

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        painter = QPainter(self)
        if not painter.isActive():
            return
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()
        radius = scaled_px(_RADIUS)
        rounded = QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setBrush(self._bg_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(rounded, radius, radius)

        self._ensure_layout()
        painter.setClipRect(QRect(0, 0, self.width(), self.height()))
        offset = self._vbar.value()
        start, end = self._selection_globals()
        if self._rows:
            # The painter is moved to content coordinates: the engine paints a
            # laid-out body at its own positions, and the console owns only
            # which slice of it is on screen.
            painter.save()
            painter.translate(0.0, float(-offset))
            paint_layout(
                painter,
                self._visible_body(offset, self.height()),
                selection_start=start,
                selection_end=end,
                theme=self.theme_manager,
                selection_color=self._selection_wash(),
            )
            painter.restore()

        self._paint_edge_fade(painter, rounded)

        pen = QPen(QColor(self._border_color))
        pen.setWidthF(0.66)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rounded, radius, radius)
        painter.end()

    def _paint_edge_fade(self, painter: QPainter, bounds: QRectF) -> None:
        """Ramp the surface over the edge that continues (see ``set_edge_fade_enabled``)."""
        if not self._edge_fade:
            return
        top, bottom = self.edge_fade_sides()
        if not (top or bottom):
            return
        colour = QColor(self._edge_fade_colour) if self._edge_fade_colour is not None else QColor(self._bg_color)
        if not colour.isValid():
            return
        height = min(scaled_px(_EDGE_FADE_HEIGHT), max(1, self.height() // 2))
        solid = QColor(colour)
        solid.setAlpha(255)
        clear = QColor(colour)
        clear.setAlpha(0)
        painter.save()
        painter.setClipRect(bounds)
        if top:
            gradient = QLinearGradient(0, 0, 0, height)
            gradient.setColorAt(0.0, solid)
            gradient.setColorAt(1.0, clear)
            painter.fillRect(QRectF(0, 0, bounds.width(), height), gradient)
        if bottom:
            gradient = QLinearGradient(0, self.height() - height, 0, self.height())
            gradient.setColorAt(0.0, clear)
            gradient.setColorAt(1.0, solid)
            painter.fillRect(
                QRectF(0, self.height() - height, bounds.width(), height), gradient
            )
        painter.restore()

    def _selection_wash(self) -> QColor:
        """The console's own selection wash (accent at its own alpha)."""
        accent = QColor(self.theme_manager.get_color("accent"))
        accent.setAlpha(_SELECTION_ALPHA)
        return accent

    def _selection_globals(self) -> tuple[int | None, int | None]:
        """Selection in the engine's body-offset coordinates (None when empty)."""
        bounds = self._selection_bounds()
        if bounds is None or not self._line_offsets:
            return None, None
        (start_line, start_char), (end_line, end_char) = bounds
        if start_line >= len(self._line_offsets) or end_line >= len(self._line_offsets):
            return None, None
        return (
            self._line_offsets[start_line] + start_char,
            self._line_offsets[end_line] + end_char,
        )

    def _row_fragment(self, index: int) -> TextFragment:
        """The engine fragment for one laid-out source line (built on demand)."""
        top, height, start, end, layout = self._rows[index]
        return TextFragment(
            rect=QRectF(float(self._pad), top, float(self._wrap_width or 1), height),
            global_start=start,
            global_end=end,
            layout=layout,
            links=(),
        )

    def _visible_body(self, offset: int, height: int) -> LayoutResult:
        """The slice of the laid-out body the viewport shows.

        The engine paints what it is given; a console keeps a log far larger
        than its viewport, so the slice is cut here rather than by handing the
        painter a clip and walking thousands of fragments per frame. Fragments
        are materialised for the slice only - the row table itself is plain
        numbers, so a layout pass allocates nothing per line.
        """
        if not self._rows:
            return LayoutResult(
                width=float(self._wrap_width or 1),
                height=float(self._content_height()),
                text_fragments=(),
                pixmaps=(),
                anchors={},
            )
        # The painter is translated by -offset, so widget y=0 is content y=offset.
        top = float(offset)
        bottom = top + float(height)
        first = bisect.bisect_right(self._frag_tops, top) - 1
        first = max(0, min(first, len(self._frag_tops) - 1))
        last = bisect.bisect_left(self._frag_tops, bottom)
        last = max(first + 1, min(last, len(self._rows)))
        return LayoutResult(
            width=float(self._wrap_width or 1),
            height=float(self._content_height()),
            text_fragments=tuple(
                self._row_fragment(index) for index in range(first, last)
            ),
            pixmaps=(),
            anchors={},
        )

    # -- layout -------------------------------------------------------------

    def _mark_dirty(self) -> None:
        """Mark the layout stale - NEVER lay out here.

        `_ensure_layout` rebuilds every line's engine layout, so calling it from every append/set turned a log that
        grows during a render into O(n^2): 10 ticks a second over a growing log froze the GUI thread (py-spy:
        setPlainText -> set_lines -> the wrap pass). The layout is rebuilt where it is actually needed (paint, scroll
        range, hit-testing).
        """
        self._layout_dirty = True
        self.update()

    def _ensure_layout(self) -> None:
        # A width that moved without an event reaching us is dirty too. A pane laid out while hidden (at a construction
        # width or a page width it no longer has) otherwise keeps that wrap until something else marks the layout
        # stale, which is what made a first show carry a range for a viewport that was gone and a tiny thumb — the
        # appended line that finally marked it dirty "fixed everything at once" (reported 2026-11-28).
        width = self._content_width()
        if not self._layout_dirty and width == self._wrap_width:
            return
        fm = QFontMetrics(self._font)
        self._row_height = max(1, fm.lineSpacing())
        # A line's layout depends on (text, ink, emphasis, width): a log that grows by a few lines per tick then lays out
        # only those lines, and a stale width drops everything.
        if self._wrap_width != width:
            self._row_cache = {}
            self._span_cache = {}
            self._wrap_width = width
        rows: list[tuple[float, float, int, int, QTextLayout]] = []
        tops: list[float] = []
        offsets: list[int] = []
        row_height = float(self._row_height)
        baseline = float(fm.ascent())
        y = float(self._pad)
        offset = 0
        rows_total = 0
        for line in self._lines:
            layout, line_rows, ascent = self._line_layout(line, width)
            height = line_rows * row_height
            # The engine draws a layout from its top-left, so the layout's own
            # (fractional) ascent decides where the baseline lands. Shift the
            # rect by the difference to the integer ascent the console has
            # always painted at - without it a row sits half a device pixel
            # higher at DPR 2, which changes the antialiasing.
            rows.append((y + baseline - ascent, height, offset, offset + len(line.text), layout))
            tops.append(y)
            offsets.append(offset)
            y += height
            offset += len(line.text) + 1
            rows_total += line_rows
        self._rows = rows
        self._frag_tops = tops
        self._line_offsets = offsets
        self._row_count = rows_total
        self._layout_dirty = False
        self._update_scroll_range()

    def _line_layout(
        self, line: ConsoleLine, width: int
    ) -> tuple[QTextLayout, int, float]:
        """The engine layout for one source line, wrapped at *width*.

        Returns ``(layout, wrapped rows, first-line ascent)`` - the two scalars
        are read on every layout pass and cost more than the lookup.
        """
        ink = line.color if line.color is not None and line.color.isValid() else self._text_color
        key = (line.text, ink.rgba(), line.bold, line.italic)
        cached = self._row_cache.get(key)
        if cached is not None:
            return cached
        styles, roles = self._span_styles(len(line.text), line.bold, line.italic)
        layout, _links = build_text_layout(
            line.text,
            styles,
            roles,
            base_font=self._font,
            theme=self.theme_manager,
            width=float(width),
            color=ink,
            # A console must never clip: `WordWrap` keeps an unbreakable token (a hash, a base64 blob, a long engine
            # name) whole and lets it overflow the row, which the old painter never did - it hard-cut at the width.
            # `WrapAtWordBoundaryOrAnywhere` keeps the natural breaks where they exist (space, `-`, `/`, `.`) and only
            # cuts inside the token when there is no boundary at all.
            wrap_mode=QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere,
        )
        rows = max(1, layout.lineCount())
        ascent = 0.0
        first = layout.lineAt(0) if rows else None
        if first is not None and first.isValid():
            ascent = float(first.ascent())
        entry = (layout, rows, ascent)
        # A trimmed log keeps the cache keys of lines it no longer holds; drop
        # the whole thing at the cap rather than evicting per entry.
        if len(self._row_cache) >= _ROW_CACHE_LIMIT:
            self._row_cache.clear()
        self._row_cache[key] = entry
        return entry

    def _span_styles(self, length: int, bold: bool, italic: bool) -> tuple[tuple, tuple]:
        """Per-character style runs for a uniformly styled line (cached by shape)."""
        key = (length, bold, italic)
        entry = self._span_cache.get(key)
        if entry is None:
            kind = InlineKind.ITALIC if italic else (InlineKind.BOLD if bold else InlineKind.TEXT)
            entry = (
                tuple(CharStyle(kind, None, bold) for _ in range(length)),
                tuple(TextRole(TextRoleKind.BODY) for _ in range(length)),
            )
            self._span_cache[key] = entry
        return entry

    def _content_width(self) -> int:
        return max(1, self.width() - 2 * self._pad - self._scroll_reserve)

    def _content_height(self) -> int:
        """Painted content height in px - one owner for the scroll range and the scrollbar facade."""
        return 2 * self._pad + self._row_count * self._row_height

    def _update_scroll_range(self) -> None:
        self._ensure_layout()
        content_height = self._content_height()
        maximum = max(0, content_height - self.height())
        bar = self._vbar
        bar.blockSignals(True)
        bar.setRange(0, maximum)
        bar.setPageStep(max(1, self.height()))
        bar.setSingleStep(self._row_height)
        bar.blockSignals(False)
        if bar.value() > maximum:
            bar.setValue(maximum)
        bar.setVisible(maximum > 0)
        self._position_scrollbar()

    def _position_scrollbar(self) -> None:
        # `isHidden`, not `isVisible`: a page that is BEING shown (the tab switch, the first show of a hidden pane) has
        # already asked for the bar while the ancestor chain is still unmapped, and `isVisible` then skipped the geometry
        # and never retried - the bar was drawn at its default rect over the first rows until the next append.
        if self._vbar.isHidden():
            return
        self._vbar.setGeometry(
            self.width() - self._scroll_reserve,
            self._pad,
            self._scroll_reserve,
            max(1, self.height() - 2 * self._pad),
        )

    # -- point <-> model ----------------------------------------------------

    def _row_at(self, y: float) -> int:
        """Visual row under *y* (clamped to the body - a drag past the edge still selects)."""
        self._ensure_layout()
        rows = self._row_count
        if rows <= 0:
            return 0
        rel = y - self._pad + self._vbar.value()
        row = int(rel // max(1, self._row_height))
        return max(0, min(row, rows - 1))

    def _fragment_at_row(self, row: int) -> int:
        """Index of the source line that owns visual *row*."""
        if not self._frag_tops:
            return 0
        row = max(0, min(row, self._row_count - 1))
        y = self._pad + row * self._row_height
        index = bisect.bisect_right(self._frag_tops, float(y)) - 1
        return max(0, min(index, len(self._frag_tops) - 1))

    def _point_at(self, x: float, y: float) -> tuple[int, int] | None:
        """(source line, char) under a widget point, through the layout's own mapping."""
        self._ensure_layout()
        if not self._rows:
            return None
        # Fragment rects are content coordinates (the body starts at `_pad`),
        # so a widget point maps into the body by adding the scroll offset - not
        # by subtracting the pad (the paint path translates by -offset only).
        content_y = y + self._vbar.value()
        row = self._row_at(y)
        index = self._fragment_at_row(row)
        fragment = self._row_fragment(index)
        offset = hit_test_text_offset(
            LayoutResult(
                width=fragment.rect.width(),
                height=fragment.rect.height(),
                text_fragments=(fragment,),
                pixmaps=(),
                anchors={},
            ),
            QPointF(float(x), float(content_y)),
        )
        if offset is None:
            # Empty space (past the last glyph, below the body): land on the
            # nearest row's cursor instead of dropping the gesture.
            frag_index = index
            frag = fragment
            local_x = min(max(x, frag.rect.left()), frag.rect.right())
            local_y = min(max(content_y, frag.rect.top()), frag.rect.bottom() - 0.5)
            line = line_for_y(frag.layout, local_y - frag.rect.top())
            if line is None or not line.isValid():
                return (frag_index, 0)
            cursor = line.xToCursor(local_x - frag.rect.left())
            if isinstance(cursor, tuple):
                cursor = cursor[1]
            local = fragment_layout_to_index(frag, int(cursor))
            return self._offset_to_point(local)
        return self._offset_to_point(offset)

    def _offset_to_point(self, offset: int) -> tuple[int, int]:
        """Body-offset -> (source line, char)."""
        if not self._line_offsets:
            return (0, 0)
        index = bisect.bisect_right(self._line_offsets, offset) - 1
        index = max(0, min(index, len(self._line_offsets) - 1))
        return (index, max(0, offset - self._line_offsets[index]))

    def _selection_bounds(self) -> tuple[tuple[int, int], tuple[int, int]] | None:
        if self._sel_anchor is None or self._sel_cursor is None:
            return None
        if self._sel_anchor == self._sel_cursor:
            return None
        if self._sel_anchor <= self._sel_cursor:
            return (self._sel_anchor, self._sel_cursor)
        return (self._sel_cursor, self._sel_anchor)

    def _clear_selection(self) -> None:
        self._sel_anchor = None
        self._sel_cursor = None

    # -- helpers ------------------------------------------------------------

    def _trim(self) -> None:
        if self._max_lines is None:
            return
        if len(self._lines) > self._max_lines:
            self._lines = self._lines[-self._max_lines :] if self._max_lines > 0 else []
            self._clear_selection()

    def _reset_layout_cache(self) -> None:
        """Drop the engine layouts - their face, ink or width is about to change."""
        self._row_cache = {}
        self._span_cache = {}
        self._mark_dirty()

    def _refresh_theme(self) -> None:
        try:
            self._bg_color = QColor(self.theme_manager.get_color("surface.background"))
            self._border_color = QColor(self.theme_manager.get_color("input.border.thin"))
            self._text_color = QColor(self.theme_manager.get_color("dialog.text"))
        except Exception:
            self._bg_color = QColor(self.palette().base().color())
            self._border_color = QColor(self.palette().mid().color())
            self._text_color = QColor(self.palette().text().color())

    def _on_theme_changed(self, *_args) -> None:
        self._refresh_theme()
        # Every line's ink is a QTextCharFormat inside its engine layout: a new
        # theme means new formats, not just a repaint.
        self._reset_layout_cache()
        self._update_scroll_range()
        self.update()

    def _on_metrics_changed(self, *_args) -> None:
        """Face (``AXIS_FONT``) and scale (``AXIS_SCALE``) re-derivation.

        The painted font is cached; re-derive it from the resolver on a face
        change (a host that has NOT taken the font over via ``set_font``),
        then re-run the scale-dependent pad/scroll reserve work.
        """
        if not self._font_external:
            self._font = apply_ui_font(self)
        self._reset_layout_cache()
        self._pad = scaled_px(_PADDING)
        self._scroll_reserve = scaled_px(MINIMAL_SCROLLBAR_WIDTH)
        was_bottom = self.is_at_bottom()
        self._mark_dirty()
        self._update_scroll_range()
        if was_bottom:
            self.scroll_to_bottom()
        self.update()

    def _on_scroll_value_changed(self, _value: int) -> None:
        # The scroll moved (wheel, bar drag, keys, a host's setValue): the follow state follows the position, so being
        # at the bottom always means "keep me here" and being away from it always means "leave me alone".
        self._follow = self.is_at_bottom() or self._vbar.maximum() <= 0
        self.update()

    # -- size hints ---------------------------------------------------------

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(0, scaled_px(40))

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(scaled_px(220), scaled_px(120))


__all__ = ["ConsoleLine", "ConsoleView", "VisualLine"]


class _ConsoleScrollBar:
    """The `QScrollBar` subset a log host calls, mapped onto `ConsoleView`'s own scroll state."""

    def __init__(self, view: "ConsoleView") -> None:
        self._view = view

    def value(self) -> int:
        return self._view.scroll_value()

    def setValue(self, value: int) -> None:  # noqa: N802 - QScrollBar spelling
        self._view.set_scroll_value(int(value))

    def minimum(self) -> int:
        return 0

    def maximum(self) -> int:
        content = self._view._content_height()
        return max(0, content - self._view.height())
