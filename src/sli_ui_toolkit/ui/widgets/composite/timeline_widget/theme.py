from __future__ import annotations

from typing import Any

from PySide6.QtGui import QColor

# Timeline token defaults: ``token -> (light, dark)`` fallback QColors.
#
# Every color the timeline paints is resolved through ``ThemeManager`` first
# (``try_get_color`` on the ``timeline.*`` token, then on the legacy shared
# token where one exists) and falls back to this table. Hosts override any
# entry by registering a palette containing the ``timeline.*`` key — no
# per-theme ``if is_dark`` hardcoded branches remain in the paint path.
_TIMELINE_TOKEN_DEFAULTS: dict[str, tuple[QColor, QColor]] = {
    "timeline.gutter.background": (QColor(244, 244, 246), QColor(42, 42, 46)),
    "timeline.group.background": (QColor(250, 250, 252), QColor(46, 46, 50)),
    "timeline.track.background": (QColor(242, 243, 246), QColor(80, 80, 80)),
    "timeline.lane.background": (QColor(232, 233, 238), QColor(50, 50, 55)),
    "timeline.grid.color": (QColor(220, 220, 225), QColor(79, 79, 79)),
    "timeline.footer.background": (QColor(236, 238, 242), QColor(38, 38, 42)),
    "timeline.separator.strong": (QColor(188, 192, 200), QColor(85, 85, 85)),
    "timeline.separator.soft": (QColor(218, 220, 226), QColor(55, 55, 60)),
    "timeline.separator.row": (QColor(210, 210, 214), QColor(210, 210, 214)),
    # Center line is split per theme so it keeps >= 3.0:1 (component AA,
    # DESIGN_LANGUAGE contrast targets) against lane_bg in BOTH themes:
    # light (105,107,119) vs lane_bg (232,233,238) = 4.36:1;
    # dark (190,190,196) vs lane_bg (50,50,55) = 6.89:1.
    # (The old single value (190,190,196) was 1.53:1 on light — invisible.)
    "timeline.center.line": (QColor(105, 107, 119), QColor(190, 190, 196)),
    "timeline.scrollbar.idle": (QColor(0, 0, 0, 65), QColor(255, 255, 255, 55)),
    "timeline.scrollbar.hover": (QColor(0, 0, 0, 95), QColor(255, 255, 255, 85)),
    "timeline.track.bool": (QColor(0, 140, 198), QColor(0, 140, 198)),
    "timeline.track.enum": (QColor(180, 88, 28), QColor(180, 88, 28)),
    "timeline.track.state": (QColor(100, 100, 116), QColor(100, 100, 116)),
    "timeline.track.vec2": (QColor(34, 140, 94), QColor(34, 140, 94)),
    "timeline.keyframe.outline": (QColor(40, 40, 46), QColor(40, 40, 46)),
    "timeline.playhead.outline": (QColor(0, 0, 0, 90), QColor(0, 0, 0, 90)),
}

# Tokens that already have a shared-palette equivalent: the timeline token
# wins, the shared token is the middle of the fallback chain, the table
# above is the last resort.
_TIMELINE_TOKEN_FALLBACKS: dict[str, str] = {
    "timeline.track.background": "AlternateBase",
    "timeline.grid.color": "separator.color",
    "timeline.separator.strong": "dialog.border",
}

# Accent-wash alphas: ``token -> (light, dark)``. A host overrides one by
# registering the token as a QColor whose alpha channel carries the value;
# otherwise the per-theme default below applies. This keeps the paint call
# sites free of ``is_dark`` branches while preserving the tuned per-theme
# translucency.
_TIMELINE_ALPHA_DEFAULTS: dict[str, tuple[int, int]] = {
    "timeline.gutter.wash.top.alpha": (18, 26),
    "timeline.gutter.wash.bottom.alpha": (4, 8),
    "timeline.gutter.edge.alpha": (14, 22),
    "timeline.group.header.start.alpha": (52, 70),
    "timeline.group.header.end.alpha": (18, 12),
    "timeline.scrollbar.track.alpha": (235, 190),
}

#: All ``timeline.*`` color tokens introduced here (handoff reference for
#: render.py / viewport.py call sites owned by the parallel Phase A work,
#: and for the inspector ``token_family`` extension in widget.py).
TIMELINE_TOKENS: tuple[str, ...] = tuple(_TIMELINE_TOKEN_DEFAULTS) + tuple(
    _TIMELINE_ALPHA_DEFAULTS
)


def _timeline_color(tm, token: str) -> QColor:
    """Resolve *token* via ``try_get_color`` with palette fallback.

    Chain: ``timeline.*`` token → legacy shared token (where mapped) →
    per-theme hardcoded default from ``_TIMELINE_TOKEN_DEFAULTS``.
    """
    hit = tm.try_get_color(token)
    if hit is not None:
        return QColor(hit)
    fallback_token = _TIMELINE_TOKEN_FALLBACKS.get(token)
    if fallback_token is not None:
        hit = tm.try_get_color(fallback_token)
        if hit is not None:
            return QColor(hit)
    light, dark = _TIMELINE_TOKEN_DEFAULTS[token]
    return QColor(dark) if tm.is_dark() else QColor(light)


def timeline_alpha(tm, token: str) -> int:
    """Resolve an accent-wash alpha token (see ``_TIMELINE_ALPHA_DEFAULTS``)."""
    light, dark = _TIMELINE_ALPHA_DEFAULTS[token]
    hit = tm.try_get_color(token)
    if hit is not None:
        return max(0, min(255, hit.alpha()))
    return dark if tm.is_dark() else light


def keyframe_outline_color(widget) -> QColor:
    """Outline for keyframe dots (handoff helper for segments.py)."""
    return _timeline_color(widget.theme_manager, "timeline.keyframe.outline")


def playhead_outline_color(widget) -> QColor:
    """Dark halo under the playhead line (handoff helper for primitives.py)."""
    return _timeline_color(widget.theme_manager, "timeline.playhead.outline")


def row_separator_color(widget) -> QColor:
    """Row bottom rule (integration helper for render.py draw_rows)."""
    return _timeline_color(widget.theme_manager, "timeline.separator.row")


def row_center_line_color(widget) -> QColor:
    """Lane center line (integration helper for render.py draw_rows)."""
    return _timeline_color(widget.theme_manager, "timeline.center.line")


def scrollbar_idle_color(widget) -> QColor:
    """Scrollbar handle idle fill (integration helper for viewport.py)."""
    return _timeline_color(widget.theme_manager, "timeline.scrollbar.idle")


def scrollbar_hover_color(widget) -> QColor:
    """Scrollbar handle hover fill (integration helper for viewport.py)."""
    return _timeline_color(widget.theme_manager, "timeline.scrollbar.hover")


def build_theme_colors(widget) -> dict[str, Any]:
    tm = widget.theme_manager
    colors = {
        "is_dark": tm.is_dark(),
        "accent": tm.get_color("accent"),
        "text_col": tm.get_color("WindowText"),
        "canvas_bg": tm.get_color("Window"),
        "gutter_bg": _timeline_color(tm, "timeline.gutter.background"),
        "group_bg": _timeline_color(tm, "timeline.group.background"),
        "track_bg": _timeline_color(tm, "timeline.track.background"),
        "lane_bg": _timeline_color(tm, "timeline.lane.background"),
        "grid_col": _timeline_color(tm, "timeline.grid.color"),
        "footer_bg": _timeline_color(tm, "timeline.footer.background"),
        "sep_strong": _timeline_color(tm, "timeline.separator.strong"),
        "sep_soft": _timeline_color(tm, "timeline.separator.soft"),
        "sb_idle": _timeline_color(tm, "timeline.scrollbar.idle"),
        "sb_hover": _timeline_color(tm, "timeline.scrollbar.hover"),
    }
    overrides = getattr(widget, "_color_overrides", None)
    if overrides:
        colors.update(overrides)
    return colors

def resolve_accent_color(widget) -> QColor:
    """Widget-level accent: the ``accent_color=``/``set_accent_color()``
    override if set, else the theme's ``accent`` token."""
    override = getattr(widget, "_color_overrides", {}).get("accent")
    if override is not None:
        return QColor(override)
    return QColor(widget.theme_manager.get_color("accent"))

def _explicit_accent_color(*candidates) -> QColor | None:
    for candidate in candidates:
        if not candidate:
            continue
        color = QColor(candidate)
        if color.isValid():
            return color
    return None

_TRACK_KIND_TOKENS: dict[str, str] = {
    "bool": "timeline.track.bool",
    "enum": "timeline.track.enum",
    "state": "timeline.track.state",
    "vec2": "timeline.track.vec2",
}

def track_color(
    widget,
    track_kind: str,
    channel_kind: str | None = None,
    *,
    track_accent_color: str | None = None,
    channel_accent_color: str | None = None,
) -> QColor:
    explicit = _explicit_accent_color(channel_accent_color, track_accent_color)
    if explicit is not None:
        return explicit
    kind = channel_kind if channel_kind in _TRACK_KIND_TOKENS else track_kind
    token = _TRACK_KIND_TOKENS.get(kind) if isinstance(kind, str) else None
    if token is not None:
        return _timeline_color(widget.theme_manager, token)
    return resolve_accent_color(widget)

def track_line_color(
    widget,
    track_id: str,
    track_kind: str,
    channel_kind: str | None = None,
    *,
    track_accent_color: str | None = None,
    channel_accent_color: str | None = None,
) -> QColor:
    return track_color(
        widget,
        track_kind,
        channel_kind,
        track_accent_color=track_accent_color,
        channel_accent_color=channel_accent_color,
    )

def track_value_color(
    widget,
    *,
    track_id: str,
    track_kind: str,
    channel_kind: str | None,
    value,
    fallback: QColor | None = None,
    track_accent_color: str | None = None,
    channel_accent_color: str | None = None,
) -> QColor:
    """Per-lane value color with host delegate hook (Phase 4 D API).

    Resolution order (additive — default behavior unchanged):

    1. explicit ``channel_accent_color`` / ``track_accent_color`` args;
    2. ``widget._callbacks.lane_value_color`` delegate — either a plain
       callable ``(*, track_id, track_kind, channel_kind, value)`` or an
       object with a ``lane_value_color`` method of that shape; a valid
       ``QColor``/color string wins, ``None``/invalid/exception falls
       through (fail-open);
    3. kind token via :func:`track_color` (no explicit accent passed, so
       the token → widget-accent fallbacks apply);
    4. explicit ``fallback`` QColor when supplied (shapes the step-3 seed
       exactly as before).

    The widget-level accent override (``accent_color=`` /
    ``set_accent_color()``) is honored through step 3's
    :func:`resolve_accent_color` fallback — a delegate returning ``None``
    never silences it.
    """
    explicit = _explicit_accent_color(channel_accent_color, track_accent_color)
    if explicit is not None:
        return explicit
    delegate_hit = _lane_delegate_color(
        widget,
        track_id=track_id,
        track_kind=track_kind,
        channel_kind=channel_kind,
        value=value,
    )
    if delegate_hit is not None:
        return delegate_hit
    fallback_color = QColor(fallback) if fallback is not None else track_color(
        widget, track_kind, channel_kind
    )
    return fallback_color


def _lane_delegate_color(
    widget,
    *,
    track_id: str,
    track_kind: str,
    channel_kind: str | None,
    value,
) -> QColor | None:
    """Try the ``lane_value_color`` delegate; ``None`` on fallthrough."""
    callbacks = getattr(widget, "_callbacks", None)
    delegate = getattr(callbacks, "lane_value_color", None)
    if delegate is None:
        return None
    try:
        if callable(delegate):
            result = delegate(
                track_id=track_id,
                track_kind=track_kind,
                channel_kind=channel_kind,
                value=value,
            )
        else:
            method = getattr(delegate, "lane_value_color", None)
            if not callable(method):
                return None
            result = method(
                track_id=track_id,
                track_kind=track_kind,
                channel_kind=channel_kind,
                value=value,
            )
    except Exception:
        return None
    if result is None:
        return None
    try:
        color = result if isinstance(result, QColor) else QColor(result)
    except Exception:
        return None
    return color if color.isValid() else None

def mix_colors(base: QColor, overlay: QColor, alpha: int) -> QColor:
    alpha_ratio = max(0.0, min(1.0, alpha / 255.0))
    inv = 1.0 - alpha_ratio
    return QColor(
        int(base.red() * inv + overlay.red() * alpha_ratio),
        int(base.green() * inv + overlay.green() * alpha_ratio),
        int(base.blue() * inv + overlay.blue() * alpha_ratio),
    )

def group_content_bg(widget, base_bg: QColor, group, strength: int) -> QColor:
    explicit = _explicit_accent_color(getattr(group, "accent_color", None))
    if explicit is not None:
        return mix_colors(base_bg, explicit, strength)
    visible_channels_fn = getattr(widget, "_visible_channels", None)
    if visible_channels_fn is not None:
        for track in group.tracks.values():
            visible = visible_channels_fn(track)
            if visible:
                accent = track_color(
                    widget,
                    track.kind,
                    visible[0].kind,
                    track_accent_color=getattr(track, "accent_color", None),
                    channel_accent_color=getattr(visible[0], "accent_color", None),
                )
                break
        else:
            accent = resolve_accent_color(widget)
    else:
        accent = resolve_accent_color(widget)
    return mix_colors(base_bg, accent, strength)
