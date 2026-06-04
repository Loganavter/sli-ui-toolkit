from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QWidget

from sli_ui_toolkit.config import get_flyout_timings
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
    item_chosen = pyqtSignal(int, int)
    simple_item_chosen = pyqtSignal(int)
    closing_animation_finished = pyqtSignal()

    SHADOW_RADIUS = 10
    MARGIN = 0
    SINGLE_APPEAR_EXTRA_Y = 8
    DOUBLE_CONTENT_EXTRA_Y = 8

    _move_duration_ms = get_flyout_timings().flyout_animation_duration_ms

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
        host = parent_window
        make_main_window_proxy(host, anchor_left, anchor_right)
        return cls(store, controller, host)

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
