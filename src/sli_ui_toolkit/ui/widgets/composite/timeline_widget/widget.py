from __future__ import annotations
from sli_ui_toolkit.ui.inspector.spec import InspectSpec, SpecField  # noqa: E402

import logging
import math
from dataclasses import replace
from typing import Any

from PySide6.QtCore import QEasingCurve, QEvent, QRect, QRectF, Qt, QTimer, Signal, QVariantAnimation

import shiboken6 as sip

from .state import TimelineViewportState
from PySide6.QtGui import QCloseEvent, QColor, QHideEvent, QPainter, QPixmap, QResizeEvent
from PySide6.QtWidgets import QScrollBar, QSizePolicy, QWidget

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.managers import SettleGate
from sli_ui_toolkit.ui.managers.ui_scale import UiScale, scaled_px
from sli_ui_toolkit.ui.widgets.atomic.minimalist_scrollbar import MinimalistScrollBar

from .debug import _timeline_debug
from .models import TimelineCallbacks
from . import interaction as timeline_interaction
from . import layout as timeline_layout
from . import primitives as timeline_primitives
from . import render as timeline_render
from . import theme as timeline_theme
from . import viewport as timeline_viewport
from . import i18n as timeline_i18n

logger = logging.getLogger(__name__)

#: Thumbnail store bound (Phase 3C lifecycle): ``_thumbnails`` stays
#: index-addressed (``dict[int, QPixmap]`` + sorted ``_thumb_indices``), but
#: every insert prunes entries outside the visible strip window
#: (``get_visible_thumbnail_frame_indices``) plus
#: ``_THUMBNAIL_KEEP_MARGIN_BLOCKS`` blocks of margin on each side — entries
#: outside that range can never paint (``strip_block_layout`` only reads
#: blocks intersecting the viewport), so they are pure memory on long
#: recordings. ``_THUMBNAIL_HARD_CAP`` is the fail-stop backstop for fully
#: fitted timelines where the whole recording is visible (farthest from the
#: window midpoint evicted first). Pruning is fail-open: it runs only once
#: viewport geometry has been committed (``_state is not None``) and a
#: non-empty window is computable — pre-fit bulk loads and zero-size
#: widgets keep everything.
_THUMBNAIL_KEEP_MARGIN_BLOCKS = 2
_THUMBNAIL_HARD_CAP = 512


def gutter_band_rect_for_scroll(widget, scroll: int) -> QRect:
    """Gutter band in content coords for a scrollbar value (correction paint).

    Returns ``[scroll, scroll + LEFT_GUTTER + 2] x [0, footer_top]`` — the
    region :func:`render.draw_sticky_gutter_overlay` paints the sticky
    gutter into (``gx = scroll_offset``, ``LEFT_GUTTER + 2`` wide clip).
    Correction-only helper: computes a damage rect, changes no state,
    emits nothing.
    """
    try:
        footer_top = int(widget.height() - timeline_viewport.footer_height(widget))
    except Exception:
        try:
            footer_top = int(widget.height())
        except Exception:
            footer_top = 0
    footer_top = max(0, footer_top)
    try:
        gutter_w = int(widget.LEFT_GUTTER) + 2
    except Exception:
        gutter_w = 2
    return QRect(int(scroll), 0, max(0, gutter_w), footer_top)


class TimelineWidget(QWidget):
    """Generic keyframe timeline with thumbnail strip, grouped tracks, and playhead.

    Supply app-specific behavior via ``callbacks`` (:class:`TimelineCallbacks`).
    """

    headMoved = Signal(int)
    deletePressed = Signal()
    zoomChanged = Signal(float)
    viewportChanged = Signal()
    viewportChangedState = Signal(object)

    def __init__(
        self,
        snapshots=None,
        parent=None,
        store=None,
        callbacks: TimelineCallbacks | None = None,
        *,
        accent_color: QColor | str | None = None,
        canvas_bg: QColor | str | None = None,
        track_bg: QColor | str | None = None,
        grid_color: QColor | str | None = None,
        text_color: QColor | str | None = None,
    ):
        super().__init__(parent)
        self._callbacks = callbacks or TimelineCallbacks()
        # Teardown bookkeeping: _destroyed gates deferred callbacks
        # (singleShot flush, settle fit) after close; _filter_targets tracks
        # every installEventFilter so hide/close can remove them symmetrically.
        self._destroyed = False
        self._filter_targets: list[QWidget] = []
        self._color_overrides: dict[str, QColor] = {}
        for key, value in (
            ("accent", accent_color),
            ("canvas_bg", canvas_bg),
            ("track_bg", track_bg),
            ("grid_col", grid_color),
            ("text_col", text_color),
        ):
            if value is not None:
                self._color_overrides[key] = QColor(value)

        # Per-widget scope only (no process-global writes): binding the
        # widget's own hooks here must never overwrite the process-global
        # ``set_localize_*`` fallback — the last-constructed dialog winning
        # the globals was a MED leak-class bug. Paths without a widget
        # handle (viewport/primitives tooltips) read the globals, which the
        # host sets explicitly at app level when it needs them.
        timeline_i18n.bind_widget(
            self,
            token_fn=self._callbacks.localize_token,
            value_fn=self._callbacks.localize_value,
        )

        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setMinimumHeight(scaled_px(120))
        self.setSizePolicy(
            QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Preferred
        )
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Playhead display state (triple, deliberately not collapsed):
        # _current_index is the logical head (what headMoved reports),
        # _visual_index is the eased on-screen position driven by
        # _playhead_anim, and _scrub_visual_index is the transient drag
        # override render.py prefers while scrubbing. Collapsing the scrub
        # override into _visual_index is unsafe: the running animation would
        # overwrite the live drag position on every tick.
        self._visual_index = 0.0
        self._scrub_visual_index: float | None = None
        self._timeline_model = None
        self._row_layout: list[tuple] = []
        self._hover_points: list[tuple[QRectF, str]] = []
        self._hover_tooltip_text = None
        self._hover_tooltip_pos = None
        self._collapsed_group_ids: set[str] = set()

        self._tooltip_timer = QTimer(self)
        self._tooltip_timer.setSingleShot(True)
        self._tooltip_timer.setInterval(350)
        self._tooltip_timer.timeout.connect(self._show_hover_tooltip)
        self._v_scrollbar = MinimalistScrollBar(Qt.Orientation.Vertical, self)
        self._v_scrollbar.setVisible(False)
        self._v_scrollbar.valueChanged.connect(lambda _value: self.update())

        fps = 60
        if store and hasattr(store, "settings"):
            fps = getattr(store.settings, "video_recording_fps", 60)
        self._fps = max(1, int(fps))
        # Playhead smoothing: OutCubic ease over 150 ms (DESIGN_LANGUAGE
        # animation timing). headMoved still fires synchronously per input;
        # only the painted position eases. QVariantAnimation (not
        # QPropertyAnimation): pure value interpolator, no target object —
        # a target-less QPropertyAnimation spams
        # "Changing state of an animation without target" on every start/stop.
        self._playhead_anim = QVariantAnimation(self)
        self._playhead_anim.setDuration(150)
        self._playhead_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._playhead_anim.valueChanged.connect(self._on_playhead_frame)

        self.RULER_HEIGHT = 25
        self.STRIP_HEIGHT = 72
        self.LEFT_GUTTER = 180
        self.MIN_LEFT_GUTTER = 140
        self.MAX_LEFT_GUTTER = 320
        self.GUTTER_RESIZE_MARGIN = 6
        self.GROUP_HEADER_HEIGHT = 20
        self.TRACK_ROW_HEIGHT = 30
        self.CHANNEL_ROW_HEIGHT = 28
        self.BOTTOM_PADDING = 10
        self.SCROLLBAR_STRIP_HEIGHT = 14
        self.HANDLE_SIZE = 18
        self.HEAD_LINE_WIDTH = 2
        self.HANDLE_WIDTH = 14
        self.HANDLE_HEIGHT = 10
        # Hit slop for selection edge handles (help: «ручки выделения»).
        self.SELECTION_EDGE_HIT_PX = 8
        # All metrics above are design px. Everything the timeline draws or
        # lays out derives from them (rows, strips, gutters, handles), so a
        # single scale application keeps the widget in step with the scaled
        # dialog chrome and fonts around it.
        self._metric_base = {
            name: getattr(self, name)
            for name in (
                "RULER_HEIGHT",
                "STRIP_HEIGHT",
                "LEFT_GUTTER",
                "MIN_LEFT_GUTTER",
                "MAX_LEFT_GUTTER",
                "GUTTER_RESIZE_MARGIN",
                "GROUP_HEADER_HEIGHT",
                "TRACK_ROW_HEIGHT",
                "CHANNEL_ROW_HEIGHT",
                "BOTTOM_PADDING",
                "SCROLLBAR_STRIP_HEIGHT",
                "HANDLE_SIZE",
                "HEAD_LINE_WIDTH",
                "HANDLE_WIDTH",
                "HANDLE_HEIGHT",
                "SELECTION_EDGE_HIT_PX",
            )
        }
        self._apply_metric_scale()
        UiScale.get_instance().scale_changed.connect(self._on_scale_changed)

        self._zoom_level = 1.0
        self._last_min_zoom = 1.0
        self._suppress_resize_recalc = False
        self._state: TimelineViewportState | None = None
        # Coalesce host-dialog resize ticks: the expensive min-zoom/width
        # recompute (and the setFixedWidth-triggered relayout/repaint it
        # causes) only runs once the resize settles, same idea as the main
        # window's resize_in_progress gating around its tile rebuild.
        self._layout_settle = SettleGate(
            on_settle=self._on_layout_settle,
            interval_ms=SettleGate.DEFAULT_INTERVAL_MS,
            parent=self,
        )
        self._needs_fit_view = False
        # Coalesced Ctrl+wheel zoom (Z2): ticks accumulate here and flush
        # once per frame window via _flush_wheel_zoom — one _commitState +
        # one updateGeometry+update per window, scrollbar set synchronously
        # from the cursor-anchor math (no singleShot roundtrip).
        self._wheel_pending_y = 0.0
        self._wheel_pending_x: float | None = None
        self._wheel_pending_ticks = 0
        self._wheel_flush_scheduled = False

        self._snapshots = snapshots if snapshots else []
        self._duration = (
            float(self._snapshots[-1].timestamp) if self._snapshots else 0.0
        )
        self._thumbnails: dict[int, QPixmap] = {}
        self._thumb_indices: list[int] = []

        self._total_frames = timeline_viewport.compute_total_frames(self)
        self._current_index = 0

        self._anchor_index = 0
        self._drag_index = 0
        self._is_selecting = False
        self._has_selection = False
        # "resize_lo" | "resize_hi" | "move" | None — edit an existing range
        # without recreating it via Shift+drag.
        self._selection_edit_mode: str | None = None
        self._selection_edit_origin_frame = 0
        self._selection_edit_lo0 = 0
        self._selection_edit_hi0 = 0

        self._mouse_down = False
        self._press_pos = None
        self._press_frame = 0
        self._drag_threshold_px = 3
        self._is_resizing_gutter = False

        self._sb_dragging = False
        self._sb_drag_start_x = 0.0
        self._sb_drag_start_value = 0
        self._host_h_scrollbar: QScrollBar | None = None

        self.theme_manager = ThemeManager.get_instance()

        if self.has_snapshots():
            # Coalesced through the settle gate (same as showEvent/set_data):
            # the fit only runs once resizes stop arriving.
            self._needs_fit_view = True
            self._layout_settle.ping()

    _PROMINENT_TRACK_IDS: set[str] = set()

    def showEvent(self, event):
        super().showEvent(event)
        self._bind_host_scrollbar()
        # Watch viewport and window for fullscreen resize where widget width stays fixed
        try:
            self._install_filter_once(self.window())
            sa = timeline_viewport.get_scroll_area(self)
            if sa is not None:
                self._install_filter_once(sa.viewport())
        except Exception:
            pass
        self._needs_fit_view = True
        self._layout_settle.ping()

    def hideEvent(self, event: QHideEvent) -> None:
        super().hideEvent(event)
        self._suspend_transient()

    def closeEvent(self, event: QCloseEvent) -> None:
        self._tear_down()
        super().closeEvent(event)

    def _install_filter_once(self, obj: QWidget | None) -> None:
        """Install ``self`` as an event filter on *obj* exactly once."""
        if obj is None:
            return
        if any(known is obj for known in self._filter_targets):
            return
        try:
            obj.installEventFilter(self)
        except (RuntimeError, AttributeError):
            return
        self._filter_targets.append(obj)

    def _remove_installed_filters(self) -> None:
        """Remove every event filter installed via :meth:`_install_filter_once`."""
        targets, self._filter_targets = list(self._filter_targets), []
        for obj in targets:
            try:
                obj.removeEventFilter(self)
            except (RuntimeError, AttributeError):
                pass

    def _suspend_transient(self) -> None:
        """Hide-time suspend: stop timers/animation, drop event filters.

        Symmetric to ``showEvent``/``_bind_host_scrollbar`` installs —
        ``showEvent`` reinstalls the filters. Idempotent; safe to call from
        both ``hideEvent`` and ``closeEvent`` paths.
        """
        try:
            self._tooltip_timer.stop()
        except (RuntimeError, AttributeError):
            pass
        try:
            self._playhead_anim.stop()
        except (RuntimeError, AttributeError):
            pass
        self._remove_installed_filters()

    def _unbind_host_scrollbar(self) -> None:
        """Disconnect host scrollbar signals acquired by :meth:`_bind_host_scrollbar`."""
        scrollbar = self._host_h_scrollbar
        self._host_h_scrollbar = None
        if scrollbar is None:
            return
        for signal in (scrollbar.valueChanged, scrollbar.rangeChanged):
            try:
                signal.disconnect(self._on_host_scroll)
            except (TypeError, RuntimeError):
                pass

    def _tear_down(self) -> None:
        """Close-time teardown: no singleton may retain the widget after this.

        Disconnects the ``UiScale.scale_changed`` singleton connection and
        the host scrollbar signals, drops the child signal connections whose
        Qt-held callables would otherwise keep the Python wrapper alive
        (tooltip timer, inner scrollbar lambda, playhead animation),
        suspends transient state, cancels the settle gate, and raises the
        ``_destroyed`` gate so deferred callbacks (``_flush_wheel_zoom``,
        ``_on_layout_settle``) never commit or emit afterwards. Idempotent.

        Terminal: a closed widget is not expected to be reshown (dialog
        children are destroyed with their dialog); ``showEvent`` still
        reinstalls event filters, but signal connections are not restored.
        """
        if self._destroyed:
            return
        self._destroyed = True
        self._suspend_transient()
        try:
            UiScale.get_instance().scale_changed.disconnect(self._on_scale_changed)
        except (TypeError, RuntimeError):
            pass
        self._unbind_host_scrollbar()
        try:
            self._layout_settle.cancel()
        except (RuntimeError, AttributeError):
            pass
        for signal, slot in (
            (self._tooltip_timer.timeout, self._show_hover_tooltip),
            (self._playhead_anim.valueChanged, self._on_playhead_frame),
        ):
            try:
                signal.disconnect(slot)
            except (TypeError, RuntimeError):
                pass
        try:
            # Lambda receiver — disconnect all slots on this one signal.
            self._v_scrollbar.valueChanged.disconnect()
        except (TypeError, RuntimeError):
            pass

    def eventFilter(self, obj, event):
        t = event.type()
        if t in (QEvent.Type.Resize, QEvent.Type.WindowStateChange):
            try:
                sa = timeline_viewport.get_scroll_area(self)
                is_viewport = sa is not None and sa.viewport() is not None and obj is sa.viewport()
                is_window = obj is self.window()
                if is_viewport or is_window:
                    self._onViewportGeometryChanged("eventFilter")
                    return False
            except Exception:
                pass
        return super().eventFilter(obj, event)

    def _onViewportGeometryChanged(self, source: str = "") -> None:
        if not self.has_snapshots():
            return
        if self._suppress_resize_recalc:
            return
        _timeline_debug("_onViewportGeometryChanged source=%s width=%s zoom=%s last_min=%s", source, self.width(), self._zoom_level, self._last_min_zoom)
        self._update_vertical_scrollbar()
        nxt = self._recomputeFittedState()
        self._commitState(nxt, source=source)
        try:
            timeline_viewport.update_fixed_width(self)
        except Exception:
            pass
        _timeline_debug("_onViewportGeometryChanged done source=%s width=%s zoom=%s last_min=%s", source, self.width(), self._zoom_level, self._last_min_zoom)

    def _current_state(self) -> TimelineViewportState:
        """Snapshot current viewport state from widget fields and helpers."""
        min_zoom = timeline_viewport.calculate_min_zoom(self)
        logical = timeline_viewport.get_logical_width(self)
        try:
            right = timeline_viewport.right_inset(self)
        except Exception:
            right = 0
        if self._total_frames > 0:
            content_width = int(math.ceil(float(self.LEFT_GUTTER) + float(logical) + float(right)))
        else:
            content_width = 0
        viewport_width = timeline_viewport.get_viewport_width(self)
        scroll_area = timeline_viewport.get_scroll_area(self)
        try:
            scroll_x = int(scroll_area.horizontalScrollBar().value()) if scroll_area is not None and scroll_area.horizontalScrollBar() is not None else 0
        except Exception:
            scroll_x = 0
        return TimelineViewportState(
            zoom=float(self._zoom_level),
            min_zoom=float(min_zoom),
            left_gutter=int(self.LEFT_GUTTER),
            content_width=int(content_width),
            viewport_width=int(viewport_width),
            scroll_x=int(scroll_x),
        )

    def _recomputeFittedState(self) -> TimelineViewportState:
        """Return current state with zoom clamped to min_zoom if fitted."""
        cur = self._current_state()
        if cur.is_fitted() and abs(cur.zoom - cur.min_zoom) > 1e-4:
            old_zoom = self._zoom_level
            self._zoom_level = cur.min_zoom
            try:
                clamped = self._current_state()
            finally:
                self._zoom_level = old_zoom
            return clamped
        return cur

    def _commitState(self, nxt: TimelineViewportState, source: str = "") -> bool:
        """Diff ``nxt`` against ``self._state`` and emit typed signals.

        ``eps 1e-4`` for zoom/min_zoom, ``==`` for px geometry. Calls
        ``updateGeometry`` + ``update`` and emits ``zoomChanged(float)`` only
        when zoom changed, ``viewportChanged`` /
        ``viewportChangedState(object)`` when zoom or geometry changed
        (``"gutterDrag"`` included: a gutter-width change is pure geometry,
        so it emits the viewport family and never ``zoomChanged``).
        Returns ``True`` if any emit happened.
        """
        old: TimelineViewportState | None = getattr(self, "_state", None)
        eps = 1e-4
        has_zoom = nxt.has_zoom_changed(old, eps=eps)
        has_geometry = nxt.has_geometry_changed(old)
        min_zoom_changed = old is not None and abs(nxt.min_zoom - old.min_zoom) > eps
        if min_zoom_changed:
            has_geometry = True
        if old is not None and not has_zoom and not has_geometry:
            self._state = nxt
            self._zoom_level = float(nxt.zoom)
            self._last_min_zoom = float(nxt.min_zoom)
            return False
        self._zoom_level = float(nxt.zoom)
        self._last_min_zoom = float(nxt.min_zoom)
        if int(self.LEFT_GUTTER) != int(nxt.left_gutter):
            self.LEFT_GUTTER = int(nxt.left_gutter)
        self._state = nxt
        _timeline_debug("_commitState source=%s zoom %s->%s min %s eps %s has_zoom=%s has_geom=%s", source, getattr(old, "zoom", None), nxt.zoom, nxt.min_zoom, eps, has_zoom, has_geometry)
        try:
            self.updateGeometry()
        except Exception:
            pass
        self.update()
        emitted = False
        if has_zoom:
            try:
                self.zoomChanged.emit(float(nxt.zoom))
            except Exception:
                pass
            emitted = True
        if has_zoom or has_geometry:
            try:
                self.viewportChanged.emit()
            except Exception:
                pass
            try:
                self.viewportChangedState.emit(nxt)
            except Exception:
                pass
            emitted = True
        return emitted

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        self._update_vertical_scrollbar()
        _timeline_debug("resizeEvent old=%sx%s new=%sx%s suppress=%s has_snap=%s width=%s zoom=%s last_min=%s", event.oldSize().width(), event.oldSize().height(), event.size().width(), event.size().height(), self._suppress_resize_recalc, self.has_snapshots(), self.width(), self._zoom_level, self._last_min_zoom)

        if not self.has_snapshots():
            _timeline_debug("resizeEvent SKIP no snapshots")
            return

        if self._suppress_resize_recalc:
            _timeline_debug("resizeEvent suppress SKIP")
            return

        old_size = event.oldSize()
        if old_size.isValid() and old_size.width() == event.size().width():
            _timeline_debug("resizeEvent width unchanged -> geometry check")
            self._onViewportGeometryChanged("resizeEvent:widthUnchanged")
            return

        self._onViewportGeometryChanged("resizeEvent")

    def _update_vertical_scrollbar(self) -> None:
        timeline_viewport.update_vertical_scrollbar(self)

    def _bind_host_scrollbar(self) -> None:
        scroll_area = timeline_viewport.get_scroll_area(self)
        if scroll_area is None:
            return
        scrollbar = scroll_area.horizontalScrollBar()
        if scrollbar is not None and scrollbar is not self._host_h_scrollbar:
            self._unbind_host_scrollbar()
            self._host_h_scrollbar = scrollbar
            self._host_h_scrollbar.valueChanged.connect(self._on_host_scroll)
            self._host_h_scrollbar.rangeChanged.connect(self._on_host_scroll)
        try:
            self._install_filter_once(scroll_area.viewport())
        except Exception:
            pass

    def _on_host_scroll(self, *_args) -> None:
        try:
            sa = timeline_viewport.get_scroll_area(self)
            cur_x = int(sa.horizontalScrollBar().value()) if sa is not None and sa.horizontalScrollBar() is not None else 0
        except Exception:
            cur_x = 0
        _state = getattr(self, "_state", None)
        prev_x = _state.scroll_x if _state is not None else None
        is_range = len(_args) == 2
        if not is_range and prev_x is not None and cur_x == prev_x:
            self._update_vertical_scrollbar()
            self.update()
            return
        # Signals-live scroll step: the content widget window already moved
        # synchronously (Qt scrollContentsBy) while the geometry-changed
        # cycle below only posts async paints. Union the gutter band into
        # the damage synchronously so the next paint pass already covers
        # the sticky gutter at the new offset.
        try:
            self.update(gutter_band_rect_for_scroll(self, cur_x))
        except Exception:
            pass
        self._onViewportGeometryChanged("hostScroll")

    def _rebuild_row_layout(self):
        timeline_layout.rebuild_row_layout(self)

    def _group_key(self, group) -> str:
        return str(getattr(group, "id", getattr(group, "label", "")))

    def _is_group_collapsed(self, group) -> bool:
        return self._group_key(group) in self._collapsed_group_ids

    def _toggle_group_collapsed(self, group) -> None:
        group_key = self._group_key(group)
        if group_key in self._collapsed_group_ids:
            self._collapsed_group_ids.remove(group_key)
        else:
            self._collapsed_group_ids.add(group_key)
        self._rebuild_row_layout()
        self._ensure_preferred_height()
        self.update()

    def _group_accent_color(self, group) -> QColor:
        explicit = QColor(getattr(group, "accent_color", None) or "")
        if explicit.isValid():
            return explicit
        for track in group.tracks.values():
            visible_chs = self._visible_channels(track)
            if visible_chs:
                return timeline_theme.track_color(
                    self,
                    track.kind,
                    visible_chs[0].kind,
                    track_accent_color=getattr(track, "accent_color", None),
                    channel_accent_color=getattr(visible_chs[0], "accent_color", None),
                )
        return timeline_theme.resolve_accent_color(self)

    def _group_header_rect(self, left: float, top: float) -> QRectF:
        return QRectF(left, top, self.LEFT_GUTTER, self.GROUP_HEADER_HEIGHT)

    def _group_chevron_rect(self, header_rect: QRectF) -> QRectF:
        return QRectF(header_rect.left() + 8, header_rect.top() + 2, 18, header_rect.height() - 4)

    def _group_toggle_hit(self, pos) -> Any | None:
        return timeline_layout.group_toggle_hit(self, pos)

    def _visible_channels(self, track):
        return timeline_layout.visible_channels(self, track)

    def _channel_has_changes(self, channel) -> bool:
        return timeline_layout.channel_has_changes(channel)

    def _should_show_track(self, track) -> bool:
        return timeline_layout.should_show_track(self, track)

    def _rows_height(self):
        return timeline_layout.rows_height(self)

    def _ensure_preferred_height(self):
        timeline_layout.ensure_preferred_height(self)

    def _update_hover_tooltip(self, pos) -> None:
        timeline_viewport.update_hover_tooltip(self, pos)

    def _show_hover_tooltip(self) -> None:
        timeline_viewport.show_hover_tooltip(self)

    def _is_on_gutter_handle(self, x: int) -> bool:
        return timeline_viewport.is_on_gutter_handle(self, x)

    def set_data(
        self,
        snapshots,
        fps: int | None = None,
        timeline_model=None,
        duration: float | None = None,
    ):
        self._bind_host_scrollbar()
        self._snapshots = list(snapshots or [])
        self._duration = (
            float(duration)
            if duration is not None
            else (float(self._snapshots[-1].timestamp) if self._snapshots else 0.0)
        )
        self._timeline_model = timeline_model
        if fps is not None:
            self._fps = max(1, int(fps))
        self._total_frames = timeline_viewport.compute_total_frames(self)
        self._rebuild_row_layout()
        self._ensure_preferred_height()

        self._anchor_index = 0
        self._drag_index = 0
        self._has_selection = False
        self._is_selecting = False
        self._selection_edit_mode = None
        self._mouse_down = False
        self._press_pos = None
        self._press_frame = 0
        self._visual_index = 0.0
        self._playhead_anim.stop()
        self._current_index = 0

        # Coalesced through the settle gate (same as __init__/showEvent).
        self._needs_fit_view = True
        self._layout_settle.ping()

    def _set_color_override(self, key: str, color: QColor | str | None) -> None:
        if color is None:
            self._color_overrides.pop(key, None)
        else:
            self._color_overrides[key] = QColor(color)
        self.update()

    def set_accent_color(self, color: QColor | str | None) -> None:
        """Override the accent color. ``None`` reverts to the theme token."""
        self._set_color_override("accent", color)

    def set_canvas_background_color(self, color: QColor | str | None) -> None:
        """Override the canvas fill. ``None`` reverts to the theme token."""
        self._set_color_override("canvas_bg", color)

    def set_track_background_color(self, color: QColor | str | None) -> None:
        """Override the track row fill. ``None`` reverts to the theme token."""
        self._set_color_override("track_bg", color)

    def set_grid_color(self, color: QColor | str | None) -> None:
        """Override the ruler/grid line color. ``None`` reverts to the theme token."""
        self._set_color_override("grid_col", color)

    def set_text_color(self, color: QColor | str | None) -> None:
        """Override label/text color. ``None`` reverts to the theme token."""
        self._set_color_override("text_col", color)

    def set_thumbnails(self, thumbnails: dict):
        self._thumbnails.update(thumbnails)
        self._thumb_indices = sorted(self._thumbnails.keys())
        self._prune_thumbnails()
        if self.has_snapshots():
            self._last_min_zoom = timeline_viewport.calculate_min_zoom(self)
            self._refresh_viewport_state()
        self.update()

    def add_thumbnail(self, index: int, pixmap: QPixmap):
        _timeline_debug("add_thumbnail idx=%s size=%sx%s total=%s", index, pixmap.width() if pixmap else -1, pixmap.height() if pixmap else -1, len(self._thumbnails)+1)
        self._thumbnails[index] = pixmap
        if not self._thumb_indices or index > self._thumb_indices[-1]:
            self._thumb_indices.append(index)
        elif index not in self._thumb_indices:
            self._thumb_indices.append(index)
            self._thumb_indices.sort()
        self._prune_thumbnails()
        if self.has_snapshots():
            self._last_min_zoom = timeline_viewport.calculate_min_zoom(self)
            self._refresh_viewport_state()
        self.update()

    def _prune_thumbnails(self) -> None:
        """Enforce the thumbnail store bound (see module constants).

        Keeps entries whose index falls inside the visible strip window
        plus margin (frame-space ``[lo, hi]`` around the visible rep
        indices) and evicts the rest, then applies the hard-cap backstop
        (farthest from the window midpoint first). Index-addressed shape
        (``_thumbnails`` + sorted ``_thumb_indices``) is preserved.
        Fail-open: anything uncomputable (no committed state yet, no
        frames, empty window, bad metrics) keeps everything.
        """
        if not self._thumbnails:
            return
        if getattr(self, "_state", None) is None or self._total_frames <= 0:
            return
        try:
            visible = self.get_visible_thumbnail_frame_indices(overscan_blocks=1)
        except Exception:
            return
        if not visible:
            return
        try:
            slot = timeline_viewport.get_slot_width(self)
            base = timeline_viewport.get_base_tile_width(self)
        except Exception:
            return
        if slot <= 0 or base <= 0:
            return
        draw_w = base if slot < base else slot
        frames_per_block = max(1.0, draw_w / slot)
        margin = int(math.ceil(frames_per_block * _THUMBNAIL_KEEP_MARGIN_BLOCKS))
        last = max(0, self._total_frames - 1)
        lo = max(0, min(visible) - margin)
        hi = min(last, max(visible) + margin)
        for idx in [i for i in self._thumbnails if i < lo or i > hi]:
            del self._thumbnails[idx]
        if len(self._thumbnails) > _THUMBNAIL_HARD_CAP:
            mid = (lo + hi) / 2.0
            ordered = sorted(self._thumbnails, key=lambda i: (abs(i - mid), i))
            for idx in ordered[_THUMBNAIL_HARD_CAP:]:
                del self._thumbnails[idx]
        self._thumb_indices = sorted(self._thumbnails.keys())

    def clear_thumbnails(self):
        _timeline_debug("clear_thumbnails count=%s", len(self._thumbnails))
        self._thumbnails.clear()
        self._thumb_indices.clear()
        self.update()

    def has_snapshots(self) -> bool:
        return self._duration > 0.0 or bool(self._snapshots)

    def get_total_duration(self) -> float:
        return max(0.0, float(self._duration))

    def get_pixels_per_second(self):
        """Current px/sec: ``pps = zoom * base_pps`` (Z1 invariant)."""
        if self._total_frames <= 0:
            return 50.0
        duration = self.get_total_duration()
        if duration <= 0:
            return 50.0
        return timeline_viewport.get_logical_width(self) / duration

    def get_visible_thumbnail_frame_indices(self, overscan_blocks: int = 1) -> list[int]:
        return timeline_viewport.get_visible_thumbnail_frame_indices(
            self,
            overscan_blocks=overscan_blocks,
        )

    def fit_view(self):
        timeline_viewport.fit_view(self)
        # Silent write-through: keep the committed snapshot fresh without
        # emitting (paths that need an emit go through _commitState, e.g.
        # _on_layout_settle). No-op until the first _commitState, so the
        # old=None first-commit emit is preserved.
        self._refresh_viewport_state()

    def update_layout_width(self):
        # Called on every host-dialog resizeEvent tick (dozens/sec while the
        # user drags a window edge). Defer the actual recompute to settle
        # instead of redoing it synchronously on each tick.
        self._layout_settle.ping()

    def _apply_metric_scale(self) -> None:
        for name, base in self._metric_base.items():
            setattr(self, name, scaled_px(base))

    def _on_scale_changed(self, _factor: float) -> None:
        self._apply_metric_scale()
        self._rebuild_row_layout()
        self._ensure_preferred_height()
        timeline_viewport.update_fixed_width(self)
        timeline_viewport.update_vertical_scrollbar(self)
        self.update()

    def _on_layout_settle(self):
        # Deferred fit/commit must never run on a destroyed widget: the
        # settle timer is parented to us, but a pending timeout can still
        # fire between close() and C++ deletion.
        if getattr(self, "_destroyed", False):
            return
        # PySide6-stubs lags shiboken6.isValid — narrow ignore per AGENTS.md.
        if not sip.isValid(self):  # type: ignore[attr-defined]
            return
        _timeline_debug("_on_layout_settle needs_fit=%s width=%s zoom=%s last_min=%s", getattr(self, "_needs_fit_view", False), self.width(), self._zoom_level, self._last_min_zoom)
        if getattr(self, "_needs_fit_view", False):
            self._needs_fit_view = False
            self.fit_view()
            _timeline_debug("_on_layout_settle after fit_view width=%s zoom=%s", self.width(), self._zoom_level)
            try:
                nxt = self._recomputeFittedState()
                self._commitState(nxt, source="settleFit")
                timeline_viewport.update_fixed_width(self)
            except Exception:
                pass
            return
        self._onViewportGeometryChanged("settle")
        _timeline_debug("_on_layout_settle after _onViewportGeometryChanged width=%s zoom=%s", self.width(), self._zoom_level)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta == 0:
                return
            try:
                cursor_x = float(event.position().x())
            except Exception:
                cursor_x = float(self.LEFT_GUTTER)
            # Coalesce: accumulate ticks, flush once per frame window (Z2).
            # Never touches _needs_fit_view — settle owns fit_view (Z1).
            self._wheel_pending_y += float(delta)
            self._wheel_pending_x = cursor_x
            self._wheel_pending_ticks += 1
            if not self._wheel_flush_scheduled:
                self._wheel_flush_scheduled = True
                QTimer.singleShot(0, self._flush_wheel_zoom)
            event.accept()
        else:
            delta = event.angleDelta().y()
            if delta != 0 and self._v_scrollbar.isVisible():
                old = self._v_scrollbar.value()
                direction = -1 if delta > 0 else 1
                self._v_scrollbar.setValue(old + direction * self._v_scrollbar.singleStep())
                if self._v_scrollbar.value() != old:
                    self._update_vertical_scrollbar()
                    self.update()
                    self.viewportChanged.emit()
                event.accept()
            else:
                try:
                    sa = timeline_viewport.get_scroll_area(self)
                    old_h = int(sa.horizontalScrollBar().value()) if sa is not None and sa.horizontalScrollBar() is not None else None
                except Exception:
                    old_h = None
                super().wheelEvent(event)
                try:
                    sa = timeline_viewport.get_scroll_area(self)
                    new_h = int(sa.horizontalScrollBar().value()) if sa is not None and sa.horizontalScrollBar() is not None else None
                    if old_h is not None and new_h is not None and new_h != old_h:
                        self._onViewportGeometryChanged("wheelHorizontal")
                except Exception:
                    pass

    def _flush_wheel_zoom(self) -> None:
        """Apply accumulated Ctrl+wheel ticks as one cursor-anchored step.

        Z2/Z3: exactly one ``_commitState`` (hence one
        ``updateGeometry``+``update``) per frame window, no scrollbar
        ping-pong — the scrollbar is set synchronously from the anchor
        math. No-change windows (already at min/max) stay silent. The emit
        contract is unchanged: ``_commitState`` remains the only emit path
        for ``zoomChanged`` / ``viewportChanged`` /
        ``viewportChangedState``. Source is ``"wheelZoom"`` for a lone
        tick, ``"wheelZoomCoalesced"`` for a coalesced window. Never commits
        or emits after close (``_destroyed`` gate + ``isValid`` check — the
        ``singleShot(0)`` callback can outlive the widget into C++ teardown).
        """
        # PySide6-stubs lags shiboken6.isValid — narrow ignore per AGENTS.md.
        if getattr(self, "_destroyed", False) or not sip.isValid(self):  # type: ignore[attr-defined]
            self._wheel_flush_scheduled = False
            self._wheel_pending_y = 0.0
            self._wheel_pending_x = None
            self._wheel_pending_ticks = 0
            return
        self._wheel_flush_scheduled = False
        pending_y = float(self._wheel_pending_y)
        cursor_x = self._wheel_pending_x
        ticks = int(self._wheel_pending_ticks)
        self._wheel_pending_y = 0.0
        self._wheel_pending_x = None
        self._wheel_pending_ticks = 0
        if pending_y == 0.0 or cursor_x is None:
            return
        old_zoom = float(self._zoom_level)
        steps = pending_y / 120.0
        new_zoom = timeline_viewport.clamp_zoom(
            self, old_zoom * (timeline_viewport.WHEEL_ZOOM_FACTOR**steps)
        )
        if abs(new_zoom - old_zoom) <= 1e-4:
            return
        new_pps = timeline_viewport.pixels_per_second_for_zoom(self, new_zoom)
        scroll_area = timeline_viewport.get_scroll_area(self)
        scrollbar = None
        scroll_old = 0
        if scroll_area is not None:
            scrollbar = scroll_area.horizontalScrollBar()
            try:
                scroll_old = int(scrollbar.value())
            except Exception:
                scroll_old = 0
        # event.position() is in widget (content) coords; viewport coords
        # subtract the pre-zoom scroll offset (the mouse never moves here).
        cursor_time = timeline_viewport.cursor_time_at_x(self, float(cursor_x))
        cursor_viewport_x = float(cursor_x) - float(scroll_old)
        target = timeline_viewport.anchor_scroll_for_zoom(
            self, cursor_viewport_x, cursor_time, new_pps
        )
        self._zoom_level = float(new_zoom)
        timeline_viewport.update_fixed_width(self)
        if scrollbar is not None:
            try:
                lo = int(scrollbar.minimum())
                hi = int(scrollbar.maximum())
            except Exception:
                lo, hi = 0, int(target)
            target = max(lo, min(int(target), hi))
            scrollbar.blockSignals(True)
            try:
                scrollbar.setValue(int(target))
            finally:
                scrollbar.blockSignals(False)
            try:
                _sync_scroll = int(scrollbar.value())
            except Exception:
                _sync_scroll = int(target)
        else:
            _sync_scroll = int(target)
        # Synchronous correction paint: setValue moved the content widget
        # window synchronously while every correction paint below
        # (_commitState -> update, update_fixed_width -> update) is async,
        # leaving ~1 frame of gutter displaced per step. repaint() paints
        # the gutter band now, in the same call stack. Band-only (not a
        # full repaint) to keep the coalesced budget: one commit + one
        # sync band repaint per window. Correction-only: no state change.
        try:
            self.repaint(gutter_band_rect_for_scroll(self, _sync_scroll))
        except Exception:
            pass
        source = "wheelZoomCoalesced" if ticks > 1 else "wheelZoom"
        try:
            nxt = self._current_state()
        except Exception:
            return
        self._commitState(nxt, source=source)

    def keyPressEvent(self, event):
        key = event.key()
        mods = event.modifiers()

        if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.deletePressed.emit()
            event.accept()
            return

        if key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            if self._total_frames <= 0:
                event.ignore()
                return
            step = 10 if mods & Qt.KeyboardModifier.ShiftModifier else 1
            direction = -1 if key == Qt.Key.Key_Left else 1
            target = self._current_index + direction * step
            self.set_current_frame(target)
            self.headMoved.emit(self._current_index)
            event.accept()
            return

        if key == Qt.Key.Key_Home:
            if self._total_frames <= 0:
                event.ignore()
                return
            self.set_current_frame(0)
            self.headMoved.emit(self._current_index)
            event.accept()
            return

        if key == Qt.Key.Key_End:
            if self._total_frames <= 0:
                event.ignore()
                return
            self.set_current_frame(self._total_frames - 1)
            self.headMoved.emit(self._current_index)
            event.accept()
            return

        super().keyPressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        timeline_render.paint_timeline(self, painter, event)
        painter.end()

    def mousePressEvent(self, event):
        timeline_interaction.mouse_press_event(self, event)

    def mouseMoveEvent(self, event):
        timeline_interaction.mouse_move_event(self, event)

    def leaveEvent(self, event):
        timeline_interaction.leave_event(self, event)
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        timeline_interaction.mouse_release_event(self, event)

    def get_selection_range(self):
        if not self._has_selection:
            return 0, max(0, self._total_frames - 1)
        return min(self._anchor_index, self._drag_index), max(self._anchor_index, self._drag_index)

    def has_selection(self) -> bool:
        return bool(self._has_selection)

    def set_current_frame(self, index):
        self._current_index = max(0, min(index, self._total_frames - 1))
        target = float(self._current_index)
        start = float(self._visual_index)
        if abs(self._current_index - start) > 2.0 or math.isclose(
            start, target, abs_tol=1e-9
        ):
            # Large jump: snap like the old lerp did; settled: nothing to do.
            self._playhead_anim.stop()
            self._visual_index = target
            self.update()
            return
        self._playhead_anim.stop()
        self._playhead_anim.setStartValue(start)
        self._playhead_anim.setEndValue(target)
        self._playhead_anim.start()

    def _on_playhead_frame(self, value) -> None:
        try:
            self._visual_index = float(value)
        except (TypeError, ValueError):
            return
        self.update()

    def _refresh_viewport_state(self) -> None:
        """Silently re-snapshot ``self._state`` from live fields (no emits).

        Write-through cache for paths that mutate geometry without a
        viewport notification today (gutter drag, thumbnail updates,
        fit_view): keeps ``TimelineViewportState`` authoritative for readers
        like ``_on_host_scroll`` while ``_commitState`` remains the only emit
        path. Deliberately a no-op while ``_state`` is ``None`` so the first
        ``_commitState(old=None)`` still emits.
        """
        if self._state is None:
            return
        try:
            nxt = self._current_state()
        except Exception:
            return
        self._state = nxt
        self._last_min_zoom = float(nxt.min_zoom)

TimelineWidget.inspect_spec = InspectSpec(
    family="TimelineWidget",
    state=(
        SpecField("fps", "_fps", private=True),
        SpecField("duration", "_duration", private=True),
        SpecField("zoom_level", "_zoom_level", private=True),
        SpecField("visual_index", "_visual_index", private=True),
        SpecField("collapsed_groups", "_collapsed_group_ids", private=True),
        SpecField("total_duration", "get_total_duration"),
        SpecField("pixels_per_second", "get_pixels_per_second"),
        SpecField("has_selection", "has_selection"),
    ),
    token_family=timeline_theme.TIMELINE_TOKENS,
    docs='docs/user/API_CATALOG.md',
)

from sli_ui_toolkit.ui.widget_descriptor import InspectSection, WidgetDescriptor

TimelineWidget.widget_descriptor = WidgetDescriptor(
    family=TimelineWidget.inspect_spec.family,
    inspect=InspectSection(
        config=getattr(TimelineWidget.inspect_spec, 'config', ()),
        state=TimelineWidget.inspect_spec.state,
        token_family=getattr(TimelineWidget.inspect_spec, 'token_family', ()),
        regions=getattr(TimelineWidget.inspect_spec, 'regions', False),
        layers=getattr(TimelineWidget.inspect_spec, 'layers', False),
        docs=getattr(TimelineWidget.inspect_spec, 'docs', ''),
        preview_seed=getattr(TimelineWidget.inspect_spec, 'preview_seed', None),
        apply_config_refresh=getattr(TimelineWidget.inspect_spec, 'apply_config_refresh', None),
    ),
)