import math
from typing import Any, Literal

from PySide6.QtCore import (
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QRect,
    QRectF,
    QSize,
    Qt,
)
from PySide6.QtGui import QBrush, QPainter, QPen
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QWidget

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
from sli_ui_toolkit.ui.widgets.helpers.rounded_clip import RoundedClipEffect

AnimationAxis = Literal["auto", "vertical", "horizontal"]


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
    if animation_axis == "vertical":
        if final_rect.center().y() >= anchor_rect.center().y():
            # Below: panel top = outer_y + radius; keep panel_top >= anchor bottom edge.
            desired = final_rect.y() - dist
            min_y = anchor_bottom - radius
            start_y = max(desired, min_y)
            return 0, start_y - final_rect.y()
        # Above: panel bottom = outer_y + height - radius; keep <= anchor top edge.
        desired = final_rect.y() + dist
        max_y = anchor_top - final_rect.height() + radius
        start_y = min(desired, max_y)
        return 0, start_y - final_rect.y()
    if animation_axis == "horizontal":
        if final_rect.center().x() >= anchor_rect.center().x():
            desired = final_rect.x() - dist
            min_x = anchor_right - radius
            start_x = max(desired, min_x)
            return start_x - final_rect.x(), 0
        desired = final_rect.x() + dist
        max_x = anchor_left - final_rect.width() + radius
        start_x = min(desired, max_x)
        return start_x - final_rect.x(), 0
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
    button (drop-shadow margin). Vertical/horizontal clearance therefore adds
    ``shadow_radius`` so the halo sits past the anchor, not on top of it.
    """
    anchor_pt = _point_in_rect(anchor_rect, anchor_point)
    flyout_pt_local = _flyout_point_local(flyout_size, flyout_point, shadow_radius)
    top_left = QPoint(
        anchor_pt.x() - flyout_pt_local.x(),
        anchor_pt.y() - flyout_pt_local.y(),
    )
    afx, afy = _parse_point(anchor_point)
    ffx, ffy = _parse_point(flyout_point)
    clearance = int(offset) + max(0, int(shadow_radius))
    # Axis-aligned push: dropdowns open straight down/up, not along the
    # center-to-center diagonal (which foreshortens the gap when widths differ).
    if afy > ffy:
        top_left.setY(top_left.y() + clearance)
    elif afy < ffy:
        top_left.setY(top_left.y() - clearance)
    elif afx > ffx:
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

    def __init__(self, parent=None, *, attach_overlay: bool = True):
        if parent is None:
            raise ValueError("BaseFlyout requires an in-window parent widget")
        super().__init__(parent)

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

    def _apply_base_style(self):
        self.container.style().unpolish(self.container)
        self.container.style().polish(self.container)
        self.container.update()

    def add_widget(self, widget):
        self.content_layout.addWidget(widget)

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
        )
        rect = QRectF(self.container.geometry())
        stroke_rect = rect.adjusted(0.5, 0.5, -0.5, -0.5)
        r = self.CONTENT_RADIUS
        path = rounded_rect_path(stroke_rect, (r, r, r, r))
        painter.setBrush(QBrush(self.theme_manager.get_color("flyout.background")))
        painter.setPen(QPen(self.theme_manager.get_color("flyout.border"), 1))
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
        """
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
        if self.parent() and self.parent().window():
            self.parent().window().activateWindow()
            self.parent().window().setFocus()

    def show(self):
        fm = getattr(self, "flyout_manager", None)
        if fm is not None:
            fm.request_show(self)
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
