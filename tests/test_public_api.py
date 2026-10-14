from __future__ import annotations

import importlib


def test_top_level_imports():
    mod = importlib.import_module("sli_ui_toolkit")
    for name in mod.__all__:
        assert hasattr(mod, name), f"sli_ui_toolkit.__all__ lists {name!r} but attribute is missing"


def test_widgets_imports():
    mod = importlib.import_module("sli_ui_toolkit.widgets")
    for name in mod.__all__:
        assert hasattr(mod, name), f"sli_ui_toolkit.widgets.__all__ lists {name!r} but attribute is missing"


def test_subpackages_importable():
    for path in (
        "sli_ui_toolkit.theme",
        "sli_ui_toolkit.icons",
        "sli_ui_toolkit.i18n",
        "sli_ui_toolkit.config",
        "sli_ui_toolkit.palettes",
        "sli_ui_toolkit.style",
    ):
        importlib.import_module(path)


def test_style_module_exports():
    import sli_ui_toolkit
    from sli_ui_toolkit import style

    for name in ("WidgetStyleTokens", "read_widget_style", "update_widget_style", "icon_size_qsize"):
        assert hasattr(style, name), f"sli_ui_toolkit.style missing {name!r}"

    # Top-level re-exports must be the same objects as the canonical module.
    assert sli_ui_toolkit.WidgetStyleTokens is style.WidgetStyleTokens
    assert sli_ui_toolkit.read_widget_style is style.read_widget_style
    assert sli_ui_toolkit.update_widget_style is style.update_widget_style


def test_theme_refresh_and_lazy_icon_exports():
    import sli_ui_toolkit
    from sli_ui_toolkit import icons, theme, widgets
    from sli_ui_toolkit.ui import widgets as ui_widgets
    from sli_ui_toolkit.ui.managers import theme_manager
    from sli_ui_toolkit.ui.widgets import themed

    assert hasattr(icons, "lazy_icon")
    assert ui_widgets.ThemedContainer is themed.ThemedContainer
    assert widgets.ThemedContainer is themed.ThemedContainer
    assert sli_ui_toolkit.ThemedContainer is themed.ThemedContainer
    assert ui_widgets.refresh_theme_subtree is theme_manager.refresh_theme_subtree
    assert widgets.refresh_theme_subtree is theme_manager.refresh_theme_subtree
    assert theme.refresh_theme_subtree is theme_manager.refresh_theme_subtree
    assert sli_ui_toolkit.refresh_theme_subtree is theme_manager.refresh_theme_subtree
