from __future__ import annotations

from collections.abc import Iterator

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtGui import QContextMenuEvent, QGuiApplication

from sli_ui_toolkit.ui.widgets.atomic.label_context_menu import (
    COPY_ACTION_ID,
    SELECT_ALL_ACTION_ID,
    build_label_menu,
    get_label_menu_builder,
    open_label_context_menu,
    set_label_menu_builder,
)
from sli_ui_toolkit.widgets import Label


@pytest.fixture(autouse=True)
def _reset_label_menu_builder() -> Iterator[None]:
    set_label_menu_builder(None)
    yield
    set_label_menu_builder(None)


def _context_menu_event() -> QContextMenuEvent:
    return QContextMenuEvent(
        QContextMenuEvent.Reason.Mouse,
        QPoint(5, 5),
        QPoint(50, 50),
    )


def test_selectable_label_consumes_event_and_opens_menu(qtbot) -> None:
    label = Label("hello", selectable=True)
    qtbot.addWidget(label)
    label.resize(120, 24)
    label.show()

    calls: list[Label] = []

    def builder(lbl):
        calls.append(lbl)
        return build_label_menu(lbl)

    set_label_menu_builder(builder)

    event = _context_menu_event()
    label.contextMenuEvent(event)

    assert calls == [label]
    assert event.isAccepted()


def test_non_selectable_label_keeps_no_menu(qtbot) -> None:
    label = Label("hello")
    qtbot.addWidget(label)
    label.resize(120, 24)
    label.show()

    calls: list[Label] = []
    set_label_menu_builder(lambda lbl: (calls.append(lbl), build_label_menu(lbl))[1])

    event = _context_menu_event()
    label.contextMenuEvent(event)

    assert calls == []


def test_empty_selectable_label_falls_through(qtbot) -> None:
    label = Label("", selectable=True)
    qtbot.addWidget(label)

    calls: list[Label] = []
    set_label_menu_builder(lambda lbl: (calls.append(lbl), build_label_menu(lbl))[1])

    label.contextMenuEvent(_context_menu_event())

    assert calls == []


def test_copy_action_copies_selection(qtbot) -> None:
    label = Label("hello world", selectable=True)
    qtbot.addWidget(label)
    label.setSelection(0, 5)

    entries, on_triggered = build_label_menu(label)
    copy_entry = entries[0]
    assert copy_entry.action_id == COPY_ACTION_ID
    assert copy_entry.enabled is True

    on_triggered(COPY_ACTION_ID, None)
    assert QGuiApplication.clipboard().text() == "hello"


def test_copy_disabled_without_selection(qtbot) -> None:
    label = Label("hello world", selectable=True)
    qtbot.addWidget(label)

    entries, _ = build_label_menu(label)
    assert entries[0].enabled is False


def test_select_all_action_selects_everything(qtbot) -> None:
    label = Label("hello world", selectable=True)
    qtbot.addWidget(label)

    entries, on_triggered = build_label_menu(label)
    select_all_entry = entries[1]
    assert select_all_entry.action_id == SELECT_ALL_ACTION_ID
    assert select_all_entry.enabled is True

    on_triggered(SELECT_ALL_ACTION_ID, None)
    assert label.selectedText() == "hello world"


def test_override_builder_is_honored(qtbot) -> None:
    label = Label("hi", selectable=True)
    qtbot.addWidget(label)
    label.resize(120, 24)
    label.show()

    seen: list[Label] = []

    def custom(lbl):
        seen.append(lbl)
        return build_label_menu(lbl)

    set_label_menu_builder(custom)
    assert get_label_menu_builder() is custom

    label.contextMenuEvent(_context_menu_event())

    assert seen == [label]

    set_label_menu_builder(None)
    assert get_label_menu_builder() is build_label_menu


def test_open_is_fail_open_on_broken_builder(qtbot) -> None:
    label = Label("hi", selectable=True)
    qtbot.addWidget(label)

    def exploding(_lbl):
        raise RuntimeError("boom")

    set_label_menu_builder(exploding)

    open_label_context_menu(label, QPoint(10, 10))
