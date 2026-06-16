import math
from typing import Any

from PyQt6.QtCore import (
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QRect,
    QSize,
    Qt,
)
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen
from PyQt6.QtWidgets import QButtonGroup, QHBoxLayout, QWidget

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
from sli_ui_toolkit.ui.widgets.composite.color_swatch import ColorSwatch


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


class BaseFlyout(QWidget):
    SHADOW_RADIUS = 8
    CONTENT_RADIUS = 8

    def __init__(self, parent=None):
        if parent is None:
            raise ValueError("BaseFlyout requires an in-window parent widget")
        super().__init__(parent)

        self.setWindowFlags(Qt.WindowType.Widget)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.overlay_layer = attach_in_window_widget(self, parent)
        self._anchor_widget: QWidget | None = None

        self._main_layout, self.container, self.content_layout = create_shadow_surface(
            self,
            shadow_radius=self.SHADOW_RADIUS,
            container_object_name="FlyoutContainer",
        )

        self.theme_manager = ThemeManager.get_instance()
        self.theme_manager.theme_changed.connect(self._apply_base_style)
        self._apply_base_style()

        self.flyout_manager = FlyoutManager.get_instance()
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

    def make_color_swatch(
        self,
        color: QColor | None = None,
        *,
        size: int = 28,
        alpha: bool = True,
    ) -> ColorSwatch:
        """Build a round color-picker swatch."""
        return ColorSwatch(color=color, size=size, alpha=alpha, parent=self)

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
        paint_shadowed_surface(
            painter,
            self.container.geometry(),
            shadow_radius=self.SHADOW_RADIUS,
            corner_radius=self.CONTENT_RADIUS,
        )
        rect = self.container.geometry()
        painter.setBrush(QBrush(self.theme_manager.get_color("flyout.background")))
        painter.setPen(QPen(self.theme_manager.get_color("flyout.border"), 1))
        painter.drawRoundedRect(rect, self.CONTENT_RADIUS, self.CONTENT_RADIUS)
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
        animation_distance: int = 24,
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
            anchor_pt = _point_in_rect(anchor_rect, anchor_point)
            flyout_pt_local = _point_in_rect(
                QRect(QPoint(0, 0), flyout_size),
                flyout_point,
            )

            top_left = QPoint(
                anchor_pt.x() - flyout_pt_local.x(),
                anchor_pt.y() - flyout_pt_local.y(),
            )

            # Push flyout away from anchor by (offset - SHADOW_RADIUS) px so the
            # visible (post-shadow) gap matches the requested offset.
            flyout_center = QPoint(
                top_left.x() + flyout_size.width() // 2,
                top_left.y() + flyout_size.height() // 2,
            )
            dir_x = flyout_center.x() - anchor_rect.center().x()
            dir_y = flyout_center.y() - anchor_rect.center().y()
            length = math.hypot(dir_x, dir_y)
            push = offset - self.SHADOW_RADIUS
            if length > 0 and push != 0:
                ux, uy = dir_x / length, dir_y / length
                top_left = QPoint(
                    top_left.x() + int(round(push * ux)),
                    top_left.y() + int(round(push * uy)),
                )
            final_rect = clamp_surface_rect(
                QRect(top_left, flyout_size),
                surface_available_rect(self, anchor_widget, self.overlay_layer, margin=0),
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

        duration = (
            animation_duration_ms
            if animation_duration_ms is not None
            else get_flyout_timings().flyout_animation_duration_ms
        )
        if self._show_animation is not None:
            self._show_animation.stop()
            self._show_animation.deleteLater()
            self._show_animation = None

        # Slide starts toward the anchor (opposite of push direction).
        slide_dx = -ux * animation_distance if length > 0 else 0
        slide_dy = -uy * animation_distance if length > 0 else 0
        start_pos = QPoint(
            final_rect.x() + int(round(slide_dx)),
            final_rect.y() + int(round(slide_dy)),
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

    def hide(self):
        fm = getattr(self, "flyout_manager", None)
        if fm is not None:
            fm.request_hide(self)
        super().hide()

        if self.parent() and self.parent().window():
            self.parent().window().activateWindow()
            self.parent().window().setFocus()

    def show(self):
        fm = getattr(self, "flyout_manager", None)
        if fm is not None:
            fm.request_show(self)
        super().show()
