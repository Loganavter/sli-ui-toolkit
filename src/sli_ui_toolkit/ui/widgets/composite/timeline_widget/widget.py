from __future__ import annotations
from sli_ui_toolkit.ui.inspector.spec import InspectSpec, SpecField  # noqa: E402

from typing import Any, ClassVar

from PySide6.QtCore import QEasingCurve, QRect, QRectF, Qt, QTimer, Signal, QVariantAnimation

import shiboken6 as sip

from .state import TimelineViewportState
from PySide6.QtGui import QCloseEvent, QColor, QHideEvent, QPainter, QPixmap, QResizeEvent
from PySide6.QtWidgets import QScrollBar, QSizePolicy, QWidget

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.managers import SettleGate
from sli_ui_toolkit.ui.managers.ui_scale import UiScale, scaled_px
from sli_ui_toolkit.ui.widgets.atomic.minimalist_scrollbar import MinimalistScrollBar

from .models import TimelineCallbacks
from . import interaction as timeline_interaction
from . import layout as timeline_layout
from . import render as timeline_render
from . import theme as timeline_theme
from . import viewport as timeline_viewport
from . import i18n as timeline_i18n


def gutter_band_rect_for_scroll(widget, scroll: int) -> QRect:
    """Compatibility alias over the canonical ``viewport.gutter_band_rect``."""
    return timeline_viewport.gutter_band_rect(widget, scroll)


class TimelineWidget(QWidget):
    """Generic keyframe timeline with thumbnail strip, grouped tracks, and playhead.

    Thin owner: construction/wiring, instance state, and thin delegators.
    Orchestration bodies live as plain ``def name(widget, ...)`` functions
    in ``viewport.py`` / ``layout.py`` / ``interaction.py``. Supply
    app-specific behavior via ``callbacks`` (:class:`TimelineCallbacks`).
    """

    # Inspector metadata assigned at module bottom.
    inspect_spec: "ClassVar[InspectSpec]"
    widget_descriptor: "ClassVar[WidgetDescriptor]"

    headMoved = Signal(int)
    deletePressed = Signal()
    zoomChanged = Signal(float)
    playPauseRequested = Signal()
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
        # Show/teardown symmetry: _transient_bound tracks the four __init__
        # signal connections (tooltip timer, inner scrollbar, playhead
        # animation, UiScale) so show restores exactly what teardown drops;
        # _host_viewport/_filter_window track the role filters so host
        # changes forget dead viewports instead of accumulating them.
        self._transient_bound = True
        self._host_viewport: QWidget | None = None
        self._filter_window: QWidget | None = None
        # Prune keep-cache (interaction.prune_thumbnails): reset on ingest.
        self._prune_keep_cache: tuple | None = None
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

        # Per-widget i18n scope only (no process-global writes): paint and
        # tooltip paths resolve through ``localize_*_for(widget, ...)``.
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
        self.setAccessibleName("Timeline")
        self.setAccessibleDescription(
            "Keyframe timeline. Left and right arrows step frames. "
            "Space toggles playback."
        )

        # Playhead display state (triple, deliberately not collapsed):
        # _current_index is the logical head (what headMoved reports),
        # _visual_index is the eased on-screen position driven by
        # _playhead_anim, and _scrub_visual_index is the transient drag
        # override render.py prefers while scrubbing.
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
        self._tooltip_timer.setInterval(timeline_interaction.TOOLTIP_DELAY_MS)
        self._tooltip_timer.timeout.connect(self._show_hover_tooltip)
        self._v_scrollbar = MinimalistScrollBar(Qt.Orientation.Vertical, self)
        self._v_scrollbar.setVisible(False)
        self._v_scrollbar.valueChanged.connect(lambda _value: self.update())

        fps = 60
        if store and hasattr(store, "settings"):
            fps = getattr(store.settings, "video_recording_fps", 60)
        self._fps = max(1, int(fps))
        # Playhead smoothing: OutCubic ease over 150 ms. headMoved still
        # fires synchronously per input; only the painted position eases.
        # QVariantAnimation (not QPropertyAnimation): pure value
        # interpolator, no target object.
        self._playhead_anim = QVariantAnimation(self)
        self._playhead_anim.setDuration(timeline_interaction.PLAYHEAD_ANIM_MS)
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
        # All metrics above are design px; everything drawn or laid out
        # derives from them, so one scale application keeps the widget in
        # step with the scaled dialog chrome and fonts around it.
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
        timeline_interaction.apply_metric_scale(self)
        UiScale.get_instance().scale_changed.connect(self._on_scale_changed)

        self._zoom_level = 1.0
        self._last_min_zoom = 1.0
        self._suppress_resize_recalc = False
        self._state: TimelineViewportState | None = None
        # Coalesce host-dialog resize ticks: the expensive min-zoom/width
        # recompute only runs once the resize settles.
        self._layout_settle = SettleGate(
            on_settle=self._on_layout_settle,
            interval_ms=SettleGate.DEFAULT_INTERVAL_MS,
            parent=self,
        )
        self._needs_fit_view = False
        # Coalesced Ctrl+wheel zoom: ticks accumulate here and flush once
        # per frame window via _flush_wheel_zoom.
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
        # Explicit ingest freeze (HANDOFF-1): the __init__ snapshot path
        # freezes exactly like interaction.ingest_data does.
        timeline_interaction.freeze_thumb_aspect(self)

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
        timeline_interaction.show_event(self)

    def hideEvent(self, event: QHideEvent) -> None:
        super().hideEvent(event)
        timeline_interaction.suspend_transient(self)

    def closeEvent(self, event: QCloseEvent) -> None:
        timeline_interaction.teardown_widget(self)
        super().closeEvent(event)

    def eventFilter(self, obj, event):
        # True when handled: stops fall-through reprocessing by other
        # filters (interaction.event_filter never commits — it only pings
        # the settle gate, so no re-entrant cascade can start here).
        if timeline_interaction.event_filter(self, obj, event):
            return True
        return super().eventFilter(obj, event)

    def _current_state(self) -> TimelineViewportState:
        """Snapshot current viewport state (delegates to ``viewport``)."""
        return timeline_viewport.current_state(self)

    def _recomputeFittedState(self) -> TimelineViewportState:
        """Current state with zoom clamped to min_zoom if fitted."""
        return timeline_viewport.recompute_fitted_state(self)

    def _commitState(self, nxt: TimelineViewportState, source: str = "") -> bool:
        """Diff ``nxt`` against ``self._state`` and emit typed signals.

        Fail-closed after teardown: no ``updateGeometry``/``update``, no
        emits once ``_destroyed`` or C++-deleted (same gate as
        ``layout_settle``/``flush_wheel_zoom``).
        """
        # PySide6-stubs lags shiboken6.isValid — narrow ignore per AGENTS.md.
        if getattr(self, "_destroyed", False) or not sip.isValid(self):  # type: ignore[attr-defined]
            return False
        return timeline_viewport.commit_state(self, nxt, source)

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        timeline_interaction.resize_event(self, event)

    def _on_host_scroll(self, *_args) -> None:
        """Host scrollbar step (delegates to ``interaction.host_scroll``)."""
        timeline_interaction.host_scroll(self, *_args)

    def _rebuild_row_layout(self):
        timeline_layout.rebuild_row_layout(self)

    def _group_key(self, group) -> str:
        return timeline_layout.group_key(group)

    def _is_group_collapsed(self, group) -> bool:
        return timeline_layout.is_group_collapsed(self, group)

    def _toggle_group_collapsed(self, group) -> None:
        timeline_layout.toggle_group_collapsed(self, group)

    def _group_accent_color(self, group) -> QColor:
        return timeline_layout.group_accent_color(self, group)

    def _group_header_rect(self, left: float, top: float) -> QRectF:
        return timeline_layout.group_header_rect(self, left, top)

    def _group_chevron_rect(self, header_rect: QRectF) -> QRectF:
        return timeline_layout.group_chevron_rect(header_rect)

    def _group_toggle_hit(self, pos) -> Any | None:
        return timeline_layout.group_toggle_hit(self, pos)

    def _visible_channels(self, track):
        return timeline_layout.visible_channels(self, track)

    def set_data(
        self,
        snapshots=None,
        fps: int | None = None,
        timeline_model=None,
        duration: float | None = None,
        *,
        source=None,
    ):
        """Feed timeline content (orchestration in ``interaction.ingest_data``)."""
        timeline_interaction.ingest_data(
            self,
            snapshots,
            fps=fps,
            timeline_model=timeline_model,
            duration=duration,
            source=source,
        )

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
        """Bulk generation replace: one store update, one prune, one paint.

        The batch path — a single :func:`interaction.prune_thumbnails`
        full pass over the merged store, never per-key work. No-op after
        teardown (no ``update()`` on a dead widget).
        """
        if not timeline_interaction.is_alive(self):
            return
        self._thumbnails.update(thumbnails)
        self._thumb_indices = sorted(self._thumbnails.keys())
        self._prune_thumbnails()
        if self.has_snapshots():
            self._last_min_zoom = timeline_viewport.calculate_min_zoom(self)
            self._refresh_viewport_state()
        self.update()

    def add_thumbnail(self, index: int, pixmap: QPixmap):
        """Single-index upsert: the prune fast path keeps streams linear.

        Passes the index as the prune hint, so an unchanged keep-window
        resolves keep-or-drop in O(1) with no store scan; any geometry
        change transparently falls back to one full pass. No-op after
        teardown.
        """
        if not timeline_interaction.is_alive(self):
            return
        self._thumbnails[index] = pixmap
        if not self._thumb_indices or index > self._thumb_indices[-1]:
            self._thumb_indices.append(index)
        elif index not in self._thumb_indices:
            self._thumb_indices.append(index)
            self._thumb_indices.sort()
        timeline_interaction.prune_thumbnails(self, _hint_index=int(index))
        if self.has_snapshots():
            self._last_min_zoom = timeline_viewport.calculate_min_zoom(self)
            self._refresh_viewport_state()
        self.update()

    def _prune_thumbnails(self) -> None:
        """Enforce the thumbnail store bound (policy in ``interaction``)."""
        timeline_interaction.prune_thumbnails(self)

    def clear_thumbnails(self):
        if not timeline_interaction.is_alive(self):
            # Still drop the store (owns no paint), but never touch paint
            # or the keep-cache of a torn-down widget beyond clearing.
            self._thumbnails.clear()
            self._thumb_indices.clear()
            self._prune_keep_cache = None
            return
        self._thumbnails.clear()
        self._thumb_indices.clear()
        self._prune_keep_cache = None
        self.update()

    def has_snapshots(self) -> bool:
        return self._duration > 0.0 or bool(self._snapshots)

    def get_total_duration(self) -> float:
        return max(0.0, float(self._duration))

    def get_pixels_per_second(self):
        """Current px/sec (delegates to ``viewport.pixels_per_second_for_zoom``)."""
        return timeline_viewport.pixels_per_second_for_zoom(self, self._zoom_level)

    def set_zoom(self, zoom: float, *, anchor: str = "cursor") -> None:
        """Public zoom setter; ``anchor`` selects the commit cursor policy."""
        if anchor not in ("cursor", "center"):
            raise ValueError(f"anchor must be 'cursor' or 'center', got {anchor!r}")
        if getattr(self, "_destroyed", False) or not sip.isValid(self):  # type: ignore[attr-defined]
            return
        try:
            new_zoom = timeline_viewport.clamp_zoom(self, zoom)
        except Exception:
            return
        if abs(float(new_zoom) - float(self._zoom_level)) <= 1e-4:
            return
        try:
            self._apply_api_zoom(float(new_zoom), anchor=anchor)
        except Exception:
            return

    def set_pps(self, pps: float, *, anchor: str = "cursor") -> None:
        """Public px/sec setter: ``zoom = pps / base_pps``, then ``set_zoom``."""
        try:
            base = float(timeline_viewport.get_base_pixels_per_second(self))
        except Exception:
            return
        if base <= 0:
            return
        self.set_zoom(float(pps) / base, anchor=anchor)

    def _apply_api_zoom(self, new_zoom: float, *, anchor: str = "cursor") -> None:
        """API zoom commit through the unified ``viewport.commit_zoom``."""
        if anchor not in ("cursor", "center"):
            raise ValueError(f"anchor must be 'cursor' or 'center', got {anchor!r}")
        timeline_viewport.commit_zoom(self, float(new_zoom), cursor_x=None, source="apiSetZoom")

    def get_visible_thumbnail_frame_indices(self, overscan_blocks: int = 1) -> list[int]:
        return timeline_viewport.get_visible_thumbnail_frame_indices(
            self,
            overscan_blocks=overscan_blocks,
        )

    def fit_view(self):
        timeline_viewport.fit_view(self)
        # Silent write-through: keep the committed snapshot fresh without
        # emitting (paths that need an emit go through _commitState).
        # No-op until the first _commitState, so the old=None first-commit
        # emit is preserved.
        self._refresh_viewport_state()

    def update_layout_width(self):
        # Called on every host-dialog resizeEvent tick; defer the actual
        # recompute to settle instead of redoing it synchronously per tick.
        self._layout_settle.ping()

    def _on_scale_changed(self, _factor: float) -> None:
        timeline_interaction.apply_metric_scale(self)
        self._rebuild_row_layout()
        timeline_layout.ensure_preferred_height(self)
        timeline_viewport.update_fixed_width(self)
        timeline_viewport.update_vertical_scrollbar(self)
        self.update()

    def _show_hover_tooltip(self) -> None:
        timeline_viewport.show_hover_tooltip(self)

    def _on_layout_settle(self):
        """Settle-gate flush (delegates to ``interaction.layout_settle``)."""
        timeline_interaction.layout_settle(self)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta == 0:
                return
            try:
                cursor_x = float(event.position().x())
            except Exception:
                cursor_x = float(self.LEFT_GUTTER)
            # Coalesce: accumulate ticks, flush once per frame window.
            # Never touches _needs_fit_view — settle owns fit_view.
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
                    timeline_viewport.update_vertical_scrollbar(self)
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
                        timeline_interaction.viewport_geometry_changed(self, "wheelHorizontal")
                except Exception:
                    pass

    def _flush_wheel_zoom(self) -> None:
        """Flush accumulated Ctrl+wheel ticks (core in ``interaction``)."""
        timeline_interaction.flush_wheel_zoom(self)

    def keyPressEvent(self, event):
        key = event.key()
        mods = event.modifiers()

        if key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            # Up/Down are reserved for routing between controls (row/panel
            # navigation, see NavigationManager/ToolbarRowsSection) -- never
            # frame-stepping here. Leave the event unaccepted (don't call
            # super().keyPressEvent(), which is what would consume it) so it
            # stays available for routing (Slider precedent, NAVIGATION.md).
            event.ignore()
            return

        if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.deletePressed.emit()
            event.accept()
            return

        if key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            if self._total_frames <= 0:
                event.ignore()
                return
            step = (
                timeline_interaction.KEY_SHIFT_STEP_FRAMES
                if mods & Qt.KeyboardModifier.ShiftModifier
                else timeline_interaction.KEY_STEP_FRAMES
            )
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

        if key in (Qt.Key.Key_PageUp, Qt.Key.Key_PageDown):
            # SpinBox precedent: PageUp/PageDown step where Left/Right must
            # stay untouched -- here they step 10 frames (nothing else claims
            # them). set_current_frame clamps at the store edges.
            if self._total_frames <= 0:
                event.ignore()
                return
            page = timeline_interaction.KEY_PAGE_STEP_FRAMES
            step = -page if key == Qt.Key.Key_PageUp else page
            self.set_current_frame(self._current_index + step)
            self.headMoved.emit(self._current_index)
            event.accept()
            return

        if key == Qt.Key.Key_Space:
            # Bare Space toggles playback via playPauseRequested (the host
            # wires it to toggle_playback); any modifier falls through to
            # the base class so host shortcuts keep working.
            if mods != Qt.KeyboardModifier.NoModifier:
                super().keyPressEvent(event)
                return
            self.playPauseRequested.emit()
            event.accept()
            return

        if key in (Qt.Key.Key_Plus, Qt.Key.Key_Minus):
            # Keyboard zoom: Plus zooms in, Minus zooms out by one wheel-tick
            # factor (1.25) around the viewport center (no cursor position on
            # a key event). Only bare and keypad-modified keys zoom -- other
            # modifiers fall through so host shortcuts keep working.
            # Clamping/silence comes from set_zoom itself.
            if mods not in (
                Qt.KeyboardModifier.NoModifier,
                Qt.KeyboardModifier.KeypadModifier,
            ):
                super().keyPressEvent(event)
                return
            current = float(self._zoom_level)
            # Keyboard zoom: one wheel-tick factor (canonical
            # ``viewport.WHEEL_ZOOM_FACTOR``) around the viewport center.
            if key == Qt.Key.Key_Plus:
                self.set_zoom(current * timeline_viewport.WHEEL_ZOOM_FACTOR, anchor="center")
            else:
                self.set_zoom(current / timeline_viewport.WHEEL_ZOOM_FACTOR, anchor="center")
            event.accept()
            return

        super().keyPressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        timeline_render.paint_timeline(self, painter, event)
        painter.end()
        # Damage-independent hover: rebuild the hit-set over the full row
        # window so partial repaints leave the same points as full ones.
        timeline_interaction.rebuild_hover_points(self)

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
        """Move the playhead (core in ``interaction.set_current_frame``)."""
        timeline_interaction.set_current_frame(self, index)

    def _on_playhead_frame(self, value) -> None:
        """Animation tick (core in ``interaction.playhead_frame``)."""
        timeline_interaction.playhead_frame(self, value)

    def _refresh_viewport_state(self) -> None:
        """Silently re-snapshot ``self._state`` (no emits; body in ``viewport``)."""
        timeline_viewport.refresh_viewport_state(self)

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
