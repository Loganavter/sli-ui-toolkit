"""Timeline colors resolve through ThemeManager ``timeline.*`` tokens.

Regression: ``build_theme_colors`` used per-``is_dark`` hardcoded ``QColor``
branches, and call sites (keyframe dot outline, playhead halo, track kind
colors, accent-wash alphas) never consulted the palette. Every color now
goes through ``try_get_color`` on a ``timeline.*`` token with a per-theme
hardcoded fallback, so hosts can override any of them via
``register_palettes`` and light/dark both resolve without hardcoded
branches in the paint path.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtGui import QColor

from sli_ui_toolkit import FLUENT_DARK, FLUENT_LIGHT, ThemeManager
from sli_ui_toolkit.ui.widgets.composite.timeline_widget import theme as timeline_theme

WIDGET_DIR = Path(__file__).resolve().parent.parent / (
    "src/sli_ui_toolkit/ui/widgets/composite/timeline_widget"
)

EXPECTED_KEYS = (
    "is_dark",
    "accent",
    "text_col",
    "canvas_bg",
    "gutter_bg",
    "group_bg",
    "track_bg",
    "lane_bg",
    "grid_col",
    "footer_bg",
    "sep_strong",
    "sep_soft",
    "sb_idle",
    "sb_hover",
)


@pytest.fixture()
def themed(qapp):
    tm = ThemeManager.get_instance()
    tm.register_palettes(FLUENT_LIGHT, FLUENT_DARK)
    tm.set_theme("light", qapp, await_ripples=False)
    try:
        yield tm
    finally:
        tm.register_palettes(FLUENT_LIGHT, FLUENT_DARK)
        tm.set_theme("light", qapp, await_ripples=False)


def _host(theme_manager) -> SimpleNamespace:
    return SimpleNamespace(theme_manager=theme_manager)


@pytest.mark.parametrize("theme_name", ["light", "dark"])
def test_build_theme_colors_resolves_both_themes(themed, qapp, theme_name):
    themed.set_theme(theme_name, qapp, await_ripples=False)
    colors = timeline_theme.build_theme_colors(_host(themed))
    assert tuple(colors) == EXPECTED_KEYS
    assert colors["is_dark"] == (theme_name == "dark")
    for key, value in colors.items():
        if key == "is_dark":
            continue
        assert isinstance(value, QColor) and value.isValid(), key


def test_build_theme_colors_differs_per_theme(themed, qapp):
    themed.set_theme("light", qapp, await_ripples=False)
    light = timeline_theme.build_theme_colors(_host(themed))
    themed.set_theme("dark", qapp, await_ripples=False)
    dark = timeline_theme.build_theme_colors(_host(themed))
    for key in ("gutter_bg", "group_bg", "lane_bg", "footer_bg", "sep_soft"):
        assert light[key] != dark[key], key


@pytest.mark.parametrize("theme_name", ["light", "dark"])
def test_timeline_token_override_wins_over_fallback(themed, qapp, theme_name):
    themed.set_theme(theme_name, qapp, await_ripples=False)
    host = _host(themed)
    before = timeline_theme.build_theme_colors(host)["gutter_bg"]
    themed.set_color("timeline.gutter.background", QColor("#123456"))
    after = timeline_theme.build_theme_colors(host)["gutter_bg"]
    assert after == QColor("#123456")
    assert after != before


@pytest.mark.parametrize(
    ("kind", "token", "default"),
    [
        ("bool", "timeline.track.bool", QColor(0, 140, 198)),
        ("enum", "timeline.track.enum", QColor(180, 88, 28)),
        ("state", "timeline.track.state", QColor(100, 100, 116)),
        ("vec2", "timeline.track.vec2", QColor(34, 140, 94)),
    ],
)
def test_track_kind_colors_tokenized(themed, qapp, kind, token, default):
    themed.set_theme("dark", qapp, await_ripples=False)
    host = _host(themed)
    assert timeline_theme.track_color(host, kind) == default
    assert timeline_theme.track_color(host, "float", kind) == default
    # Same signature/behavior as before for the public alias.
    assert (
        timeline_theme.track_line_color(host, "t1", kind)
        == timeline_theme.track_color(host, kind)
    )
    themed.set_color(token, QColor("#abcdef"))
    assert timeline_theme.track_color(host, kind) == QColor("#abcdef")


def test_outlines_and_alphas_tokenized(themed, qapp):
    themed.set_theme("dark", qapp, await_ripples=False)
    host = _host(themed)
    assert timeline_theme.keyframe_outline_color(host) == QColor(40, 40, 46)
    assert timeline_theme.playhead_outline_color(host) == QColor(0, 0, 0, 90)
    themed.set_color("timeline.keyframe.outline", QColor("#010203"))
    assert timeline_theme.keyframe_outline_color(host) == QColor("#010203")
    # Alpha tokens keep distinct per-theme defaults and stay in range.
    themed.set_theme("light", qapp, await_ripples=False)
    light_alpha = timeline_theme.timeline_alpha(
        themed, "timeline.gutter.wash.top.alpha"
    )
    themed.set_theme("dark", qapp, await_ripples=False)
    dark_alpha = timeline_theme.timeline_alpha(
        themed, "timeline.gutter.wash.top.alpha"
    )
    assert (light_alpha, dark_alpha) == (18, 26)
    for token in timeline_theme.TIMELINE_TOKENS:
        if not token.endswith(".alpha"):
            continue
        value = timeline_theme.timeline_alpha(themed, token)
        assert 0 <= value <= 255, token


def test_no_hardcoded_theme_branches_in_paint_path():
    """No ``is_dark`` branches and no numeric ``QColor(...)`` literals
    outside the central defaults table in theme.py; none at all in
    primitives.py / segments.py (transparent ``QColor(0, 0, 0, 0)`` and
    copies of live colors excepted)."""
    theme_src = (WIDGET_DIR / "theme.py").read_text()
    code_lines = [
        line for line in theme_src.splitlines() if not line.lstrip().startswith("#")
    ]
    assert not re.search(r"(?m)^\s*if\b.*is_dark", "\n".join(code_lines))
    literals = [
        line.strip()
        for line in theme_src.splitlines()
        if re.search(r"QColor\(\d", line)
    ]
    assert literals, "defaults table must hold the fallbacks"
    assert all(
        "_TIMELINE_TOKEN_DEFAULTS" in line or line.lstrip().startswith('"timeline.')
        for line in literals
    ), literals
    for name in ("primitives.py", "segments.py"):
        src = (WIDGET_DIR / name).read_text()
        assert "is_dark" not in src, name
        bad = [
            line.strip()
            for line in src.splitlines()
            if re.search(r"QColor\(\d", line)
            and "QColor(0, 0, 0, 0)" not in line
        ]
        assert bad == [], (name, bad)


def test_timeline_renders_light_and_dark(themed, qapp, qtbot):
    """A real widget paints without error under both palettes (smoke)."""
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QWidget

    from sli_ui_toolkit.ui.widgets.composite.timeline_widget.widget import (
        TimelineWidget,
    )

    widget = TimelineWidget()
    qtbot.addWidget(widget)
    widget.resize(400, 300)
    widget.show()
    qtbot.waitExposed(widget)
    images = []
    for theme_name in ("light", "dark"):
        themed.set_theme(theme_name, qapp, await_ripples=False)
        qtbot.wait(50)
        image = QImage(widget.size(), QImage.Format.Format_ARGB32)
        widget.render(image)
        assert not image.isNull()
        images.append(image)
    assert images[0] != images[1]
    assert isinstance(widget.parent(), (QWidget, type(None)))
