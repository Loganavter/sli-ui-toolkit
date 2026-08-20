from __future__ import annotations
from sli_ui_toolkit.ui.inspector.spec import InspectSpec, SpecField  # noqa: E402

from dataclasses import dataclass
from typing import Iterable

from PySide6.QtCore import QEvent, QEasingCurve, QSize, Signal
from PySide6.QtWidgets import QHBoxLayout

from sli_ui_toolkit.icons import resolve_icon
from sli_ui_toolkit.managers import AnchoredFlyoutAutoHide
from sli_ui_toolkit.ui.managers.ui_scale import UiScale, scaled_px
from sli_ui_toolkit.ui.widgets.buttons import Button
from sli_ui_toolkit.ui.widgets.composite.base_flyout import AnimationAxis, BaseFlyout

@dataclass(slots=True)
class IconAction:
    action_id: str
    icon: object = None
    tooltip: str = ""
    visible: bool = True
    enabled: bool = True

class IconActionFlyout(BaseFlyout):
    actionTriggered = Signal(str)
    elementHovered = Signal(str)
    elementHoverEnded = Signal()

    # Identity for host ``GroupShowPolicy``.
    flyout_group = "actions"

    def __init__(
        self,
        parent=None,
        *,
        actions: Iterable[IconAction] | None = None,
        button_size: int = 28,
        icon_size: int = 18,
        animation: str | None = None,
    ):
        super().__init__(parent)
        self._hovered_element = None
        self._anchor_button = None
        self._button_size = int(button_size)
        self._icon_size = int(icon_size)
        # Per-instance show-animation override for show_above/show_aligned.
        # None resolves to the process-wide default_flyout_animation.
        self._default_animation = animation
        self._actions: dict[str, IconAction] = {}
        self._buttons: dict[str, Button] = {}

        self._auto_hide = AnchoredFlyoutAutoHide(
            flyout=self,
            anchor_getter=lambda: self._anchor_button,
            parent=self,
        )

        self.h_layout = QHBoxLayout()
        self.h_layout.setContentsMargins(0, 0, 0, 0)
        self.h_layout.setSpacing(scaled_px(6))
        self.content_layout.addLayout(self.h_layout)
        UiScale.get_instance().scale_changed.connect(self._on_scale_changed)

        self.set_actions(actions or [])

    def _on_scale_changed(self, _factor: float) -> None:
        self.h_layout.setSpacing(scaled_px(6))
        for button in self._buttons.values():
            button.setFixedSize(scaled_px(self._button_size), scaled_px(self._button_size))
            button.setIconSize(QSize(scaled_px(self._icon_size), scaled_px(self._icon_size)))
        self.updateGeometry()
        self.update()

    def set_actions(self, actions: Iterable[IconAction]) -> None:
        for button in self._buttons.values():
            button.removeEventFilter(self)
            self.h_layout.removeWidget(button)
            button.deleteLater()
        self._buttons.clear()
        self._actions.clear()

        for action in actions:
            spec = action if isinstance(action, IconAction) else IconAction(**action)
            button = Button(spec.icon, parent=self.container)
            button.setFixedSize(scaled_px(self._button_size), scaled_px(self._button_size))
            button.setIconSize(QSize(scaled_px(self._icon_size), scaled_px(self._icon_size)))
            button.setToolTip(spec.tooltip)
            button.setVisible(spec.visible)
            button.setEnabled(spec.enabled)
            button.clicked.connect(
                lambda _checked=False, action_id=spec.action_id: self._trigger_action(action_id)
            )
            button.installEventFilter(self)
            button.setProperty("element_name", spec.action_id)
            self.h_layout.addWidget(button)
            self._actions[spec.action_id] = spec
            self._buttons[spec.action_id] = button

        self.update_state()

    def action_button(self, action_id: str) -> Button | None:
        return self._buttons.get(action_id)

    def set_action_state(
        self,
        action_id: str,
        *,
        icon: object | None = None,
        tooltip: str | None = None,
        visible: bool | None = None,
        enabled: bool | None = None,
    ) -> None:
        button = self._buttons.get(action_id)
        spec = self._actions.get(action_id)
        if button is None or spec is None:
            return

        if icon is not None:
            spec.icon = icon
            button.setIcon(resolve_icon(icon))
        if tooltip is not None:
            spec.tooltip = tooltip
            button.setToolTip(tooltip)
        if visible is not None:
            spec.visible = bool(visible)
            button.setVisible(spec.visible)
        if enabled is not None:
            spec.enabled = bool(enabled)
            button.setEnabled(spec.enabled)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Enter:
            element_name = obj.property("element_name")
            if element_name and element_name != self._hovered_element:
                self._hovered_element = element_name
                self.elementHovered.emit(element_name)
        elif event.type() == QEvent.Type.Leave:
            if self._hovered_element:
                self._hovered_element = None
                self.elementHoverEnded.emit()

        return super().eventFilter(obj, event)

    def update_state(self):
        self.h_layout.invalidate()
        self.h_layout.activate()
        self.container.updateGeometry()
        self.updateGeometry()
        self.adjustSize()

    def _trigger_action(self, action_id: str) -> None:
        self.actionTriggered.emit(action_id)
        self.hide()

    def show_above(self, anchor):
        self.update_state()
        if self.isVisible() and self._anchor_button is anchor:
            self.hide()
            return
        self._anchor_button = anchor
        self.show_aligned(anchor, "top-center", "bottom-center")

    def show_aligned(
        self,
        anchor_widget,
        anchor_point="top-center",
        flyout_point="bottom-center",
        *,
        position: str | None = None,
        offset=5,
        animation: str | None = None,
        animation_duration_ms: int | None = None,
        animation_distance: int | None = None,
        animation_axis: AnimationAxis = "auto",
        easing: QEasingCurve.Type = QEasingCurve.Type.OutQuad,
        toggle: bool = True,
        grab_focus: bool = True,
        register_nav_section: bool | None = None,
    ):
        # ``toggle`` guards the click-to-open/close behaviour used by
        # show_above(). Callers that reposition an already-visible flyout in
        # response to unrelated state changes (e.g. hover/store updates) must
        # pass toggle=False, otherwise this would hide the flyout instead of
        # just moving it.
        if toggle and self.isVisible() and self._anchor_button is anchor_widget:
            self.hide()
            return
        self._anchor_button = anchor_widget
        # Per-instance override wins unless the call passed an explicit value.
        if animation is None:
            animation = self._default_animation
        super().show_aligned(
            anchor_widget,
            anchor_point=anchor_point,
            flyout_point=flyout_point,
            position=position,
            offset=offset,
            animation=animation,
            animation_duration_ms=animation_duration_ms,
            animation_distance=animation_distance,
            animation_axis=animation_axis,
            easing=easing,
            grab_focus=grab_focus,
            register_nav_section=register_nav_section,
        )

    def schedule_auto_hide(self, ms: int):
        self._auto_hide.schedule(ms)

    def cancel_auto_hide(self):
        auto_hide = getattr(self, "_auto_hide", None)
        if auto_hide is not None:
            auto_hide.cancel()

    def hide(self):
        self.cancel_auto_hide()
        super().hide()

IconActionFlyout.inspect_spec = InspectSpec(  # type: ignore[attr-defined]
    family="IconActionFlyout",
    state=(
        SpecField("pinned", "pinned"),
        SpecField("flyout_group", "flyout_group"),
        SpecField("anchor", "_anchor_widget", private=True),
        SpecField("fade_opacity", "_fade_opacity_proxy", private=True),
        SpecField("visible", "isVisible"),
    ),
    token_family=("flyout.background", "flyout.border", "shadow.color", "separator.color"),
    docs='docs/user/FLYOUT_SYSTEM.md',
)

from sli_ui_toolkit.ui.widget_descriptor import InspectSection, WidgetDescriptor

IconActionFlyout.widget_descriptor = WidgetDescriptor(
    family=IconActionFlyout.inspect_spec.family,
    inspect=InspectSection(
        config=getattr(IconActionFlyout.inspect_spec, 'config', ()),
        state=IconActionFlyout.inspect_spec.state,
        token_family=getattr(IconActionFlyout.inspect_spec, 'token_family', ()),
        regions=getattr(IconActionFlyout.inspect_spec, 'regions', False),
        layers=getattr(IconActionFlyout.inspect_spec, 'layers', False),
        docs=getattr(IconActionFlyout.inspect_spec, 'docs', ''),
        preview_seed=getattr(IconActionFlyout.inspect_spec, 'preview_seed', None),
        apply_config_refresh=getattr(IconActionFlyout.inspect_spec, 'apply_config_refresh', None),
    ),
)