"""ComboBox typing: file-manager jump (default) vs legacy filter mode.

``typing_mode="jump"`` walks a highlight to the first row matching the typed
buffer, keeps every row visible, and commits only on Enter/click;
``typing_mode="filter"`` is the previous behaviour (narrow the list, apply the
first match immediately).
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.ui.widgets.comboboxes import combo_box as combo_box_module
from sli_ui_toolkit.widgets import ComboBox

ITEMS = ["Alpha", "Beta", "Delta", "deepseek-r1", "deepseek-v3", "Zeta"]


def _make_combo(qtbot, *, typing_mode="jump", items=ITEMS):
    host = QWidget()
    qtbot.addWidget(host)
    host.resize(400, 400)
    combo = ComboBox(parent=host, typing_mode=typing_mode)
    combo.addItems(items)
    combo.setCurrentIndex(0)
    combo.move(20, 20)
    host.show()
    qtbot.waitExposed(host)
    combo.showDropdown()
    return combo


def _key(combo, letter: str, key=None):
    event = QKeyEvent(
        QEvent.Type.KeyPress,
        key if key is not None else Qt.Key.Key_A,
        Qt.KeyboardModifier.NoModifier,
        letter,
    )
    combo.keyPressEvent(event)
    return event


def _type(combo, text):
    for char in text:
        _key(combo, char)


def test_default_typing_mode_is_jump(qtbot):
    combo = _make_combo(qtbot)
    assert combo.typingMode() == "jump"
    assert ComboBox(typing_mode="filter").typingMode() == "filter"
    try:
        ComboBox(typing_mode="nonsense")
    except ValueError:
        pass
    else:  # pragma: no cover - the constructor must reject unknown modes
        raise AssertionError("unknown typing mode was accepted")


def test_jump_highlights_first_match_without_changing_the_value(qtbot):
    combo = _make_combo(qtbot)
    emitted: list[int] = []
    combo.currentIndexChanged.connect(emitted.append)

    _type(combo, "deepseek")

    # Everything stays visible: jump is navigation, not filtering.
    assert combo._visible_indices() == list(range(len(ITEMS)))
    # The highlight is on the first matching row...
    assert combo._typing_focus_index == 3
    assert combo.dropdown_row_widget(3)._is_focus_row is True
    assert combo.dropdown_row_widget(2)._is_focus_row is False
    # ...and the value is untouched until a commit key/click.
    assert combo.currentIndex() == 0
    assert emitted == []
    assert combo.currentText() == "Alpha"


def test_enter_commits_the_highlighted_row_and_closes(qtbot):
    combo = _make_combo(qtbot)
    emitted: list[int] = []
    combo.currentIndexChanged.connect(emitted.append)

    _type(combo, "deepseek")
    _key(combo, "\r", key=Qt.Key.Key_Return)

    assert combo.currentIndex() == 3
    assert combo.currentText() == "deepseek-r1"
    assert combo._expanded is False
    assert emitted == [3]


def test_typing_the_same_key_again_cycles_to_the_next_match(qtbot, monkeypatch):
    combo = _make_combo(qtbot)
    clock = [100.0]
    monkeypatch.setattr(combo_box_module.time, "monotonic", lambda: clock[0])

    _type(combo, "d")
    assert combo._typing_focus_index == 2  # Delta
    # A pause longer than the typeahead window starts a NEW query, which walks
    # one row past the highlight -> the next row containing "d".
    clock[0] += combo.TYPEAHEAD_TIMEOUT_MS / 1000.0 + 0.5
    _type(combo, "d")
    assert combo._typing_focus_index == 3  # deepseek-r1
    clock[0] += combo.TYPEAHEAD_TIMEOUT_MS / 1000.0 + 0.5
    _type(combo, "d")
    assert combo._typing_focus_index == 4  # deepseek-v3


def test_backspace_shortens_the_query_then_clears_the_highlight(qtbot):
    combo = _make_combo(qtbot)

    _type(combo, "dee")
    assert combo._typing_focus_index == 3
    _key(combo, "\b", key=Qt.Key.Key_Backspace)
    assert combo._typeahead_text == "de"
    _key(combo, "\b", key=Qt.Key.Key_Backspace)
    assert combo._typeahead_text == "d"
    _key(combo, "\b", key=Qt.Key.Key_Backspace)
    assert combo._typeahead_text == ""
    assert combo._typing_focus_index == -1
    assert combo.currentIndex() == 0


def test_no_match_leaves_the_highlight_and_value_alone(qtbot):
    combo = _make_combo(qtbot)
    _type(combo, "qqq")
    assert combo._typing_focus_index == -1
    assert combo.currentIndex() == 0


def test_filter_mode_keeps_the_legacy_behaviour(qtbot):
    combo = _make_combo(qtbot, typing_mode="filter")
    _type(combo, "de")

    assert combo.searchText() == "de"
    assert combo._visible_indices() == [2, 3, 4]
    # Filtering applies the first match immediately (legacy semantics).
    assert combo.currentIndex() == 2
    assert combo._typing_focus_index == -1


def test_switching_to_filter_clears_a_jump_query(qtbot):
    combo = _make_combo(qtbot)
    _type(combo, "de")
    assert combo._typing_focus_index >= 0

    combo.setTypingMode("filter")
    assert combo._typing_focus_index == -1
    assert combo.searchText() == ""
    assert combo._visible_indices() == list(range(len(ITEMS)))


def test_search_disabled_declines_text_keys_and_ignores_typing(qtbot):
    combo = _make_combo(qtbot)
    assert combo.acceptsTextKeys() is True
    combo.setSearchEnabled(False)
    assert combo.acceptsTextKeys() is False
    combo.showDropdown()
    _type(combo, "dee")
    assert combo._typing_focus_index == -1
    assert combo.currentIndex() == 0


def test_query_survives_a_transient_close(qtbot):
    """A close between keystrokes must not restart the search from one letter.

    Owner report 2026-10-22: settings navigation leaves a reveal dropdown open;
    opening this dropdown dismisses it, its focus restoration steals focus, and
    the field's own dropdown closes — the query then continued as a single
    character per keystroke. The buffer is time-boxed, not visibility-bound.
    """
    combo = _make_combo(qtbot)
    _type(combo, "d")
    assert combo._typeahead_text == "d"
    assert combo._typing_focus_index == 2

    combo.hideDropdown()  # the flyout manager's dismissal, mid-typing
    assert combo._typeahead_text == "d"  # query kept...
    assert combo._typing_focus_index == -1  # ...highlight is not

    _type(combo, "e")  # reopen + extend
    assert combo._typeahead_text == "de"
    assert combo._typing_focus_index == 2


def test_pause_then_another_query_starts_fresh(qtbot, monkeypatch):
    combo = _make_combo(qtbot)
    clock = [50.0]
    monkeypatch.setattr(combo_box_module.time, "monotonic", lambda: clock[0])

    _type(combo, "d")
    assert combo._typeahead_text == "d"
    clock[0] += combo.TYPEAHEAD_TIMEOUT_MS / 1000.0 + 0.5
    _type(combo, "z")  # NOT "dz": the stale query was dropped
    assert combo._typeahead_text == "z"
    assert combo._typing_focus_index == 5  # Zeta


def test_escape_ends_the_typing_session(qtbot):
    combo = _make_combo(qtbot)
    _type(combo, "d")
    _key(combo, "\x1b", key=Qt.Key.Key_Escape)
    assert combo._typeahead_text == ""
    assert combo._expanded is False

    _type(combo, "e")
    assert combo._typeahead_text == "e"  # a new session, not "de"


def test_enter_commit_ends_the_typing_session(qtbot):
    combo = _make_combo(qtbot)
    _type(combo, "d")
    _key(combo, "\r", key=Qt.Key.Key_Return)
    assert combo._typeahead_text == ""

    _type(combo, "e")
    assert combo._typeahead_text == "e"
