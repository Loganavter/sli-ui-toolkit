from __future__ import annotations

import importlib
import subprocess
import sys

import pytest


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


# `__all__` is the advertised surface: `from ... import *` and the catalogue both trust it,
# so a listed name that no module defines fails only when someone resolves it, and a public
# widget missing from it silently disappears from the advertised surface. Both drifts are
# invisible to a plain `hasattr` check of the module, which is why they are pinned here.
PUBLIC_SURFACE_MODULES = (
    "sli_ui_toolkit",
    "sli_ui_toolkit.widgets",
    "sli_ui_toolkit.style",
    "sli_ui_toolkit.managers",
    "sli_ui_toolkit.theme",
    "sli_ui_toolkit.icons",
    "sli_ui_toolkit.workers",
    "sli_ui_toolkit.services",
    # Not a public entry point, but `widgets` re-exports its members wholesale and hosts
    # import sub-widgets from it, so its `__all__` is held to the same contract.
    "sli_ui_toolkit.ui.widgets.composite",
)


@pytest.mark.parametrize("module_name", PUBLIC_SURFACE_MODULES)
def test_all_names_resolve(module_name):
    module = importlib.import_module(module_name)
    names = getattr(module, "__all__", None)
    assert names, f"{module_name} does not declare __all__"
    missing = [name for name in names if not hasattr(module, name)]
    assert not missing, f"{module_name}.__all__ lists names that do not resolve: {missing}"


@pytest.mark.parametrize("module_name", PUBLIC_SURFACE_MODULES)
def test_star_import_resolves_in_a_fresh_interpreter(module_name):
    # A fresh interpreter proves the module's own import graph is complete, not just the
    # classes this test process happened to touch first.
    result = subprocess.run(
        [sys.executable, "-c", f"from {module_name} import *"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"from {module_name} import * failed:\n{result.stderr}"


def test_surface_panel_is_an_advertised_widgets_export():
    # docs/user/API_CATALOG.md sells `SurfacePanel` as a `sli_ui_toolkit.widgets` entry and
    # hosts already import it through that path; the `__all__` entry is what makes the claim
    # true for star-import and doc-driven consumers, so the two must not drift apart again.
    widgets = importlib.import_module("sli_ui_toolkit.widgets")
    assert "SurfacePanel" in widgets.__all__
    assert widgets.SurfacePanel.__name__ == "SurfacePanel"

