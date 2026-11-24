"""MessageDialog / DialogActionBar — result plumbing, keyboard paths, surface."""

from __future__ import annotations

import ast
import sys

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog

from sli_ui_toolkit import ThemeManager
from sli_ui_toolkit.palettes import FLUENT_DARK, FLUENT_LIGHT
from sli_ui_toolkit.widgets import DialogActionBar, MessageDialog, MessageResult


@pytest.fixture(autouse=True)
def light_theme(qapp):
    tm = ThemeManager.get_instance()
    tm.register_palettes(FLUENT_LIGHT, FLUENT_DARK)
    tm.set_theme("light", qapp, await_ripples=False)
    tm._flush_pending_theme()  # type: ignore[attr-defined]
    yield


def _imported_pyside_names(source: str) -> set[str]:
    """Every name imported from a ``PySide6.*`` module (stock-widget guard)."""
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("PySide6"):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names if alias.name.startswith("PySide6"))
    return names



def _dialog(**kwargs) -> MessageDialog:
    return MessageDialog(None, "Title", "Body text", cancel_text="Cancel", **kwargs)


def _active_message_dialog() -> MessageDialog:
    """The modal MessageDialog currently on screen (inside ``exec()``)."""
    widget = QApplication.activeModalWidget()
    if isinstance(widget, MessageDialog):
        return widget
    for candidate in QApplication.topLevelWidgets():
        if isinstance(candidate, MessageDialog) and candidate.isVisible():
            return candidate
    raise AssertionError("MessageDialog not found among top-level widgets")


# -- action bar ---------------------------------------------------------------


def test_action_bar_emits_accepted(qtbot):
    bar = DialogActionBar(None, primary_text="OK", secondary_text="Cancel")
    qtbot.addWidget(bar)
    seen: list[str] = []
    bar.accepted.connect(lambda: seen.append("accepted"))
    bar.rejected.connect(lambda: seen.append("rejected"))

    bar.primary.click()

    assert seen == ["accepted"]


def test_action_bar_emits_rejected(qtbot):
    bar = DialogActionBar(None, primary_text="OK", secondary_text="Cancel")
    qtbot.addWidget(bar)
    seen: list[str] = []
    bar.accepted.connect(lambda: seen.append("accepted"))
    bar.rejected.connect(lambda: seen.append("rejected"))

    bar.secondary.click()

    assert seen == ["rejected"]


def test_action_bar_without_secondary_has_one_button(qtbot):
    bar = DialogActionBar(None, primary_text="OK")
    qtbot.addWidget(bar)
    assert bar.secondary is None


# -- MessageDialog results ----------------------------------------------------


def test_primary_button_accepts(qtbot):
    dialog = _dialog()
    qtbot.addWidget(dialog)

    dialog.action_bar.primary.click()

    assert dialog.result() == QDialog.DialogCode.Accepted


def test_secondary_button_rejects(qtbot):
    dialog = _dialog()
    qtbot.addWidget(dialog)

    dialog.action_bar.secondary.click()

    assert dialog.result() == QDialog.DialogCode.Rejected


def test_escape_cancels(qtbot):
    dialog = _dialog()
    qtbot.addWidget(dialog)

    QTest.keyClick(dialog, Qt.Key.Key_Escape)

    assert dialog.result() == QDialog.DialogCode.Rejected


def test_enter_takes_the_default_ok_button(qtbot):
    dialog = _dialog()
    qtbot.addWidget(dialog)

    QTest.keyClick(dialog, Qt.Key.Key_Return)

    assert dialog.result() == QDialog.DialogCode.Accepted


def test_enter_takes_the_default_cancel_button(qtbot):
    dialog = _dialog(default="cancel")
    qtbot.addWidget(dialog)

    QTest.keyClick(dialog, Qt.Key.Key_Return)

    assert dialog.result() == QDialog.DialogCode.Rejected


def test_unknown_kind_is_rejected(qtbot):
    with pytest.raises(ValueError):
        MessageDialog(None, "Title", "Body", kind="bogus")


def test_show_message_returns_checked_state(qtbot):
    def answer() -> None:
        dialog = _active_message_dialog()
        dialog.checkbox.setChecked(True)
        dialog.action_bar.primary.click()

    QTimer.singleShot(0, answer)
    result = MessageDialog.show_message(
        None, "Title", "Body", checkbox_text="Don't show again", cancel_text="Cancel"
    )

    assert result == MessageResult(ok=True, checked=True)


def test_show_message_cancel_reports_not_ok(qtbot):
    def answer() -> None:
        _active_message_dialog().action_bar.secondary.click()

    QTimer.singleShot(0, answer)
    result = MessageDialog.show_message(None, "Title", "Body", cancel_text="Cancel")

    assert result == MessageResult(ok=False, checked=False)


def test_question_returns_true_on_accept(qtbot):
    def answer() -> None:
        _active_message_dialog().action_bar.primary.click()

    QTimer.singleShot(0, answer)
    assert MessageDialog.question(None, "Title", "Proceed?") is True


def test_question_returns_false_on_cancel(qtbot):
    def answer() -> None:
        _active_message_dialog().action_bar.secondary.click()

    QTimer.singleShot(0, answer)
    assert MessageDialog.question(None, "Title", "Proceed?") is False


# -- surface / no stock widgets ----------------------------------------------


def test_message_dialog_paints_the_dialog_background_token(qapp, qtbot):
    tm = ThemeManager.get_instance()
    light = dict(FLUENT_LIGHT)
    # Distinct values prove WHICH token the surface follows (default palettes
    # keep both equal, so an equal-colour check would not discriminate).
    light["dialog.background"] = QColor("#123456")
    light["surface.background"] = QColor("#654321")
    tm.register_palettes(light, FLUENT_DARK)
    tm.set_theme("light", qapp, await_ripples=False)
    tm._flush_pending_theme()  # type: ignore[attr-defined]
    token = tm.get_color("dialog.background")

    dialog = _dialog()
    qtbot.addWidget(dialog)
    dialog.resize(340, 220)
    dialog.show()
    qapp.processEvents()

    image = dialog.grab().toImage()

    assert token.name() == "#123456"
    assert image.pixelColor(2, 2).name() == token.name()


def test_message_dialog_source_has_no_stylesheet():
    module = sys.modules[MessageDialog.__module__]
    source = open(module.__file__, encoding="utf-8").read()
    assert "setStyleSheet" not in source
    assert "QMessageBox" not in _imported_pyside_names(source)
