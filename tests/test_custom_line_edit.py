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


def _wheel_event(y_angle_delta: int):
    """A vertical-wheel event over the field (positive = wheel up)."""
    from PySide6.QtCore import QPoint, QPointF
    from PySide6.QtGui import QWheelEvent

    return QWheelEvent(
        QPointF(10, 10),
        QPointF(10, 10),
        QPoint(0, 0),
        QPoint(0, y_angle_delta),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )


def _overflowed_edit(qtbot, qapp, width: int = 120):
    """A shown, focused field whose text overflows (scroll offset > 0)."""
    _register_palettes(qapp)
    edit = CustomLineEdit()
    qtbot.addWidget(edit)
    edit.resize(width, edit.height())
    edit.show()
    qtbot.waitExposed(edit)
    edit.setFocus()
    edit.setText("w" * 200)
    assert edit._h_offset > 0, "precondition: text overflows the field"
    return edit


def test_wheel_scrolls_overflowed_text_horizontally(qtbot, qapp):
    """The wheel pans an overflowed line (QLineEdit parity).

    Falsification: pre-change the field has no wheelEvent override — the
    offset never moves and the event stays ignored.
    """
    edit = _overflowed_edit(qtbot, qapp)
    start = edit._h_offset

    up = _wheel_event(120)
    edit.wheelEvent(up)
    assert up.isAccepted()
    assert edit._h_offset < start

    down = _wheel_event(-240)
    edit.wheelEvent(down)
    assert down.isAccepted()
    assert edit._h_offset > 0
    edit.deleteLater()


def test_wheel_ignored_when_text_fits(qtbot, qapp):
    """A fitting line lets the wheel bubble to an enclosing scroller."""
    _register_palettes(qapp)
    edit = CustomLineEdit()
    qtbot.addWidget(edit)
    edit.resize(300, edit.height())
    edit.show()
    qtbot.waitExposed(edit)
    edit.setFocus()
    edit.setText("short")

    ev = _wheel_event(120)
    edit.wheelEvent(ev)
    assert not ev.isAccepted()
    edit.deleteLater()


def test_submit_preset_tab_accepts_placeholder(qtbot, qapp):
    """Preset Tab turns an empty field's placeholder into starting text.

    Falsification: pre-change there is no setSubmitPreset (AttributeError)
    and Tab never adopts the placeholder.
    """
    _register_palettes(qapp)
    edit = CustomLineEdit()
    edit.setSubmitPreset(True)
    qtbot.addWidget(edit)
    edit.show()
    qtbot.waitExposed(edit)
    edit.setFocus()
    edit.setPlaceholderText("Say something…")

    QTest.keyClick(edit, Qt.Key.Key_Tab)
    assert edit.text() == "Say something…"
    assert edit.cursorPosition() == len("Say something…")
    assert not edit.hasSelectedText()
    edit.deleteLater()


def test_submit_preset_tab_needs_empty_field(qtbot, qapp):
    """Preset Tab with existing text keeps default behavior (no adopt)."""
    _register_palettes(qapp)
    edit = CustomLineEdit(submit_preset=True)
    qtbot.addWidget(edit)
    edit.show()
    qtbot.waitExposed(edit)
    edit.setFocus()
    edit.setPlaceholderText("Say something…")
    edit.setText("typed")

    QTest.keyClick(edit, Qt.Key.Key_Tab)
    assert edit.text() != "Say something…"
    edit.deleteLater()


def test_submit_preset_enter_submits_typed_text(qtbot, qapp):
    """Preset Enter emits submitted with the stripped text."""
    _register_palettes(qapp)
    edit = CustomLineEdit()
    edit.setSubmitPreset(True)
    qtbot.addWidget(edit)
    edit.show()
    qtbot.waitExposed(edit)
    edit.setFocus()
    edit.setPlaceholderText("Say something…")
    edit.setText("  hello  ")

    got: list[str] = []
    edit.submitted.connect(got.append)
    QTest.keyClick(edit, Qt.Key.Key_Return)
    assert got == ["hello"]
    edit.deleteLater()


def test_submit_preset_enter_falls_back_to_placeholder(qtbot, qapp):
    """Preset Enter on an empty field submits the placeholder."""
    _register_palettes(qapp)
    edit = CustomLineEdit(submit_preset=True)
    qtbot.addWidget(edit)
    edit.show()
    qtbot.waitExposed(edit)
    edit.setFocus()
    edit.setPlaceholderText("Say something…")

    got: list[str] = []
    edit.submitted.connect(got.append)
    QTest.keyClick(edit, Qt.Key.Key_Enter)
    assert got == ["Say something…"]
    edit.deleteLater()


def test_submit_preset_enter_rewinds_view_to_start(qtbot, qapp):
    """Preset Enter resets the scroll offset and caret to the start.

    Falsification: pre-change the view stays pinned to the end where the
    caret was — the question's start is not visible after submit.
    """
    edit = _overflowed_edit(qtbot, qapp)
    edit.setSubmitPreset(True)

    got: list[str] = []
    edit.submitted.connect(got.append)
    QTest.keyClick(edit, Qt.Key.Key_Return)
    assert len(got) == 1
    assert edit.cursorPosition() == 0
    assert edit._h_offset == 0
    edit.deleteLater()


def test_preset_off_keeps_plain_behavior(qtbot, qapp):
    """Without the preset there is no submitted emission or Tab-adopt."""
    _register_palettes(qapp)
    edit = CustomLineEdit()
    assert edit.isSubmitPreset() is False
    qtbot.addWidget(edit)
    edit.show()
    qtbot.waitExposed(edit)
    edit.setFocus()
    edit.setPlaceholderText("Say something…")

    got: list[str] = []
    edit.submitted.connect(got.append)
    pressed: list[bool] = []
    edit.returnPressed.connect(lambda: pressed.append(True))
    QTest.keyClick(edit, Qt.Key.Key_Return)
    assert pressed == [True]
    assert got == []
    QTest.keyClick(edit, Qt.Key.Key_Tab)
    assert edit.text() != "Say something…"
    edit.deleteLater()
