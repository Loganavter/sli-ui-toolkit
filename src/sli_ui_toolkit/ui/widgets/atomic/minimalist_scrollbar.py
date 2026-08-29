from __future__ import annotations

import logging
import os

from PySide6.QtCore import QEvent, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QRegion, QWheelEvent
from PySide6.QtWidgets import QApplication, QScrollArea, QScrollBar, QWidget

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.helpers import register_hover_widget

_SCROLLBAR_DEBUG = os.getenv("IMGSLI_SCROLLBAR_DEBUG", "0") == "1"
_sdbg_logger = logging.getLogger("sli_ui_toolkit.scrollbar")


def _ensure_sdbg_handler() -> None:
    # Rely on toolkit-wide logging configuration (core.logging) instead of
    # installing a direct StreamHandler(sys.stderr) per widget. This avoids
    # duplicate handlers and respects host logging setup. No-op for compat.
    return


def sdbg(message: str) -> None:
    if not _SCROLLBAR_DEBUG:
        return
    _sdbg_logger.setLevel(logging.DEBUG)
    _ensure_sdbg_handler()
    _sdbg_logger.debug(message)

# The bar's fixed widget width — the one public geometry number composites
# need (positioning/reserving). Everything else (gap, margin, thumb
# thicknesses, track padding) is internal to the bar's look and layout and
# stays module-private; the single public value is
# ``overlay_scrollbar_max_inset()`` — max width + gap + margin.
MINIMAL_SCROLLBAR_WIDTH = 10
_MINIMAL_SCROLLBAR_GAP = 0
_OVERLAY_INSET_MARGIN = 4
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
        self._update_colors()
        self.theme_manager.theme_changed.connect(self._update_colors)
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
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        handle_rect = self._get_handle_rect()
        if handle_rect.isEmpty():
            return
        if self._is_dragging:
            current_color = self.theme_manager.get_color("accent")
        elif self._hovered:
            current_color = self._hover_color
        else:
            current_color = self._idle_color
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(current_color)
        radius = min(handle_rect.width(), handle_rect.height()) / 2.0
        painter.drawRoundedRect(handle_rect, radius, radius)

    def _get_handle_rect(self):
        if self.minimum() == self.maximum():
            return QRect()
        if self._is_dragging:
            current_thickness = self._drag_thickness
        elif self._hovered:
            current_thickness = self._hover_thickness
        else:
            current_thickness = self._idle_thickness
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
            self.update()
            event.accept()

    def enterEvent(self, event):
        sdbg(f"enter widget={self.__class__.__name__} rect={self.rect()}")
        self.setHoverActive(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        sdbg(f"leave widget={self.__class__.__name__} rect={self.rect()}")
        self.setHoverActive(False)
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
    def __init__(self, parent=None):
        super().__init__(parent)
        self._corner_radius = 8
        self._reserve_scrollbar_space = True
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.custom_v_scrollbar = MinimalistScrollBar(Qt.Orientation.Vertical, self)
        self._scrollbar_width = MINIMAL_SCROLLBAR_WIDTH
        self._scrollbar_gap = _MINIMAL_SCROLLBAR_GAP
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
        self.custom_v_scrollbar.valueChanged.connect(self.verticalScrollBar().setValue)
        self.verticalScrollBar().rangeChanged.connect(self.custom_v_scrollbar.setRange)
        self.verticalScrollBar().rangeChanged.connect(lambda *_: self._sync_steps_from_native())
        self.custom_v_scrollbar.setVisible(False)
        self._sync_steps_from_native()
        self._apply_viewport_mask()
        self.viewport().installEventFilter(self)

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

    def set_reserve_scrollbar_space(self, reserve: bool):
        self._reserve_scrollbar_space = bool(reserve)
        self._update_scrollbar_visibility()

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
            delta = int(round(pixel))
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
            delta = int(round(angle / 120 * base))
        current = (
            self._scroll_target
            if self._scroll_target is not None
            else native.value()
        )
        target = max(native.minimum(), min(current + delta, native.maximum()))
        self._scroll_target = target
        if target != native.value() and not self._scroll_timer.isActive():
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
        self._position_scrollbar()
        self._sync_steps_from_native()
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

    def _update_scrollbar_visibility(self, min_items_count=0):
        native = self.verticalScrollBar()
        should_show = native.maximum() > native.minimum()
        sdbg(
            f"OverlayScrollArea visibility native_max={native.maximum()} native_min={native.minimum()} "
            f"should_show={should_show} reserve={self._reserve_scrollbar_space}"
        )
        self.custom_v_scrollbar.setVisible(should_show)
        # Reserve the bar's gap CONSTANTLY when reserve_scrollbar_space is on,
        # never toggle with visibility: flipping viewport margins on every
        # show/hide (which can oscillate at the content-fits boundary during
        # a scroll) changes the viewport width and re-flows the content
        # widget every step — visible jank on relayout-heavy content.
        if self._reserve_scrollbar_space:
            self.setViewportMargins(0, 0, self._scrollbar_width, 0)
        else:
            self.setViewportMargins(0, 0, 0, 0)
        self._position_scrollbar()

    def _position_scrollbar(self):
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

    def _delayed_update_scrollbar(self):
        self._sync_steps_from_native()
        self._position_scrollbar()


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
        surface_token: str | None = "dialog.background",
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
