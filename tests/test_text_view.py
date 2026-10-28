"""Painted text surface: rendering + editing (``Text`` in a scroll host).

The retired ``TextView`` split into the unified ``Text`` (the painted buffer,
its edit state and selection) and ``TextScrollArea`` (the host that scrolls
it and draws the frame). These tests drive that pair exactly as the old
composite behaved, so a regression in either half still fails here.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from sli_ui_toolkit.ui.widgets.composite.text_scroll import TextScrollArea
from sli_ui_toolkit.ui.widgets.text.engine.canvas import TextCanvasCore as TextCanvas
from sli_ui_toolkit.ui.widgets.text.engine.highlight import python_line_spans


def test_text_view_read_and_edit_modes(qapp):
    view = TextScrollArea("class Foo:\n    pass\n")
    assert view.text() == "class Foo:\n    pass\n"
    assert view.is_editing() is False
    assert view.editor() is None
    # insert_text is a no-op in read mode
    assert view.editor() is None or view.editor().insert_text("x") is None

    canvas = view.enter_edit_mode()
    assert canvas is view.canvas()
    assert isinstance(canvas, TextCanvas)
    assert view.is_editing() is True
    assert view.editor() is canvas
    canvas.insert_text("# edited\n")
    assert "# edited" in view.text()
    view.exit_edit_mode()
    assert view.is_editing() is False
    assert view.editor() is None

    view.set_text("other\n")
    assert view.text() == "other\n"


def test_text_view_editor_is_the_painted_canvas(qapp):
    view = TextScrollArea("line1\nline2\n")
    view.enter_edit_mode()
    canvas = view.editor()
    assert canvas is view.canvas()
    canvas.insert_text("x")
    assert canvas.text() == "xline1\nline2\n"
    canvas.set_editing(False)
    assert view.is_editing() is False


def test_line_number_gutter_start_offsets_text(qapp):
    view = TextScrollArea("a\nb\nc\n")
    canvas = view.enter_edit_mode()
    assert canvas._line_number_start is None
    assert canvas._gutter_width() == 0
    assert canvas._text_x() == 8  # PAD only
    view.set_line_number_start(4)
    assert canvas._line_number_start == 4
    assert canvas._gutter_width() > 0
    assert canvas._text_x() == 8 + canvas._gutter_width()
    # gutter survives revert-style set_text (TextView keeps its start)
    view.set_text("d\n")
    assert canvas._line_number_start == 4
    view.set_line_number_start(None)
    assert canvas._gutter_width() == 0


def test_python_line_spans_kinds():
    line = 'def foo(x):  # comment\n'
    kinds = [kind for _s, _e, kind in python_line_spans(line)]
    assert "keyword" in kinds
    assert "defclass" in kinds
    assert "comment" in kinds

    line2 = 'print("hello")  # done'
    kinds2 = [kind for _s, _e, kind in python_line_spans(line2)]
    assert "builtin" in kinds2
    assert "string" in kinds2
    assert "comment" in kinds2

    line3 = "x = 42 + 0x1F"
    kinds3 = [kind for _s, _e, kind in python_line_spans(line3)]
    assert kinds3.count("number") == 2


def test_python_line_spans_triple_quotes_and_def_names():
    # docstring content must not leak keywords/defclass
    doc = '    """This is class and def, not real code"""'
    kinds = [(k, s, e) for s, e, k in python_line_spans(doc)]
    assert all(k == "string" for k, _s, _e in kinds)
    assert kinds[0][1] == 4 and kinds[0][2] == len(doc)

    # a keyword after def must not become a defclass name
    line = "def from: pass"
    names = [(s, e) for s, e, k in python_line_spans(line) if k == "defclass"]
    assert names == []

    # real def/class names still caught
    line2 = "class Foo:\n    def __init__(self):"
    names2 = [line2[s:e] for s, e, k in python_line_spans(line2) if k == "defclass"]
    assert names2 == ["Foo", "__init__"]

    # unterminated triple quote marks the rest of the line as string
    doc_open = '    """unclosed docstring here'
    kinds3 = [k for _s, _e, k in python_line_spans(doc_open)]
    assert kinds3 == ["string"]


def test_text_view_edits_with_keys(qapp):
    view = TextScrollArea("class Foo:\n    pass\n")
    view.resize(400, 300)
    view.show()
    qapp.processEvents()
    view.enter_edit_mode()
    canvas = view.editor()
    assert canvas is not None

    QTest.keyClick(canvas, Qt.Key.Key_Right)
    QTest.keyClick(canvas, Qt.Key.Key_Right)
    QTest.keyClick(canvas, Qt.Key.Key_Tab)
    QTest.keyClick(canvas, Qt.Key.Key_X)
    assert canvas.text() == "cl    xass Foo:\n    pass\n"
    # Home then Backspace at the very start is a no-op
    QTest.keyClick(canvas, Qt.Key.Key_Home)
    QTest.keyClick(canvas, Qt.Key.Key_Backspace)
    QTest.keyClick(canvas, Qt.Key.Key_Backspace)
    assert canvas.text() == "cl    xass Foo:\n    pass\n"
    # End, Enter, indent, type on the new line
    QTest.keyClick(canvas, Qt.Key.Key_End)
    QTest.keyClick(canvas, Qt.Key.Key_Return)
    QTest.keyClick(canvas, Qt.Key.Key_Tab)
    QTest.keyClick(canvas, Qt.Key.Key_Y)
    assert canvas.text() == "cl    xass Foo:\n    y\n    pass\n"
    view.exit_edit_mode()


def test_text_view_changed_signal_fires_on_edit(qapp):
    view = TextScrollArea("a\n")
    view.enter_edit_mode()
    fired = []
    view.changed.connect(lambda: fired.append(1))
    view.editor().insert_text("b")
    assert fired == [1]


def test_canvas_does_not_swallow_window_shortcuts(qapp):
    """Regression: a focused TextCanvas must not starve window-scoped
    shortcuts / system hotkeys (keyboard layout switching, host QShortcuts)
    — ShortcutOverride is accepted only for keys the editor handles
    (Qt activates a shortcut exactly when the focused widget ignores the
    ShortcutOverride)."""
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtWidgets import QApplication

    view = TextScrollArea("class Foo:\n    pass\n")
    view.resize(400, 300)
    view.show()
    qapp.processEvents()
    view.enter_edit_mode()
    canvas = view.editor()
    canvas.setFocus()
    qapp.processEvents()

    def override_accepted(key, modifiers=Qt.KeyboardModifier.NoModifier, text="") -> bool:
        event = QKeyEvent(
            QEvent.Type.ShortcutOverride,
            key,
            modifiers,
            0,
            0,
            0,
            text,
        )
        QApplication.sendEvent(canvas, event)
        return event.isAccepted()

    # keys the editor consumes itself are claimed
    assert override_accepted(Qt.Key.Key_Right) is True
    assert override_accepted(Qt.Key.Key_Tab) is True
    assert override_accepted(Qt.Key.Key_X, text="x") is True  # printable text
    # anything else (layout-switch combos, host shortcuts) is NOT claimed,
    # so the window/application shortcut map keeps working
    assert override_accepted(
        Qt.Key.Key_P,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
    ) is False
    assert override_accepted(
        Qt.Key.Key_Space, Qt.KeyboardModifier.ControlModifier
    ) is False
    # read mode: even copy/select-all are not claimed (nothing to select)
    view.exit_edit_mode()
    assert override_accepted(Qt.Key.Key_Right) is False

    # ...but the editor still handles its own keys: typing still works
    view.enter_edit_mode()
    QTest.keyClick(canvas, Qt.Key.Key_X)
    assert "x" in canvas.text()


def test_canvas_typing_gate_ignores_layout_switch_keys(qapp):
    """The painted-editor typing gate: a Ctrl+Shift-combo key (keyboard
    layout switch on X11 carries printable-looking text) must NOT be
    inserted into the buffer, and an IME commit string is inserted as
    text."""
    from PySide6.QtGui import QInputMethodEvent

    view = TextScrollArea("class Foo:\n    pass\n")
    view.resize(400, 300)
    view.show()
    qapp.processEvents()
    view.enter_edit_mode()
    canvas = view.editor()

    before = canvas.text()
    # Ctrl+Shift+Key produces printable text on some layouts — the gate
    # must reject it (it is the layout-switch hotkey, not input)
    QTest.keyClick(
        canvas,
        Qt.Key.Key_X,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
    )
    assert canvas.text() == before
    # plain typing still works
    QTest.keyClick(canvas, Qt.Key.Key_X)
    assert "x" in canvas.text()
    # input context commits arrive as text (IME path)
    commit = QInputMethodEvent()
    commit.setCommitString("и")
    QApplication.sendEvent(canvas, commit)
    assert "и" in canvas.text()


def test_click_on_another_line_breaks_multi_click_chain(qapp):
    """A click on line 2 followed by a click on line 1 must move the caret,
    NOT count as a double-click chain: the chain's same-spot test runs in
    pixels, so clicks on different lines never select a word."""
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    view = TextScrollArea("alpha beta\ngamma delta\n")
    view.resize(400, 200)
    view.show()
    qapp.processEvents()
    view.enter_edit_mode()
    canvas = view.editor()
    adv = canvas._metrics.horizontalAdvance
    y0 = 8 + 7
    y1 = y0 + canvas._line_height
    pos_line2 = QPoint(8 + adv("gamma"), y1)
    pos_line1 = QPoint(8 + adv("alpha"), y0)
    # first click on line 2, second click on line 1
    QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=pos_line2)
    QTest.mouseDClick(canvas, Qt.MouseButton.LeftButton, pos=pos_line1)
    qapp.processEvents()
    # no chain: caret moved, nothing selected
    assert canvas._selection.range() is None
    assert canvas._cursor[0] == 0
    assert canvas._selected_text() is None
    view.exit_edit_mode()


def test_double_click_selects_word(qapp):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    view = TextScrollArea("alpha beta gamma\n    pass\n")
    view.resize(400, 200)
    view.show()
    qapp.processEvents()
    view.enter_edit_mode()
    canvas = view.editor()
    # "beta" starts at col 6; its middle is around x = PAD + 6*adv + 2*adv
    adv = canvas._metrics.horizontalAdvance
    x = 8 + adv("alpha ") + adv("be")
    # a real double-click: plain press first, then the dbl-click press
    QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=QPoint(x, 8 + 7))
    QTest.mouseDClick(canvas, Qt.MouseButton.LeftButton, pos=QPoint(x, 8 + 7))
    assert canvas._selection.range() == ((0, 6), (0, 10))
    assert canvas._selected_text() == "beta"
    # typing replaces the selected word
    QTest.keyClick(canvas, Qt.Key.Key_Z)
    assert canvas.text() == "alpha z gamma\n    pass\n"
    view.exit_edit_mode()


def test_triple_click_selects_line(qapp):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    view = TextScrollArea("alpha beta\n    pass\n")
    view.resize(400, 200)
    view.show()
    qapp.processEvents()
    view.enter_edit_mode()
    canvas = view.editor()
    x = 8 + canvas._metrics.horizontalAdvance("al")
    # three clicks: press(1) -> dblclick(2) -> press(3)
    QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=QPoint(x, 8 + 7))
    QTest.mouseDClick(canvas, Qt.MouseButton.LeftButton, pos=QPoint(x, 8 + 7))
    QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=QPoint(x, 8 + 7))
    assert canvas._selection.range() == ((0, 0), (0, 10))
    assert canvas._selected_text() == "alpha beta"
    view.exit_edit_mode()


def test_click_after_triple_selects_returns_to_caret(qapp):
    """Regression: after dbl-click (word) + click (line), further ordinary
    clicks must switch back to the caret — the multi-click counter used to
    keep climbing, so every click stayed in whole-line mode forever."""
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    view = TextScrollArea("alpha beta\n    pass\n")
    view.resize(400, 200)
    view.show()
    qapp.processEvents()
    view.enter_edit_mode()
    canvas = view.editor()
    x = 8 + canvas._metrics.horizontalAdvance("al")
    y = 8 + 7
    # dbl-click selects the word
    QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=QPoint(x, y))
    QTest.mouseDClick(canvas, Qt.MouseButton.LeftButton, pos=QPoint(x, y))
    assert canvas._selection.range() is not None
    # third rapid click = triple-click → whole line
    QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=QPoint(x, y))
    assert canvas._selection.range() == ((0, 0), (0, 10))
    # a further click must return to the ordinary caret mode
    QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=QPoint(x, y))
    assert canvas._selection.range() is None
    view.exit_edit_mode()


def test_rapid_triple_click_selects_line(qapp):
    """Regression: a REAL fast triple-click delivers the 3rd press as
    MouseButtonDblClick too — the handler must use the real chain count
    (3 → line), not force word selection on every double-click."""
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    view = TextScrollArea("alpha beta\n    pass\n")
    view.resize(400, 200)
    view.show()
    qapp.processEvents()
    view.enter_edit_mode()
    canvas = view.editor()
    x = 8 + canvas._metrics.horizontalAdvance("al")
    y = 8 + 7
    # press 1 (plain) → caret; press 2 (dbl) → word; press 3 (dbl again,
    # as Qt delivers rapid presses) → whole line
    QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=QPoint(x, y))
    QTest.mouseDClick(canvas, Qt.MouseButton.LeftButton, pos=QPoint(x, y))
    assert canvas._selection.range() is not None
    QTest.mouseDClick(canvas, Qt.MouseButton.LeftButton, pos=QPoint(x, y))
    assert canvas._selection.range() == ((0, 0), (0, 10))
    assert canvas._selected_text() == "alpha beta"
    # a fourth rapid click starts a fresh chain: back to the caret
    QTest.mouseDClick(canvas, Qt.MouseButton.LeftButton, pos=QPoint(x, y))
    assert canvas._selection.range() is None
    view.exit_edit_mode()


def test_line_selection_up_keeps_current_line(qapp):
    """Regression: triple-click at the line's right edge then Shift+Up must keep the whole current line selected and
    extend into the line above — the anchor at the line start must not
    collapse the current line to an empty range. Shift+Down returns."""
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    from PySide6.QtWidgets import QApplication

    view = TextScrollArea("alpha beta\n    pass\nthird\n")
    view.resize(400, 300)
    view.show()
    qapp.processEvents()
    view.enter_edit_mode()
    canvas = view.editor()
    adv = canvas._metrics.horizontalAdvance
    y = 8 + 7 + canvas._line_height  # line 1 ("    pass")
    edge_x = 8 + adv("    pass")  # exactly at the last character (past it is empty space: clears, no select)
    QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=QPoint(edge_x, y))
    QTest.mouseDClick(canvas, Qt.MouseButton.LeftButton, pos=QPoint(edge_x, y))
    QTest.mouseDClick(canvas, Qt.MouseButton.LeftButton, pos=QPoint(edge_x, y))
    # line 1 fully selected
    assert canvas._selection.range() == ((1, 0), (1, 8))
    # Shift+Up: line 1 must STAY fully selected, line 0's tail is added
    QTest.keyClick(canvas, Qt.Key.Key_Up, Qt.KeyboardModifier.ShiftModifier)
    assert canvas._selection_range_for_line(1, "    pass") == (0, 8)
    assert canvas._selection_range_for_line(0, "alpha beta") == (8, 10)
    assert canvas._selected_text() == "ta\n    pass"
    # Shift+Down round-trips back to the whole line 1
    QTest.keyClick(canvas, Qt.Key.Key_Down, Qt.KeyboardModifier.ShiftModifier)
    assert canvas._selection_range_for_line(1, "    pass") == (0, 8)
    assert canvas._selection_range_for_line(0, "alpha beta") == (0, 0)
    view.exit_edit_mode()
    # A double-click sequence can leave Qt's GLOBAL button state pressed when the
    # canvas re-targets the release; the next test in a random order then fails on
    # ``QApplication.mouseButtons() == LeftButton`` (measured 2026-10-28: it made
    # test_hover_cursor_follows_text_hit red at seed 1 and green at seeds 1234 and
    # 20261028). The leaked state belongs to THIS test, so it is cleared here.
    if QApplication.mouseButtons() != Qt.MouseButton.NoButton:
        QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=QPoint(edge_x, y))


def test_line_drag_up_selects_top_line_too(qapp):
    """Regression: triple-click (3rd press held) then dragging UP must keep
    the top line fully selected — the normalized interval puts the focus
    line at its END, which used to render the top line empty (the
    selection was one line short of the drag position)."""
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    view = TextScrollArea("zero\none\ntwo\nthree\nfour\n")
    view.resize(400, 200)
    view.show()
    qapp.processEvents()
    view.enter_edit_mode()
    canvas = view.editor()
    adv = canvas._metrics.horizontalAdvance
    lh = canvas._line_height

    def y_of(line: int) -> int:
        return 8 + 7 + line * lh

    pos2 = QPoint(8 + adv("tw"), y_of(2))
    # real triple-click where the 3rd press is HELD, then drag up to line 0
    QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=pos2)
    QTest.mouseDClick(canvas, Qt.MouseButton.LeftButton, pos=pos2)
    QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=pos2)
    QTest.mouseMove(canvas, pos=QPoint(8 + adv("zer"), y_of(0)))
    QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=QPoint(8 + adv("zer"), y_of(0)))
    qapp.processEvents()
    assert canvas._selected_text() == "zero\none\ntwo"
    assert canvas._selection_range_for_line(0, "zero") == (0, 4)
    assert canvas._selection_range_for_line(2, "two") == (0, 3)
    view.exit_edit_mode()


def test_drag_selects_range(qapp):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    view = TextScrollArea("alpha beta gamma\n    pass\n")
    view.resize(400, 200)
    view.show()
    qapp.processEvents()
    view.enter_edit_mode()
    canvas = view.editor()
    adv = canvas._metrics.horizontalAdvance
    start = QPoint(8 + adv("alpha "), 8 + 7)
    end = QPoint(8 + adv("alpha beta"), 8 + 7)
    QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(canvas, pos=end)
    QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=end)
    assert canvas._selected_text() == "beta"
    view.exit_edit_mode()


def test_caret_hidden_while_selection_active(qapp):
    """The text caret is not painted while a selection is active: the
    cursor rides inside the selected range during a drag, and a caret on
    top of the highlight reads as a glitch."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    view = TextScrollArea("alpha beta gamma\n    pass\n")
    view.resize(400, 200)
    view.show()
    qapp.processEvents()
    view.enter_edit_mode()
    canvas = view.editor()
    canvas.setFocus()
    qapp.processEvents()
    # select "beta" (cols 6..10) and park the cursor inside the selection
    canvas._selection.set_range((0, 6), (0, 10))
    canvas._cursor = (0, 8)
    # The canvas is transparent by default (the host paints the surface) —
    # composite it over white so unpainted pixels read as white instead of
    # transparent black when probing for the caret.
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QImage, QPainter

    img = QImage(canvas.size(), QImage.Format.Format_RGB32)
    img.fill(0xFFFFFFFF)
    painter = QPainter(img)
    canvas.render(painter, QPoint(0, 0))
    painter.end()
    adv = canvas._metrics.horizontalAdvance
    caret_x = canvas._text_x() + adv("alpha be")
    # a caret bar spans the FULL line height (top and bottom rows included);
    # glyph strokes stay within the text band — sample the top/bottom rows
    top = sum(
        1
        for y in range(8, 11)
        if img.pixelColor(caret_x, y).lightness() < 120
    )
    bottom = sum(
        1
        for y in range(8 + canvas._line_height - 4, 8 + canvas._line_height)
        if img.pixelColor(caret_x, y).lightness() < 120
    )
    assert top + bottom == 0, f"caret painted during selection (top={top}, bottom={bottom})"
    view.exit_edit_mode()


def test_select_all_and_copy(qapp):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    view = TextScrollArea("alpha\nbeta\n")
    view.enter_edit_mode()
    canvas = view.editor()
    QTest.keyClick(canvas, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    assert canvas._selected_text() == "alpha\nbeta\n"
    canvas._copy_selection()
    assert QApplication.clipboard().text() == "alpha\nbeta\n"
    canvas.clear_selection()
    assert canvas._selected_text() is None
    view.exit_edit_mode()


_MD = (
    "## Heading\n"
    "A paragraph with **bold** and `code`.\n"
    "- first\n"
    "- second\n"
    "![alt](fig.png)\n"
)


def test_text_view_document_mode(qapp):
    from PySide6.QtGui import QPixmap

    view = TextScrollArea("", mode="document")
    view.resize(400, 300)
    view.show()
    qapp.processEvents()

    def resolve_asset(path):
        if path == "fig.png":
            return QPixmap(40, 30)
        return None

    view.set_markdown(_MD, resolve_asset=resolve_asset)
    qapp.processEvents()
    assert view.is_document() is True
    assert view.is_editing() is False
    plain = view.plain_text()
    assert "Heading" in plain
    assert "bold" in plain
    assert "second" in plain
    # the layout produced text fragments and the pixmap
    canvas = view.canvas()
    assert canvas._document_layout is not None
    assert len(canvas._document_layout.text_fragments) > 0
    assert len(canvas._document_layout.pixmaps) == 1
    # painting does not crash
    view.grab()
    # modes are fixed at construction: a document surface stays a document
    view.set_text("# Replaced\n\nBody.\n")
    assert view.is_document() is True
    assert "Replaced" in view.plain_text()


def test_text_view_document_mode_sizing(qapp):
    view = TextScrollArea("", mode="document")
    view.resize(400, 300)
    view.show()
    qapp.processEvents()
    view.set_markdown("## Title\n\nSome body text here.\n")
    qapp.processEvents()
    canvas = view.canvas()
    assert canvas.height() > 2 * 8  # layout height + PAD
    # resize re-lays out
    view.resize(600, 300)
    qapp.processEvents()
    assert canvas.width() > 0


def test_text_view_document_selection_and_copy(qapp):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    view = TextScrollArea("", mode="document")
    view.resize(400, 300)
    view.show()
    qapp.processEvents()
    view.set_markdown("## Title\n\nSome body text here.\n")
    qapp.processEvents()
    canvas = view.canvas()
    layout = canvas._document_layout

    # hit the body fragment inside the actual text ("Some body text here.")
    frag = layout.text_fragments[1]
    y = int(frag.rect.center().y()) + 8
    start = QPoint(8 + 20, y)
    end = QPoint(8 + 90, y)
    QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(canvas, pos=end)
    QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=end)
    sel = canvas._doc_selection.selection
    assert sel is not None
    assert sel[0] != sel[1]
    selected = canvas._document_index.slice_plain(*sorted(sel))
    assert selected.strip()
    # Ctrl+C copies the selection
    QTest.keyClick(canvas, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
    assert QApplication.clipboard().text() == selected
    # Ctrl+A selects everything
    QTest.keyClick(canvas, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    assert canvas._doc_selection.selection == (0, len(canvas._document_index.text))


def _doc_word_pos(canvas, word: str) -> QPoint:
    """Canvas-space point inside ``word`` of the first body fragment."""
    from PySide6.QtCore import QPoint

    index = canvas._document_index
    for frag in canvas._document_layout.text_fragments:
        lo, hi = frag.global_start, frag.global_end
        if word in index.text[lo:hi]:
            local = index.text.find(word, lo) - lo
            layout = frag.layout
            for li in range(layout.lineCount()):
                line = layout.lineAt(li)
                if line.textStart() <= local < line.textStart() + line.textLength():
                    cx, _ = line.cursorToX(local + len(word) // 2)
                    x = int(frag.rect.x() + cx)
                    y = int(frag.rect.y() + line.y() + line.height() / 2) + 8
                    return QPoint(x, y)
    raise AssertionError(f"word {word!r} not found in document layout")


def test_text_view_document_double_click_selects_word(qapp):
    """Document mode gets the same double-click word selection as code mode
    (the unified selection chain): the inspector's Docs section now behaves
    like its Code section."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    view = TextScrollArea("", mode="document")
    view.resize(400, 300)
    view.show()
    qapp.processEvents()
    view.set_markdown("## Title\n\nSome body text here with words.\n")
    qapp.processEvents()
    canvas = view.canvas()
    pos = _doc_word_pos(canvas, "body")
    QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=pos)
    QTest.mouseDClick(canvas, Qt.MouseButton.LeftButton, pos=pos)
    qapp.processEvents()
    sel = canvas._doc_selection.range()
    assert sel is not None
    assert canvas._document_index.text[sel[0]:sel[1]] == "body"
    view.deleteLater()


def test_text_view_document_triple_click_selects_paragraph(qapp):
    """Triple-click in document mode selects the whole paragraph/segment —
    the document analogue of code mode's whole-line selection."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    view = TextScrollArea("", mode="document")
    view.resize(400, 300)
    view.show()
    qapp.processEvents()
    view.set_markdown("## Title\n\nFirst paragraph with several words.\n\nSecond paragraph here.\n")
    qapp.processEvents()
    canvas = view.canvas()
    pos = _doc_word_pos(canvas, "First")
    for _ in range(3):
        QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=pos)
    qapp.processEvents()
    sel = canvas._doc_selection.range()
    assert sel is not None
    assert canvas._document_index.text[sel[0]:sel[1]] == "First paragraph with several words."
    view.deleteLater()


def test_text_view_document_triple_click_in_code_selects_line(qapp):
    """Triple-click inside a fenced code block selects the current LINE
    (like the code editor), not the whole fence."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    view = TextScrollArea("", mode="document")
    view.resize(400, 300)
    view.show()
    qapp.processEvents()
    view.set_markdown(
        "```python\n"
        "alpha = 1\n"
        "beta = 2\n"
        "gamma = 3\n"
        "```\n"
    )
    qapp.processEvents()
    canvas = view.canvas()
    pos = _doc_word_pos(canvas, "beta")
    for _ in range(3):
        QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=pos)
    qapp.processEvents()
    sel = canvas._doc_selection.range()
    assert sel is not None
    assert canvas._document_index.text[sel[0]:sel[1]] == "beta = 2"
    view.deleteLater()


def test_text_view_document_drag_after_double_click_extends_by_words(qapp):
    """Holding and dragging after a double-click in document mode grows the
    selection word-by-word (same as the help canvas and code mode)."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    view = TextScrollArea("", mode="document")
    view.resize(400, 300)
    view.show()
    qapp.processEvents()
    view.set_markdown("## Title\n\nFirst paragraph with several words.\n")
    qapp.processEvents()
    canvas = view.canvas()
    start = _doc_word_pos(canvas, "First")
    end = _doc_word_pos(canvas, "several")
    QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseDClick(canvas, Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(canvas, pos=end)
    QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=end)
    qapp.processEvents()
    sel = canvas._doc_selection.range()
    assert sel is not None
    selected = canvas._document_index.text[sel[0]:sel[1]]
    assert selected.startswith("First")
    assert "several" in selected
    view.deleteLater()



def test_text_view_document_link_click_emits(qapp):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    view = TextScrollArea("", mode="document")
    view.resize(400, 300)
    view.show()
    qapp.processEvents()
    view.set_markdown("See [docs](help://page) for more.\n")
    qapp.processEvents()
    links = []
    view.linkActivated.connect(links.append)
    canvas = view.canvas()
    layout = canvas._document_layout
    link_rect = None
    for frag in layout.text_fragments:
        for link in frag.links:
            link_rect = link.rect.translated(frag.rect.topLeft())
            break
        if link_rect is not None:
            break
    assert link_rect is not None
    pos = QPoint(
        int(link_rect.center().x()) + 8, int(link_rect.center().y()) + 8
    )
    QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=pos)
    assert links == ["help://page"]


def test_line_at_maps_each_line_centre_to_its_own_index(qapp):
    """Content identity: the y -> line mapping the code-mode paint uses resolves
    each line's centre to its own index and text (a duplicated/off-by-one
    mapping would fail). The code-mode paint had no such content check."""
    from sli_ui_toolkit.ui.widgets.text.engine import constants

    lines = ["alpha", "beta", "gamma", "delta", "epsilon"]
    canvas = TextCanvas("\n".join(lines))
    line_height = canvas._line_height
    assert line_height > 0
    for i, text in enumerate(lines):
        y = constants.PAD + i * line_height + line_height // 2
        index = canvas.line_at(y)
        assert index == i
        assert canvas.line_text(index) == text


def _editing_canvas(qapp, text="alpha beta\ngamma\n"):
    """A shown, editing canvas with focus (real mouse delivery)."""
    from PySide6.QtCore import QPoint

    view = TextScrollArea(text)
    view.resize(400, 200)
    view.show()
    qapp.processEvents()
    view.enter_edit_mode()
    canvas = view.editor()
    assert canvas is not None
    return view, canvas


def test_empty_click_clears_selection_and_caret(qapp):
    """Clicking past the glyphs drops the selection AND the caret.

    Falsification: pre-change the caret jumps to the nearest position
    (clamped) instead of disappearing.
    """
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    from sli_ui_toolkit.ui.widgets.text.engine import constants

    view, canvas = _editing_canvas(qapp)
    adv = canvas._metrics.horizontalAdvance
    y0 = constants.PAD + canvas._line_height // 2
    on_text = QPoint(canvas._text_x() + adv("alp"), y0)
    QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=on_text)
    assert canvas._caret_placed is True
    placed_cursor = canvas._cursor

    # Far past the line end: no jump-to-end, no selection, caret gone.
    QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=QPoint(390, y0))
    assert canvas._selection.range() is None
    assert canvas._caret_placed is False
    assert canvas._cursor == placed_cursor

    # Below the last line: same clearing.
    QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=QPoint(390, 190))
    assert canvas._selection.range() is None
    assert canvas._caret_placed is False

    # Back on text: the caret returns.
    QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=on_text)
    assert canvas._caret_placed is True
    view.exit_edit_mode()


def test_caret_blinks_while_focused_editing(qapp):
    """The caret toggles on a timer while focused + editing.

    Falsification: pre-change there is no blink machinery (solid caret).
    """
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    from sli_ui_toolkit.ui.widgets.text.engine import constants

    view, canvas = _editing_canvas(qapp)
    adv = canvas._metrics.horizontalAdvance
    y0 = constants.PAD + canvas._line_height // 2
    QTest.mouseClick(
        canvas,
        Qt.MouseButton.LeftButton,
        pos=QPoint(canvas._text_x() + adv("alp"), y0),
    )
    qapp.processEvents()
    assert canvas.hasFocus()
    assert canvas._caret_blink.isActive()

    canvas._caret_on = True
    canvas.update()
    qapp.processEvents()
    lit = canvas.grab().toImage()
    canvas._toggle_caret_blink()
    assert canvas._caret_on is False
    qapp.processEvents()
    dark = canvas.grab().toImage()
    assert lit != dark, "blink-off must remove the caret pixels"
    canvas._toggle_caret_blink()
    assert canvas._caret_on is True

    view.exit_edit_mode()
    assert not canvas._caret_blink.isActive()
    view.exit_edit_mode()


def test_hover_cursor_follows_text_hit(qapp):
    """I-beam only where glyphs stand; Arrow over empty space.

    Falsification: pre-change editing sets I-beam widget-wide, so empty
    space promises selectable text that is not there.
    """
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from sli_ui_toolkit.ui.widgets.text.engine import constants

    view, canvas = _editing_canvas(qapp)
    y0 = constants.PAD + canvas._line_height // 2
    adv = canvas._metrics.horizontalAdvance
    QTest.mouseMove(canvas, pos=QPoint(canvas._text_x() + adv("a"), y0))
    qapp.processEvents()
    assert QApplication.mouseButtons() == Qt.MouseButton.NoButton
    assert canvas.cursor().shape() == Qt.CursorShape.IBeamCursor
    QTest.mouseMove(canvas, pos=QPoint(390, y0))
    qapp.processEvents()
    assert canvas.cursor().shape() == Qt.CursorShape.ArrowCursor
    view.exit_edit_mode()
