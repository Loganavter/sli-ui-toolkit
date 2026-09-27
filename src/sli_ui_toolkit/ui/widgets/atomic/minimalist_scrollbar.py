from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QEvent, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QRegion, QWheelEvent
from PySide6.QtWidgets import QApplication, QScrollArea, QScrollBar, QWidget

from sli_ui_toolkit.core.debug_flags import any_flag
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.helpers import register_hover_widget

_sdbg_logger = logging.getLogger("sli_ui_toolkit.scrollbar")


def _scrollbar_debug_enabled() -> bool:
    return any_flag("SLI_SCROLLBAR_DEBUG", "IMGSLI_SCROLLBAR_DEBUG")


def _ensure_sdbg_handler() -> None:
    # Rely on toolkit-wide logging configuration (core.logging) instead of
    # installing a direct StreamHandler(sys.stderr) per widget. This avoids
    # duplicate handlers and respects host logging setup. No-op for compat.
    return


def sdbg(message: str) -> None:
    if not _scrollbar_debug_enabled():
        return
    _ensure_sdbg_handler()
    _sdbg_logger.debug("[scrollbar] " + message)

# The bar's fixed widget width — the one public geometry number composites
# need (positioning/reserving). Everything else (gap, margin, thumb
# thicknesses, track padding) is internal to the bar's look and layout and
# stays module-private; the single public value is
# ``overlay_scrollbar_max_inset()`` — max width + gap + margin.
MINIMAL_SCROLLBAR_WIDTH = 10
_MINIMAL_SCROLLBAR_GAP = 0
_OVERLAY_INSET_MARGIN = 4

# Sentinel distinguishing "kwarg not passed" from an explicit ``None``
# (``None`` is a meaningful policy value: a persistent, never-hiding bar).
_UNSET: Any = object()


@dataclass
class OverlayScrollbarConfig:
    """Declarative scrollbar policy — alternative to individual kwargs.

    Mirrors ``ButtonConfig``: pass as ``OverlayScrollArea(config=...)`` /
    ``ListPanel(scrollbar_config=...)`` for presets, or tweak one-offs
    through the matching ``set_*`` setters. All fields apply live via
    ``set_scrollbar_config``.
    """

    reserve_space: bool = True
    reserve_width: int = MINIMAL_SCROLLBAR_WIDTH
    gap: int = _MINIMAL_SCROLLBAR_GAP
    auto_hide_seconds: float | None = 1.2

    def to_kwargs(self) -> dict[str, Any]:
        """Field values keyed by the ``OverlayScrollArea.__init__`` kwarg."""
        return {
            "reserve_scrollbar_space": self.reserve_space,
            "scrollbar_width": self.reserve_width,
            "scrollbar_gap": self.gap,
            "scrollbar_auto_hide": self.auto_hide_seconds,
        }
_MINIMAL_SCROLLBAR_THICKNESS_IDLE = 4
_MINIMAL_SCROLLBAR_THICKNESS_HOVER = 6
_MINIMAL_SCROLLBAR_THICKNESS_DRAG = MINIMAL_SCROLLBAR_WIDTH
_MINIMAL_SCROLLBAR_HANDLE_PADDING = 8

# Wheel-scroll glide (Chrome/Firefox-style): deltas accumulate into a target
# scroll position and the viewport eases toward it at tick rate, stopping
# when the target is reached. The timer only runs while a glide is in flight.
_SCROLL_TICK_MS = 16
_SCROLL_EASE = 0.14
_SCROLL_MIN_NOTCH_PX = 40

class MinimalistScrollBar(QScrollBar):
    def __init__(self, orientation=Qt.Orientation.Vertical, parent=None):
        super().__init__(orientation, parent)
        self.theme_manager = ThemeManager.get_instance()
        self._is_dragging = False
        self._drag_start_offset = 0
        self._idle_thickness = _MINIMAL_SCROLLBAR_THICKNESS_IDLE
        self._hover_thickness = _MINIMAL_SCROLLBAR_THICKNESS_HOVER
        self._drag_thickness = _MINIMAL_SCROLLBAR_THICKNESS_DRAG
        self._minimum_handle_length = 32
        self._hovered = False
        self._idle_color = QColor()
        self._hover_color = QColor()
        # Bar visuals switch instantly (no interpolation): thickness and
        # visibility snap to their state targets on hover/drag/idle.
        self._anim_thickness = float(self._idle_thickness)
        self._anim_alpha = 1.0
        # Idle auto-hide (opt-in): after `_auto_hide_seconds` without scroll
        # activity the bar hides instantly; any value change / hover / drag
        # brings it back. None keeps the bar always visible.
        self._auto_hide_seconds: float | None = None
        self._idle_timer = QTimer(self)
        self._idle_timer.setSingleShot(True)
        self._idle_timer.timeout.connect(self._on_idle_timeout)
        self._update_colors()
        self.theme_manager.theme_changed.connect(self._update_colors)
        self.valueChanged.connect(self._on_activity)
        self.setMouseTracking(True)
        # TextCanvas (inside TextView) sets IBeam while editing — without an
        # explicit cursor the bar would inherit the parent's shape on some
        # platforms and show IBeam over the thumb/track. Keep it Arrow.
        self.setCursor(Qt.CursorShape.ArrowCursor)
        register_hover_widget(self)

    def _update_colors(self):
        if self.theme_manager.is_dark():
            self._idle_color = QColor(255, 255, 255, 60)
            self._hover_color = QColor(255, 255, 255, 90)
        else:
            self._idle_color = QColor(0, 0, 0, 70)
            self._hover_color = QColor(0, 0, 0, 100)
        self.update()

    def paintEvent(self, event):
        if self.minimum() == self.maximum():
            return
        if self._anim_alpha <= 0.01:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        handle_rect = self._get_handle_rect()
        if handle_rect.isEmpty():
            return
        if self._is_dragging:
            current_color = QColor(self.theme_manager.get_color("accent"))
        elif self._hovered:
            current_color = QColor(self._hover_color)
        else:
            current_color = QColor(self._idle_color)
        current_color.setAlpha(int(current_color.alpha() * self._anim_alpha))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(current_color)
        radius = min(handle_rect.width(), handle_rect.height()) / 2.0
        painter.drawRoundedRect(handle_rect, radius, radius)

    def _get_handle_rect(self):
        if self.minimum() == self.maximum():
            return QRect()
        current_thickness = self._anim_thickness
        padding = _MINIMAL_SCROLLBAR_HANDLE_PADDING
        total_range = self.maximum() - self.minimum() + self.pageStep()
        scroll_range = self.maximum() - self.minimum()
        if total_range <= 0:
            return QRect()
        if self.orientation() == Qt.Orientation.Vertical:
            groove_len = self.height() - padding * 2
            if groove_len <= 0:
                return QRect()
            handle_len = max(
                (self.pageStep() / total_range) * groove_len,
                self._minimum_handle_length,
            )
            track_len = groove_len - handle_len
            handle_pos_rel = (((self.value() - self.minimum()) / scroll_range * track_len) if scroll_range > 0 else 0)
            handle_y = handle_pos_rel + padding
            handle_x = (self.width() - current_thickness) // 2
            return QRect(int(handle_x), int(handle_y), int(current_thickness), int(handle_len))
        groove_len = self.width() - padding * 2
        if groove_len <= 0:
            return QRect()
        handle_len = max(
            (self.pageStep() / total_range) * groove_len,
            self._minimum_handle_length,
        )
        track_len = groove_len - handle_len
        handle_pos_rel = (((self.value() - self.minimum()) / scroll_range * track_len) if scroll_range > 0 else 0)
        handle_x = handle_pos_rel + padding
        handle_y = (self.height() - current_thickness) // 2
        return QRect(int(handle_x), int(handle_y), int(handle_len), int(current_thickness))

    def mousePressEvent(self, event):
        handle_rect = self._get_handle_rect()
        pos_val = event.pos().y() if self.orientation() == Qt.Orientation.Vertical else event.pos().x()
        handle_start = handle_rect.y() if self.orientation() == Qt.Orientation.Vertical else handle_rect.x()
        sdbg(
            f"press widget={self.__class__.__name__} parent={self.parentWidget().__class__.__name__ if self.parentWidget() else None} "
            f"pos={event.position().toPoint()} rect={self.rect()} handle={handle_rect} value={self.value()}"
        )
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if handle_rect.contains(event.pos()):
            sdbg(f"press -> on-handle (start drag) value={self.value()}")
            self._is_dragging = True
            self._drag_start_offset = pos_val - handle_start
            self._update_state_targets()
            self._poke()
            self.update()
            event.accept()
            return
        padding = _MINIMAL_SCROLLBAR_HANDLE_PADDING
        handle_len = handle_rect.height() if self.orientation() == Qt.Orientation.Vertical else handle_rect.width()
        track_len = ((self.height() if self.orientation() == Qt.Orientation.Vertical else self.width()) - padding * 2 - handle_len)
        new_pos_click = pos_val - padding - (handle_len / 2)
        scroll_range = self.maximum() - self.minimum()
        if track_len > 0:
            new_value = self.minimum() + (new_pos_click / track_len) * scroll_range
            sdbg(f"press -> on-track jump {self.value()} -> {int(new_value)}")
            self.setValue(int(new_value))
            self._is_dragging = True
            self._drag_start_offset = handle_len / 2
            self._update_state_targets()
            self._poke()
            self.update()
        event.accept()

    def mouseMoveEvent(self, event):
        sdbg(
            f"move widget={self.__class__.__name__} dragging={self._is_dragging} "
            f"pos={event.position().toPoint()} rect={self.rect()} value={self.value()} buttons={event.buttons()}"
        )
        if self._is_dragging:
            padding = _MINIMAL_SCROLLBAR_HANDLE_PADDING
            if self.orientation() == Qt.Orientation.Vertical:
                handle_len = self._get_handle_rect().height()
                track_len = (self.height() - padding * 2) - handle_len
                mouse_pos = event.pos().y()
            else:
                handle_len = self._get_handle_rect().width()
                track_len = (self.width() - padding * 2) - handle_len
                mouse_pos = event.pos().x()
            mouse_pos_in_track = mouse_pos - padding - self._drag_start_offset
            scroll_range = self.maximum() - self.minimum()
            if track_len > 0:
                new_value = self.minimum() + (mouse_pos_in_track / track_len) * scroll_range
                self.setValue(int(new_value))
        event.accept()

    def mouseReleaseEvent(self, event):
        sdbg(
            f"release widget={self.__class__.__name__} dragging={self._is_dragging} "
            f"pos={event.position().toPoint()} value={self.value()}"
        )
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_dragging = False
            self._update_state_targets()
            self._poke()
            self.update()
            event.accept()

    def enterEvent(self, event):
        sdbg(f"enter widget={self.__class__.__name__} rect={self.rect()}")
        self.setHoverActive(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        sdbg(f"leave widget={self.__class__.__name__} rect={self.rect()}")
        self.setHoverActive(False)
        self._restart_idle_timer()
        super().leaveEvent(event)

    def hoverHitTest(self, pos) -> bool:
        point = pos.toPoint() if hasattr(pos, "toPoint") else pos
        result = self.rect().contains(point)
        sdbg(f"hoverHitTest widget={self.__class__.__name__} pos={point} rect={self.rect()} -> {result}")
        return result

    def setHoverActive(self, active: bool) -> None:
        active = bool(active)
        if self._hovered != active:
            self._hovered = active
            self._update_state_targets()
            if active:
                self._poke()
            self.update()

    # -------- instant visuals / auto-hide --------

    def _update_state_targets(self) -> None:
        if self._is_dragging:
            self._anim_thickness = float(self._drag_thickness)
        elif self._hovered:
            self._anim_thickness = float(self._hover_thickness)
        else:
            self._anim_thickness = float(self._idle_thickness)
        self.update()

    def _restart_idle_timer(self) -> None:
        if self._auto_hide_seconds is None:
            return
        self._idle_timer.start(int(self._auto_hide_seconds * 1000))

    def _on_idle_timeout(self) -> None:
        if not self.isVisible():
            return
        if self._is_dragging or self._hovered:
            self._restart_idle_timer()
            return
        self._anim_alpha = 0.0
        super().setVisible(False)
        self.update()

    def _on_activity(self, *_args) -> None:
        # Scroll activity (mirrored value changes), hover, or drag keeps the
        # bar around; it also re-shows a hidden bar.
        if self._auto_hide_seconds is None:
            return
        if not self.isVisible():
            super().setVisible(True)
        self._anim_alpha = 1.0
        self.update()
        self._restart_idle_timer()

    def _poke(self) -> None:
        if self._auto_hide_seconds is None:
            return
        if not self.isVisible():
            super().setVisible(True)
        self._anim_alpha = 1.0
        self.update()
        self._restart_idle_timer()

    def set_auto_hide(self, seconds: float | None) -> None:
        """Hide the bar after ``seconds`` without scroll activity.

        Value changes (mirrored from the scroll area), hovering, and
        dragging all count as activity and re-show a hidden bar. ``None``
        (default) keeps the bar always visible.
        """
        self._auto_hide_seconds = float(seconds) if seconds is not None else None
        if self._auto_hide_seconds is None:
            self._idle_timer.stop()
            if not self.isVisible():
                super().setVisible(True)
            self._anim_alpha = 1.0
            self.update()
        else:
            self._restart_idle_timer()

    def set_animated_visible(self, visible: bool) -> None:
        """Show/hide instantly (kept name for caller compatibility)."""
        if visible:
            if not self.isVisible():
                super().setVisible(True)
            self._anim_alpha = 1.0
            self.update()
            self._restart_idle_timer()
        else:
            if not self.isVisible():
                return
            self._anim_alpha = 0.0
            super().setVisible(False)
            self.update()

def overlay_scrollbar_max_inset(
    bar_width: int = MINIMAL_SCROLLBAR_WIDTH,
    bar_gap: int = _MINIMAL_SCROLLBAR_GAP,
) -> int:
    """The overlay inset when the bar is shown: max bar width + gap + margin.

    The single value ``overlay_scrollbar_inset()`` reports live — this is
    the always-on static estimate for callers that must reserve space before
    the bar's visibility (and thus the live value) is known, e.g. column
    counting that depends on the width but also determines overflow.
    """
    return bar_width + bar_gap + _OVERLAY_INSET_MARGIN


class OverlayScrollArea(QScrollArea):
    def __init__(
        self,
        parent=None,
        *,
        config: OverlayScrollbarConfig | None = None,
        reserve_scrollbar_space: bool | None = None,
        scrollbar_width: int | None = None,
        scrollbar_gap: int | None = None,
        scrollbar_auto_hide: Any = _UNSET,
        corner_radius: int | None = None,
        widget_resizable: bool | None = None,
    ):
        """Scroll area with an overlay-style thin scrollbar.

        ``config`` carries the scrollbar policy preset; individual kwargs
        override its fields (``None`` falls back to the config value —
        except ``scrollbar_auto_hide``, where ``None`` is meaningful and
        means "persistent bar", so omit it to fall back).

        Both axes get an overlay bar (vertical + horizontal); each appears
        only while its axis overflows. ``widget_resizable=False`` keeps
        fixed-size content (the area never stretches it to the viewport).
        """
        super().__init__(parent)
        cfg = config or OverlayScrollbarConfig()
        self._corner_radius = 8 if corner_radius is None else max(0, int(corner_radius))
        self._reserve_scrollbar_space = (
            cfg.reserve_space if reserve_scrollbar_space is None else bool(reserve_scrollbar_space)
        )
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        self.setWidgetResizable(False if widget_resizable is False else True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.custom_v_scrollbar = MinimalistScrollBar(Qt.Orientation.Vertical, self)
        self.custom_h_scrollbar = MinimalistScrollBar(Qt.Orientation.Horizontal, self)
        self._scrollbar_width = max(
            0, int(cfg.reserve_width if scrollbar_width is None else scrollbar_width)
        )
        self._scrollbar_gap = max(
            0, int(cfg.gap if scrollbar_gap is None else scrollbar_gap)
        )
        self._stored_items_count = 0
        self._update_timer = QTimer(self)
        self._update_timer.setSingleShot(True)
        self._update_timer.timeout.connect(self._delayed_update_scrollbar)
        # Wheel glide state: an accumulated target the ticker eases toward.
        self._scroll_target: int | None = None
        self._syncing_scroll = False
        self._scroll_timer = QTimer(self)
        self._scroll_timer.setInterval(_SCROLL_TICK_MS)
        self._scroll_timer.timeout.connect(self._scroll_tick)
        self.verticalScrollBar().valueChanged.connect(self.custom_v_scrollbar.setValue)
        self.verticalScrollBar().valueChanged.connect(self._on_native_scroll_changed)
        self.verticalScrollBar().rangeChanged.connect(self.custom_v_scrollbar.setRange)
        self.verticalScrollBar().rangeChanged.connect(lambda *_: self._sync_steps_from_native())
        self.horizontalScrollBar().valueChanged.connect(self.custom_h_scrollbar.setValue)
        self.horizontalScrollBar().rangeChanged.connect(self.custom_h_scrollbar.setRange)
        self.horizontalScrollBar().rangeChanged.connect(lambda *_: self._sync_h_steps_from_native())
        # Custom→native: dragging the floating thumb must move content
        # (previously the thumb set only its own value — dead drag).
        # Same-value setValue() never re-emits, plus the _syncing_scroll
        # guard, so no feedback loop.
        self.custom_v_scrollbar.valueChanged.connect(self._on_custom_v_changed)
        self.custom_h_scrollbar.valueChanged.connect(self._on_custom_h_changed)
        self.custom_v_scrollbar.set_auto_hide(
            cfg.auto_hide_seconds if scrollbar_auto_hide is _UNSET else scrollbar_auto_hide
        )
        self.custom_h_scrollbar.set_auto_hide(
            cfg.auto_hide_seconds if scrollbar_auto_hide is _UNSET else scrollbar_auto_hide
        )
        self.custom_v_scrollbar.setVisible(False)
        self.custom_h_scrollbar.setVisible(False)
        self._sync_steps_from_native()
        self._sync_h_steps_from_native()
        self._apply_viewport_mask()
        self.viewport().installEventFilter(self)

    def _on_custom_v_changed(self, value: int) -> None:
        if self._syncing_scroll:
            return
        try:
            self.verticalScrollBar().setValue(int(value))
        except Exception:
            pass

    def _on_custom_h_changed(self, value: int) -> None:
        if self._syncing_scroll:
            return
        try:
            self.horizontalScrollBar().setValue(int(value))
        except Exception:
            pass

    def setWidget(self, widget):
        previous = self.widget()
        if previous is not None:
            previous.removeEventFilter(self)
        super().setWidget(widget)
        if widget is not None:
            widget.installEventFilter(self)
        self._queue_scrollbar_sync()

    def eventFilter(self, watched, event):
        if watched in (self.viewport(), self.widget()) and event.type() in (
            QEvent.Type.Resize,
            QEvent.Type.Show,
            QEvent.Type.LayoutRequest,
        ):
            self._queue_scrollbar_sync()
        return super().eventFilter(watched, event)

    def set_reserve_scrollbar_space(self, reserve: bool) -> None:
        self._reserve_scrollbar_space = bool(reserve)
        self._update_scrollbar_visibility()

    def reserve_scrollbar_space(self) -> bool:
        return self._reserve_scrollbar_space

    def set_scrollbar_width(self, width: int) -> None:
        """Reserved gutter width (px) for the overlay bar.

        Takes effect on the next visibility sync; when content overflows
        the viewport keeps this many px clear on the right.
        """
        width = max(0, int(width))
        if self._scrollbar_width == width:
            return
        self._scrollbar_width = width
        self._update_scrollbar_visibility()

    def scrollbar_width(self) -> int:
        return self._scrollbar_width

    def set_scrollbar_gap(self, gap: int) -> None:
        """Gap (px) between the bar and the scroll area's right edge."""
        gap = max(0, int(gap))
        if self._scrollbar_gap == gap:
            return
        self._scrollbar_gap = gap
        self._update_scrollbar_visibility()

    def scrollbar_gap(self) -> int:
        return self._scrollbar_gap

    def set_scrollbar_auto_hide(self, seconds: float | None) -> None:
        """Idle auto-hide for the overlay bars (default 1.2s; ``None`` keeps
        them always visible once shown)."""
        self.custom_v_scrollbar.set_auto_hide(seconds)
        self.custom_h_scrollbar.set_auto_hide(seconds)

    def scrollbar_auto_hide_seconds(self) -> float | None:
        return self.custom_v_scrollbar._auto_hide_seconds

    def set_scrollbar_config(self, config: OverlayScrollbarConfig) -> None:
        """Apply a whole scrollbar policy at once (live)."""
        self.set_reserve_scrollbar_space(config.reserve_space)
        self.set_scrollbar_width(config.reserve_width)
        self.set_scrollbar_gap(config.gap)
        self.set_scrollbar_auto_hide(config.auto_hide_seconds)

    def scrollbar_config(self) -> OverlayScrollbarConfig:
        """Current scrollbar policy as a config object."""
        return OverlayScrollbarConfig(
            reserve_space=self._reserve_scrollbar_space,
            reserve_width=self._scrollbar_width,
            gap=self._scrollbar_gap,
            auto_hide_seconds=self.custom_v_scrollbar._auto_hide_seconds,
        )

    def overlay_scrollbar_inset(self) -> int:
        """Content-side clearance (px) content must leave for the bar.

        Non-zero only when ``reserve_scrollbar_space`` is off (the bar
        floats over the viewport instead of getting its own margin) and
        the bar is actually visible (content overflows). Always a single
        fixed value — the bar's maximum width (the state it takes while
        being dragged) plus a small margin — so hosts never need to chase
        the thumb's idle/hover/drag thickness. Callers that lay content
        out manually inside the scroll area can use this to avoid a fixed
        guess at the bar's width, and to skip the inset entirely when
        nothing scrolls.
        """
        if self._reserve_scrollbar_space or not self.custom_v_scrollbar.isVisible():
            return 0
        return self._scrollbar_width + self._scrollbar_gap + _OVERLAY_INSET_MARGIN

    def overlay_horizontal_scrollbar_inset(self) -> int:
        """Bottom clearance for the floating horizontal bar (mirror of
        :meth:`overlay_scrollbar_inset`)."""
        if self._reserve_scrollbar_space or not self.custom_h_scrollbar.isVisible():
            return 0
        return self._scrollbar_width + self._scrollbar_gap + _OVERLAY_INSET_MARGIN

    def set_corner_radius(self, radius: int):
        radius = max(0, int(radius))
        if self._corner_radius == radius:
            return
        self._corner_radius = radius
        self._apply_viewport_mask()

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        """Glide the vertical scroll position to an accumulated target.

        Wheel deltas accumulate Chrome/Firefox-style and the ticker eases
        toward the target instead of jumping in discrete steps. A new
        ``ScrollBegin`` phase (touchpads) re-bases the target on the live
        position so leftover glide never fights a fresh gesture.
        """
        native = self.verticalScrollBar()
        if native.minimum() == native.maximum():
            event.ignore()
            return
        if event.phase() == Qt.ScrollPhase.ScrollBegin:
            self._scroll_target = native.value()
        pixel = event.pixelDelta().y()
        if pixel:
            delta = -int(round(pixel))
        else:
            angle = event.angleDelta().y()
            if not angle:
                event.ignore()
                return
            lines = QApplication.wheelScrollLines()
            base = max(1, native.singleStep())
            if lines == 0:
                base = max(base, int(self.viewport().height() * 0.8))
            else:
                base = max(base * lines, _SCROLL_MIN_NOTCH_PX)
            # Qt convention: positive angleDelta (wheel up / finger up) moves
            # the viewport toward the top, i.e. decreases the scroll value.
            delta = -int(round(angle / 120 * base))
        current = (
            self._scroll_target
            if self._scroll_target is not None
            else native.value()
        )
        target = max(native.minimum(), min(current + delta, native.maximum()))
        if target != native.value():
            self._scroll_target = target
            if not self._scroll_timer.isActive():
                self._scroll_timer.start()
        event.accept()

    def _on_native_scroll_changed(self, _value: int) -> None:
        # An external setValue (thumb drag, keyboard, programmatic scroll)
        # cancels an in-flight wheel glide so the bar never fights it.
        if not self._syncing_scroll and self._scroll_target is not None:
            self._scroll_target = None
            self._scroll_timer.stop()

    def _scroll_tick(self) -> None:
        native = self.verticalScrollBar()
        target = self._scroll_target
        if target is None:
            self._scroll_timer.stop()
            return
        value = native.value()
        remaining = target - value
        if abs(remaining) <= 0.5:
            self._syncing_scroll = True
            try:
                native.setValue(target)
            finally:
                self._syncing_scroll = False
            self._scroll_target = None
            self._scroll_timer.stop()
            return
        step = remaining * _SCROLL_EASE
        if abs(step) < 1:
            step = 1 if step > 0 else -1
        self._syncing_scroll = True
        try:
            native.setValue(value + int(step))
        finally:
            self._syncing_scroll = False

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_scrollbars()
        self._sync_steps_from_native()
        self._sync_h_steps_from_native()
        self._apply_viewport_mask()
        self._queue_scrollbar_sync()

    def _queue_scrollbar_sync(self):
        self._update_timer.start(0)

    def _apply_viewport_mask(self):
        viewport = self.viewport()
        if viewport is None:
            return
        if self._corner_radius <= 0:
            viewport.clearMask()
            return
        path = QPainterPath()
        path.addRoundedRect(QRectF(viewport.rect()), self._corner_radius, self._corner_radius)
        region = QRegion(path.toFillPolygon().toPolygon())
        viewport.setMask(region)

    def _sync_steps_from_native(self):
        native = self.verticalScrollBar()
        self.custom_v_scrollbar.blockSignals(True)
        self.custom_v_scrollbar.setRange(native.minimum(), native.maximum())
        self.custom_v_scrollbar.setPageStep(native.pageStep())
        self.custom_v_scrollbar.setSingleStep(native.singleStep())
        self.custom_v_scrollbar.setValue(native.value())
        self.custom_v_scrollbar.blockSignals(False)
        self._update_scrollbar_visibility()

    def _sync_h_steps_from_native(self):
        native = self.horizontalScrollBar()
        self.custom_h_scrollbar.blockSignals(True)
        self.custom_h_scrollbar.setRange(native.minimum(), native.maximum())
        self.custom_h_scrollbar.setPageStep(native.pageStep())
        self.custom_h_scrollbar.setSingleStep(native.singleStep())
        self.custom_h_scrollbar.setValue(native.value())
        self.custom_h_scrollbar.blockSignals(False)
        self._update_scrollbar_visibility()

    def _update_scrollbar_visibility(self, min_items_count=0):
        native_v = self.verticalScrollBar()
        native_h = self.horizontalScrollBar()
        v_show = native_v.maximum() > native_v.minimum()
        h_show = native_h.maximum() > native_h.minimum()
        sdbg(
            f"OverlayScrollArea visibility v_max={native_v.maximum()} v_min={native_v.minimum()} "
            f"h_max={native_h.maximum()} h_min={native_h.minimum()} "
            f"v_show={v_show} h_show={h_show} reserve={self._reserve_scrollbar_space}"
        )
        self.custom_v_scrollbar.set_animated_visible(v_show)
        self.custom_h_scrollbar.set_animated_visible(h_show)
        # Reserve the bar's gap only while that axis actually overflows.
        # When everything fits there is no bar to make room for, so the
        # viewport takes the full size instead of holding a dead gutter.
        # Margins only ever grow the other axis's need (a narrower viewport
        # cannot un-overflow horizontal, a shorter one cannot un-overflow
        # vertical), so no oscillate at the fits boundary.
        try:
            _rm = self._scrollbar_width if (self._reserve_scrollbar_space and v_show) else 0
            _bm = self._scrollbar_width if (self._reserve_scrollbar_space and h_show) else 0
            self.setViewportMargins(0, 0, _rm, _bm)
        except Exception:
            pass
        self._position_scrollbars()

    def _position_scrollbars(self):
        self._position_v_scrollbar()
        self._position_h_scrollbar()

    def _position_scrollbar(self):
        self._position_v_scrollbar()

    def _position_v_scrollbar(self):
        if not self.custom_v_scrollbar.isVisible():
            sdbg("OverlayScrollArea position: bar hidden, not positioned")
            return
        # Anchor to the scroll area's right edge so reserve_scrollbar_space=True
        # places the bar in the reserved gap rather than inside the viewport.
        sdbg(
            f"OverlayScrollArea position area_size={self.size()} viewport={self.viewport().geometry()} "
            f"scrollbar={self.custom_v_scrollbar.geometry()}"
        )
        self.custom_v_scrollbar.setGeometry(
            self.width() - self._scrollbar_width - self._scrollbar_gap,
            self.viewport().y(),
            self._scrollbar_width,
            self.viewport().height(),
        )
        sdbg(f"OverlayScrollArea position -> scrollbar={self.custom_v_scrollbar.geometry()}")

    def _position_h_scrollbar(self):
        if not self.custom_h_scrollbar.isVisible():
            sdbg("OverlayScrollArea position: h-bar hidden, not positioned")
            return
        # Anchor to the scroll area's bottom edge (mirror of the right-edge
        # vertical bar); with reserve the bar sits in the margin gap.
        sdbg(
            f"OverlayScrollArea position h area_size={self.size()} viewport={self.viewport().geometry()} "
            f"scrollbar={self.custom_h_scrollbar.geometry()}"
        )
        self.custom_h_scrollbar.setGeometry(
            self.viewport().x(),
            self.height() - self._scrollbar_width - self._scrollbar_gap,
            self.viewport().width(),
            self._scrollbar_width,
        )
        sdbg(f"OverlayScrollArea position h -> scrollbar={self.custom_h_scrollbar.geometry()}")

    def _delayed_update_scrollbar(self):
        self._sync_steps_from_native()
        self._sync_h_steps_from_native()
        self._position_scrollbars()


class SurfaceScrollArea(OverlayScrollArea):
    """Scroll area that paints its surface from a theme token.

    Stock ``QScrollArea`` viewports and ``setWidget``-flipped content
    widgets auto-fill the QPalette ``Window`` role, which hosts keep darker
    than the dialog surface token (dark ``Window`` ``#1e1e1e`` vs
    ``dialog.background`` ``#2b2b2b``) — transparent content then renders on
    a near-black substrate.

    The surface is the scroll area's own ``background-color`` (a
    widget-level stylesheet survives ``QStyle::polish`` at ``show()``,
    which per-widget palettes do not), with the viewport and the content
    widget pinned transparent via attributes. A ``paintEvent`` fill is NOT
    possible here: ``QPainter`` on a ``QAbstractScrollArea`` in its own
    paint event is inactive (Qt special-cases scroll-area painting), and a
    stylesheet on the viewport/content would put ``QStyleSheetStyle`` on
    the blitted path — a full viewport repaint per scroll step (visible
    jerk on relayout-heavy content). The corner mask is disabled for the
    same reason. ``surface_token=None`` clears the stylesheet and lets an
    ancestor that paints the surface (e.g. a pane fill) show through. The
    color is re-read on ``theme_changed`` so palette overrides via
    ``set_color`` take effect.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        surface_token: str | None = "surface.background",
    ) -> None:
        super().__init__(parent)
        self.set_corner_radius(0)
        self._surface_token: str | None = None
        self.viewport().setAutoFillBackground(False)
        try:
            ThemeManager.get_instance().theme_changed.connect(
                self._on_theme_changed
            )
        except Exception:
            pass
        self.set_surface_token(surface_token)

    def set_surface_token(self, token: str | None) -> None:
        """Switch the surface between token fill and transparent mode."""
        self._surface_token = token
        if token is None:
            self.setStyleSheet("")
        else:
            try:
                color = QColor(ThemeManager.get_instance().get_color(token))
            except Exception:
                color = QColor(self.palette().window().color())
            self.setStyleSheet(f"background-color: {color.name()};")
        # Pin AFTER the stylesheet change: applying a background rule makes
        # QStyleSheetStyle flip autoFillBackground on for the content
        # widget, and clearing it (unpolish) restores the flip — an
        # attribute would otherwise silently come back and paint the Window
        # role again.
        self._pin_content_transparent()

    def setWidget(self, widget):  # noqa: N802
        super().setWidget(widget)
        self._pin_content_transparent()

    def _pin_content_transparent(self) -> None:
        content = self.widget()
        if content is not None:
            # QScrollArea.setWidget flips autoFillBackground on for the
            # content widget; an attribute survives polish, unlike palette.
            content.setAutoFillBackground(False)

    def _on_theme_changed(self, *_args) -> None:
        # Bound method, so the connection dies with the widget; a lambda
        # would survive the widget and raise on the deleted C++ view.
        try:
            self.set_surface_token(self._surface_token)
        except RuntimeError:
            pass
