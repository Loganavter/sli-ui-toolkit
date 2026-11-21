"""The call surface a host migrating off stock widgets makes, pinned on the toolkit side.

Two gaps a host reported while migrating (each named by the lane that hit it): a log pane calls
`setPlainText`/`setHtml`/`verticalScrollBar().setValue(...)`, and a queue list calls `addItem`/`insertItem`/`takeItem`.
Neither existed, so those widgets stayed stock. These tests pin the compatibility surface and the semantics a host
depends on (row order after an insert, the removed text, the bottom pin reaching the console's scroll).
"""

from __future__ import annotations

from sli_ui_toolkit.widgets import ConsoleView, IconListWidget


def test_console_set_plain_text_replaces_the_content(qapp):
    view = ConsoleView()
    view.setPlainText("first\nsecond")
    assert [line.text for line in view.lines()] == ["first", "second"]
    view.setPlainText("only")
    assert [line.text for line in view.lines()] == ["only"]


def test_console_set_html_shows_its_plain_text(qapp):
    view = ConsoleView()
    view.setHtml("<p>alpha</p><p><b>beta</b></p>")
    assert [line.text for line in view.lines()] == ["alpha", "beta"]


def test_console_scrollbar_pins_to_the_bottom(qapp):
    view = ConsoleView()
    view.resize(200, 60)
    view.show()
    view.setPlainText("\n".join(f"line {index}" for index in range(200)))
    qapp.processEvents()
    bar = view.verticalScrollBar()
    assert bar.maximum() > 0
    bar.setValue(bar.maximum())
    assert view.is_at_bottom()


def test_list_add_insert_keeps_the_order(qapp):
    rows = IconListWidget()
    rows.addItem("a")
    rows.addItem("c")
    rows.insertItem(1, "b")
    assert rows.count() == 3
    assert [rows.item(index).text() for index in range(3)] == ["a", "b", "c"]


def test_list_take_item_returns_the_text_and_drops_the_row(qapp):
    rows = IconListWidget()
    rows.addItem("a")
    rows.addItem("b")
    assert rows.takeItem(0) == "a"
    assert rows.count() == 1
    assert rows.item(0).text() == "b"
    assert rows.takeItem(5) is None


def test_set_font_during_construction_is_safe(qapp):
    # `apply_ui_font` calls setFont while the console's own fields are still unset; routing that call into the painted
    # font path read `self._pad` and crashed a host at boot (every test here was green at the time).
    view = ConsoleView()
    view.setFont(view.font())            # the constructor's own call, replayed
    assert view.font() is not None
    # And a real host-sized font still reaches the painted face.
    from PySide6.QtGui import QFont

    font = QFont()
    font.setPixelSize(18)
    view.setFont(font)
    assert view.font().pixelSize() == 18
