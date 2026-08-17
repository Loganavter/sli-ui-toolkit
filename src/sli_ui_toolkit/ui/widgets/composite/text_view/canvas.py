"""TextCanvas — the painted text surface that IS the editor.

The same painted widget switches between read and edit modes, so both look
identical by construction. Edit mode adds a caret, selection, and
keyboard/mouse input; the host ``TextView`` scrolls it and draws the rounded
frame around the visible area.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QEvent, QPointF, QRect, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QFontMetrics,
    QGuiApplication,
    QKeySequence,
    QPainter,
)
from PySide6.QtWidgets import QSizePolicy, QWidget

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.managers.ui_scale import UiScale
from . import constants
from .document import build_text_index, layout_document, paint_layout, parse_help_blocks
from .selection import DocumentSelection, TextSelection
from sli_ui_toolkit.ui.widgets.composite.text_view.layout.hit_test import (
    hit_test_link,
    hit_test_pixmap,
    hit_test_text_offset,
)
from .highlight import python_line_spans, python_span_colors
from .painter import draw_text_line
from .selection import TextSelection

Position = tuple[int, int]


class TextCanvas(QWidget):
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
        if self._document_blocks is not None:
            self._relayout_document()

    def _on_scale_changed(self, *_args) -> None:
        if self._document_blocks is not None:
            # The singleton connections outlive the widget: a canvas whose
            # C++ side is already deleted (GC'd wrapper, scale test teardown)
            # must not raise from the signal into the emitting test.
            try:
                self._relayout_document()
            except RuntimeError:
                pass

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

    def _sync_height(self) -> None:
        # The content height is a MINIMUM, not a fixed size: the host scroll
        # area stretches the canvas to its viewport (the text view fills the
        # window and only scrolls when the content exceeds it) — a fixed
        # height forced the renderer to expand to the whole document.
        if self._document_layout is not None:
            self.setMinimumHeight(
                int(self._document_layout.height) + 2 * constants.PAD
            )
        else:
            lines = max(1, len(self._lines))
            self.setMinimumHeight(
                self._line_height * lines + 2 * constants.PAD
            )
        self.updateGeometry()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self._document_blocks is not None:
            self._relayout_document()

    # -- editing helpers ----------------------------------------------------

    def insert_text(self, text: str) -> None:
        if not self._editing:
            return
        self._commit_undo()
        self._replace_or_insert(text)
        self._after_edit()

    def _commit_undo(self) -> None:
        self._undo.append((self.text(), self._cursor))
        if len(self._undo) > 100:
            self._undo.pop(0)

    def _selection_bounds(self) -> tuple[Position, Position] | None:
        """The normalized selection interval used by paint/copy/replace.

        A line-mode selection (triple-click chain, ``_chain_selecting ==
        "line"``) keeps BOTH boundary lines WHOLE. The raw anchor/focus
        interval cannot express this:

        - extending UP: the far end sits at the anchor line's START
          ([(0, 8), (1, 0)] after triple-clicking line 1 and dragging to
          line 0) — extend the far end to the line's end, otherwise line
          1 renders empty;
        - dragging up puts the FOCUS line at its END in the normalized
          interval ([(0, len0), (2, 0)]) — extend the near end back to
          the line's start, otherwise the TOP line renders empty.

        Keyboard Shift+arrows keep their column-based top edge
        (``lo_col`` is not a line end there, so it is left untouched).
        """
        rng = self._selection.range()
        if rng is None:
            return None
        (lo_line, lo_col), (hi_line, hi_col) = rng
        if self._chain_selecting == "line" and lo_line < hi_line:
            if hi_col == 0:
                hi_col = len(self._lines[hi_line])
            if lo_col == len(self._lines[lo_line]):
                lo_col = 0
        return ((lo_line, lo_col), (hi_line, hi_col))

    def _replace_or_insert(self, text: str) -> None:
        rng = self._selection_bounds()
        if rng is not None:
            (lo_line, lo_col), (hi_line, hi_col) = rng
            self._lines[lo_line] = (
                self._lines[lo_line][:lo_col] + self._lines[hi_line][hi_col:]
                if lo_line != hi_line
                else self._lines[lo_line][:lo_col] + self._lines[lo_line][hi_col:]
            )
            if lo_line != hi_line:
                del self._lines[lo_line + 1:hi_line + 1]
            self._cursor = (lo_line, lo_col)
            self._selection.clear()
        line, col = self._cursor
        if "\n" in text:
            parts = text.split("\n")
            head = self._lines[line][:col] + parts[0]
            tail = parts[-1] + self._lines[line][col:]
            self._lines[line:line + 1] = [head] + parts[1:-1] + [tail]
            self._cursor = (line + len(parts) - 1, len(parts[-1]))
        else:
            self._lines[line] = self._lines[line][:col] + text + self._lines[line][col:]
            self._cursor = (line, col + len(text))

    def _after_edit(self) -> None:
        self._sync_height()
        self.changed.emit()
        self.update()

    def _move_cursor(self, dx: int, dy: int, event) -> None:
        line, col = self._cursor
        if not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self._selection.clear()
            self._chain_selecting = None
        if dy:
            line = max(0, min(len(self._lines) - 1, line + dy))
            col = min(col, len(self._lines[line]))
        if dx:
            col = max(0, min(len(self._lines[line]), col + dx))
        self._cursor = (line, col)
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            if self._selection.anchor is None:
                self._selection.anchor = self._cursor
            self._selection.focus = self._cursor
        self._ensure_cursor_visible()
        self.update()

    def _ensure_cursor_visible(self) -> None:
        parent = self.parentWidget()
        scroll = getattr(parent, "verticalScrollBar", None)
        if scroll is None:
            return
        bar = scroll()
        y = constants.PAD + self._cursor[0] * self._line_height
        viewport = parent.viewport()  # type: ignore[attr-defined]
        top = bar.value()
        bottom = top + viewport.height()
        if y < top:
            bar.setValue(y)
        elif y + self._line_height > bottom:
            bar.setValue(y + self._line_height - viewport.height())

    def _backspace(self) -> None:
        if self._selection.active():
            self._commit_undo()
            self._replace_or_insert("")
            self._after_edit()
            return
        line, col = self._cursor
        if col == 0 and line == 0:
            return
        self._commit_undo()
        if col > 0:
            self._lines[line] = self._lines[line][:col - 1] + self._lines[line][col:]
            self._cursor = (line, col - 1)
        else:
            prev_len = len(self._lines[line - 1])
            self._lines[line - 1] += self._lines[line]
            del self._lines[line]
            self._cursor = (line - 1, prev_len)
        self._after_edit()

    def _delete(self) -> None:
        if self._selection.active():
            self._commit_undo()
            self._replace_or_insert("")
            self._after_edit()
            return
        line, col = self._cursor
        if col < len(self._lines[line]):
            self._commit_undo()
            self._lines[line] = self._lines[line][:col] + self._lines[line][col + 1:]
            self._after_edit()
        elif line + 1 < len(self._lines):
            self._commit_undo()
            self._lines[line] += self._lines[line + 1]
            del self._lines[line + 1]
            self._after_edit()

    def _insert_newline(self) -> None:
        self._commit_undo()
        line, col = self._cursor
        self._lines[line:line + 1] = [self._lines[line][:col], self._lines[line][col:]]
        self._cursor = (line + 1, 0)
        self._after_edit()

    def _undo_action(self) -> None:
        if not self._undo:
            return
        text, cursor = self._undo.pop()
        self._lines = text.split("\n") if text else [""]
        self._cursor = cursor
        self._selection.clear()
        self._chain_selecting = None
        self._after_edit()

    def select_all(self) -> None:
        """Select the whole buffer (Ctrl+A)."""
        self._selection.select_all(self._lines)
        self._cursor = self._selection.focus or (0, 0)
        self.update()

    def clear_selection(self) -> None:
        self._selection.clear()
        self.update()

    def _selected_text(self) -> str | None:
        rng = self._selection_bounds()
        if rng is None:
            return None
        (lo_line, lo_col), (hi_line, hi_col) = rng
        if lo_line == hi_line:
            return self._lines[lo_line][lo_col:hi_col]
        parts = [self._lines[lo_line][lo_col:]]
        parts.extend(self._lines[lo_line + 1:hi_line])
        parts.append(self._lines[hi_line][:hi_col])
        return "\n".join(parts)

    def _copy_selection(self) -> None:
        selected = self._selected_text()
        if selected is not None:
            QGuiApplication.clipboard().setText(selected)

    def _cut(self) -> None:
        if self._selected_text() is None:
            return
        self._copy_selection()
        self._commit_undo()
        self._replace_or_insert("")
        self._after_edit()

    def _paste(self) -> None:
        text = QGuiApplication.clipboard().text()
        if text:
            self.insert_text(text)

    # -- mouse --------------------------------------------------------------

    def _pos_from_point(self, point) -> Position:
        line = max(
            0,
            min(
                len(self._lines) - 1,
                (point.y() - constants.PAD) // max(1, self._line_height),
            ),
        )
        x = point.x() - self._text_x()
        col = 0
        for index, _ch in enumerate(self._lines[line]):
            if self._metrics.horizontalAdvance(self._lines[line][:index + 1]) > x:
                break
            col = index + 1
        return (line, col)

    def _click_select(self, pos: Position, count: int) -> None:
        """Apply a multi-click selection (1 = caret, 2 = word, 3 = line)."""
        line = self._lines[pos[0]]
        if count >= 3:
            rng = TextSelection.line_range(pos, line)
            self._chain_selecting = "line"
        elif count == 2:
            rng = TextSelection.word_range(pos, line)
            self._chain_selecting = "word"
        else:
            self._chain_selecting = None
            self._cursor = pos
            self._selection.set_range(pos, pos)
            return
        self._cursor = rng[1]
        self._selection.set_range(rng[0], rng[1])

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if self._document_layout is not None:
            self._document_mouse_press(event)
            return
        if not self._editing:
            super().mousePressEvent(event)
            return
        self.setFocus()
        point = event.position().toPoint()
        pos = self._pos_from_point(point)
        count = self._selection.press(pos, point=(point.x(), point.y()))
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            # extend from the existing anchor
            self._cursor = pos
            if self._selection.anchor is None:
                self._selection.anchor = pos
            self._selection.focus = pos
            self._chain_selecting = None
        else:
            self._click_select(pos, count)
        self._press_point = point
        self._drag_extending = False
        self.update()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if self._document_layout is not None:
            self._document_mouse_press(event)
            return
        if not self._editing:
            super().mouseDoubleClickEvent(event)
            return        # Qt routes every rapid press to this handler (not
        # mousePressEvent) while within the double-click interval — a fast
        # triple-click arrives here as the 3rd press too. Use the REAL
        # chain count instead of forcing 2, so press 3 selects the line;
        # forcing 2 made a fast triple-click fall back to the word.
        point = event.position().toPoint()
        pos = self._pos_from_point(point)
        count = self._selection.press(pos, point=(point.x(), point.y()))
        self._click_select(pos, count)
        self._press_point = point
        self._drag_extending = False
        self.update()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._document_layout is not None:
            self._document_mouse_move(event)
            super().mouseMoveEvent(event)
            return
        if (
            self._editing
            and self._selection.anchor is not None
            and event.buttons() & Qt.MouseButton.LeftButton
        ):
            if not self._drag_extending:
                delta = (
                    event.position().toPoint() - self._press_point
                ).manhattanLength()
                if delta < 4:
                    super().mouseMoveEvent(event)
                    return
                self._drag_extending = True
            pos = self._pos_from_point(event.position().toPoint())
            self._cursor = pos
            if self._chain_selecting == "word":
                rng = TextSelection.word_range(pos, self._lines[pos[0]])
                self._selection.focus = rng[1]
            elif self._chain_selecting == "line":
                self._selection.focus = (pos[0], len(self._lines[pos[0]]))
            else:
                self._selection.focus = pos
            self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._document_layout is not None:
            self._document_mouse_release(event)
            return
        super().mouseReleaseEvent(event)

    # -- keyboard -----------------------------------------------------------

    def _claims_shortcut(self, event) -> bool:
        """Whether the canvas consumes the key itself (ShortcutOverride).

        The override must be accepted ONLY for keys the editor handles:
        otherwise the focused canvas would swallow every window-scoped
        shortcut and system hotkey (keyboard layout switching, IME toggles,
        the host's QShortcuts) — a widget that accepts all keys starves
        them."""
        if not getattr(self, "_editing", False):
            # read-only code / document mode: only the selection shortcuts
            return self._document_layout is not None and any(
                event.matches(seq)
                for seq in (
                    QKeySequence.StandardKey.Copy,
                    QKeySequence.StandardKey.SelectAll,
                )
            )
        if event.key() in (
            Qt.Key.Key_Tab,
            Qt.Key.Key_Return,
            Qt.Key.Key_Enter,
            Qt.Key.Key_Left,
            Qt.Key.Key_Right,
            Qt.Key.Key_Up,
            Qt.Key.Key_Down,
            Qt.Key.Key_Home,
            Qt.Key.Key_End,
            Qt.Key.Key_Backspace,
            Qt.Key.Key_Delete,
        ):
            return True
        if any(
            event.matches(seq)
            for seq in (
                QKeySequence.StandardKey.Copy,
                QKeySequence.StandardKey.Paste,
                QKeySequence.StandardKey.Cut,
                QKeySequence.StandardKey.Undo,
                QKeySequence.StandardKey.SelectAll,
            )
        ):
            return True
        return self._is_typing_key(event)

    def event(self, event) -> bool:  # noqa: N802
        # Qt's focus traversal eats the Tab key BEFORE keyPressEvent when
        # the window has other focusable widgets — catch it here so Tab
        # indents instead of moving focus. ``getattr`` guards events that
        # arrive before ``__init__`` finishes or during teardown.
        if (
            getattr(self, "_editing", False)
            and event.type() == QEvent.Type.KeyPress
            and event.key() == Qt.Key.Key_Tab
            and not (event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        ):
            self.insert_text("    ")
            return True
        if event.type() == QEvent.Type.ShortcutOverride:
            # Claim only the keys the editor handles itself; everything
            # else (window-scoped QShortcuts, system hotkeys like layout
            # switching) keeps working while the canvas has focus.
            if self._claims_shortcut(event):
                event.accept()
            else:
                event.ignore()
            return True
        return super().event(event)

    def _is_typing_key(self, event) -> bool:
        """Whether the key event is plain text input.

        Painted-editor typing gate (``redirectKeyToField`` pattern): only
        unmodified or Shift-modified printable keys count as typing. Keypad
        is irrelevant and ``GroupSwitchModifier`` (X11: the keyboard-layout
        switch key) must be masked out — a layout-switch hotkey press must
        never be eaten as text; it propagates to the host instead."""
        modifiers = event.modifiers() & ~(
            Qt.KeyboardModifier.KeypadModifier
            | Qt.KeyboardModifier.GroupSwitchModifier
        )
        return (
            modifiers
            in (
                Qt.KeyboardModifier.NoModifier,
                Qt.KeyboardModifier.ShiftModifier,
            )
            and event.key() != Qt.Key.Key_Shift
            and bool(event.text())
            and (event.text().isprintable() or event.text() == "\t")
        )

    def inputMethodEvent(self, event) -> None:  # noqa: N802
        """Accept the input context's events so the platform keeps the
        widget as its text-input client (IME/layout machinery), and commit
        strings as text. Preedit-only updates are accepted but not
        rendered — the painted editor has no composition display."""
        if getattr(self, "_editing", False) and event.commitString():
            self.insert_text(event.commitString())
        event.accept()

    def inputMethodQuery(self, query) -> object:  # noqa: N802
        """Feed the input context the same geometry/text it gets from
        QLineEdit (cursor rect, font, surrounding text)."""
        if not getattr(self, "_editing", False):
            return super().inputMethodQuery(query)
        line, col = self._cursor
        if query == Qt.InputMethodQuery.ImCursorRectangle:
            cx = self._text_x() + self._metrics.horizontalAdvance(
                self._lines[line][:col]
            )
            y = constants.PAD + line * self._line_height
            return QRect(cx, y, 2, self._line_height)
        if query == Qt.InputMethodQuery.ImFont:
            return self._font
        if query == Qt.InputMethodQuery.ImSurroundingText:
            return "\n".join(self._lines)
        if query == Qt.InputMethodQuery.ImCursorPosition:
            return (
                sum(len(line_text) + 1 for line_text in self._lines[:line]) + col
            )
        if query == Qt.InputMethodQuery.ImAnchorPosition:
            anchor = self._selection.anchor
            if anchor is None:
                anchor = self._cursor
            aline, acol = anchor
            return (
                sum(len(line_text) + 1 for line_text in self._lines[:aline]) + acol
            )
        return super().inputMethodQuery(query)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if self._document_layout is not None:
            if self._document_key(event):
                return
            super().keyPressEvent(event)
            return
        if not getattr(self, "_editing", False):
            super().keyPressEvent(event)
            return
        if event.matches(QKeySequence.StandardKey.Copy):
            self._copy_selection()
            return
        if event.matches(QKeySequence.StandardKey.SelectAll):
            self.select_all()
            return
        if event.matches(QKeySequence.StandardKey.Paste):
            self._paste()
            return
        if event.matches(QKeySequence.StandardKey.Cut):
            self._cut()
            return
        if event.matches(QKeySequence.StandardKey.Undo):
            self._undo_action()
            return
        key = event.key()
        if key == Qt.Key.Key_Left:
            self._move_cursor(-1, 0, event)
        elif key == Qt.Key.Key_Right:
            self._move_cursor(1, 0, event)
        elif key == Qt.Key.Key_Up:
            self._move_cursor(0, -1, event)
        elif key == Qt.Key.Key_Down:
            self._move_cursor(0, 1, event)
        elif key == Qt.Key.Key_Home:
            self._move_cursor_to_col(0, event)
        elif key == Qt.Key.Key_End:
            self._move_cursor_to_col(len(self._lines[self._cursor[0]]), event)
        elif key == Qt.Key.Key_Backspace:
            self._backspace()
        elif key == Qt.Key.Key_Delete:
            self._delete()
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._insert_newline()
        elif key == Qt.Key.Key_Tab:
            self.insert_text("    ")
        elif self._is_typing_key(event):
            self.insert_text(event.text())
        else:
            super().keyPressEvent(event)

    def _move_cursor_to_col(self, col: int, event) -> None:
        if not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self._selection.clear()
            self._chain_selecting = None
        self._cursor = (
            self._cursor[0],
            max(0, min(len(self._lines[self._cursor[0]]), col)),
        )
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            if self._selection.anchor is None:
                self._selection.anchor = self._cursor
            self._selection.focus = self._cursor
        self.update()

    # -- painting -----------------------------------------------------------

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

    _FOLD_ARROW = "\u25b8"  # ▸

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
