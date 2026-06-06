from __future__ import annotations

from sli_ui_toolkit import FLUENT_DARK, FLUENT_LIGHT, ThemeManager


def test_palettes_are_dicts():
    assert isinstance(FLUENT_LIGHT, dict) and FLUENT_LIGHT
    assert isinstance(FLUENT_DARK, dict) and FLUENT_DARK


def test_theme_manager_singleton(qapp):
    a = ThemeManager.get_instance()
    b = ThemeManager.get_instance()
    assert a is b


def test_theme_switching(qapp):
    tm = ThemeManager.get_instance()
    tm.register_palettes(FLUENT_LIGHT, FLUENT_DARK)

    tm.set_theme("light")
    assert tm.get_current_theme() == "light"
    assert tm.is_dark() is False

    tm.set_theme("dark")
    assert tm.get_current_theme() == "dark"
    assert tm.is_dark() is True
