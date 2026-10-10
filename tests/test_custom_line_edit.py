"""CustomLineEdit — painted single-line editor (no QLineEdit).

Geometry regression (horizontal-only margins, descenders fit) plus the
painted-editor contract: typing/caret/selection/clipboard, validators,
max-length, echo mode, clear button, and the QLineEdit-compatible signals.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics, QGuiApplication, QIntValidator
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLineEdit

from sli_ui_toolkit import FLUENT_DARK, FLUENT_LIGHT, ThemeManager
from sli_ui_toolkit.widgets import CustomLineEdit


def _register_palettes(qapp):
    tm = ThemeManager.get_instance()
    tm.register_palettes(FLUENT_LIGHT, FLUENT_DARK)
    tm.set_theme("dark", qapp)


def test_custom_line_edit_text_margins_are_horizontal_only(qapp):
    _register_palettes(qapp)
    edit = CustomLineEdit()
    margins = edit.textMargins()
    assert margins.left() == CustomLineEdit.H_PADDING
    assert margins.right() == CustomLineEdit.H_PADDING
    assert margins.top() == 0
    assert margins.bottom() == 0
    # No QSS at all: any stylesheet on the widget (even color-only) makes Qt
    # ignore setFont() when painting, freezing the text at the design size.
    # Colors come from the palette instead (apply_text_color + Highlight /
    # PlaceholderText roles).
    assert edit.styleSheet() == ""
    edit.deleteLater()


def test_custom_line_edit_content_taller_than_font_with_descenders(qapp):
    """Fixed height minus text margins must fit fontMetrics().height()."""
    _register_palettes(qapp)
    edit = CustomLineEdit()
    margins = edit.textMargins()
    content_h = edit.height() - margins.top() - margins.bottom()
    assert content_h >= QFontMetrics(edit.font()).height()
    edit.deleteLater()


def test_not_a_qlineedit(qapp):
    """The painted editor must not subclass QLineEdit."""
    _register_palettes(qapp)
    edit = CustomLineEdit()
    assert not isinstance(edit, QLineEdit)
    # EchoMode mirrors QLineEdit's integer values.
    assert edit.EchoMode.Password == QLineEdit.EchoMode.Password.value
    edit.deleteLater()


def test_typing_emits_textchanged_and_textedited(qtbot, qapp):
    _register_palettes(qapp)
    edit = CustomLineEdit()
    qtbot.addWidget(edit)
    edit.show()
    qtbot.waitExposed(edit)
    edit.setFocus()
    changed, edited = [], []
    edit.textChanged.connect(changed.append)
    edit.textEdited.connect(edited.append)
    QTest.keyClicks(edit, "abc")
    assert edit.text() == "abc"
    assert edit.cursorPosition() == 3
    assert changed and changed[-1] == "abc"
    assert edited and edited[-1] == "abc"
    edit.deleteLater()


def test_settext_emits_changed_but_not_edited(qapp):
    _register_palettes(qapp)
    edit = CustomLineEdit()
    changed, edited = [], []
    edit.textChanged.connect(changed.append)
    edit.textEdited.connect(edited.append)
    edit.setText("hello")
    assert edit.text() == "hello"
    assert changed == ["hello"]
    assert edited == []
    edit.deleteLater()


def test_validator_rejects_invalid_keystrokes(qtbot, qapp):
    _register_palettes(qapp)
    edit = CustomLineEdit()
    edit.setValidator(QIntValidator(0, 100, edit))
    qtbot.addWidget(edit)
    edit.show()
    qtbot.waitExposed(edit)
    edit.setFocus()
    QTest.keyClicks(edit, "42")
    assert edit.text() == "42"
    QTest.keyClicks(edit, "x")
    assert edit.text() == "42"
    assert edit.hasAcceptableInput()
    edit.deleteLater()


def test_max_length_clamps_typing(qtbot, qapp):
    _register_palettes(qapp)
    edit = CustomLineEdit()
    edit.setMaxLength(3)
    qtbot.addWidget(edit)
    edit.show()
    qtbot.waitExposed(edit)
    edit.setFocus()
    QTest.keyClicks(edit, "abcde")
    assert edit.text() == "abc"
    edit.deleteLater()


def test_select_all_copy_and_cut(qapp):
    _register_palettes(qapp)
    edit = CustomLineEdit()
    edit.setText("hello world")
    edit.selectAll()
    assert edit.hasSelectedText()
    assert edit.selectionStart() == 0
    assert edit.selectedText() == "hello world"
    edit.copy()
    assert QGuiApplication.clipboard().text() == "hello world"
    edit.cut()
    assert edit.text() == ""
    edit.deleteLater()


def test_set_selection_and_cursor(qapp):
    _register_palettes(qapp)
    edit = CustomLineEdit()
    edit.setText("abcdef")
    edit.setSelection(1, 3)
    assert edit.selectedText() == "bcd"
    edit.setCursorPosition(0)
    assert edit.cursorPosition() == 0
    assert not edit.hasSelectedText()
    edit.deleteLater()


def test_clear_button_clears_text(qtbot, qapp):
    _register_palettes(qapp)
    edit = CustomLineEdit()
    edit.setClearButtonEnabled(True)
    edit.setText("value")
    edit.setFixedWidth(160)
    qtbot.addWidget(edit)
    edit.show()
    qtbot.waitExposed(edit)
    assert edit.isClearButtonEnabled()
    rect = edit._clear_button_rect()
    qtbot.mouseClick(edit, Qt.MouseButton.LeftButton, pos=rect.center())
    assert edit.text() == ""
    edit.deleteLater()


def test_return_pressed_signal(qtbot, qapp):
    _register_palettes(qapp)
    edit = CustomLineEdit()
    qtbot.addWidget(edit)
    edit.show()
    qtbot.waitExposed(edit)
    edit.setFocus()
    fired = []
    edit.returnPressed.connect(lambda: fired.append(True))
    QTest.keyClick(edit, Qt.Key.Key_Return)
    assert fired == [True]
    edit.deleteLater()


def test_copy_paste_round_trip(qapp):
    _register_palettes(qapp)
    QGuiApplication.clipboard().setText("pasted")
    edit = CustomLineEdit()
    edit.setFocus()
    edit.paste()
    assert edit.text() == "pasted"
    edit.deleteLater()


def test_caret_and_selection_use_text_line_height(qapp):
    """Caret/selection must be text-height, not the whole 32px field."""
    _register_palettes(qapp)
    edit = CustomLineEdit()
    fm = QFontMetrics(edit.font())
    line = edit._text_line_rect(edit._content_rect())
    assert line.height() == fm.ascent() + fm.descent()
    assert line.height() < edit.height()
    edit.deleteLater()


def test_shortcut_override_claims_plain_letters(qapp):
    """A plain printable key must be claimed on ShortcutOverride.

    Regression: the painted field did not claim ShortcutOverride for typing
    keys, so a window-level single-letter shortcut (e.g. "e") won the event and
    the character was never inserted into the focused field.
    """
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QKeyEvent

    _register_palettes(qapp)
    edit = CustomLineEdit()
    ev = QKeyEvent(
        QEvent.Type.ShortcutOverride,
        Qt.Key.Key_E,
        Qt.KeyboardModifier.NoModifier,
        "e",
    )
    assert edit.event(ev) is True
    assert ev.isAccepted()
    edit.deleteLater()
