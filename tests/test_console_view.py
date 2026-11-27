"""ConsoleView — painted console surface contract.

Covers the migration-critical behaviors of the QTextEdit replacement:
per-visual-line content identity (no neighbor bleed), word-wrap mapping,
max-line trimming, follow-the-tail auto-scroll vs position-keeping, and
Ctrl+C clipboard copy.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import (
    QColor,
    QContextMenuEvent,
    QFontMetrics,
    QGuiApplication,
)
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.ui.widgets.composite.console_view import (
    CONSOLE_CLEAR_ACTION_ID,
    CONSOLE_COPY_ACTION_ID,
    CONSOLE_SELECT_ALL_ACTION_ID,
    ConsoleLine,
    ConsoleView,
)
from sli_ui_toolkit.ui.widgets.composite.context_menu.models import (
    ContextMenuAction,
)
from sli_ui_toolkit.ui.widgets.helpers.context_menu import ContextMenuMixin


def _make_view(qtbot, width: int = 420, height: int = 200, **kwargs) -> ConsoleView:
    view = ConsoleView(**kwargs)
    qtbot.addWidget(view)
    view.resize(width, height)
    view._ensure_layout()
    return view


def _context_menu_event() -> QContextMenuEvent:
    return QContextMenuEvent(
        QContextMenuEvent.Reason.Mouse,
        QPoint(5, 5),
        QPoint(50, 50),
    )


def _open_context_menu(qtbot, view: QWidget):
    """Deliver a real right-click; return the popup the widget opened.

    ``ContextMenu.popup_at`` is non-blocking (only ``exec_at`` runs a nested
    loop), so the test drives the same handler a live right-click does.
    """
    view.resize(420, 200)
    view.show()
    event = _context_menu_event()
    QApplication.sendEvent(view, event)
    assert event.isAccepted()
    menu = view._owned_context_menu
    assert menu is not None, "right-click did not build a context menu"
    return menu


def _spec(menu, action_id: str):
    for row in menu._rows:
        if row._spec.action_id == action_id:
            return row._spec
    raise AssertionError(f"no row for action {action_id!r}")


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


# -- right-click menu -------------------------------------------------------


def test_right_click_opens_themed_menu_with_three_items(qtbot):
    view = _make_view(qtbot)
    view.append("hello")
    menu = _open_context_menu(qtbot, view)
    try:
        assert menu.isVisible()
        assert menu.is_popup_surface()
        assert [row._spec.text for row in menu._rows] == [
            "Copy",
            "Select all",
            "Clear",
        ]
        assert [row._spec.action_id for row in menu._rows] == [
            CONSOLE_COPY_ACTION_ID,
            CONSOLE_SELECT_ALL_ACTION_ID,
            CONSOLE_CLEAR_ACTION_ID,
        ]
    finally:
        menu.hide()


def test_menu_copy_is_disabled_without_a_selection(qtbot):
    view = _make_view(qtbot)
    view.append("hello")
    menu = _open_context_menu(qtbot, view)
    try:
        assert _spec(menu, CONSOLE_COPY_ACTION_ID).enabled is False
    finally:
        menu.hide()

    view.select_all()
    menu = _open_context_menu(qtbot, view)
    try:
        assert _spec(menu, CONSOLE_COPY_ACTION_ID).enabled is True
    finally:
        menu.hide()


def test_menu_copy_action_writes_the_selection_to_the_clipboard(qtbot):
    view = _make_view(qtbot)
    view.append("hello")
    view.append("world")
    view.select_all()
    menu = _open_context_menu(qtbot, view)
    row = menu.row_for_action(CONSOLE_COPY_ACTION_ID)
    assert row is not None
    QGuiApplication.clipboard().setText("<stale clipboard>")

    menu._on_row_clicked(row, row._spec)

    assert QGuiApplication.clipboard().text() == "hello\nworld"
    # Copy never drops the console's selection (unlike the label menu).
    assert view.selected_text() == "hello\nworld"


def test_menu_select_all_action_selects_every_line(qtbot):
    view = _make_view(qtbot)
    view.append("a")
    view.append("b")
    menu = _open_context_menu(qtbot, view)
    row = menu.row_for_action(CONSOLE_SELECT_ALL_ACTION_ID)
    assert row is not None

    menu._on_row_clicked(row, row._spec)

    assert view.selected_text() == "a\nb"


def test_menu_clear_action_empties_the_lines(qtbot):
    view = _make_view(qtbot)
    view.append("a")
    view.append("b")
    menu = _open_context_menu(qtbot, view)
    row = menu.row_for_action(CONSOLE_CLEAR_ACTION_ID)
    assert row is not None

    menu._on_row_clicked(row, row._spec)

    assert view.lines() == ()
    assert view.text() == ""


# -- shared opt-in plumbing (ConsoleView is the first consumer) -------------


class _DemoMenuWidget(ContextMenuMixin, QWidget):
    """Minimal non-console consumer: proves the mixin is genuinely shared."""

    def __init__(self) -> None:
        super().__init__()
        self.triggered: list[str] = []
        self.entries = (
            ContextMenuAction("demo.action", "Demo action", data="payload"),
        )

    def build_context_menu(self):
        return self.entries, lambda action_id, _data: self.triggered.append(
            action_id
        )


def test_mixin_gives_any_widget_the_same_menu_without_new_plumbing(qtbot):
    widget = _DemoMenuWidget()
    qtbot.addWidget(widget)
    menu = _open_context_menu(qtbot, widget)
    try:
        assert menu.isVisible()
        assert [row._spec.text for row in menu._rows] == ["Demo action"]
    finally:
        menu.hide()

    menu = _open_context_menu(qtbot, widget)
    row = menu.row_for_action("demo.action")
    assert row is not None
    menu._on_row_clicked(row, row._spec)
    assert widget.triggered == ["demo.action"]


def test_mixin_falls_through_when_the_widget_offers_no_entries(qtbot):
    class _EmptyMenuWidget(ContextMenuMixin, QWidget):
        def build_context_menu(self):
            return (), lambda _action_id, _data: None

    widget = _EmptyMenuWidget()
    qtbot.addWidget(widget)
    widget.resize(120, 40)
    widget.show()
    event = _context_menu_event()
    QApplication.sendEvent(widget, event)

    assert getattr(widget, "_owned_context_menu", None) is None
    assert not event.isAccepted()
