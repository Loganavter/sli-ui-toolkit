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


#: State keys each control family owns. Before these existed a control borrowed another family's token, so a host
#: could not restyle one control without repainting its neighbour (P2 of the colour-token investigation).
CONTROL_STATE_TOKENS = (
    "input.background",
    "input.border",
    "input.text",
    "input.text.disabled",
    "input.placeholder",
    "input.underline",
    "input.underline.focused",
    "input.underline.disabled",
    "input.selection.background",
    "checkbox.text",
    "checkbox.text.disabled",
    "checkbox.border",
    "checkbox.background.hover",
    "checkbox.background.pressed",
    "switch.track.hover",
    "switch.track.disabled",
    "switch.text.disabled",
    "slider.track.filled",
    "slider.track.hover",
    "slider.track.disabled",
    "slider.thumb.disabled",
    "list_item.text.selected",
    "list_item.text.disabled",
    "list_item.background.focused",
    "menu.background",
    "menu.background.hover",
    "menu.text",
    "menu.text.disabled",
    "menu.separator",
    "titlebar.menu.text",
    # P3b: the remaining painters own their ink, their hover step and the calendar chip.
    "flyout.text",
    "progress.text",
    "label.text",
    "label.text.muted",
    "calendar.background.data",
)


@pytest.mark.parametrize("token", CONTROL_STATE_TOKENS)
def test_control_state_token_present_in_both_palettes(token):
    for theme_name, palette in (("light", FLUENT_LIGHT), ("dark", FLUENT_DARK)):
        assert token in palette, f"[{theme_name}] control state token {token!r} is missing from the palette"
        color = palette[token]
        assert isinstance(color, QColor), f"[{theme_name}] token {token!r} is not a QColor"
        assert color.isValid(), f"[{theme_name}] token {token!r} resolved to an invalid color"


def test_default_palettes_expose_the_same_key_set():
    light, dark = set(FLUENT_LIGHT), set(FLUENT_DARK)
    assert light == dark, (
        f"palette key sets diverged - light only: {sorted(light - dark)}; dark only: {sorted(dark - light)}"
    )


@pytest.mark.parametrize("token", CONTROL_STATE_TOKENS)
def test_control_state_token_resolves_through_the_manager(theme, token):
    tm = ThemeManager.get_instance()
    palette = FLUENT_DARK if theme == "dark" else FLUENT_LIGHT
    resolved = tm.try_get_color(token)
    assert isinstance(resolved, QColor) and resolved.rgba() == palette[token].rgba(), (
        f"[{theme}] token {token!r} does not resolve to its palette value"
    )
