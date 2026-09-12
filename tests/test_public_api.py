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
