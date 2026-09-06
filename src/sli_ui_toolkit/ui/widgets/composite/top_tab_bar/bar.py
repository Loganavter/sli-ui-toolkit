"""TopTabBar — horizontal content-section tab strip."""

from __future__ import annotations

from typing import Iterable

from PySide6.QtCore import QPointF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QPen
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QWidget

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.buttons import DrawContext, Layer
from sli_ui_toolkit.ui.widgets.buttons.button import Button
from sli_ui_toolkit.ui.widgets.composite.adaptive_tab_strip import CloseButtonPolicy
from sli_ui_toolkit.ui.widgets.composite.top_tab_bar.constants import (
    DEFAULT_TAB_RADIUS,
    TAB_BAR_H_MARGIN,
    TAB_CLOSE_MARGIN,
    TAB_MIN_WIDTH,
    TAB_SPACING,
)
from sli_ui_toolkit.ui.widgets.composite.top_tab_bar.items import TabItem, TabSpec, TopTabItem
from sli_ui_toolkit.ui.widgets.composite.top_tab_bar.tab_button import TopTabButton



class _CloseXLayer(Layer):
    """Painted close (X) glyph with internal padding (no icon asset needed)."""

    def draw(self, ctx: DrawContext, tm: ThemeManager) -> None:
        widget = ctx.widget
        color = tm.try_get_color("dialog.text")
        if color is None or not color.isValid():
            color = QColor(0, 0, 0, 140)
        p = ctx.painter
        p.setPen(QPen(QColor(color), 1.5))
        inset = widget.width() * 0.3
        x0, y0 = inset, inset
        x1, y1 = widget.width() - inset, widget.height() - inset
        p.drawLine(QPointF(x0, y0), QPointF(x1, y1))
        p.drawLine(QPointF(x0, y1), QPointF(x1, y0))


class _CloseSlotBackgroundLayer(Layer):
    """Close-slot background following the TAB BAR's state (the adaptive-tab
    ``close_slot_background_color`` contract): selected tabs use the tab
    background, the hovered tab the hover token, otherwise transparent. When
    the cursor is directly over the X the slot darkens one step, so the
    close button reacts visibly even while its tab is already hovered."""

    def draw(self, ctx: DrawContext, tm: ThemeManager) -> None:
        bar = ctx.widget.parentWidget()
        while bar is not None and not hasattr(bar, "close_slot_background_color_for"):
            bar = bar.parentWidget()
        if bar is None:
            return
        color = bar.close_slot_background_color_for(ctx.widget.parentWidget())
        if color is None or color.alpha() <= 0:
            return
        over = ctx.widget.rect().contains(
            ctx.widget.mapFromGlobal(QCursor.pos())
        )
        if over:
            color = QColor(color).darker(115)
        p = ctx.painter
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(color))
        p.drawRoundedRect(ctx.rect, 5, 5)


class TopTabBar(QWidget):
    """Horizontal content-section tab strip (IconListWidget axis twin)."""

    currentChanged = Signal(int)
    currentItemChanged = Signal(object, object)
    #: emitted when a tab's close (X) region is clicked (disabled by default)
    tabCloseRequested = Signal(int)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        tab_height: int = 32,
        expand_tabs: bool = False,
        show_indicator: bool = False,
        corner_radius: int = DEFAULT_TAB_RADIUS,
        close_policy: CloseButtonPolicy = CloseButtonPolicy.NONE,
        close_zone: int = 20,
    ) -> None:
        super().__init__(parent)
        self._tab_height = int(tab_height)
        self._expand_tabs = bool(expand_tabs)
        self._show_indicator = bool(show_indicator)
        self._corner_radius = int(corner_radius)
        self._close_policy = CloseButtonPolicy(close_policy)
        self._close_zone = max(0, int(close_zone))
        self._close_size = max(12, min(int(close_zone), self._tab_height))
        self._tabs: list[TabSpec] = []
        self._current_index: int = -1
        #: tab index under the cursor (the bar owns hover, adaptive-style:
        #: the close slots derive their background from it)
        self._hover_index: int = -1
        self.setMouseTracking(True)

        # Fixed-width strip inside a stretchable host: QHBoxLayout must never
        # compress Fixed tab buttons into each other when the bar is narrower
        # than its content (that yields negative gaps / overlapping chrome).
        self.setSizePolicy(
            QSizePolicy.Policy.MinimumExpanding,
            QSizePolicy.Policy.Fixed,
        )
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._strip = QWidget(self)
        self._strip.setObjectName("TopTabStrip")
        self._strip.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        layout = QHBoxLayout(self._strip)
        layout.setContentsMargins(TAB_BAR_H_MARGIN, 0, TAB_BAR_H_MARGIN, 0)
        layout.setSpacing(TAB_SPACING)
        self._layout = layout

        outer.addWidget(
            self._strip,
            0,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )
        outer.addStretch(1)
        self._sync_strip_geometry()

        try:
            ThemeManager.get_instance().theme_changed.connect(self._on_theme_changed)
        except Exception:
            pass

    def set_items(self, items: Iterable[TopTabItem | str | tuple]) -> None:
        self.clear()
        for item in items:
            if isinstance(item, TopTabItem):
                self.add_item(item.text, data=item.data)
            elif isinstance(item, tuple):
                text = str(item[0]) if item else ""
                data = item[1] if len(item) > 1 else None
                self.add_item(text, data=data)
            else:
                self.add_item(str(item))

    def add_item(self, text: str, data: object | None = None) -> TabItem:
        closable = self._close_policy is not CloseButtonPolicy.NONE
        button = TopTabButton(
            text=text,
            toggle=True,
            size=(0, self._tab_height),
            variant="top_tab",
            corner_radii=(self._corner_radius, self._corner_radius, 0, 0),
            close_zone=(
                self._close_size + TAB_CLOSE_MARGIN if closable else 0
            ),
        )
        button.set_show_indicator(self._show_indicator)
        button.setFixedHeight(self._tab_height)
        if self._expand_tabs:
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            button.setMinimumWidth(TAB_MIN_WIDTH)
        else:
            button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            button.setFixedWidth(button.sizeHint().width())

        tab = TabSpec(text=text, button=button)
        if data is not None:
            tab.data_roles[int(Qt.ItemDataRole.UserRole)] = data
        self._tabs.append(tab)

        index = len(self._tabs) - 1
        button.clicked.connect(lambda _i=index: self._on_tab_clicked(_i))
        self._layout.addWidget(button)

        if closable:
            # Embedded in the tab's right edge (adaptive-tab close-slot
            # mechanics): the close button is a child of the tab button; its
            # background follows the tab's state, not its own hover.
            close_button = Button(
                size=(self._close_size, self._close_size),
                corner_radius=5,
                variant="default",
                layers=[_CloseSlotBackgroundLayer(), _CloseXLayer()],
            )
            close_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            close_button.setToolTip("Close")
            close_button.clicked.connect(
                lambda _i=index: self.tabCloseRequested.emit(_i)
            )
            button.attach_close_button(close_button)
            tab.close_button = close_button

        self._sync_strip_geometry()
        return TabItem(self, index)

    def clear(self) -> None:
        for tab in self._tabs:
            tab.button.setParent(None)
            tab.button.deleteLater()
            close_button = tab.close_button
            if close_button is not None:
                close_button.setParent(None)
                close_button.deleteLater()
        self._tabs.clear()
        prev = self._current_index
        self._current_index = -1
        self._sync_strip_geometry()
        if prev != -1:
            self.currentChanged.emit(-1)
            self.currentItemChanged.emit(None, None)

    def count(self) -> int:
        return len(self._tabs)

    def item(self, idx: int) -> TabItem | None:
        if 0 <= idx < len(self._tabs):
            return TabItem(self, idx)
        return None

    def currentIndex(self) -> int:
        return self._current_index

    def setCurrentIndex(self, idx: int) -> None:
        if idx < 0 or idx >= len(self._tabs):
            idx = -1
        if idx == self._current_index:
            return
        prev = self._current_index
        self._current_index = idx
        for i, tab in enumerate(self._tabs):
            selected = i == idx
            tab.button.set_selected(selected)
            self._sync_tab_chrome(tab, selected)
        prev_item = TabItem(self, prev) if 0 <= prev < len(self._tabs) else None
        curr_item = TabItem(self, idx) if 0 <= idx < len(self._tabs) else None
        self.currentChanged.emit(idx)
        self.currentItemChanged.emit(curr_item, prev_item)

    currentRow = currentIndex
    setCurrentRow = setCurrentIndex

    # -- hover (bar-owned, adaptive-tab contract) ---------------------------

    def _tab_at(self, local_pos) -> int:
        for index, tab in enumerate(self._tabs):
            if tab.button.geometry().contains(local_pos):
                return index
        return -1

    def _set_hover_index(self, index: int) -> None:
        if index == self._hover_index:
            return
        self._hover_index = index
        for i, tab in enumerate(self._tabs):
            # Force the tab's visual hover (the Button hover API only clears;
            # direct property assignment is the reliable setter here).
            tab.button._hovered = i == index
            close_button = tab.close_button
            if close_button is not None:
                close_button.update()

    def set_hover_from_global(self, global_pos) -> None:
        local = self.mapFromGlobal(global_pos)
        index = self._tab_at(local) if self.rect().contains(local) else -1
        self._set_hover_index(index)

    def enterEvent(self, event) -> None:  # noqa: N802
        self.set_hover_from_global(QCursor.pos())
        super().enterEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        self._set_hover_index(self._tab_at(event.position().toPoint()))
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._set_hover_index(-1)
        super().leaveEvent(event)

    def close_slot_background_color_for(self, tab_button) -> QColor | None:
        """Slot fill derived from the BAR's state (selected/hovered/other)."""
        for index, tab in enumerate(self._tabs):
            if tab.button is not tab_button:
                continue
            tm = ThemeManager.get_instance()
            if index == self.currentIndex():
                color = tm.try_get_color("surface.background")
                if color is None:
                    color = tm.try_get_color("Window")
            elif index == self._hover_index:
                color = tm.try_get_color("button.toggle.background.hover")
                if color is None:
                    color = tm.try_get_color("list_item.background.hover")
            else:
                return None
            return QColor(color) if color is not None else None
        return None

    def tabText(self, idx: int) -> str:
        item = self.item(idx)
        return item.text() if item is not None else ""

    def setTabText(self, idx: int, text: str) -> None:
        item = self.item(idx)
        if item is None:
            return
        item.setText(text)
        if not self._expand_tabs and 0 <= idx < len(self._tabs):
            button = self._tabs[idx].button
            button.setFixedWidth(button.sizeHint().width())
        self._sync_strip_geometry()

    def tabData(self, idx: int) -> object | None:
        item = self.item(idx)
        return item.data() if item is not None else None

    def setTabData(self, idx: int, value: object) -> None:
        item = self.item(idx)
        if item is not None:
            item.setData(Qt.ItemDataRole.UserRole, value)

    def sizeHint(self) -> QSize:
        return QSize(self._content_width(), self._tab_height)

    def minimumSizeHint(self) -> QSize:
        # Tabs clip/overflow when the host is narrower than the content (see
        # the squeeze test) — the bar must not force the host wider than it
        # wants, so the minimum is just the chrome floor, not the content.
        return QSize(self._layout.contentsMargins().left()
                     + self._layout.contentsMargins().right() + TAB_MIN_WIDTH,
                     self._tab_height)

    def _content_width(self) -> int:
        margins = self._layout.contentsMargins()
        width = margins.left() + margins.right()
        if not self._tabs:
            return max(width, TAB_MIN_WIDTH)
        widths = [
            max(TAB_MIN_WIDTH, tab.button.sizeHint().width())
            for tab in self._tabs
        ]
        width += sum(widths)
        if len(widths) > 1:
            width += self._layout.spacing() * (len(widths) - 1)
        return width

    def _sync_strip_geometry(self) -> None:
        width = self._content_width()
        self._strip.setFixedSize(width, self._tab_height)
        self.setFixedHeight(self._tab_height)
        self.updateGeometry()

    def _on_tab_clicked(self, idx: int) -> None:
        if idx == self._current_index:
            return
        self.setCurrentIndex(idx)

    def _sync_tab_chrome(self, tab: TabSpec, selected: bool) -> None:
        tm = ThemeManager.get_instance()
        tab.button.setBorderColor(None)
        if selected:
            accent = tm.try_get_color("accent")
            tab.button.setForegroundColor(
                QColor(accent) if accent is not None else None
            )
        else:
            tab.button.setForegroundColor(None)
        tab.button.update()

    def _on_theme_changed(self, *_args) -> None:
        for i, tab in enumerate(self._tabs):
            self._sync_tab_chrome(tab, i == self._current_index)
        if not self._expand_tabs:
            for tab in self._tabs:
                tab.button.setFixedWidth(tab.button.sizeHint().width())
        self._sync_strip_geometry()
