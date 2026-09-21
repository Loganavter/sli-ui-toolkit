"""Task 3 (tokens/docs) regression tests.

Covers: every theme token used in src resolves without
"unknown theme token" warnings on both FLUENT palettes (G1 gate), the four
newly registered tokens, icon-cache clear + scale/content keying,
UiScale-triggered app-QSS re-apply, and ToolbarRowsSection on_exit_right
wiring.
"""

from __future__ import annotations

import copy
import logging
import os
import pathlib
import re

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.palettes import FLUENT_DARK, FLUENT_LIGHT
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.managers.icon_manager import (
    _get_themed_icon_cached,
    clear_icon_cache,
    get_themed_icon,
)
from sli_ui_toolkit.ui.managers.navigation_sections import ToolbarRowsSection
from sli_ui_toolkit.ui.managers.ui_scale import UiScale

_TOKEN_RE = re.compile(
    r"(?:get_color|try_get_color|set_color|set_surface_token|surface_token)"
    r"\(\s*[\"']([^\"']+)[\"']"
)


def _used_tokens() -> set[str]:
    src = pathlib.Path(__file__).parent.parent / "src" / "sli_ui_toolkit"
    used: set[str] = set()
    for path in src.rglob("*.py"):
        used.update(_TOKEN_RE.findall(path.read_text()))
    return used


@pytest.fixture()
def hermetic_managers(qapp):
    """Snapshot/restore theme palettes, QSS template, and UI scale."""
    tm = ThemeManager.get_instance()
    scale = UiScale.get_instance()
    saved_light = copy.deepcopy(tm._light_palette)
    saved_dark = copy.deepcopy(tm._dark_palette)
    saved_theme = tm.get_current_theme()
    saved_template = tm._qss_template
    saved_paths = list(tm._qss_paths)
    saved_factor = scale.factor()
    tm.register_palettes(
        light_palette=copy.deepcopy(FLUENT_LIGHT),
        dark_palette=copy.deepcopy(FLUENT_DARK),
    )
    tm.set_theme("light", qapp, await_ripples=False)
    yield tm
    tm.register_palettes(light_palette=saved_light, dark_palette=saved_dark)
    tm.set_theme(saved_theme, qapp, await_ripples=False)
    tm._qss_template = saved_template
    tm._qss_paths = saved_paths
    scale.set_factor(saved_factor)
    qapp.processEvents()


# -- G1: zero unknown-token warnings ---------------------------------------


def test_all_used_tokens_resolve_without_warnings(qapp, hermetic_managers, caplog):
    tokens = _used_tokens()
    assert "surface.background" in tokens  # the headline registration
    assert len(tokens) > 20  # scan actually found the token call sites
    with caplog.at_level(logging.WARNING, logger="ThemeManager"):
        for theme in ("light", "dark"):
            hermetic_managers.set_theme(theme, qapp, await_ripples=False)
            caplog.clear()
            for token in sorted(tokens):
                color = hermetic_managers.get_color(token)
                assert isinstance(color, QColor) and color.isValid(), token
            unknowns = [
                r for r in caplog.records if "unknown theme token" in r.message
            ]
            assert unknowns == [], [r.message for r in unknowns]


def test_new_tokens_registered_in_both_palettes():
    expected = {
        "surface.background": ("#ffffff", "#2b2b2b"),
        "surface.list": ("#f0f0f0", "#3c3c3c"),
        "list_item.background.selected": ("#0078d4", "#0078d4"),
        "list_item.icon.selected": ("#ffffff", "#ffffff"),
    }
    for token, (light, dark) in expected.items():
        assert QColor(FLUENT_LIGHT[token]).name() == light, token
        assert QColor(FLUENT_DARK[token]).name() == dark, token


# -- Icon cache -------------------------------------------------------------


def _write_png(path: pathlib.Path, color: str, size: int = 16) -> None:
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(color))
    assert pixmap.save(str(path), "PNG")


def test_icon_cache_clear_and_content_keying(qapp, tmp_path, hermetic_managers):
    clear_icon_cache()
    assert _get_themed_icon_cached.cache_info().currsize == 0
    icon_file = tmp_path / "icon.png"
    _write_png(icon_file, "#ff0000")

    misses_before = _get_themed_icon_cached.cache_info().misses
    first = get_themed_icon(str(icon_file), True)
    assert not first.isNull()
    assert _get_themed_icon_cached.cache_info().misses == misses_before + 1
    get_themed_icon(str(icon_file), True)  # cache hit
    assert _get_themed_icon_cached.cache_info().misses == misses_before + 1

    _write_png(icon_file, "#0000ff", size=24)  # new content → new key
    get_themed_icon(str(icon_file), True)
    assert _get_themed_icon_cached.cache_info().misses == misses_before + 2

    UiScale.get_instance().set_factor(1.5)  # new scale → new key
    try:
        get_themed_icon(str(icon_file), True)
        assert _get_themed_icon_cached.cache_info().misses == misses_before + 3
    finally:
        UiScale.get_instance().set_factor(1.0)

    clear_icon_cache()
    assert _get_themed_icon_cached.cache_info().currsize == 0


# -- Scale-triggered QSS re-apply -------------------------------------------


def test_scale_change_reapplies_app_qss(qapp, tmp_path, hermetic_managers):
    qss_file = tmp_path / "app.qss"
    qss_file.write_text("QWidget { padding: 10px; color: @accent; }\n")
    tm = hermetic_managers
    tm.register_qss_path(str(qss_file))
    tm.apply_theme_to_app(qapp)
    assert "10px" in (qapp.styleSheet() or "")
    assert "@accent" not in (qapp.styleSheet() or "")

    UiScale.get_instance().set_factor(1.5)
    try:
        qapp.processEvents()
        assert "15px" in (qapp.styleSheet() or "")
    finally:
        UiScale.get_instance().set_factor(1.0)
    qapp.setStyleSheet("")


# -- on_exit_right wiring ----------------------------------------------------


def test_toolbar_rows_section_exit_right(qapp):
    # Plain StrongFocus widgets: native buttons accept the trial Left/Right
    # keypress in _widget_handles, which would consume before the edge.
    row = QWidget()
    row.resize(300, 40)
    left = QWidget(parent=row)
    left.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    left.setGeometry(0, 0, 100, 40)
    right = QWidget(parent=row)
    right.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    right.setGeometry(100, 0, 100, 40)
    row.show()
    qapp.processEvents()

    calls: list[str] = []
    section = ToolbarRowsSection(
        rows_provider=lambda: [row],
        on_exit_right=lambda reason=None: calls.append("right") or True,
    )
    assert section.navigate(int(Qt.Key.Key_Right), right) is True
    assert calls == ["right"]

    plain = ToolbarRowsSection(rows_provider=lambda: [row])
    assert plain.navigate(int(Qt.Key.Key_Right), right) is True  # consumes

    row.deleteLater()
