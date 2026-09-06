from __future__ import annotations
from sli_ui_toolkit.ui.inspector.spec import InspectSpec, SpecField  # noqa: E402

import logging

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QHBoxLayout, QWidget

from sli_ui_toolkit.managers import AnchoredFlyoutAutoHide
from sli_ui_toolkit.ui.managers.ui_scale import UiScale, scaled_px
from sli_ui_toolkit.ui.widgets.buttons import Button
from sli_ui_toolkit.ui.widgets.composite.base_flyout import BaseFlyout

logger = logging.getLogger(__name__)

class IndexedToggleFlyout(BaseFlyout):
    # Identity for host ``GroupShowPolicy``.
    flyout_group = "toggle"

    def __init__(
        self,
        parent_widget: QWidget,
        *,
        slot_count: int = 3,
        slot_icon=None,
        button_size: int = 28,
        animation: str | None = None,
    ):
        super().__init__(parent_widget)
        self._anchor_button = None
        self._button_size = int(button_size)
        self._slot_icon = slot_icon
        # Per-instance show-animation override for show_for_button. None
        # resolves to the process-wide default_flyout_animation.
        self._default_animation = animation
        self._buttons: list[Button] = []

        self.h_layout = QHBoxLayout()
        self.h_layout.setContentsMargins(0, 0, 0, 0)
        self.h_layout.setSpacing(scaled_px(6))
        self.content_layout.addLayout(self.h_layout)
        UiScale.get_instance().scale_changed.connect(self._refresh_layout)

        self._auto_hide = AnchoredFlyoutAutoHide(
            flyout=self,
            anchor_getter=lambda: self._anchor_button,
            parent=self,
        )

        self.set_slot_count(slot_count)
        self.hide()

    @property
    def buttons(self) -> tuple[Button, ...]:
        return tuple(self._buttons)

    def set_slot_count(self, slot_count: int) -> None:
        slot_count = max(0, int(slot_count))

        while len(self._buttons) < slot_count:
            index = len(self._buttons) + 1
            button = Button(
                self._slot_icon,
                toggle=True,
                badge=index,
                size=(self._button_size, self._button_size),
                parent=self.container,
            )
            button.set_show_strike_through(True)
            self.h_layout.addWidget(button)
            self._buttons.append(button)

        for index, button in enumerate(self._buttons):
            visible = index < slot_count
            button.setVisible(visible)
            button.setBadge(index + 1)
            if not visible:
                button.setBadge(None)

        self._refresh_layout()

    def set_slots(
        self,
        active_states: list[bool] | tuple[bool, ...],
        *,
        display_numbers: list[int | None] | tuple[int | None, ...] | None = None,
    ) -> None:
        self.set_slot_count(len(active_states))
        for index, is_active in enumerate(active_states):
            button = self._buttons[index]
            button.setChecked(not bool(is_active), emit_signal=False)
            display_number = None
            if display_numbers is not None and index < len(display_numbers):
                display_number = display_numbers[index]
            button.setBadge(display_number)
        self._refresh_layout()

    def _refresh_layout(self) -> None:
        self.h_layout.setSpacing(scaled_px(6))
        self.h_layout.invalidate()
        self.h_layout.activate()
        self.container.updateGeometry()
        self.adjustSize()

    def show_for_button(
        self,
        anchor_btn: QWidget,
        parent_widget: QWidget | None = None,
        hover_delay_ms: int = 0,
        *,
        grab_focus: bool = True,
        register_nav_section: bool | None = None,
        animation: str | None = None,
    ):
        def _do_show():
            self._anchor_button = anchor_btn
            # In-app preview must be instant (animation="none") — same fix as
            # slider_hint: fade snapshots hide children and would show an empty
            # box while compositing; host default is "fade" (80ms).
            resolved_anim = animation if animation is not None else self._default_animation
            self.show_aligned(
                anchor_btn,
                "top-center",
                "bottom-center",
                animation=resolved_anim,
                grab_focus=grab_focus,
                register_nav_section=register_nav_section,
            )

        if hover_delay_ms > 0:
            QTimer.singleShot(hover_delay_ms, _do_show)
        else:
            _do_show()

    def schedule_auto_hide(self, ms: int):
        self._auto_hide.schedule(ms)

    def cancel_auto_hide(self):
        auto_hide = getattr(self, "_auto_hide", None)
        if auto_hide is not None:
            auto_hide.cancel()

    def hide(self):
        self.cancel_auto_hide()
        super().hide()

    def contains_global(self, global_pos) -> bool:
        return super().contains_global(global_pos)

IndexedToggleFlyout.inspect_spec = InspectSpec(
    family="IndexedToggleFlyout",
    state=(
        SpecField("pinned", "pinned"),
        SpecField("flyout_group", "flyout_group"),
        SpecField("anchor", "_anchor_widget", private=True),
        SpecField("fade_opacity", "_fade_opacity", private=True),
        SpecField("visible", "isVisible"),
        SpecField("slot_count", "slot_count"),
    ),
    token_family=("flyout.background", "flyout.border", "shadow.color", "separator.color"),
    docs='docs/user/FLYOUT_SYSTEM.md',
)

from sli_ui_toolkit.ui.widget_descriptor import InspectSection, WidgetDescriptor

IndexedToggleFlyout.widget_descriptor = WidgetDescriptor(
    family=IndexedToggleFlyout.inspect_spec.family,
    inspect=InspectSection(
        config=getattr(IndexedToggleFlyout.inspect_spec, 'config', ()),
        state=IndexedToggleFlyout.inspect_spec.state,
        token_family=getattr(IndexedToggleFlyout.inspect_spec, 'token_family', ()),
        regions=getattr(IndexedToggleFlyout.inspect_spec, 'regions', False),
        layers=getattr(IndexedToggleFlyout.inspect_spec, 'layers', False),
        docs=getattr(IndexedToggleFlyout.inspect_spec, 'docs', ''),
        preview_seed=getattr(IndexedToggleFlyout.inspect_spec, 'preview_seed', None),
        apply_config_refresh=getattr(IndexedToggleFlyout.inspect_spec, 'apply_config_refresh', None),
    ),
)