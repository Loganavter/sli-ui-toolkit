import logging
import math
from typing import Any, Literal

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QPoint,
    QPropertyAnimation,
    QRect,
    QRectF,
    QSize,
    Qt,
)
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QRhiWidget, QWidget

from sli_ui_toolkit.config import get_flyout_timings
from sli_ui_toolkit.ui.in_window_surface import (
    attach_in_window_widget,
    clamp_surface_rect,
    create_shadow_surface,
    paint_shadowed_surface,
    place_surface_rect,
    surface_anchor_rect,
    surface_available_rect,
)
from sli_ui_toolkit.managers import FlyoutManager
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.atomic.radio import RadioButton
from sli_ui_toolkit.ui.widgets.atomic.text_labels import Label
from sli_ui_toolkit.ui.widgets.buttons.layers.background import rounded_rect_path
from sli_ui_toolkit.ui.widgets.composite.gpu_fill.widget import FlyoutGpuFillWidget
from sli_ui_toolkit.ui.widgets.helpers.rounded_clip import RoundedClipEffect

AnimationAxis = Literal["auto", "vertical", "horizontal", "diagonal"]

logger = logging.getLogger(__name__)

_H_AXIS = {"left": 0.0, "center": 0.5, "right": 1.0}
_V_AXIS = {"top": 0.0, "center": 0.5, "bottom": 1.0}


def _parse_point(spec: str) -> tuple[float, float]:
    """Return (fx, fy) fractions in [0, 1] from a string like 'bottom-left' or 'top'."""
    parts = spec.split("-") if "-" in spec else [spec, "center"]
    v, h = (parts + ["center"])[:2]
    if v in _H_AXIS and h in _V_AXIS:
        v, h = h, v
    return (_H_AXIS.get(h, 0.5), _V_AXIS.get(v, 0.5))


def _point_in_rect(rect: QRect, spec: str) -> QPoint:
    fx, fy = _parse_point(spec)
    return QPoint(
        int(round(rect.left() + fx * rect.width())),
        int(round(rect.top() + fy * rect.height())),
    )


def _content_rect_in_flyout(size: QSize, shadow_radius: int) -> QRect:
    """Visible panel rect inside the outer flyout size (excludes shadow halo)."""
    r = max(0, int(shadow_radius))
    return QRect(
        r,
        r,
        max(0, int(size.width()) - 2 * r),
        max(0, int(size.height()) - 2 * r),
    )


def _flyout_point_local(size: QSize, spec: str, shadow_radius: int) -> QPoint:
    """Named point on the *rendered* panel, not the outer shadow bounds.

    Aligning ``top-left`` of the full widget to an anchor left edge leaves the
    opaque panel shifted right/down by ``SHADOW_RADIUS`` (the drop-shadow
    margin). Callers of ``show_aligned`` expect edge alignment of what the
    user sees.
    """
    return _point_in_rect(_content_rect_in_flyout(size, shadow_radius), spec)


def _flip_point_vertical(spec: str) -> str:
    """Swap top/bottom tokens in a point spec (``bottom-left`` → ``top-left``)."""
    parts = [p for p in spec.split("-") if p]
    flipped: list[str] = []
    for part in parts:
        if part == "top":
            flipped.append("bottom")
        elif part == "bottom":
            flipped.append("top")
        else:
            flipped.append(part)
    return "-".join(flipped) if flipped else spec


def slide_start_delta(
    final_rect: QRect,
    anchor_rect: QRect,
    *,
    distance: int,
    animation_axis: AnimationAxis,
    shadow_radius: int,
    ux: float,
    uy: float,
    length: float,
) -> tuple[int, int]:
    """Return ``(dx, dy)`` from final pos to slide-in start.

    ``distance`` is the desired travel of the *outer* widget. When opening
    below/above an anchor, a naive ``final - distance`` start puts the
    opaque panel (inset by ``shadow_radius``) through the middle of a short
    toolbar button — the same class of bug as aligning to the shadow halo
    instead of the visible panel. Clamp so the panel edge does not cross
    into the anchor.

    Use ``y + height`` / ``x + width`` for edges — not ``QRect.bottom()`` /
    ``right()``, which are inclusive last-pixel coordinates and sit one
    device pixel short of the true outer edge.
    """
    dist = max(0, int(distance))
    radius = max(0, int(shadow_radius))
    anchor_left = anchor_rect.x()
    anchor_top = anchor_rect.y()
    anchor_right = anchor_rect.x() + anchor_rect.width()
    anchor_bottom = anchor_rect.y() + anchor_rect.height()

    def _vertical_dy() -> int:
        if final_rect.center().y() >= anchor_rect.center().y():
            # Below: panel top = outer_y + radius; keep panel_top >= anchor bottom edge.
            desired = final_rect.y() - dist
            min_y = anchor_bottom - radius
            start_y = max(desired, min_y)
        else:
            # Above: panel bottom = outer_y + height - radius; keep <= anchor top edge.
            desired = final_rect.y() + dist
            max_y = anchor_top - final_rect.height() + radius
            start_y = min(desired, max_y)
        return start_y - final_rect.y()

    def _horizontal_dx() -> int:
        if final_rect.center().x() >= anchor_rect.center().x():
            desired = final_rect.x() - dist
            min_x = anchor_right - radius
            start_x = max(desired, min_x)
        else:
            desired = final_rect.x() + dist
            max_x = anchor_left - final_rect.width() + radius
            start_x = min(desired, max_x)
        return start_x - final_rect.x()

    if animation_axis == "vertical":
        return 0, _vertical_dy()
    if animation_axis == "horizontal":
        return _horizontal_dx(), 0
    if animation_axis == "diagonal":
        # Both axes travel the full `distance`, each independently clamped
        # against the anchor edge -- unlike "auto" below (which splits one
        # `distance`-length vector along anchor->flyout, so a corner-aligned
        # flyout whose centers differ a lot more on one axis than the other
        # gets a near-invisible slide on the smaller axis: e.g. a wide panel
        # barely offset vertically from a narrow anchor button ends up
        # looking like a near-pure horizontal slide, or vice-versa). This
        # guarantees a clearly visible motion on *both* axes regardless of
        # how the anchor and flyout sizes compare.
        return _horizontal_dx(), _vertical_dy()
    # auto: along anchor→flyout, still clamp the dominant axis against the
    # shadow inset so a wide menu under a narrow button does not foreshorten
    # into a diagonal dive through the trigger.
    if length <= 0:
        return 0, 0
    slide_dx = int(round(-ux * dist))
    slide_dy = int(round(-uy * dist))
    start = QPoint(final_rect.x() + slide_dx, final_rect.y() + slide_dy)
    if abs(uy) >= abs(ux):
        if final_rect.center().y() >= anchor_rect.center().y():
            min_y = anchor_bottom - radius
            if start.y() < min_y:
                start.setY(min_y)
        else:
            max_y = anchor_top - final_rect.height() + radius
            if start.y() > max_y:
                start.setY(max_y)
    else:
        if final_rect.center().x() >= anchor_rect.center().x():
            min_x = anchor_right - radius
            if start.x() < min_x:
                start.setX(min_x)
        else:
            max_x = anchor_left - final_rect.width() + radius
            if start.x() > max_x:
                start.setX(max_x)
    return start.x() - final_rect.x(), start.y() - final_rect.y()


def _compute_aligned_top_left(
    anchor_rect: QRect,
    flyout_size: QSize,
    *,
    anchor_point: str,
    flyout_point: str,
    offset: int,
    shadow_radius: int,
) -> QPoint:
    """Align visible panel point to anchor point, then clear the shadow halo.

    Content-point alignment alone puts the opaque panel just outside the
    anchor, but the outer widget still extends ``shadow_radius`` back over the
    button (drop-shadow margin). Clearance is therefore at least
    ``shadow_radius`` so the halo never sits on top of the anchor — but it is
    *not* added on top of ``offset``: per show_aligned's own contract, offset
    is the total visible pixel gap the caller asked for, so once offset
    already clears the halo on its own it should be used as-is (a caller
    passing offset=10 should not silently get an 18px gap).

    Caveat callers keep tripping over: this means any ``offset <
    shadow_radius`` (the common ``BaseFlyout.SHADOW_RADIUS = 8`` default)
    is silently raised to ``shadow_radius`` -- e.g. offset=2 and offset=4
    render *identically* (both floored to 8px), so tuning a value in that
    range looks like "offset does nothing" with zero indication why. Logged
    below at DEBUG when the floor actually changes the requested value;
    pass an offset at or above the flyout's own ``SHADOW_RADIUS`` (or lower
    ``SHADOW_RADIUS`` itself) to get the exact pixel gap requested.
    """
    anchor_pt = _point_in_rect(anchor_rect, anchor_point)
    flyout_pt_local = _flyout_point_local(flyout_size, flyout_point, shadow_radius)
    top_left = QPoint(
        anchor_pt.x() - flyout_pt_local.x(),
        anchor_pt.y() - flyout_pt_local.y(),
    )
    afx, afy = _parse_point(anchor_point)
    ffx, ffy = _parse_point(flyout_point)
    clearance = max(int(offset), max(0, int(shadow_radius)))
    if clearance != int(offset):
        logger.debug(
            "show_aligned: offset=%s floored to shadow_radius=%s "
            "(anchor_point=%r, flyout_point=%r) -- pass offset>=shadow_radius "
            "for the exact gap requested",
            offset,
            clearance,
            anchor_point,
            flyout_point,
        )
    # Axis-aligned push: dropdowns open straight down/up (or left/right),
    # not along the center-to-center diagonal (which foreshortens the gap
    # when widths differ). Independent if-blocks, not if/elif -- a true
    # corner-to-corner anchor (e.g. anchor "top-left" / flyout
    # "bottom-right") differs on *both* axes and needs clearance pushed on
    # both, otherwise one axis is left flush against the anchor with zero
    # gap (only the first block that happened to match ever fired).
    if afy > ffy:
        top_left.setY(top_left.y() + clearance)
    elif afy < ffy:
        top_left.setY(top_left.y() - clearance)
    if afx > ffx:
        top_left.setX(top_left.x() + clearance)
    elif afx < ffx:
        top_left.setX(top_left.x() - clearance)
    return top_left


def aligned_flyout_rect(
    anchor_rect: QRect,
    flyout_size: QSize,
    *,
    anchor_point: str,
    flyout_point: str,
    offset: int,
    shadow_radius: int,
    available: QRect,
) -> QRect:
    """Place flyout by named points; flip vertically when the preferred side overflows."""
    preferred = QRect(
        _compute_aligned_top_left(
            anchor_rect,
            flyout_size,
            anchor_point=anchor_point,
            flyout_point=flyout_point,
            offset=offset,
            shadow_radius=shadow_radius,
        ),
        flyout_size,
    )
    flipped_anchor = _flip_point_vertical(anchor_point)
    flipped_flyout = _flip_point_vertical(flyout_point)
    if flipped_anchor != anchor_point or flipped_flyout != flyout_point:
        flipped = QRect(
            _compute_aligned_top_left(
                anchor_rect,
                flyout_size,
                anchor_point=flipped_anchor,
                flyout_point=flipped_flyout,
                offset=offset,
                shadow_radius=shadow_radius,
            ),
            flyout_size,
        )
        # Same policy as place_surface_rect("bottom"): flip instead of sliding
        # over the anchor when the preferred side does not fit.
        if (
            preferred.bottom() > available.bottom()
            and flipped.top() >= available.top()
        ):
            preferred = flipped
        elif (
            preferred.top() < available.top()
            and flipped.bottom() <= available.bottom()
        ):
            preferred = flipped
    return clamp_surface_rect(preferred, available)


class BaseFlyout(QWidget):
    SHADOW_RADIUS = 8
    CONTENT_RADIUS = 8

    def __init__(
        self,
        parent=None,
        *,
        attach_overlay: bool = True,
        pinned: bool = False,
        gpu_fill: bool = False,
        gpu_fill_api: "QRhiWidget.Api | None" = None,
    ):
        if parent is None:
            raise ValueError("BaseFlyout requires an in-window parent widget")
        super().__init__(parent)

        # Pinned flyouts (persistent HUDs, e.g. a zoom-percent or info chip
        # anchored to a canvas) opt out of FlyoutManager's passive-dismiss
        # paths: outside click, outside wheel, app/window deactivate, and
        # anchor move/resize no longer hide them (see FlyoutManager._dismiss_passive
        # / _close_flyouts_with_moved_anchors). An explicit close_all() still
        # closes them. Callers are expected to keep them positioned via
        # reposition() (e.g. from the host's resize/move handlers) since the
        # manager will not do it for them.
        self.pinned = pinned

        self.setWindowFlags(Qt.WindowType.Widget)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        # Non-window child widgets are visible by default in Qt as soon as
        # their ancestor window is shown. Flyouts must stay hidden until an
        # explicit show()/show_aligned() call, otherwise every flyout ever
        # constructed (e.g. via eager tab creation at startup) flashes on
        # screen the moment the main window becomes visible. Use the base
        # QWidget.hide() here (not self.hide()) to avoid the overridden
        # hide()'s activateWindow()/setFocus() side effects during __init__.
        QWidget.hide(self)
        self.overlay_layer = (
            attach_in_window_widget(self, parent) if attach_overlay else None
        )
        self._anchor_widget: QWidget | None = None

        self._main_layout, self.container, self.content_layout = create_shadow_surface(
            self,
            shadow_radius=self.SHADOW_RADIUS,
            container_object_name="FlyoutContainer",
        )
        # Background + border are painted on the flyout shell; children are clipped
        # to the same corner radius so row hovers/ripples do not bleed past corners.
        self.container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self._container_clip = RoundedClipEffect(self.CONTENT_RADIUS, self.container)
        self.container.setGraphicsEffect(self._container_clip)

        # Host-overridable surface style (background/border/shadow) — see
        # set_background_brush / set_border_color / set_shadow_color below.
        # None means "use the theme token", matching Button's
        # override_bg/border_color/hover_color convention in style_api.py.
        self._background_brush: QBrush | None = None
        self._border_color_override: QColor | None = None
        self._shadow_color: QColor | None = None

        # Opt-in second rendering path for the panel fill: a QRhiWidget child
        # sitting behind content_layout's widgets, painting via a GPU shader
        # instead of paintEvent's QBrush fill. Off by default -- the QPainter
        # path above stays the only path unless a caller asks for gpu_fill.
        # Currently solid-color only (see gpu_fill/widget.py); a brush that
        # isn't a flat QColor falls back to the QPainter fill even with
        # gpu_fill=True.
        self._gpu_fill: FlyoutGpuFillWidget | None = None
        if gpu_fill:
            self._gpu_fill = FlyoutGpuFillWidget(self.container, api=gpu_fill_api)
            self._gpu_fill.lower()
            self._gpu_fill.setGeometry(self.container.rect())
            # Starts hidden: only a *solid-color* set_background_brush() call
            # turns it on (see there). Until then the theme-token default /
            # a gradient / texture brush still goes through paintEvent's
            # QPainter fill below, same as gpu_fill=False.
            self._gpu_fill.setVisible(False)
            self.container.installEventFilter(self)

        self.theme_manager = ThemeManager.get_instance()
        self.theme_manager.theme_changed.connect(self._apply_base_style)
        self._apply_base_style()

        self.flyout_manager = FlyoutManager.get_instance()
        if attach_overlay:
            self.flyout_manager.register_flyout(self)
            self.destroyed.connect(lambda: self.flyout_manager.unregister_flyout(self))

        self._show_animation: QPropertyAnimation | None = None

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            event.accept()
            return
        super().keyPressEvent(event)

    def eventFilter(self, obj, event):  # noqa: N802 — Qt API
        if (
            self._gpu_fill is not None
            and obj is self.container
            and event.type() == QEvent.Type.Resize
        ):
            self._gpu_fill.setGeometry(self.container.rect())
        return super().eventFilter(obj, event)

    def _apply_base_style(self):
        self.container.style().unpolish(self.container)
        self.container.style().polish(self.container)
        self.container.update()

    def add_widget(self, widget):
        self.content_layout.addWidget(widget)

    # -------- surface style (background / border / shadow) --------
    #
    # Same shape as Button's style_api.py: a plain setter storing an
    # instance override, ``None`` falls back to the theme token, and the
    # setter repaints. No QSS/property dispatch here (unlike Button)
    # because BaseFlyout doesn't expose Qt Designer-style dynamic
    # properties — these are plain Python attributes.

    def set_background_brush(self, brush: QBrush | QColor | None) -> None:
        """Override the flyout panel's fill.

        Accepts a flat ``QColor`` (solid override) or any ``QBrush`` —
        a ``QLinearGradient``/``QRadialGradient`` for a glass-style tint,
        or ``QBrush(QPixmap(...))`` to stretch a custom texture. Pass
        ``None`` to go back to the ``flyout.background`` theme token.
        """
        self._background_brush = (
            QBrush(brush) if brush is not None and not isinstance(brush, QBrush) else brush
        )
        if self._gpu_fill is not None:
            solid = (
                self._background_brush is not None
                and self._background_brush.style() == Qt.BrushStyle.SolidPattern
            )
            self._gpu_fill.setVisible(solid)
            if solid:
                self._gpu_fill.set_fill_color(self._background_brush.color())
        self.update()

    def background_brush(self) -> QBrush | None:
        return self._background_brush

    def set_border_color(self, color: QColor | None) -> None:
        """Override the panel's stroke color; ``None`` restores ``flyout.border``."""
        self._border_color_override = QColor(color) if color is not None else None
        self.update()

    def border_color(self) -> QColor | None:
        return self._border_color_override

    def set_shadow_color(self, color: QColor | None) -> None:
        """Tint the drop shadow (e.g. an accent-colored glow); ``None`` restores
        the default black shadow. Only RGB is used — alpha falloff is
        computed by the shadow painter, not taken from ``color``."""
        self._shadow_color = QColor(color) if color is not None else None
        self.update()

    def shadow_color(self) -> QColor | None:
        return self._shadow_color

    # -------- builder helpers --------

    def add_section(self, text: str, *, pixel_size: int = 12) -> Label:
        """Add a section heading label."""
        label = Label(
            text,
            pixel_size=pixel_size,
            bold=True,
            color_token="dialog.text",
        )
        self.content_layout.addWidget(label)
        return label

    def add_row(
        self,
        label_text: str,
        widget: QWidget,
        *,
        label_pixel_size: int = 11,
        stretch_before_widget: bool = True,
    ) -> Label:
        """Add a labeled row (label left, widget right)."""
        host = QWidget()
        row = QHBoxLayout(host)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        label = Label(
            label_text,
            pixel_size=label_pixel_size,
            color_token="dialog.text",
        )
        row.addWidget(label)
        if stretch_before_widget:
            row.addStretch()
        row.addWidget(widget)
        self.content_layout.addWidget(host)
        return label

    def add_radio_row(
        self,
        label_text: str,
        options: list[tuple[str, Any]],
        *,
        default: Any = None,
    ) -> tuple[Label, QButtonGroup, dict[Any, RadioButton]]:
        """Add a label followed by a horizontal row of RadioButtons."""
        label = Label(
            label_text,
            pixel_size=11,
            color_token="dialog.text",
        )
        self.content_layout.addWidget(label)

        host = QWidget()
        row = QHBoxLayout(host)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        group = QButtonGroup(self)
        radios: dict[Any, RadioButton] = {}
        for i, (text, value) in enumerate(options):
            rb = RadioButton(text)
            if (default is None and i == 0) or value == default:
                rb.setChecked(True)
            group.addButton(rb)
            row.addWidget(rb)
            radios[value] = rb
        row.addStretch()
        self.content_layout.addWidget(host)
        return label, group, radios

    def _ensure_overlay_parent(self, anchor_widget: QWidget):
        if anchor_widget is None:
            return
        if self.overlay_layer is None:
            self.overlay_layer = attach_in_window_widget(self, anchor_widget)
        if self.overlay_layer is not None and self.parentWidget() is not self.overlay_layer.host:
            was_visible = self.isVisible()
            self.overlay_layer.attach(self)
            if was_visible:
                self.show()
                self.raise_()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        paint_shadowed_surface(
            painter,
            self.container.geometry(),
            shadow_radius=self.SHADOW_RADIUS,
            corner_radius=self.CONTENT_RADIUS,
            shadow_color=self._shadow_color,
        )
        rect = QRectF(self.container.geometry())
        stroke_rect = rect.adjusted(0.5, 0.5, -0.5, -0.5)
        r = self.CONTENT_RADIUS
        path = rounded_rect_path(stroke_rect, (r, r, r, r))
        background = self._background_brush or QBrush(
            self.theme_manager.get_color("flyout.background")
        )
        border = self._border_color_override or self.theme_manager.get_color(
            "flyout.border"
        )
        # A visible _gpu_fill already painted this frame's solid fill via its
        # own QRhi pass (see set_background_brush) -- painting it again here
        # would just be redundant CPU work under the same rounded clip.
        gpu_fill_active = self._gpu_fill is not None and self._gpu_fill.isVisible()
        # Anchor texture/gradient brushes to the panel's own corner instead
        # of (0, 0) of the flyout widget (which is inset by the shadow
        # margin), so a custom texture lines up with the visible panel.
        painter.setBrushOrigin(stroke_rect.topLeft())
        painter.setBrush(Qt.BrushStyle.NoBrush if gpu_fill_active else background)
        painter.setPen(QPen(border, 1))
        painter.drawPath(path)
        painter.end()

    def show_aligned(
        self,
        anchor_widget: QWidget,
        anchor_point: str = "bottom-center",
        flyout_point: str = "top-center",
        *,
        position: str | None = None,
        offset: int = 5,
        animation: str = "none",
        animation_duration_ms: int | None = None,
        animation_distance: int | None = None,
        animation_axis: AnimationAxis = "auto",
        easing: QEasingCurve.Type = QEasingCurve.Type.OutQuad,
    ):
        """Align a point on the flyout to a point on ``anchor_widget``.

        ``anchor_point`` and ``flyout_point`` are strings like ``"bottom-center"``,
        ``"top-left"``, ``"center-right"``. The vertical part (``top``/``center``/
        ``bottom``) and horizontal part (``left``/``center``/``right``) can appear
        in any order; a single token is treated as the other axis being ``center``.

        Defaults (``anchor="bottom-center"``, ``flyout="top-center"``) place the
        flyout directly under the anchor.

        For compatibility, callers may still pass the old ``position=`` values
        (``"top"``, ``"bottom"``, ``"left"``, ``"right"``, and corners).

        ``offset`` is the visible pixel gap between the anchor and the rendered
        flyout edge along the natural direction between the two points.

        Supported ``animation`` modes:
            * ``"none"`` (default) — appears in place.
            * ``"slide"`` — slides in from the direction opposite to its offset.

        ``animation_axis``:
            * ``"auto"`` — slide along the anchor→flyout vector (default).
            * ``"vertical"`` — slide only on Y (dropdown under a toolbar button).
            * ``"horizontal"`` — slide only on X.
            * ``"diagonal"`` — slide on both X and Y, each the full
              ``distance``/``animation_distance`` independently (not split
              across a single vector like ``"auto"``) — for a corner-aligned
              flyout where you want a clearly visible slide on both axes
              regardless of how the anchor/flyout sizes compare.
        """
        self._last_align_kwargs = dict(
            anchor_widget=anchor_widget,
            anchor_point=anchor_point,
            flyout_point=flyout_point,
            position=position,
            offset=offset,
        )
        self._anchor_widget = anchor_widget
        self._ensure_overlay_parent(anchor_widget)

        self.flyout_manager.request_show(self)

        if self.container.layout():
            self.container.layout().invalidate()
            self.container.layout().activate()
            self.container.updateGeometry()
        self.adjustSize()
        flyout_size = self.size()

        anchor_rect = surface_anchor_rect(self, anchor_widget, self.overlay_layer)
        if position is not None:
            final_rect = self._overlay_rect_relative_to_anchor(
                anchor_widget,
                flyout_size,
                position=position,
                offset=offset - self.SHADOW_RADIUS,
            )
            flyout_center = final_rect.center()
        else:
            final_rect = aligned_flyout_rect(
                anchor_rect,
                flyout_size,
                anchor_point=anchor_point,
                flyout_point=flyout_point,
                offset=offset,
                shadow_radius=self.SHADOW_RADIUS,
                available=surface_available_rect(
                    self, anchor_widget, self.overlay_layer, margin=0
                ),
            )
            flyout_center = final_rect.center()

        dir_x = flyout_center.x() - anchor_rect.center().x()
        dir_y = flyout_center.y() - anchor_rect.center().y()
        length = math.hypot(dir_x, dir_y)
        if length > 0:
            ux, uy = dir_x / length, dir_y / length
        else:
            ux = uy = 0.0

        mode = animation if animation else "none"

        if mode == "none":
            self.setGeometry(final_rect)
            self.show()
            self.raise_()
            return

        timings = get_flyout_timings()
        duration = (
            animation_duration_ms
            if animation_duration_ms is not None
            else timings.flyout_animation_duration_ms
        )
        distance = (
            animation_distance
            if animation_distance is not None
            else timings.dropdown_drop_offset_px
        )
        if self._show_animation is not None:
            self._show_animation.stop()
            self._show_animation.deleteLater()
            self._show_animation = None

        slide_dx, slide_dy = slide_start_delta(
            final_rect,
            anchor_rect,
            distance=distance,
            animation_axis=animation_axis,
            shadow_radius=self.SHADOW_RADIUS,
            ux=ux,
            uy=uy,
            length=length,
        )
        start_pos = QPoint(
            final_rect.x() + slide_dx,
            final_rect.y() + slide_dy,
        )
        self.setGeometry(QRect(start_pos, final_rect.size()))
        # Блокируем mouse-events до конца анимации — иначе flyout, проезжающий
        # под уже неподвижным курсором, подсвечивает «случайную» строку.
        # WA_TransparentForMouseEvents отключает доставку и виджету, и его
        # детям (см. Qt docs). Снимаем на animation finished + reconcile,
        # чтобы реальный hover применился по фактическому положению курсора.
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.show()
        self.raise_()

        anim = QPropertyAnimation(self, b"pos", self)
        anim.setDuration(int(duration))
        anim.setStartValue(start_pos)
        anim.setEndValue(QPoint(final_rect.x(), final_rect.y()))
        anim.setEasingCurve(easing)
        anim.finished.connect(self._on_show_animation_finished)
        self._show_animation = anim
        anim.start()

    def reposition(self) -> None:
        """Re-run the last :meth:`show_aligned` call, without animation.

        For ``pinned=True`` flyouts: the manager exempts them from
        auto-hide-on-anchor-move (unlike regular flyouts, which just close),
        so the host must call this from its own resize/move handlers to keep
        the HUD tracking its anchor. No-op if never shown, no longer visible,
        or the anchor widget was deleted.
        """
        kwargs = getattr(self, "_last_align_kwargs", None)
        if not kwargs or not self.isVisible():
            return
        anchor_widget = kwargs.get("anchor_widget")
        if anchor_widget is None:
            return
        try:
            if not anchor_widget.isVisible():
                return
        except RuntimeError:
            return
        self.show_aligned(
            anchor_widget,
            kwargs.get("anchor_point", "bottom-center"),
            kwargs.get("flyout_point", "top-center"),
            position=kwargs.get("position"),
            offset=kwargs.get("offset", 5),
            animation="none",
        )

    def _on_show_animation_finished(self) -> None:
        if self._show_animation is not None:
            self._show_animation.deleteLater()
            self._show_animation = None
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        try:
            from sli_ui_toolkit.ui.widgets.helpers import hover_coordinator
            hover_coordinator().reconcile()
        except Exception:
            pass

    def _overlay_rect_relative_to_anchor(
        self,
        anchor_widget: QWidget,
        size: QSize,
        *,
        position: str,
        offset: int,
    ) -> QRect:
        if self.overlay_layer is not None and hasattr(
            self.overlay_layer, "place_rect_relative_to_anchor"
        ):
            return self.overlay_layer.place_rect_relative_to_anchor(
                anchor_widget,
                size,
                position=position,
                offset=offset,
            )
        return place_surface_rect(
            self,
            anchor_widget,
            size,
            position=position,
            offset=offset,
            margin=0,
            overlay_layer=self.overlay_layer,
        )

    def contains_global(self, global_pos) -> bool:
        if not self.isVisible():
            return False
        if self.overlay_layer is not None and hasattr(self.overlay_layer, "contains_global"):
            return self.overlay_layer.contains_global(self, global_pos)
        return self.rect().contains(self.mapFromGlobal(global_pos))

    def anchor_contains_global(self, global_pos) -> bool:
        anchor = getattr(self, "_anchor_widget", None)
        if anchor is None:
            return False
        try:
            anchor_top_left = anchor.mapToGlobal(QPoint(0, 0))
            return QRect(anchor_top_left, anchor.size()).contains(global_pos)
        except RuntimeError:
            return False

    def anchor_widgets(self) -> tuple[QWidget, ...]:
        anchor = getattr(self, "_anchor_widget", None)
        return (anchor,) if isinstance(anchor, QWidget) else ()

    def trigger_widgets(self) -> tuple[QWidget, ...]:
        """Widgets whose click toggles this flyout closed while it's open.

        Defaults to :meth:`anchor_widgets` -- for a typical flyout (dropdown,
        context menu) the anchor *is* the trigger button, so clicking it
        again while open should dismiss instead of reopening.

        Override to return ``()`` (or a narrower subset) when the anchor is
        used purely for positioning against a widget that isn't itself a
        click-to-toggle trigger -- e.g. a hover-driven flyout anchored to a
        whole button group for width/placement. Left coupled to
        ``anchor_widgets()`` by default, FlyoutManager's click-on-anchor
        heuristic (see its ``eventFilter``) would misread a click on any
        *sibling* button in that group as "clicked the trigger, dismiss".
        """
        return self.anchor_widgets()

    def trigger_contains_global(self, global_pos) -> bool:
        for widget in self.trigger_widgets():
            try:
                top_left = widget.mapToGlobal(QPoint(0, 0))
                if QRect(top_left, widget.size()).contains(global_pos):
                    return True
            except RuntimeError:
                continue
        return False

    def restore_focus_on_hide(self) -> bool:
        """Whether hide() should shove focus back onto the host window.

        Context menus return False: activateWindow/setFocus on Wayland can
        re-enter focusChanged handlers and visually jerk QRhi canvases.
        """
        return True

    def hide(self):
        fm = getattr(self, "flyout_manager", None)
        if fm is not None:
            fm.request_hide(self)
        super().hide()

        if not self.restore_focus_on_hide():
            return
        window = self.parent().window() if self.parent() else None
        if window is None or window.isActiveWindow():
            # Already the active window (the common case for a
            # hover-driven flyout closing while the user's cursor is still
            # inside the host app) -- activateWindow()/setFocus() would be
            # a no-op WM round-trip in that case, and doing it on every
            # close of a flyout that hides at hover frequency is enough
            # synchronous WM traffic to visibly stall the main thread
            # (observed as an "app not responding" busy-cursor flash).
            return
        if not getattr(self, "_window_active_on_show", False):
            # The host window was already inactive (app in the background,
            # OS focus elsewhere) at the moment this flyout opened -- e.g. a
            # purely hover-driven flyout (slider hint, settings panel) that
            # opened just because the cursor passed over its trigger while
            # the user was working in another app. There is no prior focus
            # state to "restore" here, so calling activateWindow() would
            # only steal/ request OS focus for a window the user never
            # activated -- surfacing as an unsolicited taskbar flash / "app
            # wants attention" hint. Only windows that were genuinely active
            # when the flyout opened (and lost activation during its
            # lifetime, e.g. to a nested dialog) get focus handed back.
            return
        window.activateWindow()
        window.setFocus()

    def show(self):
        fm = getattr(self, "flyout_manager", None)
        if fm is not None:
            fm.request_show(self)
        window = self.parent().window() if self.parent() else None
        self._window_active_on_show = bool(window is not None and window.isActiveWindow())
        super().show()

    def raise_(self) -> None:  # noqa: N802 — Qt API
        super().raise_()
        fm = getattr(self, "flyout_manager", None)
        if fm is not None and hasattr(fm, "ensure_overlay_stacking"):
            # Skip re-entry when we are the context menu being raised by stacking.
            if getattr(type(self), "flyout_group", None) == "context_menu":
                return
            try:
                fm.ensure_overlay_stacking(raised=self)
            except Exception:
                pass
