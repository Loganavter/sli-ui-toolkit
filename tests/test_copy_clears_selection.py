"""Copy is a toolkit-standard action: clipboard + the selection is dropped.

Owner report 2026-10-21: after choosing "Copy" / "Copy as Markdown" from the
help viewer's context menu the text stayed washed as if the selection were
still active. The rule now lives in the toolkit (``Text.copy_selection`` /
``Text.copy_selection_markdown``, the engine copy path, the label menu and
``Label``'s own Ctrl+C) so every selectable surface behaves the same — the
copy ends the selection gesture. These tests fail on the pre-change tree: the
clipboard is set and ``hasSelectedText()`` stays True.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtTest import QTest

from sli_ui_toolkit.ui.widgets.atomic.label_context_menu import (
    COPY_ACTION_ID,
    build_label_menu,
)
from sli_ui_toolkit.ui.widgets.atomic.text_labels import Label
from sli_ui_toolkit.widgets import Text

MD = "# Title\n\n- **one** — first.\n- **two** — second.\n"


def _copy_key(widget) -> None:
    QTest.keyClick(widget, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)


def test_plain_text_copy_clears_the_selection(qapp, qtbot):
    widget = Text("copy this fragment", mode="plain", selectable=True)
    qtbot.addWidget(widget)
    widget.setSelection(5, 4)
    assert widget.hasSelectedText()

    assert widget.copy_selection() is True
    assert QGuiApplication.clipboard().text() == "this"
    assert widget.hasSelectedText() is False


def test_plain_text_ctrl_c_clears_the_selection(qapp, qtbot):
    widget = Text("copy this fragment", mode="plain", selectable=True)
    qtbot.addWidget(widget)
    widget.setSelection(5, 4)
    widget.setFocus()

    _copy_key(widget)
    assert QGuiApplication.clipboard().text() == "this"
    assert widget.hasSelectedText() is False


def test_document_copy_clears_the_selection(qapp, qtbot):
    widget = Text("", mode="document")
    qtbot.addWidget(widget)
    widget.set_markdown(MD)
    canvas = widget.canvas()
    start = widget.plain_text().index("one")
    canvas._doc_selection.set_range(start, start + len("one"))
    # Explicit sentinel, not "the clipboard happens to differ": the clipboard
    # is process-wide and the tier runs in a random order, so an earlier copy
    # test can leave exactly this word on it (measured: seed 20261028).
    clipboard = QGuiApplication.clipboard()
    clipboard.setText("<stale clipboard>")

    assert widget.copy_selection() is True
    assert clipboard.text() == "one"
    assert widget.hasSelectedText() is False


def test_document_ctrl_c_clears_the_selection(qapp, qtbot):
    widget = Text("", mode="document")
    qtbot.addWidget(widget)
    widget.set_markdown(MD)
    canvas = widget.canvas()
    start = widget.plain_text().index("one")
    canvas._doc_selection.set_range(start, start + len("one"))
    canvas.setFocus()

    _copy_key(canvas)
    assert QGuiApplication.clipboard().text() == "one"
    assert widget.hasSelectedText() is False


def test_document_copy_markdown_clears_the_selection(qapp, qtbot):
    widget = Text("", mode="document")
    qtbot.addWidget(widget)
    widget.set_markdown(MD)
    canvas = widget.canvas()
    text = widget.plain_text()
    start = text.index("• one")
    end = text.index("• two") + len("• two — second.")
    canvas._doc_selection.set_range(start, end)

    assert widget.copy_selection_markdown(MD) is True
    # The document's trailing newline rides along (the second item is last).
    assert QGuiApplication.clipboard().text() == (
        "- **one** — first.\n- **two** — second.\n"
    )
    assert widget.hasSelectedText() is False


def test_code_copy_clears_the_selection(qapp, qtbot):
    widget = Text("first line\nsecond line", mode="code")
    qtbot.addWidget(widget)
    canvas = widget.canvas()
    start = widget.text().index("line")
    canvas._selection.set_range((0, start), (0, start + len("line")))

    assert widget.copy_selection() is True
    assert QGuiApplication.clipboard().text() == "line"
    assert widget.hasSelectedText() is False


def test_label_menu_copy_clears_the_selection(qapp, qtbot):
    label = Label("copy this fragment", selectable=True)
    qtbot.addWidget(label)
    label.setSelection(5, 4)
    assert label.hasSelectedText()

    _entries, on_triggered = build_label_menu(label)
    on_triggered(COPY_ACTION_ID, None)
    assert QGuiApplication.clipboard().text() == "this"
    assert label.hasSelectedText() is False


def test_label_ctrl_c_clears_the_selection(qapp, qtbot):
    label = Label("copy this fragment", selectable=True)
    qtbot.addWidget(label)
    label.setSelection(5, 4)
    label.setFocus()

    _copy_key(label)
    assert QGuiApplication.clipboard().text() == "this"
    assert label.hasSelectedText() is False


def test_plain_text_menu_copy_clears_the_selection(qapp, qtbot):
    """``Text(mode="plain")`` opens the same toolkit label menu, so the Copy
    row must follow the same rule as the default ``Label``."""
    widget = Text("copy this fragment", mode="plain", selectable=True)
    qtbot.addWidget(widget)
    widget.setSelection(5, 4)
    assert widget.hasSelectedText()

    _entries, on_triggered = build_label_menu(widget)
    on_triggered(COPY_ACTION_ID, None)
    assert QGuiApplication.clipboard().text() == "this"
    assert widget.hasSelectedText() is False
