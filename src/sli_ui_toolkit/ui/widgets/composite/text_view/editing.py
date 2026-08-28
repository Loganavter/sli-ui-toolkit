"""Buffer/cursor/undo/selection editing model for ``TextCanvas`` (code mode).

``_CanvasEditingApi`` owns the plain-text buffer mutation methods -- insert,
backspace, delete, newline, undo, cut/copy/paste, and the normalized
selection-bounds math they share. It is a mixin (same pattern as
``base_flyout``'s ``_Flyout*Api`` family): it reads/writes the owning
``TextCanvas``'s ``_lines``/``_cursor``/``_selection``/``_undo``/
``_chain_selecting`` state directly via ``self``, and calls back into
facade/paint methods (``self._sync_height()``, ``self.update()``) the same
way any other mixin in this split does.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication

from . import constants

Position = tuple[int, int]


class _CanvasEditingApi:
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
        self._last_edit_line = self._cursor[0]
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
