"""Close-button machinery for the adaptive tab strip.

``_CloseButtonSlot`` hosts one close Button inside a tab, keeps the slot
sized to the button at every UiScale factor, and forwards hover
events into the owning tab bar so tab hover/highlight stays consistent
while the cursor is over the button.
"""

from __future__ import annotations

from enum import Enum

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.managers.ui_scale import scaled_px
from sli_ui_toolkit.ui.widgets.buttons import DrawContext, Layer


class _CloseButtonTabBackgroundLayer(Layer):
    def draw(self, ctx: DrawContext, tm: ThemeManager) -> None:
        slot = ctx.widget.parentWidget()
        tab_bar = slot.parentWidget() if slot is not None else None
        color = None
        get_color = getattr(tab_bar, "close_slot_background_color", None)
        if callable(get_color):
            color = get_color(slot)
        if color is None or color.alpha() <= 0:
            return
        ctx.painter.fillRect(ctx.rect, color)


class CloseButtonPolicy(str, Enum):
    NONE = "none"
    CURRENT_ONLY = "current_only"
    ALL = "all"
    ALL_WHEN_FIT_ELSE_CURRENT = "all_when_fit_else_current"


class _CloseButtonSlot(QWidget):
    def __init__(
        self,
        button: QWidget,
        *,
        vertical_offset: int = 1,
        design_size: int = 28,
        parent=None,
    ):
        super().__init__(parent)
        self.button = button
        self._vertical_offset = int(vertical_offset)
        self._design_size = max(1, int(design_size))
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        button.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        button.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        button.setAutoFillBackground(False)
        self.setMouseTracking(True)
        button.setMouseTracking(True)
        button.setParent(self)
        button.installEventFilter(self)
        self.resync()

    def resync(self) -> None:
        """Re-fit the slot to the close button's scaled size.

        The slot's fixed size is baked from the button's geometry at
        creation; a live UiScale change rescales the button but not the
        slot, so the button would stick out of the tab's right edge and
        sit vertically off-center until the next create/remove cycle.

        Sizes are derived from the DESIGN size (not ``button.width()``):
        the bar's own ``scale_changed`` handler runs before the buttons'
        handlers (subscription order), so reading the button would see the
        previous factor's size.
        """
        offset = scaled_px(self._vertical_offset)
        size = scaled_px(self._design_size)
        self.setFixedSize(size, size + offset * 2)
        self.button.move(0, max(0, offset * 2))

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)

    def eventFilter(self, watched, event):  # noqa: N802
        if watched is self.button and event.type() in (
            QEvent.Type.Enter,
            QEvent.Type.MouseMove,
            QEvent.Type.Leave,
        ):
            tab_bar = self.parentWidget()
            if hasattr(tab_bar, "set_hover_from_global"):
                if event.type() == QEvent.Type.Leave:
                    global_pos = QCursor.pos()
                elif hasattr(event, "globalPosition"):
                    global_pos = event.globalPosition().toPoint()
                else:
                    global_pos = self.button.mapToGlobal(event.pos())
                tab_bar.set_hover_from_global(global_pos)
                if event.type() in (QEvent.Type.Enter, QEvent.Type.MouseMove):
                    self._force_button_hover_region(global_pos)
        return super().eventFilter(watched, event)

    def enterEvent(self, event):  # noqa: N802
        self._sync_parent_hover("slot-enter")
        super().enterEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802
        self._sync_parent_hover("slot-move")
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):  # noqa: N802
        self._sync_parent_hover("slot-leave")
        super().leaveEvent(event)

    def _sync_parent_hover(self, reason: str) -> None:
        tab_bar = self.parentWidget()
        set_hover = getattr(tab_bar, "set_hover_from_global", None)
        if not callable(set_hover):
            return
        global_pos = QCursor.pos()
        set_hover(global_pos)

    def _force_button_hover_region(self, global_pos) -> None:
        update_hover_region = getattr(self.button, "_update_hover_region", None)
        if update_hover_region is None:
            return
        local_pos = self.button.mapFromGlobal(global_pos)
        if not self.button.rect().contains(local_pos):
            return
        update_hover_region(QPointF(local_pos))
