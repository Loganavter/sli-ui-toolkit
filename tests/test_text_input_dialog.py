"""TextInputDialog — QInputDialog.getText shape, validator gate, surface."""

from __future__ import annotations

import ast
import sys

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QIntValidator
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog

from sli_ui_toolkit import ThemeManager
from sli_ui_toolkit.palettes import FLUENT_DARK, FLUENT_LIGHT
from sli_ui_toolkit.widgets import TextInputDialog


@pytest.fixture(autouse=True)
def light_theme(qapp):
    tm = ThemeManager.get_instance()
    tm.register_palettes(FLUENT_LIGHT, FLUENT_DARK)
    tm.set_theme("light", qapp, await_ripples=False)
    tm._flush_pending_theme()  # type: ignore[attr-defined]
    yield


def _imported_pyside_names(source: str) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("PySide6"):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names if alias.name.startswith("PySide6"))
    return names



def _dialog(**kwargs) -> TextInputDialog:
    return TextInputDialog(None, "Title", "Prompt", "start", **kwargs)


def _active_input_dialog() -> TextInputDialog:
    widget = QApplication.activeModalWidget()
    if isinstance(widget, TextInputDialog):
        return widget
    for candidate in QApplication.topLevelWidgets():
        if isinstance(candidate, TextInputDialog) and candidate.isVisible():
            return candidate
    raise AssertionError("TextInputDialog not found among top-level widgets")


def test_enter_accepts_the_edited_text(qapp, qtbot):
    dialog = _dialog()
    qtbot.addWidget(dialog)
    dialog.field.setText("edited")

    QTest.keyClick(dialog.field, Qt.Key.Key_Return)
    qapp.processEvents()  # CustomLineEdit's deferred clearFocus

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.field.text() == "edited"


def test_escape_cancels_from_the_field(qtbot):
    dialog = _dialog()
    qtbot.addWidget(dialog)

    QTest.keyClick(dialog.field, Qt.Key.Key_Escape)

    assert dialog.result() == QDialog.DialogCode.Rejected


def test_escape_cancels_from_the_dialog(qtbot):
    dialog = _dialog()
    qtbot.addWidget(dialog)

    QTest.keyClick(dialog, Qt.Key.Key_Escape)

    assert dialog.result() == QDialog.DialogCode.Rejected


def test_invalid_value_keeps_the_dialog_open(qapp, qtbot):
    dialog = _dialog(validator=QIntValidator(0, 10))
    qtbot.addWidget(dialog)
    dialog.field.setText("99")

    QTest.keyClick(dialog.field, Qt.Key.Key_Return)
    qapp.processEvents()  # CustomLineEdit's deferred clearFocus

    assert dialog.result() != QDialog.DialogCode.Accepted

    dialog.field.setText("5")
    QTest.keyClick(dialog.field, Qt.Key.Key_Return)
    qapp.processEvents()

    assert dialog.result() == QDialog.DialogCode.Accepted


def test_invalid_value_blocks_the_primary_button(qtbot):
    dialog = _dialog(validator=QIntValidator(0, 10))
    qtbot.addWidget(dialog)
    dialog.field.setText("99")

    dialog.action_bar.primary.click()

    assert dialog.result() != QDialog.DialogCode.Accepted


def test_initial_text_is_selected_and_placeholder_forwarded(qtbot):
    dialog = TextInputDialog(None, "Title", "Prompt", "start", placeholder="type here")
    qtbot.addWidget(dialog)

    assert dialog.field.text() == "start"
    assert dialog.field.selectedText() == "start"
    assert dialog.field.placeholderText() == "type here"


def test_get_text_returns_the_edited_value(qtbot):
    def answer() -> None:
        dialog = _active_input_dialog()
        dialog.field.setText("edited")
        dialog.action_bar.primary.click()

    QTimer.singleShot(0, answer)

    assert TextInputDialog.get_text(None, "Title", "Prompt", "start") == ("edited", True)


def test_get_text_returns_empty_on_cancel(qtbot):
    def answer() -> None:
        _active_input_dialog().action_bar.secondary.click()

    QTimer.singleShot(0, answer)

    assert TextInputDialog.get_text(None, "Title", "Prompt", "start") == ("", False)


def test_text_input_dialog_paints_the_dialog_background_token(qapp, qtbot):
    tm = ThemeManager.get_instance()
    light = dict(FLUENT_LIGHT)
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


def test_text_input_dialog_source_has_no_stylesheet_or_stock_input():
    module = sys.modules[TextInputDialog.__module__]
    source = open(module.__file__, encoding="utf-8").read()
    imported = _imported_pyside_names(source)
    assert "setStyleSheet" not in source
    assert "QInputDialog" not in imported
    assert "QLineEdit" not in imported
