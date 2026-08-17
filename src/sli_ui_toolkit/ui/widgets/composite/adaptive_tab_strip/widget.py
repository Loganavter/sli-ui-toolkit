"""AdaptiveTabStrip — the thin host facade of the adaptive tab strip.

Owns the row layout (tab bar + add button), the close-button policy and
slots, and the QTabBar-like compatibility surface; everything about the bar
itself (tabs, painting, scrolling, hover) lives in ``_AdaptiveTabBar``
(tab_bar.py) and the close-button machinery in ``close_button.py``.
"""

from __future__ import annotations

import math
from typing import Any

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QTabBar, QWidget

from sli_ui_toolkit.ui.inspector.spec import InspectSpec, SpecField
from sli_ui_toolkit.ui.managers.ui_scale import UiScale, scaled_px
from sli_ui_toolkit.ui.widgets.buttons import Button, default_layers

from .close_button import (
    CloseButtonPolicy,
    _CloseButtonSlot,
    _CloseButtonTabBackgroundLayer,
)
from .tab_bar import _AdaptiveTabBar


class AdaptiveTabStrip(QWidget):
    currentChanged = Signal(int)
    tabCloseRequested = Signal(int)
    tabContextMenuRequested = Signal(int, QPoint)
    addRequested = Signal()

    def __init__(
        self,
        *,
        add_icon: Any,
        close_icon: Any,
        close_policy: CloseButtonPolicy = CloseButtonPolicy.ALL_WHEN_FIT_ELSE_CURRENT,
        single_tab_closable: bool = True,
        close_button_size: int = 28,
        close_icon_size: int = 16,
        close_button_vertical_offset: int = 1,
        margins: tuple[int, int, int, int] = (0, 4, 8, 4),
        spacing: int = 2,
        parent=None,
    ):
        super().__init__(parent)
        self.close_policy = CloseButtonPolicy(close_policy)
        self.single_tab_closable = bool(single_tab_closable)
        self._add_icon = add_icon
        self._close_icon = close_icon
        self._close_button_size = int(close_button_size)
        self._close_icon_size = int(close_icon_size)
        self._close_button_vertical_offset = int(close_button_vertical_offset)
        self._design_margins = tuple(int(m) for m in margins)
        self._design_spacing = int(spacing)
        self._updating_close_buttons = False

        self.tab_bar = _AdaptiveTabBar(
            close_button_width=scaled_px(self._close_button_size),
            parent=self,
        )
        self.add_button = Button(add_icon, parent=self)
        self._sync_visual_tab_height()

        layout = QHBoxLayout(self)
        self._apply_layout_metrics()
        layout.addWidget(self.tab_bar)
        layout.addWidget(self.add_button, 0, Qt.AlignmentFlag.AlignBottom)
        layout.addStretch(1)

        self.tab_bar.currentChanged.connect(self._on_current_changed)
        self.tab_bar.tabContextMenuRequested.connect(self.tabContextMenuRequested)
        self.add_button.clicked.connect(self.addRequested)
        UiScale.get_instance().scale_changed.connect(self._on_scale_changed)

    def _apply_layout_metrics(self) -> None:
        layout = self.layout()
        if layout is None:
            return
        layout.setContentsMargins(
            *(scaled_px(m) for m in self._design_margins)
        )
        layout.setSpacing(scaled_px(self._design_spacing))

    def _sync_visual_tab_height(self) -> None:
        plus_height = max(
            self.add_button.sizeHint().height(),
            self.add_button.minimumHeight(),
            self.add_button.height(),
        )
        self.tab_bar.set_visual_tab_height(plus_height)
        self.tab_bar.setMinimumHeight(
            plus_height
            + math.ceil(
                self.tab_bar._SELECTED_SHADOW_OFFSET
                + self.tab_bar._SELECTED_SHADOW_SPREAD
            )
        )

    def _on_scale_changed(self, _factor: float) -> None:
        self._apply_layout_metrics()
        self._sync_visual_tab_height()
        self.tab_bar._relayout()
        self.tab_bar.updateGeometry()
        self.tab_bar.update()
        self.refresh_close_buttons()
        self.updateGeometry()
        self.update()
        # The strip's own updateGeometry() does not reliably re-flow the
        # parent layout (observed live: the strip keeps the previous
        # factor's height until an explicit activate) — re-assert size and
        # activate the parent's layout on the next tick.
        from PySide6.QtCore import QTimer

        QTimer.singleShot(0, self._finish_scale_resync)

    def _finish_scale_resync(self) -> None:
        try:
            self.adjustSize()
        except RuntimeError:
            return
        parent = self.parentWidget()
        if parent is not None and parent.layout() is not None:
            parent.layout().invalidate()
            parent.layout().activate()

    def _on_current_changed(self, index: int) -> None:
        self.refresh_close_buttons()
        self.currentChanged.emit(index)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.refresh_close_buttons()

    def refresh_close_buttons(self) -> None:
        if self._updating_close_buttons:
            return
        self._updating_close_buttons = True
        try:
            count = self.count()
            show_all = self._should_show_all_close_buttons()
            for index in range(count):
                existing = self.tab_bar.tabButton(index, QTabBar.ButtonPosition.RightSide)
                should_show = self._should_show_close_button(index, count, show_all)
                if should_show and existing is None:
                    self.tab_bar.setTabButton(
                        index,
                        QTabBar.ButtonPosition.RightSide,
                        self._create_close_slot(),
                    )
                elif not should_show and existing is not None:
                    self.tab_bar.setTabButton(index, QTabBar.ButtonPosition.RightSide, None)
        finally:
            self._updating_close_buttons = False

    def _row_layout(self) -> QHBoxLayout:
        # Always set in __init__ (QHBoxLayout(self)) — never None in practice.
        layout = self.layout()
        assert isinstance(layout, QHBoxLayout)
        return layout

    def _should_show_all_close_buttons(self) -> bool:
        if self.close_policy is CloseButtonPolicy.ALL:
            return True
        if self.close_policy is CloseButtonPolicy.CURRENT_ONLY:
            return False
        row_layout = self._row_layout()
        margins = row_layout.contentsMargins()
        available = (
            self.contentsRect().width()
            - margins.left()
            - margins.right()
            - max(self.add_button.width(), self.add_button.sizeHint().width())
            - row_layout.spacing()
        )
        return self.tab_bar.full_tabs_width() <= available

    def _should_show_close_button(self, index: int, count: int, show_all: bool) -> bool:
        if self.close_policy is CloseButtonPolicy.NONE:
            return False
        if count <= 0 or (count == 1 and not self.single_tab_closable):
            return False
        return show_all or index == self.currentIndex()

    def _create_close_slot(self) -> QWidget:
        button = Button(
            self._close_icon,
            size=(self._close_button_size, self._close_button_size),
            icon_size=self._close_icon_size,
            corner_radius=5,
            variant="ghost",
            layers=[_CloseButtonTabBackgroundLayer(), *default_layers()],
        )
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        slot = _CloseButtonSlot(
            button,
            vertical_offset=self._close_button_vertical_offset,
            design_size=self._close_button_size,
            parent=self.tab_bar,
        )
        button.clicked.connect(lambda: self._emit_close_for_slot(slot))
        return slot

    def _emit_close_for_slot(self, slot: QWidget) -> None:
        for index in range(self.count()):
            if self.tab_bar.tabButton(index, QTabBar.ButtonPosition.RightSide) is slot:
                self.tabCloseRequested.emit(index)
                return

    # QTabBar-like compatibility surface.
    def addTab(self, text: str) -> int:  # noqa: N802
        index = self.tab_bar.addTab(text)
        self._row_layout().activate()
        self.refresh_close_buttons()
        return index

    def insertTab(self, index: int, text: str) -> int:  # noqa: N802
        index = self.tab_bar.insertTab(index, text)
        self._row_layout().activate()
        self.refresh_close_buttons()
        return index

    def removeTab(self, index: int) -> None:  # noqa: N802
        self.tab_bar.removeTab(index)
        self._row_layout().activate()
        self.refresh_close_buttons()

    def replaceTab(self, index: int, text: str) -> int:  # noqa: N802
        """Swap the tab at ``index`` for a new one without a visible
        intermediate frame.

        A naive ``removeTab`` followed by ``addTab``/``insertTab`` briefly
        changes the tab count, which shifts every tab after ``index`` to
        close the gap and then shifts them back once the replacement is
        inserted. Disabling updates for the whole swap guarantees only the
        final layout is ever painted, instead of a transient reflow frame.
        """
        updates_were_enabled = self.updatesEnabled()
        self.setUpdatesEnabled(False)
        try:
            self.tab_bar.removeTab(index)
            new_index = self.tab_bar.insertTab(index, text)
            self._row_layout().activate()
            self.refresh_close_buttons()
        finally:
            self.setUpdatesEnabled(updates_were_enabled)
        if updates_were_enabled:
            self.update()
        return new_index

    def count(self) -> int:
        return self.tab_bar.count()

    def currentIndex(self) -> int:  # noqa: N802
        return self.tab_bar.currentIndex()

    def setCurrentIndex(self, index: int) -> None:  # noqa: N802
        self.tab_bar.setCurrentIndex(index)

    def setTabData(self, index: int, data: Any) -> None:  # noqa: N802
        self.tab_bar.setTabData(index, data)

    def tabData(self, index: int) -> Any:  # noqa: N802
        return self.tab_bar.tabData(index)

    def setTabToolTip(self, index: int, text: str) -> None:  # noqa: N802
        self.tab_bar.setTabToolTip(index, text)

    def tabText(self, index: int) -> str:  # noqa: N802
        return self.tab_bar.tabText(index)

    def setTabText(self, index: int, text: str) -> None:  # noqa: N802
        self.tab_bar.setTabText(index, text)

    def tabButton(self, index: int, position):  # noqa: N802
        return self.tab_bar.tabButton(index, position)

    def tabRect(self, index: int) -> QRect:  # noqa: N802
        return self.tab_bar.tabRect(index)

    def blockSignals(self, block: bool) -> bool:  # noqa: N802
        previous = super().blockSignals(block)
        self.tab_bar.blockSignals(block)
        return previous

def _seed_preview_tabs(preview, live) -> None:
    """Copy the live strip's tabs onto a fresh preview instance.

    The inspector's config snippet carries construction values only —
    without this, a stateful composite like the tab strip previews as an
    empty bar (nothing but the panel backdrop). Runs after every preview
    rebuild; safe no-op when the live strip has no tabs."""
    try:
        for index in range(live.count()):
            preview.addTab(live.tabText(index))
        preview.setCurrentIndex(live.currentIndex())
    except Exception:
        pass


def _refresh_config_applied(live, applied: tuple[str, ...]) -> None:
    """Re-run the layout/close-button passes ``__init__`` performs, so
    config-snippet values written onto the LIVE instance take effect:
    margins/spacing re-apply, the tab height re-syncs, and the close
    buttons are rebuilt with the current size/icon/offset (the generic
    attribute write + repaint cannot see these)."""
    try:
        live._apply_layout_metrics()
        live._sync_visual_tab_height()
        live.tab_bar._relayout()
        live.tab_bar.updateGeometry()
        live.tab_bar.update()
        for index in range(live.count()):
            live.tab_bar.setTabButton(
                index, QTabBar.ButtonPosition.RightSide, None
            )
        live.refresh_close_buttons()
        live.updateGeometry()
        live.update()
    except Exception:
        pass


AdaptiveTabStrip.inspect_spec = InspectSpec(  # type: ignore[attr-defined]
    family="AdaptiveTabStrip",
    state=(
        SpecField("count", "count"),
        SpecField("current_index", "currentIndex"),
    ),
    token_family=(
        "button.toggle.background.normal",
        "Window",
        "separator.color",
        "button.toggle.background.hover",
        "WindowText",
    ),
    preview_seed=_seed_preview_tabs,
    apply_config_refresh=_refresh_config_applied,
    docs='docs/user/TABS_API.md',
)