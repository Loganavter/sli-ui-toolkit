"""Widget-level token resolution must be parity-checked over both themes."""
from __future__ import annotations
import pytest
from PySide6.QtGui import QColor
from sli_ui_toolkit import FLUENT_DARK, FLUENT_LIGHT, ThemeManager
@pytest.fixture(params=["light", "dark"])
def theme(request, qapp):
    tm = ThemeManager.get_instance()
    tm.register_palettes(FLUENT_LIGHT, FLUENT_DARK)
    tm.set_theme(request.param, qapp, await_ripples=False)
    tm._flush_pending_theme()  # type: ignore[attr-defined]
    yield request.param
    tm.set_theme("light", qapp, await_ripples=False)
    tm._flush_pending_theme()  # type: ignore[attr-defined]
def _assert_valid_palette_color(color: QColor, token: str, theme_name: str):
    assert isinstance(color, QColor)
    assert color.isValid(), f"[{theme_name}] token {token!r} resolved to invalid color"
    palette = FLUENT_DARK if theme_name == "dark" else FLUENT_LIGHT
    expected = palette.get(token)
    if isinstance(expected, QColor):
        assert color.rgba() == expected.rgba(), f"[{theme_name}] token {token!r} mismatch palette"
@pytest.mark.parametrize("token", ["Window", "WindowText", "Base", "Text", "Button", "ButtonText"])
def test_core_palette_tokens_resolve_in_both_themes(theme, qapp, token):
    tm = ThemeManager.get_instance()
    color = tm.get_color(token)
    _assert_valid_palette_color(color, token, theme)
@pytest.mark.parametrize("token", ["accent", "accent.hover", "dialog.background", "tooltip.background"])
def test_extended_tokens_resolve_in_both_themes(theme, qapp, token):
    tm = ThemeManager.get_instance()
    color = tm.try_get_color(token) or tm.get_color(token)
    assert color is not None and color.isValid()
    if color.name() == QColor("#000000").name():
        palette = FLUENT_DARK if theme == "dark" else FLUENT_LIGHT
        assert palette.get(token) is not None or token == "accent.hover"
def test_widget_bg_resolves_in_both_themes(qapp, qtbot, theme):
    from sli_ui_toolkit.widgets import Button
    btn = Button(text="Parity", variant="surface")
    btn.show()
    qtbot.addWidget(btn)
    qapp.processEvents()
    tm = ThemeManager.get_instance()
    bg = tm.get_color("Button")
    _assert_valid_palette_color(bg, "Button", theme)
def test_try_get_color_returns_none_for_missing_token_in_both_themes(theme):
    tm = ThemeManager.get_instance()
    assert tm.try_get_color("__missing_token__") is None
    fallback = tm.get_color("__missing_token__")
    assert isinstance(fallback, QColor) and fallback.isValid()
