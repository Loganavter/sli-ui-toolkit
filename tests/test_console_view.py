"""ConsoleView — painted console surface contract.

Covers the migration-critical behaviors of the QTextEdit replacement:
per-visual-line content identity (no neighbor bleed), word-wrap mapping,
max-line trimming, follow-the-tail auto-scroll vs position-keeping, and
Ctrl+C clipboard copy.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFontMetrics, QGuiApplication
from PySide6.QtTest import QTest

from sli_ui_toolkit.ui.widgets.composite.console_view import ConsoleLine, ConsoleView


def _make_view(qtbot, width: int = 420, height: int = 200, **kwargs) -> ConsoleView:
    view = ConsoleView(**kwargs)
    qtbot.addWidget(view)
    view.resize(width, height)
    view._ensure_layout()
    return view


def test_visual_lines_map_to_own_source(qtbot):
    view = _make_view(qtbot)
    view.append("alpha", color=QColor("#ff0000"))
    view.append("beta", color=QColor("#00ff00"), bold=True)
    view.append("gamma")

    visual = view.visual_lines()
    assert [v.text for v in visual] == ["alpha", "beta", "gamma"]
    assert [v.source_index for v in visual] == [0, 1, 2]
    for v in visual:
        source = view.lines()[v.source_index]
        assert source.color is not None or v.source_index == 2
        assert v.text == source.text
        assert (v.start, v.end) == (0, len(source.text))


def test_word_wrap_preserves_source_and_width(qtbot):
    view = _make_view(qtbot, width=160, height=120)
    long_text = "the quick brown fox jumps over the lazy dog again and again"
    view.append(long_text, color=QColor("#123456"))

    visual = view.visual_lines()
    assert len(visual) > 1, "long line should wrap"
    assert all(v.source_index == 0 for v in visual)
    # Contiguous spans reconstruct the source exactly (no dropped spaces).
    assert "".join(v.text for v in visual) == long_text
    # Every wrapped row fits the content width.
    fm = QFontMetrics(view._font)
    width = view._content_width()
    for v in visual:
        assert fm.horizontalAdvance(v.text) <= width


def test_line_index_at_resolves_each_row(qtbot):
    view = _make_view(qtbot, width=420, height=240)
    for i in range(5):
        view.append(f"line-{i}")
    for row in range(5):
        y = view._pad + row * view._row_height + view._row_height // 2
        assert view.line_index_at(y) == row


def test_trimming_keeps_newest(qtbot):
    view = _make_view(qtbot, max_lines=3)
    for i in range(6):
        view.append(f"line-{i}")
    assert [line.text for line in view.lines()] == ["line-3", "line-4", "line-5"]
    assert view.text() == "line-3\nline-4\nline-5"


def test_append_at_bottom_follows_tail(qtbot):
    view = _make_view(qtbot, width=300, height=100)
    for i in range(60):
        view.append(f"line-{i}")
    view.scroll_to_bottom()
    assert view.is_at_bottom()
    bottom = view.scroll_value()

    view.append("tail")
    assert view.is_at_bottom()
    assert view.scroll_value() >= bottom
    assert view.lines()[-1].text == "tail"


def test_append_while_scrolled_up_keeps_position(qtbot):
    view = _make_view(qtbot, width=300, height=100)
    for i in range(60):
        view.append(f"line-{i}")
    view.scroll_to_bottom()
    view.set_scroll_value(0)
    assert not view.is_at_bottom()

    view.append("while-scrolled-up")
    assert view.scroll_value() == 0
    assert view.line_index_at(view._pad + view._row_height // 2) == 0


def test_ctrl_c_copies_selection(qtbot):
    view = _make_view(qtbot)
    view.append("hello")
    view.append("world")
    view.select_all()
    assert view.selected_text() == "hello\nworld"
    assert view.copy() is None
    assert QGuiApplication.clipboard().text() == "hello\nworld"

    QGuiApplication.clipboard().clear()
    view.setFocus()
    QTest.keyClick(view, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
    assert QGuiApplication.clipboard().text() == "hello\nworld"


def test_ctrl_a_selects_all_and_clear_resets(qtbot):
    view = _make_view(qtbot)
    view.append("a")
    view.append("b")
    QTest.keyClick(view, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    assert view.selected_text() == "a\nb"
    view.clear()
    assert view.lines() == ()
    assert view.selected_text() == ""
    assert view.text() == ""


def test_set_lines_preserves_scroll_when_not_at_bottom(qtbot):
    view = _make_view(qtbot, width=300, height=100)
    for i in range(60):
        view.append(f"line-{i}")
    view.scroll_to_bottom()
    view.set_scroll_value(0)
    view.set_lines([ConsoleLine(f"new-{i}") for i in range(60)])
    assert [line.text for line in view.lines()][0] == "new-0"
    assert view.scroll_value() == 0
