"""ConsoleView — painted, read-only multi-line console surface.

The console renders its own text through the toolkit painter pipeline
(``QPainter.drawText`` + ``QFontMetrics``) with word-wrapped lines,
per-line color/bold/italic, a ``MinimalistScrollBar``, follow-the-tail
auto-scroll, mouse selection and clipboard copy.

The widget owns its own surface (background/border read from
``ThemeManager``), so it needs no QSS. Hosts append :class:`ConsoleLine`
objects through :meth:`ConsoleView.append`; the log/process consoles layer
their level semantics on top.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from PySide6.QtCore import QPointF, QRect, QRectF, QSize, Qt
from PySide6.QtGui import (
    QColor,
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

#: Design-px surface metrics (scaled through ``UiScale`` at read time).
_RADIUS = 6
_PADDING = 6
_BOTTOM_TOLERANCE = 2


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


class ConsoleView(QWidget):
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
        self._visual: list[VisualLine] = []
        self._layout_dirty = True
        self._wrap_cache: dict[str, list[tuple[int, int]]] = {}
        self._plain_text_cache: str | None = None
        self._wrap_width: int | None = None

        self._readonly_requested = True
        self._v_scroll_policy = None
        self._h_scroll_policy = None
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
        """Append a line, following the tail only when already at the bottom."""
        at_bottom = self.is_at_bottom()
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
        if at_bottom:
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
        at_bottom = self.is_at_bottom()
        self._plain_text_cache = None
        for text in texts:
            self._lines.append(ConsoleLine(text))
        self._trim()
        self._mark_dirty()
        self._update_scroll_range()
        if at_bottom:
            self.scroll_to_bottom()
        return len(texts)

    def set_lines(self, lines: Iterable[ConsoleLine]) -> None:
        """Replace the whole model (theme recolor / bulk rebuild).

        The scroll position is preserved unless the view was already at the
        bottom, in which case it stays pinned there.
        """
        was_bottom = self.is_at_bottom()
        prev_value = self._vbar.value()
        self._plain_text_cache = None
        self._lines = list(lines)
        self._trim()
        self._clear_selection()
        self._mark_dirty()
        self._update_scroll_range()
        if was_bottom:
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

    def is_at_bottom(self) -> bool:
        return self._vbar.value() >= self._vbar.maximum() - _BOTTOM_TOLERANCE

    def scroll_value(self) -> int:
        return self._vbar.value()

    def set_scroll_value(self, value: int) -> None:
        self._vbar.setValue(int(value))

    # -- geometry / introspection (used by the widget and by tests) ---------

    def visual_lines(self) -> list[VisualLine]:
        """Wrapped visual rows, in paint order, each bound to its source line."""
        self._ensure_layout()
        return list(self._visual)

    def line_index_at(self, y: int) -> int:
        """Source line index whose row contains pixel ``y`` (-1 when none)."""
        self._ensure_layout()
        visual_index = self._visual_index_at(y)
        if visual_index is None:
            return -1
        return self._visual[visual_index].source_index

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
        fm = QFontMetrics(self._font)
        offset = self._vbar.value()
        first = max(0, offset // max(1, self._row_height))
        y = self._pad + first * self._row_height - offset
        for visual_index in range(first, len(self._visual)):
            if y > self.height():
                break
            self._paint_visual_line(painter, visual_index, y, fm)
            y += self._row_height

        pen = QPen(QColor(self._border_color))
        pen.setWidthF(0.66)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rounded, radius, radius)
        painter.end()

    def _paint_visual_line(
        self, painter: QPainter, visual_index: int, y: int, fm: QFontMetrics
    ) -> None:
        visual = self._visual[visual_index]
        self._paint_selection(painter, visual, y, fm)
        line = self._lines[visual.source_index]
        color = line.color
        painter.setPen(QColor(color) if color is not None and color.isValid() else self._text_color)
        painter.setFont(self._line_font(line))
        baseline = y + fm.ascent()
        painter.drawText(QPointF(float(self._pad), float(baseline)), visual.text)

    def _paint_selection(
        self, painter: QPainter, visual: VisualLine, y: int, fm: QFontMetrics
    ) -> None:
        bounds = self._selection_bounds()
        if bounds is None:
            return
        (start_line, start_char), (end_line, end_char) = bounds
        source_index = visual.source_index
        if source_index < start_line or source_index > end_line:
            return
        source = self._lines[source_index].text
        start = start_char if source_index == start_line else 0
        end = end_char if source_index == end_line else len(source)
        start = max(start, visual.start)
        end = min(end, visual.end)
        if start >= end:
            return
        x0 = self._pad + fm.horizontalAdvance(visual.text[: start - visual.start])
        x1 = self._pad + fm.horizontalAdvance(visual.text[: end - visual.start])
        accent = QColor(self.theme_manager.get_color("accent"))
        accent.setAlpha(90)
        painter.fillRect(
            QRect(int(x0), int(y), max(1, int(x1 - x0)), self._row_height), accent
        )

    # -- layout -------------------------------------------------------------

    def _mark_dirty(self) -> None:
        """Mark the layout stale - NEVER re-wrap here.

        `_ensure_layout` re-wraps every line, so calling it from every append/set turned a log that grows during a render
        into O(n^2): 10 ticks a second over a growing log froze the GUI thread (py-spy: setPlainText -> set_lines ->
        _wrap_line). The layout is rebuilt where it is actually needed (paint, scroll range, hit-testing).
        """
        self._layout_dirty = True
        self.update()

    def _ensure_layout(self) -> None:
        if not self._layout_dirty:
            return
        fm = QFontMetrics(self._font)
        self._row_height = max(1, fm.lineSpacing())
        width = self._content_width()
        # Wrapping depends on (text, width) only, so a line already wrapped at this width is free on the next pass. A log
        # that grows by a few lines per tick then costs only those lines, not the whole history.
        if getattr(self, "_wrap_width", None) != width:
            self._wrap_cache = {}
            self._wrap_width = width
        cache = self._wrap_cache
        self._visual = []
        for source_index, line in enumerate(self._lines):
            spans = cache.get(line.text)
            if spans is None:
                spans = self._wrap_line(line.text, fm, width)
                cache[line.text] = spans
            for start, end in spans:
                self._visual.append(
                    VisualLine(line.text[start:end], source_index, start, end)
                )
        self._layout_dirty = False
        self._update_scroll_range()

    def _content_width(self) -> int:
        return max(1, self.width() - 2 * self._pad - self._scroll_reserve)

    def _wrap_line(self, text: str, fm: QFontMetrics, width: int) -> list[tuple[int, int]]:
        if not text:
            return [(0, 0)]
        if fm.horizontalAdvance(text) <= width:
            return [(0, len(text))]
        spans: list[tuple[int, int]] = []
        length = len(text)
        i = 0
        while i < length:
            measured = 0
            last_space = -1
            j = i
            while j < length:
                advance = fm.horizontalAdvance(text[j])
                if measured + advance > width and j > i:
                    break
                measured += advance
                if text[j] == " ":
                    last_space = j
                j += 1
            if j >= length:
                spans.append((i, length))
                break
            if last_space >= i:
                spans.append((i, last_space + 1))
                i = last_space + 1
            else:
                spans.append((i, j))
                i = j
        return spans or [(0, length)]

    def _content_height(self) -> int:
        """Painted content height in px - one owner for the scroll range and the scrollbar facade."""
        return 2 * self._pad + len(self._visual) * self._row_height

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
        if not self._vbar.isVisible():
            return
        self._vbar.setGeometry(
            self.width() - self._scroll_reserve,
            self._pad,
            self._scroll_reserve,
            max(1, self.height() - 2 * self._pad),
        )

    # -- point <-> model ----------------------------------------------------

    def _visual_index_at(self, y: int) -> int | None:
        if not self._visual:
            return None
        rel = y - self._pad + self._vbar.value()
        if rel < 0:
            return None
        index = int(rel // max(1, self._row_height))
        if index < 0 or index >= len(self._visual):
            return None
        return index

    def _point_at(self, x: float, y: float) -> tuple[int, int] | None:
        if not self._visual:
            return None
        visual_index = self._visual_index_at(int(y))
        if visual_index is None:
            visual_index = 0 if y < self._pad else len(self._visual) - 1
        visual = self._visual[visual_index]
        offset = self._char_offset_at(visual, x)
        return (visual.source_index, visual.start + offset)

    def _char_offset_at(self, visual: VisualLine, x: float) -> int:
        fm = QFontMetrics(self._font)
        rel = x - self._pad
        if rel <= 0:
            return 0
        measured = 0
        for index, char in enumerate(visual.text):
            advance = fm.horizontalAdvance(char)
            if rel < measured + advance / 2.0:
                return index
            measured += advance
        return len(visual.text)

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

    def _line_font(self, line: ConsoleLine) -> QFont:
        if not line.bold and not line.italic:
            return self._font
        font = QFont(self._font)
        font.setBold(line.bold)
        font.setItalic(line.italic)
        return font

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
        self.update()

    def _on_metrics_changed(self, *_args) -> None:
        """Face (``AXIS_FONT``) and scale (``AXIS_SCALE``) re-derivation.

        The painted font is cached; re-derive it from the resolver on a face
        change (a host that has NOT taken the font over via ``set_font``),
        then re-run the scale-dependent pad/scroll reserve work.
        """
        if not self._font_external:
            self._font = apply_ui_font(self)
        self._pad = scaled_px(_PADDING)
        self._scroll_reserve = scaled_px(MINIMAL_SCROLLBAR_WIDTH)
        was_bottom = self.is_at_bottom()
        self._mark_dirty()
        self._update_scroll_range()
        if was_bottom:
            self.scroll_to_bottom()
        self.update()

    def _on_scroll_value_changed(self, _value: int) -> None:
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
