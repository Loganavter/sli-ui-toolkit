"""BaseFlyout — the in-window flyout shell (thin facade).

The class keeps only construction, Qt-required event names, and the
inspection spec; the concerns live in sibling mixin modules (buttons/
style_api.py + events.py is the same pattern):

- ``style.py``      — ``_FlyoutStyleApi``      panel fill / border / shadow + paint
- ``builder.py``    — ``_FlyoutBuilderApi``    add_section / add_row / add_radio_row
- ``animation.py``  — ``_FlyoutFadeMixin``     snapshot fade pipeline + hide fade
- ``placement.py``  — ``_FlyoutPlacementApi``  show_aligned / reposition
- ``lifecycle.py``  — ``_FlyoutLifecycleApi``  hide / show / raise_ / focus restore
- ``contract.py``   — ``_FlyoutManagerApi``    hit-testing surface for FlyoutManager
- ``geometry.py``   — pure placement math (no widget state)
"""

from __future__ import annotations

import logging

import shiboken6

from PySide6.QtCore import (
    QEvent,
    QParallelAnimationGroup,
    QPropertyAnimation,
    Qt,
    QVariantAnimation,
)
from PySide6.QtGui import QBrush, QColor, QPixmap
from PySide6.QtWidgets import QApplication, QRhiWidget, QWidget

logger = logging.getLogger(__name__)

from sli_ui_toolkit.managers import FlyoutManager
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.in_window_surface import (
    attach_in_window_widget,
    create_shadow_surface,
)
from sli_ui_toolkit.ui.inspector.spec import InspectSpec, SpecField
from sli_ui_toolkit.ui.widgets.composite.gpu_fill.widget import FlyoutGpuFillWidget
from sli_ui_toolkit.ui.widgets.helpers.rounded_clip import RoundedClipEffect

from .animation import FlyoutFadeController
from .builder import _FlyoutBuilderApi
from .contract import _FlyoutManagerApi
from .debug import _flyout_debug
from .lifecycle import _FlyoutLifecycleApi
from .placement import _FlyoutPlacementApi
from .style import _FlyoutStyleApi


class BaseFlyout(
    _FlyoutStyleApi,
    _FlyoutBuilderApi,
    _FlyoutPlacementApi,
    _FlyoutLifecycleApi,
    _FlyoutManagerApi,
    QWidget,
):
    """In-window flyout shell. Mixins precede ``QWidget`` so their overrides
    (``show``/``hide``/``raise_``/``paintEvent``) win the MRO; ``super()``
    inside them still resolves to QWidget's own methods."""

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

        # Fade-in/fade-out state. Must exist before attach_in_window_widget()
        # below: the overlay attach can call self.hide() during __init__ (host
        # overlays re-parent and hide the widget), and hide() reads these.
        self._show_animation: (
            QParallelAnimationGroup | QPropertyAnimation | QVariantAnimation | None
        ) = None
        self._hide_animation = None
        # Current fade opacity (1.0 = fully opaque). Fade is implemented
        # without a QGraphicsEffect: a one-shot snapshot of the flyout is
        # captured outside paintEvent (see _capture_fade_cache) and paintEvent
        # composites it with this opacity. A graphics effect on the shell would
        # conflict with the container's RoundedClipEffect (nested effects) and
        # with this widget's own QPainter(self) paintEvent, which shows up as
        # "A paint device can only be painted by one painter at a time" /
        # "Unbalanced save/restore" warnings on real composited windows.
        # In-window flyouts are plain child widgets (not toplevels), so
        # windowOpacity() would not work either.
        # All fade state (snapshot cache, opacity, hide-fade animation,
        # flags) lives in the controller; the widget only references it.
        self._fade = FlyoutFadeController()

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

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._focus_guard_installed = False
        # Фокус-кольцо — библиотечный токен + масштаб (как у Button FocusLayer)
        from sli_ui_toolkit.ui.managers.ui_scale import UiScale, scaled_px as _sp

        self._focus_ring_base_width = 2
        self._focus_ring_width = _sp(2)
        self._focus_ring_color = None  # lazy resolve via ThemeManager
        self._keyboard_focus = False
        self._last_focus_reason: Qt.FocusReason | None = None
        UiScale.get_instance().scale_changed.connect(self._on_scale_for_focus_ring)

    def _on_scale_for_focus_ring(self, _factor: float | None = None) -> None:
        from sli_ui_toolkit.ui.managers.ui_scale import scaled_px as _sp

        base = getattr(self, "_focus_ring_base_width", 2)
        self._focus_ring_width = _sp(int(base))
        self.update()

    def set_focus_ring_width(self, width: int) -> None:
        """Задать толщину кольца фокуса (дизайн-px, масштабируется UiScale)."""
        self._focus_ring_base_width = int(width)
        from sli_ui_toolkit.ui.managers.ui_scale import scaled_px as _sp

        self._focus_ring_width = _sp(int(width))
        self.update()

    def set_focus_ring_color(self, color) -> None:
        self._focus_ring_color = color
        self.update()

    def focusInEvent(self, event) -> None:  # noqa: N802
        # Ring modality resolved centrally via NavigationManager (4.2.4):
        # input device is the source of truth, reason is only a hint.
        reason = event.reason() if hasattr(event, "reason") else Qt.FocusReason.OtherFocusReason
        try:
            from sli_ui_toolkit.ui.managers.navigation_manager import (
                resolve_keyboard_focus,
            )

            is_kbd = resolve_keyboard_focus(reason)
        except Exception:
            # degraded, no manager
            is_kbd = reason not in (
                Qt.FocusReason.MouseFocusReason,
                Qt.FocusReason.MenuBarFocusReason,
                Qt.FocusReason.PopupFocusReason,
            )
        self._keyboard_focus = bool(is_kbd)
        self._last_focus_reason = reason
        super().focusInEvent(event)
        self.update()

    def focusOutEvent(self, event) -> None:  # noqa: N802
        self._keyboard_focus = False
        super().focusOutEvent(event)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        if getattr(self, "_keyboard_focus", False) and self.hasFocus():
            from PySide6.QtGui import QColor, QPen, QPainter

            _override = getattr(self, "_focus_ring_color", None)
            if _override is not None:
                try:
                    c = QColor(_override) if not isinstance(_override, QColor) else QColor(_override)
                    if not c.isValid():
                        raise ValueError("invalid override color")
                except Exception:
                    logger.warning("BaseFlyout: invalid focus ring override color", exc_info=True)
                    tm = ThemeManager.get_instance()
                    accent = tm.try_get_color("accent")
                    c = QColor(accent) if accent is not None and accent.isValid() else QColor(tm.get_color("accent"))
            else:
                # Сверь с Button FocusLayer — accent с alpha 220
                tm = ThemeManager.get_instance()
                accent = tm.try_get_color("accent")
                if accent is not None and accent.isValid():
                    c = QColor(accent)
                else:
                    c = QColor(tm.get_color("accent"))
                try:
                    c.setAlpha(220)
                except Exception:
                    pass
            from sli_ui_toolkit.ui.managers.ui_scale import UiScale as _US

            factor = _US.get_instance().factor()
            thickness = max(1.0, 2.0 * factor)
            # Пользовательский width переопределяет factor-масштаб, если задан
            if getattr(self, "_focus_ring_base_width", 2) != 2:
                w = int(getattr(self, "_focus_ring_width", 2))
                thickness = float(w)
            w = thickness
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setPen(QPen(c, w))
            p.setBrush(Qt.BrushStyle.NoBrush)
            # Кольцо по капсуле (container), а не по тени — для _ScrollValueFlyout 46x47 это пилюля
            try:
                geom = self.container.geometry()
                # radius как у Button FocusLayer: design_radius = corner_radius / factor
                r_design = float(self.CONTENT_RADIUS) / factor if factor > 0 else float(self.CONTENT_RADIUS)
                # scaled radius уже в geom, но path.addRoundedRect ждёт design_radius
                p.drawRoundedRect(geom.adjusted(w * 0.5, w * 0.5, -w * 0.5, -w * 0.5), r_design, r_design)
            except Exception:
                p.drawRoundedRect(self.rect().adjusted(w * 0.5, w * 0.5, -w * 0.5, -w * 0.5), self.CONTENT_RADIUS, self.CONTENT_RADIUS)
            p.end()

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.hide()
            event.accept()
            return
        if key in (
            Qt.Key.Key_Up, Qt.Key.Key_Down,
            Qt.Key.Key_Left, Qt.Key.Key_Right,
        ):
            if self._navigate_focusable(key):
                event.accept()
                return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            focused = QApplication.focusWidget()
            if focused is not None and focused is not self:
                from PySide6.QtWidgets import QAbstractButton

                from sli_ui_toolkit.ui.widgets.buttons.button import Button
                # Flyout rows (e.g. CsdMenuRow) are the toolkit's own Button,
                # not QAbstractButton — it isn't a Qt button subclass, but it
                # exposes a QAbstractButton.click()-parity method.
                if isinstance(focused, (QAbstractButton, Button)):
                    focused.click()
                    event.accept()
                    return
        super().keyPressEvent(event)

    def _navigate_focusable(self, key: int) -> bool:
        """Move focus to the next/previous StrongFocus child.

        Returns ``True`` if focus was moved, ``False`` to yield.
        """
        children = sorted(
            [
                c for c in self.findChildren(QWidget)
                if (
                    c.focusPolicy() == Qt.FocusPolicy.StrongFocus
                    and c.isVisible()
                    and c.isEnabled()
                )
            ],
            key=lambda w: w.mapToGlobal(w.rect().center()).x(),
        )
        if not children:
            return False
        focused = QApplication.focusWidget()
        idx = next((i for i, c in enumerate(children) if c is focused), None)
        if key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            # Up/Down normally wrap within this flyout's own children (see
            # the fallback below) -- fine for a flyout that's just a
            # self-contained popover. But a flyout linked below a specific
            # widget (NavigationManager.link_below, e.g.
            # ToolbarRowsSection entering it via extension_below) reads as
            # a *continuation* of that widget rather than an isolated
            # overlay -- Up at this flyout's first control (or Down at its
            # last) should step back out to the linked owner instead of
            # wrapping around its own content. Only flyouts that opted
            # into a link have an owner here, so unlinked flyouts keep
            # wrapping exactly as before.
            # For PanelVisibility (toggle, single horizontal row) Up from *any*
            # button should return to anchor (otherwise only leftmost can leave,
            # bug seen as "only rightmost index can leave").
            # _nav_exit="down"/"up"/"any"/True — декларативный выход из любого места,
            # а не только с края (напр. MagnifierColorOptions side="above" → Down из любого).
            nav_exit = getattr(self, "_nav_exit", None) or getattr(self, "_nav_exit_any", None)
            if nav_exit:
                want_up = nav_exit in (True, "any", "both", "up", "up_any", "any_up")
                want_down = nav_exit in (True, "any", "both", "down", "down_any", "any_down")
                if (want_up and key == Qt.Key.Key_Up) or (want_down and key == Qt.Key.Key_Down):
                    from sli_ui_toolkit.managers import NavigationManager

                    owner = NavigationManager.get_instance().extension_owner(self)
                    if owner is not None:
                        owner.setFocus(Qt.FocusReason.OtherFocusReason)
                        return True
            is_toggle = getattr(self, "flyout_group", None) == "toggle"
            if is_toggle and key == Qt.Key.Key_Up:
                from sli_ui_toolkit.managers import NavigationManager

                owner = NavigationManager.get_instance().extension_owner(self)
                if owner is not None:
                    owner.setFocus(Qt.FocusReason.OtherFocusReason)
                    return True
            at_top = idx is not None and idx == 0
            at_bottom = idx is not None and idx == len(children) - 1
            if (key == Qt.Key.Key_Up and at_top) or (key == Qt.Key.Key_Down and at_bottom):
                # For toggle, Up already handled above; Down at last still needs owner return
                if is_toggle and key == Qt.Key.Key_Up:
                    return True  # already handled
                from sli_ui_toolkit.managers import NavigationManager

                owner = NavigationManager.get_instance().extension_owner(self)
                if owner is not None:
                    owner.setFocus(Qt.FocusReason.OtherFocusReason)
                    return True
        if key in (Qt.Key.Key_Down, Qt.Key.Key_Right):
            target = children[(idx + 1) % len(children)] if idx is not None else children[0]
        else:
            target = children[(idx - 1) % len(children)] if idx is not None else children[-1]
        target.setFocus(Qt.FocusReason.OtherFocusReason)
        return True

    def eventFilter(self, obj, event):  # noqa: N802 — Qt API
        if (
            self._gpu_fill is not None
            and obj is self.container
            and event.type() == QEvent.Type.Resize
        ):
            self._gpu_fill.setGeometry(self.container.rect())
        # Focus guard: while a flyout child holds focus, prevent Qt's
        # focus chain from redirecting it to a widget outside the flyout
        # (e.g. CsdMenuTrigger getting TabFocusReason after the flyout
        # opens).  Redirect back to the target child.
        # While a hide-fade is in progress the guard must not fight focus
        # moving to a newly opened dialog (File → Settings) — otherwise
        # every FocusIn(MainWindow/SettingsDialog) during the ~fade ms is
        # bounced back to CsdMenuRow, creating a focusChanged flood and
        # transient re-probes (see Improve-ImgSLI transient_ui_manager).
        if (
            getattr(self, "_focus_guard_installed", False)
            and not getattr(getattr(self, "_fade", None), "hide_fade_in_progress", False)
            and event.type() == QEvent.Type.FocusIn
            and obj is not self
            and isinstance(obj, QWidget)
            and not self.isAncestorOf(obj)
            and hasattr(self, "_grab_focus_target")
            and self._grab_focus_target is not None
        ):
            if shiboken6.isValid(self._grab_focus_target):
                import traceback

                _caller = "".join(traceback.format_stack()[-5:-3])
                _flyout_debug(
                    "[flyout-nav] focus guard: redirecting FocusIn(%s id=%s objName=%s) back to %s id=%s (flyout id=%s hide_fade=%s) caller=%s",
                    type(obj).__name__,
                    id(obj),
                    obj.objectName(),
                    type(self._grab_focus_target).__name__,
                    id(self._grab_focus_target),
                    id(self),
                    getattr(getattr(self, "_fade", None), "hide_fade_in_progress", False),
                    _caller.strip(),
                )
                self._grab_focus_target.setFocus(
                    self._grab_focus_reason
                )
                return True  # consume the event
        return super().eventFilter(obj, event)

    def add_widget(self, widget):
        self.content_layout.addWidget(widget)

    def _fade_opacity_proxy(self) -> float:
        return self._fade.opacity


BaseFlyout.inspect_spec = InspectSpec(  # type: ignore[attr-defined]
    family="BaseFlyout",
    state=(
        SpecField("pinned", "pinned"),
        SpecField("flyout_group", "flyout_group"),
        SpecField("anchor", "_anchor_widget", private=True),
        SpecField("fade_opacity", "_fade_opacity_proxy", private=True),
        SpecField("visible", "isVisible"),
    ),
    token_family=("surface.background", "flyout.border", "shadow.color", "separator.color"),
    docs='docs/user/FLYOUT_SYSTEM.md',
)

from sli_ui_toolkit.ui.widget_descriptor import InspectSection, WidgetDescriptor

BaseFlyout.widget_descriptor = WidgetDescriptor(
    family=BaseFlyout.inspect_spec.family,
    inspect=InspectSection(
        config=getattr(BaseFlyout.inspect_spec, 'config', ()),
        state=BaseFlyout.inspect_spec.state,
        token_family=getattr(BaseFlyout.inspect_spec, 'token_family', ()),
        regions=getattr(BaseFlyout.inspect_spec, 'regions', False),
        layers=getattr(BaseFlyout.inspect_spec, 'layers', False),
        docs=getattr(BaseFlyout.inspect_spec, 'docs', ''),
        preview_seed=getattr(BaseFlyout.inspect_spec, 'preview_seed', None),
        apply_config_refresh=getattr(BaseFlyout.inspect_spec, 'apply_config_refresh', None),
    ),
)