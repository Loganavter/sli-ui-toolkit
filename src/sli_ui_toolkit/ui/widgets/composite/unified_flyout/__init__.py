from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget

from .bootstrap import _UnifiedFlyoutBootstrapMixin
from .common import FlyoutMode
from .content import _UnifiedFlyoutContentMixin
from .dragdrop import _UnifiedFlyoutDragDropMixin
from .layout import _UnifiedFlyoutLayoutMixin
from .refresh import _UnifiedFlyoutRefreshMixin
from .style import _UnifiedFlyoutStyleMixin
from .simple_adapter import (
    SimpleUnifiedFlyoutController,
    SimpleUnifiedFlyoutStore,
    UnifiedFlyoutItem,
    make_main_window_proxy,
)

__all__ = [
    "FlyoutMode",
    "UnifiedFlyout",
    "UnifiedFlyoutItem",
    "SimpleUnifiedFlyoutStore",
    "SimpleUnifiedFlyoutController",
]

class UnifiedFlyout(
    _UnifiedFlyoutBootstrapMixin,
    _UnifiedFlyoutStyleMixin,
    _UnifiedFlyoutLayoutMixin,
    _UnifiedFlyoutRefreshMixin,
    _UnifiedFlyoutContentMixin,
    _UnifiedFlyoutDragDropMixin,
    QWidget,
):
    item_chosen = Signal(int, int)
    simple_item_chosen = Signal(int)
    # list_num (1|2), index — host should open a context menu (or remove).
    item_context_menu_requested = Signal(int, int)
    closing_animation_finished = Signal()
    # Identity tag for host ``GroupShowPolicy`` rules — no behavior by itself.
    flyout_group = "unified_list"

    SHADOW_RADIUS = 10
    MARGIN = 0
    # Gap between anchor bottom and the list panel top. Do not reuse
    # SimpleOptionsFlyout's (APPEAR_EXTRA_Y - MARGIN): that offset is for the
    # outer flyout widget which carries its own top margin; UnifiedFlyout
    # positions the panel content rect directly (shadow halo sits above it).
    SINGLE_PANEL_GAP_Y = 6

    def __init__(self, store, main_controller, main_window):
        super().__init__(main_window)
        self.store = store
        self.main_controller = main_controller
        self.main_window = main_window

        self._initialize_runtime_state()
        self._initialize_widget()
        self._attach_overlay_layer()
        self._initialize_components()
        self.hide()

    def is_drag_enabled(self) -> bool:
        return bool(getattr(self, "_drag_enabled", True))

    def set_drag_enabled(self, enabled: bool) -> None:
        self._drag_enabled = bool(enabled)
    @classmethod
    def create_double_list(
        cls,
        parent_window,
        anchor_left,
        anchor_right,
        *,
        left_items: list | None = None,
        right_items: list | None = None,
        current_left: int = -1,
        current_right: int = -1,
    ) -> "UnifiedFlyout":
        """Self-contained constructor — no external store/controller required.

        Provides plain item lists and two anchor widgets. The widget builds its
        own minimal store/controller internally.
        """
        store = SimpleUnifiedFlyoutStore()
        store.set_lists(
            left_items or [],
            right_items or [],
            current_left=current_left,
            current_right=current_right,
        )
        controller = SimpleUnifiedFlyoutController(store)
        flyout = cls(store, controller, parent_window)
        flyout.set_list_anchors(anchor_left, anchor_right)
        # Standalone default: right-click removes the row (no app menu).
        flyout.item_context_menu_requested.connect(
            controller.remove_specific_image_from_list
        )
        return flyout

    def set_lists(
        self,
        left_items: list,
        right_items: list,
        *,
        current_left: int = -1,
        current_right: int = -1,
    ) -> None:
        """Update items when constructed via `create_double_list`."""
        if not isinstance(self.store, SimpleUnifiedFlyoutStore):
            raise RuntimeError(
                "set_lists() is only available when the flyout was built via "
                "UnifiedFlyout.create_double_list()."
            )
        self.store.set_lists(
            left_items,
            right_items,
            current_left=current_left,
            current_right=current_right,
        )
        if self.isVisible():
            self._schedule_structure_sync()
