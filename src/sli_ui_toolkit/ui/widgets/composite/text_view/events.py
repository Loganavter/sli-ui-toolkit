"""Mouse/keyboard/IME event handling for ``TextCanvas``.

``_CanvasEventsApi`` owns Qt input dispatch: mouse press/move/release,
key press, shortcut-override claiming, and input-method (IME) plumbing.
It is a mixin preceding ``QWidget`` in ``TextCanvas``'s MRO (same trick
``base_flyout`` uses per ``docs/dev/ARCHITECTURE.md``): its
``mousePressEvent``/``keyPressEvent``/``event``/etc. overrides win, while
``super()`` inside them still resolves through to ``QWidget``'s own
methods.
"""

from __future__ import annotations

import logging
import os
import time

from PySide6.QtCore import QEvent, QRect, Qt
from PySide6.QtGui import QKeySequence

from . import constants
from .editing import Position
from .selection import TextSelection

_logger = logging.getLogger(__name__)


class _CanvasEventsApi:
    def _pos_from_point(self, point) -> Position:
        line = max(
            0,
            min(
                len(self._lines) - 1,
                (point.y() - constants.PAD) // max(1, self._line_height),
            ),
        )
        x = point.x() - self._text_x()
        if x <= 0:
            return (line, 0)
        text = self._lines[line]
        if not text:
            return (line, 0)
        # Incremental per-char advance (no slicing) — previous version did
        # text[:i] slicing + dict cache per prefix (O(L^2) alloc for 100-char
        # line). Use single-char horizontalAdvance cached per glyph.
        # For this font fixedPitch is False (variable width: 'l'=3, 'm'=7),
        # so monospace division fails; sum of single-char advances equals
        # prefix advance (verified: 'alpha' 31 == sum chars).
        width = 0
        col = 0
        # local bind for speed
        metrics = self._metrics
        # simple per-char cache dict (module-level) to avoid repeated QFontMetrics call
        # Use painter's _advance_cache for single chars if available, else metrics
        try:
            from .painter import _advance_cache as _ac
        except Exception:
            _ac = {}
        for idx, ch in enumerate(text):
            # cache key (ch, False) for regular font
            key = (ch, False)
            w = _ac.get(key)
            if w is None:
                w = metrics.horizontalAdvance(ch)
                if len(_ac) < 8192:
                    _ac[key] = w
            width += w
            if width > x:
                break
            col = idx + 1
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
        # Single debug check per move — logger only, no file IO (hot path)
        dbg = os.getenv("SLI_TEXTVIEW_DEBUG") == "1"
        if dbg and event.buttons() & Qt.MouseButton.LeftButton:
            _logger.warning(
                "drag raw editing=%s anchor=%s buttons=%s pos=%s",
                self._editing,
                self._selection.anchor,
                event.buttons(),
                event.position().toPoint(),
            )
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
            # No manual 16 ms throttle — Qt coalesces multiple update() into one
            # paint via the event loop (compresses). Manual throttle added
            # 170 ms gaps when the event loop was blocked by theme lookups &
            # file IO. Keep only jitter avoidance.
            pos = self._pos_from_point(event.position().toPoint())
            if dbg:
                _logger.warning("drag hit_test line=%s col=%s", pos[0], pos[1])
            # Avoid redundant update when pos hasn't moved (jitter)
            if pos == getattr(self, "_last_drag_pos", None):
                super().mouseMoveEvent(event)
                return
            self._last_drag_pos = pos
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
            cx = self._text_x() + self._metrics.horizontalAdvance(self._lines[line][:col])
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
