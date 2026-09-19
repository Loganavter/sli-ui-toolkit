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


def _relative_luminance(color: QColor) -> float:
    def channel(value: int) -> float:
        c = value / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return (
        0.2126 * channel(color.red())
        + 0.7152 * channel(color.green())
        + 0.0722 * channel(color.blue())
    )


def _contrast_ratio(first: QColor, second: QColor) -> float:
    lighter = max(_relative_luminance(first), _relative_luminance(second))
    darker = min(_relative_luminance(first), _relative_luminance(second))
    return (lighter + 0.05) / (darker + 0.05)


@pytest.mark.parametrize("theme_name", ["light", "dark"])
def test_center_line_token_split_and_contrast(themed, qapp, theme_name):
    """``timeline.center.line`` is split per theme and keeps >= 3.0:1
    (component AA) against ``timeline.lane.background`` in both themes."""
    themed.set_theme(theme_name, qapp, await_ripples=False)
    host = _host(themed)
    center = timeline_theme.row_center_line_color(host)
    lane = timeline_theme._timeline_color(themed, "timeline.lane.background")
    assert center.isValid() and lane.isValid()
    assert _contrast_ratio(center, lane) >= 3.0, (theme_name, center, lane)


def test_center_line_light_dark_differ(themed, qapp):
    themed.set_theme("light", qapp, await_ripples=False)
    light = timeline_theme.row_center_line_color(_host(themed))
    themed.set_theme("dark", qapp, await_ripples=False)
    dark = timeline_theme.row_center_line_color(_host(themed))
    assert light != dark
    assert (light.red(), light.green(), light.blue()) == (105, 107, 119)
    assert (dark.red(), dark.green(), dark.blue()) == (190, 190, 196)


@pytest.mark.parametrize("theme_name", ["light", "dark"])
def test_center_line_override_wins(themed, qapp, theme_name):
    themed.set_theme(theme_name, qapp, await_ripples=False)
    host = _host(themed)
    themed.set_color("timeline.center.line", QColor("#445566"))
    assert timeline_theme.row_center_line_color(host) == QColor("#445566")


def test_lane_delegate_hook_resolution_order(themed, qapp):
    """Delegate sits between explicit accent args and kind-token fallback;
    ``None``/invalid/exception fall through (fail-open), default ``None``
    keeps legacy behavior."""
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget.models import (
        TimelineCallbacks,
    )

    themed.set_theme("dark", qapp, await_ripples=False)

    def host_with(delegate):
        return SimpleNamespace(
            theme_manager=themed,
            _callbacks=TimelineCallbacks(lane_value_color=delegate),
        )

    plain = host_with(None)
    legacy = timeline_theme.track_value_color(
        plain, track_id="t", track_kind="float", channel_kind=None, value=1.0
    )
    # Default delegate (None) == legacy fallback.
    assert legacy == timeline_theme.track_color(plain, "float", None)

    # Callable delegate wins over the token fallback.
    hooked = host_with(
        lambda *, track_id, track_kind, channel_kind, value: QColor("#112233")
    )
    assert timeline_theme.track_value_color(
        hooked, track_id="t", track_kind="float", channel_kind=None, value=1.0
    ) == QColor("#112233")

    # Object delegate with a method works too.
    class Delegate:
        def lane_value_color(self, *, track_id, track_kind, channel_kind, value):
            return QColor("#445566")

    obj_host = host_with(Delegate())
    assert timeline_theme.track_value_color(
        obj_host, track_id="t", track_kind="float", channel_kind=None, value=1.0
    ) == QColor("#445566")

    # Explicit accent args win over the delegate.
    assert timeline_theme.track_value_color(
        hooked,
        track_id="t",
        track_kind="float",
        channel_kind=None,
        value=1.0,
        track_accent_color="#ff0000",
    ) == QColor("#ff0000")

    # Fail-open: None / invalid / raising delegates fall back to legacy.
    for bad in (
        lambda **kw: None,
        lambda **kw: "not-a-color!!###",
        SimpleNamespace(),  # no lane_value_color method
    ):
        bad_host = host_with(bad)
        assert timeline_theme.track_value_color(
            bad_host, track_id="t", track_kind="float", channel_kind=None, value=1.0
        ) == timeline_theme.track_color(bad_host, "float", None)

    def _boom(**kw):
        raise RuntimeError("delegate blew up")

    boom_host = host_with(_boom)
    assert timeline_theme.track_value_color(
        boom_host, track_id="t", track_kind="float", channel_kind=None, value=1.0
    ) == timeline_theme.track_color(boom_host, "float", None)


def test_timeline_data_source_protocol_shape():
    """The frozen member shape supervisors wire ``set_data(source=...)`` to."""
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget.models import (
        TimelineDataSource,
    )

    class StubSource:
        snapshots = [1, 2]
        fps = 30
        duration = 2.5
        timeline_model = None

    assert isinstance(StubSource(), TimelineDataSource)

    class MissingDuration:
        snapshots = []
        fps = 30
        timeline_model = None

    assert not isinstance(MissingDuration(), TimelineDataSource)


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


def test_tooltip_resolves_per_widget_callbacks_not_globals(qapp, qtbot):
    """Paint/tooltip i18n must honor the widget's own callbacks.

    Regression: post-C-T construction stopped mirroring callbacks into the
    process globals, but paint still read the globals — tooltips fell back
    to raw keys. Now every paint path goes through ``localize_*_for``.
    """
    from types import SimpleNamespace

    from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
        viewport as timeline_viewport,
    )
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget.models import (
        TimelineCallbacks,
    )
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget.widget import (
        TimelineWidget,
    )

    group = SimpleNamespace(label="G")
    track = SimpleNamespace(id="t", label="T", kind="scalar")
    channel = SimpleNamespace(label="ch", kind="scalar")
    keyframe = SimpleNamespace(timestamp=3.0, value=1.0)

    plain = TimelineWidget()
    qtbot.addWidget(plain)
    hooked = TimelineWidget(
        callbacks=TimelineCallbacks(
            localize_token=lambda token: "TR:" + str(token),
            localize_value=lambda value: "V:" + str(value),
        )
    )
    qtbot.addWidget(hooked)
    try:
        raw = timeline_viewport.tooltip_for_keyframe(
            plain, group, track, channel, keyframe
        )
        assert "TR:" not in raw
        assert "ch" in raw
        routed = timeline_viewport.tooltip_for_keyframe(
            hooked, group, track, channel, keyframe
        )
        assert "TR:ch" in routed
        assert "V:1.0" in routed
    finally:
        plain.close()
        hooked.close()


def _make_data_widget(qapp, qtbot):
    """Real widget with duration>0 and frames>0 for zoom/pps edge tests."""
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget.widget import (
        TimelineWidget,
    )

    widget = TimelineWidget()
    qtbot.addWidget(widget)
    widget.resize(800, 240)
    widget.show()
    widget.set_data(
        [SimpleNamespace(timestamp=0.0), SimpleNamespace(timestamp=10.0)],
        fps=30,
        duration=10.0,
    )
    qapp.processEvents()
    qapp.processEvents()
    widget._layout_settle.cancel()
    widget.fit_view()
    qapp.processEvents()
    return widget


def test_color_override_setters(themed, qapp, qtbot):
    """The five public color setters route through ``_set_color_override``.

    Each setter overrides its ``build_theme_colors`` key; ``None`` reverts
    to the theme value. Calls the setters (widget.py is read-only here —
    no widget edits, coverage only).
    """
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget.widget import (
        TimelineWidget,
    )

    widget = TimelineWidget()
    qtbot.addWidget(widget)
    try:
        cases = [
            ("set_accent_color", "accent"),
            ("set_canvas_background_color", "canvas_bg"),
            ("set_track_background_color", "track_bg"),
            ("set_grid_color", "grid_col"),
            ("set_text_color", "text_col"),
        ]
        for method_name, key in cases:
            themed.set_theme("light", qapp, await_ripples=False)
            baseline = timeline_theme.build_theme_colors(widget)[key]
            assert baseline.isValid()
            getattr(widget, method_name)("#112233")
            assert widget._color_overrides[key] == QColor("#112233")
            assert timeline_theme.build_theme_colors(widget)[key] == QColor(
                "#112233"
            )
            getattr(widget, method_name)(None)
            assert key not in widget._color_overrides
            assert timeline_theme.build_theme_colors(widget)[key] == baseline
        # Direct ``_set_color_override`` path (the setters delegate here).
        widget._set_color_override("accent", QColor("#445566"))
        assert timeline_theme.build_theme_colors(widget)["accent"] == QColor(
            "#445566"
        )
        widget._set_color_override("accent", None)
        assert "accent" not in widget._color_overrides
    finally:
        widget.close()


def test_set_pps_edge_values_clamp_to_min_zoom(themed, qapp, qtbot):
    """``set_pps(0 | negative | NaN)`` never crashes and lands on min zoom."""
    import math

    from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
        viewport as timeline_viewport,
    )

    themed.set_theme("light", qapp, await_ripples=False)
    widget = _make_data_widget(qapp, qtbot)
    try:
        base = timeline_viewport.get_base_pixels_per_second(widget)
        assert base > 0
        min_zoom = timeline_viewport.calculate_min_zoom(widget)
        for bad_pps in (0.0, -50.0, float("nan")):
            widget.set_zoom(1.0)
            widget.set_pps(bad_pps)
            assert math.isfinite(widget._zoom_level), bad_pps
            assert widget._zoom_level == pytest.approx(min_zoom)
            assert widget.get_pixels_per_second() == pytest.approx(
                min_zoom * base
            )
    finally:
        widget.close()


def test_set_zoom_clamp_boundaries(themed, qapp, qtbot):
    """Below-min zooms clamp to min zoom; above-max clamps to 1.0."""
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
        viewport as timeline_viewport,
    )

    themed.set_theme("light", qapp, await_ripples=False)
    widget = _make_data_widget(qapp, qtbot)
    try:
        min_zoom = timeline_viewport.calculate_min_zoom(widget)
        assert 0 < min_zoom < 1.0
        widget.set_zoom(5.0)
        assert widget._zoom_level == pytest.approx(1.0)
        for tiny in (1e-6, min_zoom / 2.0, 0.0):
            widget.set_zoom(1.0)
            widget.set_zoom(tiny)
            assert widget._zoom_level == pytest.approx(min_zoom)
    finally:
        widget.close()


WASH_ALPHA_DEFAULTS = {
    "timeline.group.wash.track.alpha": (22, 46),
    "timeline.group.wash.first.alpha": (18, 42),
    "timeline.group.wash.channel.alpha": (10, 24),
    "timeline.ruler.minor.tick.alpha": (180, 150),
}


@pytest.mark.parametrize("theme_name", ["light", "dark"])
@pytest.mark.parametrize("token", sorted(WASH_ALPHA_DEFAULTS))
def test_wash_alpha_token_defaults_and_override(themed, qapp, token, theme_name):
    """Promoted wash tokens resolve per-theme defaults; host override wins.

    Defaults are the exact pre-refactor per-theme strengths (paints stay
    pixel-identical); a host-registered token alpha wins in both themes.
    Cross-checks ``render._wash_alpha`` (read-only import) against the
    canonical ``theme.timeline_alpha`` on both paths.
    """
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
        render as timeline_render,
    )

    themed.set_theme(theme_name, qapp, await_ripples=False)
    light_default, dark_default = WASH_ALPHA_DEFAULTS[token]
    expected = dark_default if theme_name == "dark" else light_default
    assert timeline_theme.timeline_alpha(themed, token) == expected
    assert timeline_render._wash_alpha(themed, token) == expected
    themed.set_color(token, QColor(0, 0, 0, 77))
    assert timeline_theme.timeline_alpha(themed, token) == 77
    assert timeline_render._wash_alpha(themed, token) == 77


@pytest.mark.parametrize("theme_name", ["light", "dark"])
def test_wash_strengths_compose_valid_colors(themed, qapp, theme_name):
    """Wash alphas are strengths, not colors: no WCAG pair applies.

    The applicable assertion is that every promoted strength composes a
    valid, base-distinct accent wash in both themes (fail-closed on a
    transparent/degenerate wash), and the ruler minor-tick alpha composes
    a valid tick color from the grid token.
    """
    from PySide6.QtGui import QColor

    themed.set_theme(theme_name, qapp, await_ripples=False)
    host = _host(themed)
    track_bg = timeline_theme._timeline_color(themed, "timeline.track.background")
    gutter_bg = timeline_theme._timeline_color(themed, "timeline.gutter.background")
    grid_col = timeline_theme._timeline_color(themed, "timeline.grid.color")
    assert track_bg.isValid() and gutter_bg.isValid() and grid_col.isValid()
    group = SimpleNamespace(accent_color=None, tracks={})
    for token, base in (
        ("timeline.group.wash.track.alpha", track_bg),
        ("timeline.group.wash.first.alpha", track_bg),
        ("timeline.group.wash.channel.alpha", gutter_bg),
    ):
        strength = timeline_theme.timeline_alpha(themed, token)
        assert 0 < strength < 255, (token, strength)
        washed = timeline_theme.group_content_bg(host, base, group, strength)
        assert isinstance(washed, QColor) and washed.isValid()
        assert washed != base, (token, theme_name)
    tick_strength = timeline_theme.timeline_alpha(
        themed, "timeline.ruler.minor.tick.alpha"
    )
    assert 0 < tick_strength < 255
    tick_col = QColor(grid_col)
    tick_col.setAlpha(tick_strength)
    assert tick_col.isValid() and tick_col.alpha() == tick_strength
