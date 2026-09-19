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


# --- Phase 2 T-life: show/teardown symmetry -----------------------------------
#
# Teardown drops every install/connect; show restores them, so a reopened
# (or second) dialog keeps tooltips, easing, inner-scrollbar paints, and
# scale response. Filter installs pair exactly with removes.


def _life_snaps(n=8):
    return [SimpleNamespace(timestamp=float(i)) for i in range(n)]


def test_close_then_show_restores_transient_signals(qapp, qtbot, monkeypatch):
    """Teardown disconnects the four __init__ connections; show rebinds them.

    Behavioral proof (not flag inspection): after teardown each emit is
    silent; after ``show_event`` each emit reaches the slot again.
    """
    from sli_ui_toolkit.ui.managers.ui_scale import UiScale
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
        interaction as timeline_interaction,
    )
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget.widget import (
        TimelineWidget,
    )
    from PySide6.QtCore import QVariantAnimation

    tooltip_calls: list = []
    playhead_calls: list = []
    scale_calls: list = []
    monkeypatch.setattr(
        TimelineWidget, "_show_hover_tooltip", lambda self: tooltip_calls.append(1)
    )
    monkeypatch.setattr(
        TimelineWidget, "_on_playhead_frame", lambda self, v: playhead_calls.append(v)
    )
    monkeypatch.setattr(
        TimelineWidget, "_on_scale_changed", lambda self, f: scale_calls.append(f)
    )
    widget = TimelineWidget(snapshots=_life_snaps())
    qtbot.addWidget(widget)
    widget.resize(800, 240)
    widget.show()
    qtbot.waitExposed(widget)
    try:
        assert widget._transient_bound is True
        timeline_interaction.teardown_widget(widget)
        assert widget._transient_bound is False
        widget._tooltip_timer.timeout.emit()
        widget._playhead_anim.valueChanged.emit(5.5)
        UiScale.get_instance().scale_changed.emit(1.0)
        qapp.processEvents()
        assert tooltip_calls == [] and playhead_calls == [] and scale_calls == []
        # Reopen: the show half restores every dropped connection and
        # revives the destroyed gate.
        timeline_interaction.show_event(widget)
        assert widget._transient_bound is True
        assert widget._destroyed is False
        widget._tooltip_timer.timeout.emit()
        widget._playhead_anim.valueChanged.emit(5.5)
        UiScale.get_instance().scale_changed.emit(1.0)
        qapp.processEvents()
        assert tooltip_calls == [1]
        assert playhead_calls == [5.5]
        assert scale_calls == [1.0]
        # Live easing still starts post-restore (no dead animation).
        widget._total_frames = 50
        widget._visual_index = 5.0
        widget._current_index = 5
        widget.set_current_frame(6)
        assert widget._playhead_anim.state() == QVariantAnimation.State.Running
    finally:
        widget.close()


def test_second_dialog_alive_with_tooltips_easing_scale(qapp, qtbot, monkeypatch):
    """A second dialog after close keeps tooltips/easing/scale (fresh wiring)."""
    from PySide6.QtGui import QPixmap
    from PySide6.QtCore import QVariantAnimation
    from sli_ui_toolkit.ui.managers.ui_scale import UiScale
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget.widget import (
        TimelineWidget,
    )

    first = TimelineWidget(snapshots=_life_snaps())
    qtbot.addWidget(first)
    first.show()
    qtbot.waitExposed(first)
    first.close()
    qapp.processEvents()

    scale_calls: list = []
    monkeypatch.setattr(
        TimelineWidget, "_on_scale_changed", lambda self, f: scale_calls.append(f)
    )
    second = TimelineWidget(snapshots=_life_snaps())
    qtbot.addWidget(second)
    second.resize(800, 240)
    second.show()
    qtbot.waitExposed(second)
    try:
        # Scale singleton reaches the new dialog.
        UiScale.get_instance().scale_changed.emit(1.0)
        qapp.processEvents()
        assert scale_calls == [1.0]
        # Easing runs on the new dialog.
        second._total_frames = 50
        second._visual_index = 5.0
        second._current_index = 5
        second.set_current_frame(6)
        assert second._playhead_anim.state() == QVariantAnimation.State.Running
        # Tooltip timer wired: hover over a populated hit-set starts it.
        px = QPixmap(16, 9)
        second.set_thumbnails({i: px for i in range(0, 8)})
        second._hover_tooltip_text = "probe"
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtCore import QEvent, QPointF
        from PySide6.QtCore import Qt
        second._tooltip_timer.stop()
        event = QMouseEvent(
            QEvent.Type.MouseMove,
            QPointF(400.0, 100.0),
            Qt.MouseButton.NoButton,
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        second.mouseMoveEvent(event)
        assert second._tooltip_timer.interval() == 350
    finally:
        second.close()


def test_filter_install_remove_pairing(qapp, qtbot):
    """Every install pairs with a remove; rebinds never accumulate."""
    from PySide6.QtCore import QObject
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
        interaction as timeline_interaction,
    )
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget.widget import (
        TimelineWidget,
    )

    widget = TimelineWidget()
    qtbot.addWidget(widget)
    try:
        first, second = QObject(), QObject()
        timeline_interaction.install_filter_once(widget, first)
        timeline_interaction.install_filter_once(widget, first)
        assert len([t for t in widget._filter_targets if t is first]) == 1
        timeline_interaction.install_filter_once(widget, second)
        assert len(widget._filter_targets) == 2
        timeline_interaction.install_filter_once(widget, None)
        assert len(widget._filter_targets) == 2
        timeline_interaction.remove_installed_filters(widget)
        assert widget._filter_targets == []
        # Idempotent: second removal is a no-op, reinstall works.
        timeline_interaction.remove_installed_filters(widget)
        timeline_interaction.install_filter_once(widget, first)
        assert widget._filter_targets == [first]
        timeline_interaction.remove_installed_filters(widget)
        assert widget._filter_targets == []
    finally:
        widget.close()


def test_host_change_forgets_dead_viewport(qapp, qtbot):
    """Reparenting onto a new scroll area drops the old viewport filter."""
    from PySide6.QtWidgets import QScrollArea
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
        interaction as timeline_interaction,
    )
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget.widget import (
        TimelineWidget,
    )

    area_a = QScrollArea()
    area_b = QScrollArea()
    qtbot.addWidget(area_a)
    qtbot.addWidget(area_b)
    widget = TimelineWidget(snapshots=_life_snaps())
    try:
        area_a.setWidget(widget)
        area_a.resize(800, 240)
        area_a.show()
        qapp.processEvents()
        qapp.processEvents()
        timeline_interaction.bind_host_scrollbar(widget)
        first_viewport = widget._host_viewport
        assert first_viewport is not None
        assert first_viewport in widget._filter_targets
        # Reparent: the widget now lives under area_b.
        widget.setParent(None)
        area_b.setWidget(widget)
        area_b.resize(800, 240)
        area_b.show()
        qapp.processEvents()
        qapp.processEvents()
        timeline_interaction.bind_host_scrollbar(widget)
        assert widget._host_viewport is not None
        assert widget._host_viewport is not first_viewport
        assert first_viewport not in widget._filter_targets
        # Exactly one viewport filter (no accumulation across hosts).
        viewports = [t for t in widget._filter_targets if t is widget._host_viewport]
        assert len(viewports) == 1
    finally:
        widget.close()
        area_a.close()
        area_b.close()


def test_destroyed_gates_no_emit_no_update_no_anim(qapp, qtbot):
    """commit/set_current/playhead/ingest/thumbs honor teardown like settle."""
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
        interaction as timeline_interaction,
    )
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget.widget import (
        TimelineWidget,
    )
    from PySide6.QtCore import QVariantAnimation

    widget = TimelineWidget(snapshots=_life_snaps())
    qtbot.addWidget(widget)
    widget._total_frames = 50
    widget._commitState(widget._current_state(), source="test")
    widget.close()
    qapp.processEvents()
    fired: list = []
    widget.zoomChanged.connect(lambda v: fired.append(v))
    widget.viewportChanged.connect(lambda: fired.append(None))
    widget.viewportChangedState.connect(fired.append)
    # Commit gate: silent False, no state write.
    zoom_before = widget._zoom_level
    assert widget._commitState(widget._current_state(), source="probe") is False
    assert fired == []
    assert widget._zoom_level == zoom_before
    # Playhead gate: index/visual frozen, animation never starts.
    assert widget._current_index == 0
    widget.set_current_frame(20)
    assert widget._current_index == 0
    assert widget._playhead_anim.state() != widget._playhead_anim.State.Running
    visual_before = widget._visual_index
    timeline_interaction.playhead_frame(widget, 42.0)
    assert widget._visual_index == visual_before
    # Ingest gate: snapshots/fps/frames untouched, no settle ping crash.
    snaps_before = list(widget._snapshots)
    fps_before = widget._fps
    widget.set_data(_life_snaps(3), fps=24)
    assert list(widget._snapshots) == snaps_before
    assert widget._fps == fps_before
    # Thumbnail gates: store untouched, no update() on a dead widget.
    thumbs_before = dict(widget._thumbnails)
    from PySide6.QtGui import QPixmap
    widget.set_thumbnails({1: QPixmap(16, 9)})
    widget.add_thumbnail(2, QPixmap(16, 9))
    assert dict(widget._thumbnails) == thumbs_before


def test_event_filter_true_without_commit(qapp, qtbot):
    """Handled filter events return True and never commit synchronously."""
    from PySide6.QtCore import QSize
    from PySide6.QtGui import QResizeEvent
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
        interaction as timeline_interaction,
    )
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget.widget import (
        TimelineWidget,
    )

    widget = TimelineWidget(snapshots=_life_snaps())
    qtbot.addWidget(widget)
    widget.resize(800, 240)
    widget.show()
    qtbot.waitExposed(widget)
    try:
        commits: list = []
        original = TimelineWidget._commitState
        widget._commitState = lambda nxt, source="": (
            commits.append(source), False,
        )[1]
        try:
            event = QResizeEvent(QSize(800, 240), QSize(700, 240))
            assert timeline_interaction.event_filter(widget, widget.window(), event) is True
            assert widget.eventFilter(widget.window(), event) is True
            assert commits == []
            # Unrelated objects/events fall through unhandled.
            from PySide6.QtCore import QObject, QEvent
            assert timeline_interaction.event_filter(widget, QObject(), QEvent(QEvent.Type.User)) is False
        finally:
            widget._commitState = original.__get__(widget, TimelineWidget)
        # Destroyed widgets never handle.
        widget.close()
        assert timeline_interaction.event_filter(widget, widget.window(), event) is False
    finally:
        try:
            widget.close()
        except Exception:
            pass


def test_prune_then_placeholder(qapp, qtbot):
    """Evicted reps miss exact-match (placeholder); visible reps hit."""
    from PySide6.QtGui import QPixmap
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
        interaction as timeline_interaction,
    )
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
        viewport as timeline_viewport,
    )
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget.widget import (
        TimelineWidget,
    )

    snaps = [SimpleNamespace(timestamp=float(i)) for i in range(101)]
    widget = TimelineWidget(snapshots=snaps)
    qtbot.addWidget(widget)
    widget.resize(800, 240)
    widget.show()
    qapp.processEvents()
    widget._layout_settle.cancel()
    widget.fit_view()
    widget._commitState(widget._current_state(), source="test")
    widget._commitState(widget._current_state().with_zoom(1.0), source="test")
    try:
        visible = widget.get_visible_thumbnail_frame_indices(overscan_blocks=1)
        assert visible and len(visible) <= 12
        px = QPixmap(16, 9)
        far = [i for i in range(0, widget._total_frames, 37) if i not in visible]
        assert far, "need off-window inserts for the eviction probe"
        for i in far + [v for v in visible if v not in far]:
            widget.add_thumbnail(i, px)
        for v in visible:
            assert timeline_viewport.thumbnail_for_rep(widget, v) is not None
        for i in far:
            if i not in widget._thumbnails:
                # Evicted: exact-match misses → render draws the placeholder.
                assert timeline_viewport.thumbnail_for_rep(widget, i) is None
        assert len(widget._thumbnails) <= timeline_interaction._THUMBNAIL_HARD_CAP
    finally:
        widget.close()


def test_prune_batch_stays_linear_and_exact(qapp, qtbot, monkeypatch):
    """Bulk streams prune in O(1) amortized per insert with identical results."""
    from PySide6.QtGui import QPixmap
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
        interaction as timeline_interaction,
    )
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget.widget import (
        TimelineWidget,
    )

    snaps = [SimpleNamespace(timestamp=float(i)) for i in range(101)]
    widget = TimelineWidget(snapshots=snaps)
    qtbot.addWidget(widget)
    widget.resize(800, 240)
    widget.show()
    qapp.processEvents()
    widget._layout_settle.cancel()
    widget.fit_view()
    widget._commitState(widget._current_state(), source="test")
    widget._commitState(widget._current_state().with_zoom(1.0), source="test")
    try:
        full_passes: list = []
        original_interval = timeline_interaction._prune_keep_interval

        def counting_interval(w):
            full_passes.append(1)
            return original_interval(w)

        monkeypatch.setattr(
            timeline_interaction, "_prune_keep_interval", counting_interval
        )
        px = QPixmap(16, 9)
        for i in range(0, widget._total_frames):
            widget.add_thumbnail(i, px)
        # One full pass to establish the window; the stream resolves inline.
        assert len(full_passes) <= 3, full_passes
        assert widget._prune_keep_cache is not None
        visible = widget.get_visible_thumbnail_frame_indices(overscan_blocks=1)
        for v in visible:
            assert v in widget._thumbnails
        # Every survivor sits inside the keep-interval (no over-retention).
        interval = original_interval(widget)
        assert interval is not None
        lo, hi = interval
        assert all(lo <= i <= hi for i in widget._thumbnails)
    finally:
        widget.close()


def test_scroll_round_trip_no_thrash(qapp, qtbot):
    """Scrollbar forth/back lands on identical state with bounded commits."""
    from PySide6.QtWidgets import QScrollArea
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget.widget import (
        TimelineWidget,
    )

    widget = TimelineWidget(snapshots=_life_snaps(20))
    area = QScrollArea()
    qtbot.addWidget(area)
    area.setWidget(widget)
    area.resize(800, 240)
    area.show()
    qapp.processEvents()
    qapp.processEvents()
    widget._layout_settle.cancel()
    widget.fit_view()
    widget.set_zoom(1.0)
    qapp.processEvents()
    bar = area.horizontalScrollBar()
    try:
        assert bar.maximum() > bar.minimum()
        commits: list = []
        original = TimelineWidget._commitState

        def counting(self, nxt, source=""):
            commits.append(source)
            return original(self, nxt, source)

        widget._commitState = counting.__get__(widget, TimelineWidget)
        try:
            widget._refresh_viewport_state()
            home = widget._state.scroll_x
            bar.setValue(bar.maximum())
            qapp.processEvents()
            assert widget._state.scroll_x == bar.value()
            bar.setValue(bar.minimum())
            qapp.processEvents()
            assert widget._state.scroll_x == home
            # Forth + back: at most one commit per real step, none for rest.
            assert len(commits) <= 4, commits
            settled = len(commits)
            bar.setValue(bar.value())  # no-op step stays silent
            qapp.processEvents()
            assert len(commits) == settled
        finally:
            widget._commitState = original.__get__(widget, TimelineWidget)
    finally:
        widget.close()
        area.close()


def test_explicit_freeze_refreezes_in_place_swaps(qapp, qtbot):
    """HANDOFF-1: same-length in-place snapshot swaps re-freeze the aspect."""
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget import (
        viewport as timeline_viewport,
    )
    from sli_ui_toolkit.ui.widgets.composite.timeline_widget.widget import (
        TimelineWidget,
    )

    snaps = [SimpleNamespace(timestamp=float(i), width=640, height=480) for i in range(5)]
    widget = TimelineWidget()
    qtbot.addWidget(widget)
    try:
        widget.set_data(snaps, fps=30)
        widget._layout_settle.cancel()
        assert timeline_viewport.frozen_thumb_aspect(widget) == 640 / 480
        # Same list object, same length, new content (in-place swap): the
        # best-effort key is unchanged, but ingest re-freezes explicitly.
        for snap in snaps:
            snap.width, snap.height = 1920, 1080
        widget.set_data(snaps, fps=30)
        widget._layout_settle.cancel()
        assert timeline_viewport.frozen_thumb_aspect(widget) == 1920 / 1080
        frozen = widget._frozen_thumb_aspect
        assert isinstance(frozen, tuple) and len(frozen) == 2
        assert frozen[1] == 1920 / 1080
    finally:
        widget.close()


def test_track_stubs_diverged_per_theme(themed, qapp):
    """Former light==dark stubs now resolve per theme (center line as is)."""
    light_values = {}
    dark_values = {}
    themed.set_theme("light", qapp, await_ripples=False)
    for token in (
        "timeline.track.bool",
        "timeline.track.enum",
        "timeline.track.state",
        "timeline.track.vec2",
        "timeline.keyframe.outline",
        "timeline.playhead.outline",
        "timeline.separator.row",
    ):
        light_values[token] = timeline_theme._timeline_color(themed, token)
    themed.set_theme("dark", qapp, await_ripples=False)
    for token in (
        "timeline.track.bool",
        "timeline.track.enum",
        "timeline.track.state",
        "timeline.track.vec2",
        "timeline.keyframe.outline",
        "timeline.playhead.outline",
        "timeline.separator.row",
    ):
        dark_values[token] = timeline_theme._timeline_color(themed, token)
    for token in light_values:
        assert light_values[token].isValid() and dark_values[token].isValid()
        assert light_values[token] != dark_values[token], token
    # Dark values stay pinned (existing contract); light values are the
    # darkened same-hue variants (contrast-checked in the theme module).
    assert dark_values["timeline.track.bool"] == QColor(0, 140, 198)
    assert dark_values["timeline.separator.row"] == QColor(120, 120, 128)


# --- Phase 3 polish: strip-chrome split tokens + contrast ----------------------
#
# (d): every strip/gutter/separator/playhead chrome token resolves
# per-theme (no unjustified light==dark stub remains — the split
# center-line token stays pinned by the tests above). Contrast follows
# DESIGN_LANGUAGE: component chrome is pairwise distinct per theme and
# the playhead accent keeps >= 3.0:1 against the lane surface.

_STRIP_CHROME_TOKENS = (
    "timeline.gutter.background",
    "timeline.group.background",
    "timeline.track.background",
    "timeline.lane.background",
    "timeline.grid.color",
    "timeline.footer.background",
    "timeline.separator.strong",
    "timeline.separator.soft",
    "timeline.scrollbar.idle",
    "timeline.scrollbar.hover",
    "timeline.playhead.outline",
)


@pytest.mark.parametrize("token", _STRIP_CHROME_TOKENS)
@pytest.mark.parametrize("theme_name", ["light", "dark"])
def test_strip_chrome_token_resolves_valid(themed, qapp, token, theme_name):
    themed.set_theme(theme_name, qapp, await_ripples=False)
    color = timeline_theme._timeline_color(themed, token)
    assert color.isValid(), (token, theme_name)


@pytest.mark.parametrize("token", _STRIP_CHROME_TOKENS)
def test_strip_chrome_token_split_per_theme(themed, qapp, token):
    """No unjustified light==dark chrome stub remains (center line aside,
    pinned separately and untouched by this wave)."""
    themed.set_theme("light", qapp, await_ripples=False)
    light = timeline_theme._timeline_color(themed, token)
    themed.set_theme("dark", qapp, await_ripples=False)
    dark = timeline_theme._timeline_color(themed, token)
    assert light != dark, token


@pytest.mark.parametrize("theme_name", ["light", "dark"])
def test_strip_surfaces_pairwise_distinct(themed, qapp, theme_name):
    """Gutter / track / lane / footer surfaces differ within each theme."""
    themed.set_theme(theme_name, qapp, await_ripples=False)
    surfaces = {
        token: timeline_theme._timeline_color(themed, token)
        for token in (
            "timeline.gutter.background",
            "timeline.track.background",
            "timeline.lane.background",
            "timeline.footer.background",
        )
    }
    rgbs = [color.rgb() for color in surfaces.values()]
    assert len(set(rgbs)) == len(rgbs), (theme_name, surfaces)


@pytest.mark.parametrize("theme_name", ["light", "dark"])
def test_playhead_accent_contrast_on_lane(themed, qapp, theme_name):
    """The playhead accent keeps >= 3.0:1 (component AA) against the lane."""
    themed.set_theme(theme_name, qapp, await_ripples=False)
    accent = themed.get_color("accent")
    lane = timeline_theme._timeline_color(themed, "timeline.lane.background")
    assert accent.isValid() and lane.isValid()
    assert _contrast_ratio(accent, lane) >= 3.0, (theme_name, accent, lane)
