"""Popup placement and slide/fade animation for ``ContextMenu``.

Split out of ``menu.py`` -- cursor-positioned popup geometry and the fade
in/out animation lifecycle, mirroring ``base_flyout/``'s ``placement.py`` +
``animation.py`` split. Every function here takes the owning ``ContextMenu``
as its first argument.
"""

from __future__ import annotations

import math

from PySide6.QtCore import (
    QEasingCurve,
    QEventLoop,
    QPoint,
    QPropertyAnimation,
    QRect,
    Qt,
    QVariantAnimation,
)
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.config import get_flyout_timings
from sli_ui_toolkit.ui.in_window_surface import (
    clamp_surface_rect,
    surface_anchor_rect,
    surface_available_rect,
)
from sli_ui_toolkit.ui.popup_surface import (
    bind_popup_transient_parent,
    place_popup_at_global,
    screen_available_rect,
)
from sli_ui_toolkit.ui.widgets.composite.base_flyout import (
    AnimationAxis,
    aligned_flyout_rect,
    resolve_flyout_animation,
    slide_start_delta,
)
from sli_ui_toolkit.ui.widgets.composite.context_menu import submenu as submenu_ops


def popup_show_aligned(
    menu,
    anchor_widget: QWidget,
    anchor_point: str = "bottom-center",
    flyout_point: str = "top-center",
    *,
    position: str | None = None,
    offset: int = 5,
    animation: str | None = None,
    animation_duration_ms: int | None = None,
    animation_distance: int | None = None,
    animation_axis: AnimationAxis = "auto",
    easing: QEasingCurve.Type = QEasingCurve.Type.OutQuad,
) -> None:
    menu._anchor_widget = anchor_widget
    container_layout = menu.container.layout()
    if container_layout is not None:
        container_layout.invalidate()
        container_layout.activate()
        menu.container.updateGeometry()
    menu.adjustSize()
    flyout_size = menu.size()

    anchor_rect = surface_anchor_rect(menu, anchor_widget, None)
    if position is not None:
        final_rect = menu._overlay_rect_relative_to_anchor(
            anchor_widget,
            flyout_size,
            position=position,
            offset=offset - menu.SHADOW_RADIUS,
        )
        flyout_center = final_rect.center()
    else:
        available = screen_available_rect(menu, margin=0)
        final_rect = aligned_flyout_rect(
            anchor_rect,
            flyout_size,
            anchor_point=anchor_point,
            flyout_point=flyout_point,
            offset=offset,
            shadow_radius=menu.SHADOW_RADIUS,
            available=available,
        )
        # Popup coords are global; aligned_flyout_rect already clamped.
        flyout_center = final_rect.center()

    dir_x = flyout_center.x() - anchor_rect.center().x()
    dir_y = flyout_center.y() - anchor_rect.center().y()
    length = math.hypot(dir_x, dir_y)
    if length > 0:
        ux, uy = dir_x / length, dir_y / length
    else:
        ux = uy = 0.0

    mode = animation if animation is not None else (
        get_flyout_timings().default_flyout_animation or "none"
    )
    mode = mode if mode else "none"
    if mode == "none":
        menu.setGeometry(final_rect)
        menu.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        menu.show()
        menu.raise_()
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
    if menu._show_animation is not None:
        menu._show_animation.stop()
        menu._show_animation.deleteLater()
        menu._show_animation = None

    slide_dx, slide_dy = slide_start_delta(
        final_rect,
        anchor_rect,
        distance=distance,
        animation_axis=animation_axis,
        shadow_radius=menu.SHADOW_RADIUS,
        ux=ux,
        uy=uy,
        length=length,
    )
    start_pos = QPoint(
        final_rect.x() + slide_dx,
        final_rect.y() + slide_dy,
    )
    menu.setGeometry(QRect(start_pos, final_rect.size()))
    menu.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
    menu.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
    menu.show()
    menu.raise_()

    anim = QPropertyAnimation(menu, b"pos", menu)
    anim.setDuration(int(duration))
    anim.setStartValue(start_pos)
    anim.setEndValue(QPoint(final_rect.x(), final_rect.y()))
    anim.setEasingCurve(easing)
    anim.finished.connect(menu._on_show_animation_finished)
    menu._show_animation = anim
    anim.start()


def popup_at(menu, global_pos: QPoint, *, animation: str | None = None) -> None:
    submenu_ops.close_submenu(menu)
    menu._relayout_widths()
    container_layout = menu.container.layout()
    if container_layout is not None:
        container_layout.invalidate()
        container_layout.activate()
        menu.container.updateGeometry()
    menu.adjustSize()

    # Cursor-positioned menus resolve the same animation mode as the rest
    # (explicit -> global default -> historical "slide"); a fade-bearing
    # mode fades the menu in at the cursor and fades it out on hide.
    mode = resolve_flyout_animation(animation)
    menu._fade.fade_out_enabled = "fade" in mode
    want_fade = "fade" in mode

    # Keep the open cursor outside the widget (incl. shadow) so the same
    # spot can dismiss on the next press. Opaque content still sits near
    # the cursor via the shadow inset.
    origin = global_pos + QPoint(1, 1)
    if menu.is_popup_surface():
        bind_popup_transient_parent(menu, menu._logical_parent)
        place_popup_at_global(menu, origin, margin=4)
        menu.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        # Show FIRST, snapshot second: grab() of a top-level popup window
        # that was never shown can miss content (corners, shadow — the
        # "top-left corner pops in opaque" artifact) because the native
        # surface doesn't exist yet. show() + re-place stay synchronous
        # (no event-loop pass), so no frame ever paints at full opacity
        # before the fade takes over.
        menu.show()
        menu.raise_()
        # Wayland may ignore pre-show geometry; re-apply once mapped.
        place_popup_at_global(menu, origin, margin=4)
        if want_fade:
            menu._fade.capture(menu)
            menu._fade.set_opacity(menu, 0.0)
            _start_popup_fade_in(menu)
        return

    parent = menu.parentWidget()
    local_pos = parent.mapFromGlobal(origin) if parent is not None else origin
    target = QRect(local_pos, menu.size())
    if menu.overlay_layer is not None and hasattr(menu.overlay_layer, "clamp_rect"):
        try:
            target = menu.overlay_layer.clamp_rect(target, margin=4)
        except TypeError:
            target = menu.overlay_layer.clamp_rect(target)
    else:
        target = clamp_surface_rect(
            target,
            surface_available_rect(menu, None, menu.overlay_layer, margin=4),
        )
    menu.setGeometry(target)

    menu.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
    if want_fade:
        menu._fade.capture(menu)
        menu._fade.set_opacity(menu, 0.0)
    menu.show()
    menu.raise_()
    if want_fade:
        _start_popup_fade_in(menu)
    # Do not setFocus(): on Wayland focusing a ContextMenu can emit
    # ApplicationDeactivate, which then closes the menu and jerks QRhi
    # canvases. Escape is handled via FlyoutManager / key filters.


def _start_popup_fade_in(menu) -> None:
    if menu._show_animation is not None:
        menu._show_animation.stop()
        menu._show_animation.deleteLater()
        menu._show_animation = None
    anim = QVariantAnimation(menu)
    anim.setDuration(get_flyout_timings().flyout_animation_duration_ms)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.Type.OutQuad)
    anim.valueChanged.connect(
        lambda value: menu._fade.on_fade_value_changed(menu, value)
    )
    anim.finished.connect(lambda: _on_popup_fade_in_finished(menu))
    menu._show_animation = anim
    anim.start()


def _on_popup_fade_in_finished(menu) -> None:
    if menu._show_animation is not None:
        menu._show_animation.deleteLater()
        menu._show_animation = None
    menu._fade.clear()
    menu._fade.opacity = 1.0
    menu.update()


def should_popup_fade_out(menu) -> bool:
    return bool(
        menu.is_popup_surface()
        and not menu._is_submenu
        and menu._fade.fade_out_enabled
        and menu.isVisible()
        and not menu._popup_fade_in_progress
    )


def start_popup_fade_out(menu) -> None:
    menu._popup_fade_in_progress = True
    menu._fade.capture(menu)
    anim = QVariantAnimation(menu)
    anim.setDuration(get_flyout_timings().flyout_fade_out_duration_ms)
    anim.setStartValue(menu._fade.opacity)
    anim.setEndValue(0.0)
    anim.setEasingCurve(QEasingCurve.Type.InQuad)
    anim.valueChanged.connect(
        lambda value: menu._fade.on_fade_value_changed(menu, value)
    )
    anim.finished.connect(lambda: _on_popup_fade_out_finished(menu))
    menu._popup_fade_anim = anim
    anim.start()


def _on_popup_fade_out_finished(menu) -> None:
    if menu._popup_fade_anim is not None:
        menu._popup_fade_anim.deleteLater()
        menu._popup_fade_anim = None
    menu._popup_fade_in_progress = False
    menu._fade.clear()
    menu._fade.opacity = 1.0
    QWidget.hide(menu)
    menu.aboutToHide.emit()
    if menu.is_popup_surface() and not menu._is_submenu:
        menu.deleteLater()


def exec_at(menu, global_pos: QPoint) -> str | None:
    result: dict[str, str | None] = {"id": None}
    loop = QEventLoop()

    def _on_triggered(action_id: str, _data: object) -> None:
        result["id"] = action_id

    def _on_about_to_hide() -> None:
        loop.quit()

    menu.actionTriggered.connect(_on_triggered)
    menu.aboutToHide.connect(_on_about_to_hide)
    popup_at(menu, global_pos)
    loop.exec()
    menu.actionTriggered.disconnect(_on_triggered)
    menu.aboutToHide.disconnect(_on_about_to_hide)
    return result["id"]
