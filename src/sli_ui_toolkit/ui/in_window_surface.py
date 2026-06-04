from __future__ import annotations

from PyQt6.QtCore import QPoint, QRect, QSize, Qt
from PyQt6.QtGui import QPainter
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QBoxLayout, QVBoxLayout, QWidget

from sli_ui_toolkit.config import resolve_overlay_layer
from sli_ui_toolkit.ui.widgets.helpers import draw_rounded_shadow

def attach_in_window_widget(widget: QWidget, anchor: QWidget | None) -> object | None:
    overlay_layer = resolve_overlay_layer(anchor)
    if overlay_layer is not None:
        overlay_layer.attach(widget)
    return overlay_layer


def surface_anchor_rect(
    surface: QWidget,
    anchor: QWidget,
    overlay_layer: object | None = None,
) -> QRect:
    if overlay_layer is not None and hasattr(overlay_layer, "anchor_rect"):
        return overlay_layer.anchor_rect(anchor)

    parent = surface.parentWidget()
    if parent is not None and not surface.isWindow():
        return QRect(anchor.mapTo(parent, QPoint(0, 0)), anchor.size())
    return QRect(anchor.mapToGlobal(QPoint(0, 0)), anchor.size())


def surface_available_rect(
    surface: QWidget,
    anchor: QWidget | None = None,
    overlay_layer: object | None = None,
    *,
    margin: int = 0,
) -> QRect:
    if overlay_layer is not None and hasattr(overlay_layer, "available_rect"):
        available = overlay_layer.available_rect()
    else:
        parent = surface.parentWidget()
        if parent is not None and not surface.isWindow():
            available = parent.rect()
        else:
            screen = None
            if anchor is not None:
                try:
                    screen = anchor.screen() or QGuiApplication.screenAt(
                        anchor.mapToGlobal(QPoint(0, 0))
                    )
                except Exception:
                    screen = None
            if screen is None:
                screen = QGuiApplication.primaryScreen()
            available = (
                screen.availableGeometry()
                if screen is not None
                else QRect(QPoint(0, 0), QSize(1, 1))
            )

    if margin:
        return available.adjusted(margin, margin, -margin, -margin)
    return available


def clamp_surface_rect(
    rect: QRect,
    available: QRect,
    *,
    allow_resize: bool = False,
) -> QRect:
    result = QRect(rect)
    if allow_resize:
        result.setWidth(max(1, min(result.width(), available.width())))
        result.setHeight(max(1, min(result.height(), available.height())))

    if result.right() > available.right():
        result.moveRight(available.right())
    if result.left() < available.left():
        result.moveLeft(available.left())
    if result.bottom() > available.bottom():
        result.moveBottom(available.bottom())
    if result.top() < available.top():
        result.moveTop(available.top())
    return result


def place_surface_rect(
    surface: QWidget,
    anchor: QWidget,
    size: QSize,
    *,
    position: str = "bottom",
    offset: int = 0,
    margin: int = 8,
    overlay_layer: object | None = None,
    allow_resize: bool = False,
) -> QRect:
    anchor_rect = surface_anchor_rect(surface, anchor, overlay_layer)
    available = surface_available_rect(
        surface,
        anchor,
        overlay_layer,
        margin=margin,
    )

    cx = anchor_rect.x() + (anchor_rect.width() - size.width()) // 2
    cy = anchor_rect.y() + (anchor_rect.height() - size.height()) // 2
    w, h = size.width(), size.height()

    if position == "top":
        target = QRect(cx, anchor_rect.top() - h - offset, w, h)
        fallback = QRect(cx, anchor_rect.bottom() + offset, w, h)
        if target.top() < available.top() and fallback.bottom() <= available.bottom():
            target = fallback
    elif position == "left":
        target = QRect(anchor_rect.left() - w - offset, cy, w, h)
        fallback = QRect(anchor_rect.right() + offset, cy, w, h)
        if target.left() < available.left() and fallback.right() <= available.right():
            target = fallback
    elif position == "right":
        target = QRect(anchor_rect.right() + offset, cy, w, h)
        fallback = QRect(anchor_rect.left() - w - offset, cy, w, h)
        if target.right() > available.right() and fallback.left() >= available.left():
            target = fallback
    elif position == "top-left":
        target = QRect(anchor_rect.left() - w - offset, anchor_rect.top() - h - offset, w, h)
        if target.left() < available.left():
            target.moveLeft(anchor_rect.right() + offset)
        if target.top() < available.top():
            target.moveTop(anchor_rect.bottom() + offset)
    elif position == "top-right":
        target = QRect(anchor_rect.right() + offset, anchor_rect.top() - h - offset, w, h)
        if target.right() > available.right():
            target.moveRight(anchor_rect.left() - offset)
        if target.top() < available.top():
            target.moveTop(anchor_rect.bottom() + offset)
    elif position == "bottom-left":
        target = QRect(anchor_rect.left() - w - offset, anchor_rect.bottom() + offset, w, h)
        if target.left() < available.left():
            target.moveLeft(anchor_rect.right() + offset)
        if target.bottom() > available.bottom():
            target.moveBottom(anchor_rect.top() - offset)
    elif position == "bottom-right":
        target = QRect(anchor_rect.right() + offset, anchor_rect.bottom() + offset, w, h)
        if target.right() > available.right():
            target.moveRight(anchor_rect.left() - offset)
        if target.bottom() > available.bottom():
            target.moveBottom(anchor_rect.top() - offset)
    else:  # "bottom" (default)
        target = QRect(cx, anchor_rect.bottom() + offset, w, h)
        fallback = QRect(cx, anchor_rect.top() - h - offset, w, h)
        if target.bottom() > available.bottom() and fallback.top() >= available.top():
            target = fallback

    if overlay_layer is not None and hasattr(overlay_layer, "clamp_rect"):
        try:
            return overlay_layer.clamp_rect(target, margin=margin)
        except TypeError:
            return overlay_layer.clamp_rect(target)
    return clamp_surface_rect(target, available, allow_resize=allow_resize)

def create_shadow_surface(
    host: QWidget,
    *,
    shadow_radius: int,
    container_object_name: str,
    layout_cls: type[QBoxLayout] = QVBoxLayout,
    outer_margins: tuple[int, int, int, int] | None = None,
    content_margins: tuple[int, int, int, int] = (4, 4, 4, 4),
    content_spacing: int = 4,
) -> tuple[QBoxLayout, QWidget, QBoxLayout]:
    if outer_margins is None:
        outer_margins = (shadow_radius, shadow_radius, shadow_radius, shadow_radius)

    main_layout = layout_cls(host)
    main_layout.setContentsMargins(*outer_margins)

    container = QWidget(host)
    container.setObjectName(container_object_name)
    container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    main_layout.addWidget(container)

    content_layout = layout_cls(container)
    content_layout.setContentsMargins(*content_margins)
    content_layout.setSpacing(content_spacing)

    return main_layout, container, content_layout

def paint_shadowed_surface(
    painter: QPainter,
    surface_rect,
    *,
    shadow_radius: int,
    corner_radius: int,
) -> None:
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    draw_rounded_shadow(
        painter,
        surface_rect,
        steps=shadow_radius,
        radius=corner_radius,
    )
