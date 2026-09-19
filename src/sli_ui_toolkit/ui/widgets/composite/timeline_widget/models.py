from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, runtime_checkable

@runtime_checkable
class TimelineKeyframe(Protocol):
    @property
    def timestamp(self) -> float: ...
    @property
    def value(self) -> Any: ...
    @property
    def interpolation(self) -> str: ...

@runtime_checkable
class TimelineChannel(Protocol):
    @property
    def kind(self) -> str: ...
    @property
    def label(self) -> str: ...
    @property
    def keyframes(self) -> list: ...
    @property
    def interpolate_values(self) -> bool: ...

@runtime_checkable
class TimelineTrack(Protocol):
    @property
    def id(self) -> str: ...
    @property
    def kind(self) -> str: ...
    @property
    def label(self) -> str: ...
    @property
    def channels(self) -> dict[str, Any]: ...

@runtime_checkable
class TimelineGroup(Protocol):
    @property
    def label(self) -> str: ...
    @property
    def tracks(self) -> dict[str, Any]: ...

@runtime_checkable
class TimelineModel(Protocol):
    @property
    def groups(self) -> dict[str, Any]: ...
    @property
    def sample_timestamps(self) -> list: ...
    def get_duration(self) -> float: ...


@runtime_checkable
class TimelineDataSource(Protocol):
    """Typed data-source shape decoupling the widget's snapshot store.

    ADOPTION (supervisor wires in ``widget.py`` — models.py declares only):
    ``TimelineWidget.set_data`` keeps accepting the legacy inputs
    ``(snapshots, fps=None, timeline_model=None, duration=None)`` unchanged.
    The follow-up adds an overload accepting ``source: TimelineDataSource``
    and maps ``source.snapshots → snapshots``, ``source.fps → fps``,
    ``source.duration → duration``,
    ``source.timeline_model → timeline_model`` (each ``None``/missing falls
    back to the legacy default). No widget behavior changes until that
    overload lands; this Protocol is the frozen member shape for it.
    """

    @property
    def snapshots(self) -> list: ...
    @property
    def fps(self) -> int: ...
    @property
    def duration(self) -> float: ...
    @property
    def timeline_model(self) -> Any | None: ...


#: Callable shape for the per-lane value-color override:
#: ``(*, track_id, track_kind, channel_kind, value) -> QColor | str | None``.
#: Return ``None`` (or an invalid color) to fall through to the accent chain.
LaneValueColorFn = Callable[..., Any]


@runtime_checkable
class TimelineLaneColorDelegate(Protocol):
    """Object shape for the per-lane value-color override.

    Either a plain :data:`LaneValueColorFn` callable or an object with this
    method may be supplied as ``TimelineCallbacks.lane_value_color``.
    ``theme.track_value_color`` tries the delegate after explicit
    per-track/channel accent colors and before kind-token/widget-accent
    fallbacks; ``None``/invalid/exception falls through (fail-open).
    """

    def lane_value_color(
        self,
        *,
        track_id: str,
        track_kind: str,
        channel_kind: str | None,
        value: Any,
    ) -> Any: ...

@dataclass
class TimelineCallbacks:
    """Callback hooks to customize timeline behavior without hardcoding app logic."""

    should_show_track: Any = None
    """(track) -> bool. If None, shows tracks with changed channels."""

    visible_channels: Any = None
    """(track) -> list[channel]. If None, returns channels with changes."""

    is_track_active: Any = None
    """(track, channel, timestamp) -> bool. If None, always True."""

    localize_token: Any = None
    """(token: str) -> str. If None, returns token as-is.

    Bound per-widget (see ``i18n.bind_widget``).
    """

    localize_value: Any = None
    """(value) -> str. If None, uses default formatting.

    Bound per-widget (see ``i18n.bind_widget``).
    """

    lane_value_color: Any = None
    """Per-lane value-color override (see ``TimelineLaneColorDelegate``).

    Either a ``LaneValueColorFn`` callable or a delegate object with a
    ``lane_value_color(*, track_id, track_kind, channel_kind, value)``
    method. Return a ``QColor``/valid color string to override, or ``None``
    to keep the accent chain (explicit accent → delegate → kind token →
    widget accent); exceptions also fall through (fail-open). If None
    (default), Tkonverter/current behavior is unchanged.
    """

    prominent_track_ids: set[str] = field(default_factory=set)
    """Track IDs that are shown only when they have changes."""
