from __future__ import annotations

import pytest
from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPixmap

from sli_ui_toolkit import FLUENT_DARK, FLUENT_LIGHT, ThemeManager
from sli_ui_toolkit.icons import get_icon_by_name, lazy_icon, resolve_icon
from sli_ui_toolkit.ui.widgets.helpers.icon_pixmap import (
    _pixmap_cache,
    normalized_icon_pixmap,
)
from sli_ui_toolkit.widgets import Button


def _solid_icon(color: str) -> QIcon:
    pix = QPixmap(16, 16)
    pix.fill(QColor(color))
    return QIcon(pix)


@pytest.mark.parametrize(
    "name",
    ["add", "delete", "edit", "save", "check", "chevron-down", "settings"],
)
def test_bundled_icons_resolve(qapp, name):
    icon = resolve_icon(name)
    assert isinstance(icon, QIcon)
    assert not icon.isNull(), f"bundled icon {name!r} resolved to a null QIcon"


def test_resolve_none_returns_empty_icon(qapp):
    icon = resolve_icon(None)
    assert isinstance(icon, QIcon)
    assert icon.isNull()


def test_lazy_icon_resolves_to_current_theme_on_flip(qapp):
    tm = ThemeManager.get_instance()
    tm.register_palettes(FLUENT_LIGHT, FLUENT_DARK)
    prev_theme = tm.get_current_theme()

    light_icon = _solid_icon("#112233")
    dark_icon = _solid_icon("#ddeeff")
    handle = lazy_icon(lambda: dark_icon if tm.is_dark() else light_icon)

    try:
        tm.set_theme("light", await_ripples=False)
        resolved_light = resolve_icon(handle)
        assert resolved_light.cacheKey() == light_icon.cacheKey()

        tm.set_theme("dark", await_ripples=False)
        resolved_dark = resolve_icon(handle)
        assert resolved_dark.cacheKey() == dark_icon.cacheKey()
        assert resolved_dark.cacheKey() != resolved_light.cacheKey()
    finally:
        tm.set_theme(prev_theme, await_ripples=False)


def test_resolve_icon_accepts_zero_arg_callable_and_bundled_theme_flip(qapp):
    tm = ThemeManager.get_instance()
    tm.register_palettes(FLUENT_LIGHT, FLUENT_DARK)
    prev_theme = tm.get_current_theme()

    handle = lazy_icon(lambda: get_icon_by_name("add"))
    raw_callable = lambda: get_icon_by_name("add")

    try:
        tm.set_theme("light", await_ripples=False)
        light_qicon = resolve_icon(handle)
        assert resolve_icon(raw_callable).cacheKey() == light_qicon.cacheKey()

        tm.set_theme("dark", await_ripples=False)
        dark_qicon = resolve_icon(handle)
        assert resolve_icon(raw_callable).cacheKey() == dark_qicon.cacheKey()
        assert dark_qicon.cacheKey() != light_qicon.cacheKey()
    finally:
        tm.set_theme(prev_theme, await_ripples=False)


def test_normalized_icon_pixmap_lazy_handle_hits_cache_across_two_paints(qapp, qtbot):
    cached_icon = _solid_icon("#228844")
    calls = {"count": 0}

    def _provider() -> QIcon:
        calls["count"] += 1
        return cached_icon

    handle = lazy_icon(_provider)
    _pixmap_cache.clear()

    btn = Button(icon=handle, size=(32, 32))
    qtbot.addWidget(btn)
    btn.resize(32, 32)

    canvas = QImage(QSize(32, 32), QImage.Format.Format_ARGB32_Premultiplied)
    btn.render(canvas)
    assert len(_pixmap_cache) == 1
    first_pix = next(iter(_pixmap_cache.values()))

    btn.render(canvas)
    assert len(_pixmap_cache) == 1
    second_pix = next(iter(_pixmap_cache.values()))
    assert second_pix is first_pix
    assert calls["count"] == 2

    direct_first = normalized_icon_pixmap(handle, 16)
    direct_second = normalized_icon_pixmap(handle, 16)
    assert direct_second is direct_first
