"""Live theme-token capture (the get_color/try_get_color funnel)."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.inspector.capture import capture_tokens
from sli_ui_toolkit.ui.inspector.contract import FieldKind
from sli_ui_toolkit.widgets import Button, Label


def _theme(app):
    tm = ThemeManager.get_instance()
    tm.register_palettes(
        {
            "accent": "#0078d4",
            "dialog.text": "#111111",
            "surface.list": "#f0f0f0",
        },
        {
            "accent": "#0096ff",
            "dialog.text": "#dddddd",
            "surface.list": "#2a2a2a",
        },
    )
    tm.set_theme("light", app)
    return tm


def test_capture_records_resolved_keys(qapp):
    button = Button(text="x")
    tokens = capture_tokens(button, _theme(qapp))
    keys = {f.name for f in tokens}
    assert "surface.list" in keys
    assert "dialog.text" in keys
    by_name = {f.name: f for f in tokens}
    assert by_name["surface.list"].kind is FieldKind.COLOR
    assert by_name["surface.list"].value == "#f0f0f0"


def test_capture_marks_missing_keys(qapp):
    button = Button(text="x")
    tokens = capture_tokens(button, _theme(qapp))
    missing = [f for f in tokens if f.meta.get("missing")]
    # button.toggle.border is not in the test palette
    assert any(f.name == "button.toggle.border" for f in missing)


def test_capture_restores_original_methods(qapp):
    tm = _theme(qapp)
    original_get = tm.get_color
    original_try = tm.try_get_color
    capture_tokens(Button(text="x"), tm)
    assert tm.get_color is original_get
    assert tm.try_get_color is original_try


def test_capture_empty_without_theme(qapp):
    assert capture_tokens(Button(text="x"), None) == ()


def test_capture_empty_on_bare_widget(qapp):
    tokens = capture_tokens(QWidget(), _theme(qapp))
    assert tokens == ()
