"""TopTabBar — horizontal content-section tab strip."""

from __future__ import annotations

from typing import Iterable

from PySide6.QtCore import QEvent, QPointF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QPen
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QWidget

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.atomic.minimalist_scrollbar import MinimalistScrollBar
from sli_ui_toolkit.ui.managers.ui_metrics import AXIS_FONT, AXIS_SCALE, connect_ui_metrics
from sli_ui_toolkit.ui.managers.ui_scale import scaled_px
from sli_ui_toolkit.ui.widgets.buttons import DrawContext, Layer
from sli_ui_toolkit.ui.widgets.buttons.button import Button
from sli_ui_toolkit.ui.widgets.composite.adaptive_tab_strip import CloseButtonPolicy
from sli_ui_toolkit.ui.widgets.composite.top_tab_bar.style import TabStyle
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
        style: "TabStyle | None" = None,
    ) -> None:
        super().__init__(parent)
        self._tab_height = int(tab_height)
        self._expand_tabs = bool(expand_tabs)
        self._show_indicator = bool(show_indicator)
        self._corner_radius = int(corner_radius)
        self._close_policy = CloseButtonPolicy(close_policy)
        self._close_zone = max(0, int(close_zone))
        self._style = style or TabStyle()
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
        self._strip = QWidget(self)
        self._strip.setObjectName("TopTabStrip")
        self._strip.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        layout = QHBoxLayout(self._strip)
        layout.setContentsMargins(TAB_BAR_H_MARGIN, 0, TAB_BAR_H_MARGIN, 0)
        layout.setSpacing(self._style.tab_spacing(TAB_SPACING))
        self._layout = layout

        self._h_offset = 0
        self._hovering = False
        self.setMouseTracking(True)
        self._h_scroll = MinimalistScrollBar(Qt.Orientation.Horizontal, self)
        self._h_scroll.set_animated_visible(False)
        self._h_scroll.valueChanged.connect(self._on_h_scroll)
        self._sync_strip_geometry()

        try:
            ThemeManager.get_instance().theme_changed.connect(self._on_theme_changed)
        except Exception:
            pass
        try:
            # Tab widths re-fit from ``sizeHint()`` (painted text metrics), so
            # a font landing late must re-flow too, not only a scale change.
            connect_ui_metrics(
                self, self._on_scale_changed, axes=frozenset({AXIS_FONT, AXIS_SCALE})
            )
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
        tab_height = self._scaled_tab_height()
        button = TopTabButton(
            text=text,
            toggle=True,
            size=(0, tab_height),
            variant="top_tab",
            corner_radii=(
                self._style.tab_radius(self._corner_radius),
                self._style.tab_radius(self._corner_radius),
                0,
                0,
            ),
            flat=self._style.flat,
            style=self._style,
            close_zone=(
                self._scaled_close_size() + TAB_CLOSE_MARGIN if closable else 0
            ),
        )
        button.set_show_indicator(self._show_indicator)
        button.setFixedHeight(tab_height)
        if self._expand_tabs:
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            button.setMinimumWidth(self._style.tab_min_width(TAB_MIN_WIDTH))
        else:
            button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            button.setFixedWidth(button.sizeHint().width())

        tab = TabSpec(text=text, button=button)
        if data is not None:
            tab.data_roles[int(Qt.ItemDataRole.UserRole)] = data
        self._tabs.append(tab)

        index = len(self._tabs) - 1
        button.clicked.connect(lambda _i=index: self._on_tab_clicked(_i))
        button.installEventFilter(self)
        self._layout.addWidget(button)
        self._sync_h_scroll()

        if closable:
            # Embedded in the tab's right edge (adaptive-tab close-slot
            # mechanics): the close button is a child of the tab button; its
            # background follows the tab's state, not its own hover.
            close_button = Button(
                size=(self._scaled_close_size(), self._scaled_close_size()),
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
            tab.button.hide()
            tab.button.setParent(None)
            tab.button.deleteLater()
            close_button = tab.close_button
            if close_button is not None:
                close_button.hide()
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

    def showEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().showEvent(event)
        self._sync_h_scroll()

    def enterEvent(self, event) -> None:  # noqa: N802 - Qt API
        self._hovering = True
        self._sync_h_scroll()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt API
        self._hovering = False
        self._sync_h_scroll()
        super().leaveEvent(event)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt API
        # A tab is a CHILD: hovering it sends the bar a `Leave`, so the strip would drop its hover the moment the pointer
        # is on a tab. The buttons report their own enter/leave instead.
        if watched is not self and event.type() == QEvent.Type.Enter:
            self._hovering = True
            self._sync_h_scroll()
        elif watched is not self and event.type() == QEvent.Type.Leave:
            self._hovering = False
            self._sync_h_scroll()
        return super().eventFilter(watched, event)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
        """Shrink the tabs to fit instead of hiding the last ones.

        A bar narrower than its content used to clip the overflowing tabs with no affordance at all - the host's last tab
        ("Log") simply disappeared behind the pane. Now the redundant width is taken from each tab proportionally down to
        a floor, and the label elides; every tab stays reachable at any width.
        """
        super().resizeEvent(event)
        self._sync_h_scroll()

    def _fit_tabs(self) -> None:
        if not self._tabs or self._expand_tabs:
            return
        margins = self._layout.contentsMargins()
        available = max(0, self.width() - margins.left() - margins.right())
        widths = [button.sizeHint().width() for button in (tab.button for tab in self._tabs)]
        spacing = self._layout.spacing() * max(0, len(widths) - 1)
        if sum(widths) + spacing <= available:
            for tab, width in zip(self._tabs, widths):
                tab.button.setFixedWidth(width)
            return
        floor = max(24, self._style.tab_min_width(TAB_MIN_WIDTH) // 2)
        budget = max(floor * len(widths), available - spacing)
        scale = budget / max(1, sum(widths))
        for tab, width in zip(self._tabs, widths):
            tab.button.setFixedWidth(max(floor, int(width * scale)))

    def sizeHint(self) -> QSize:
        return QSize(self._content_width(), self._scaled_tab_height())

    def minimumSizeHint(self) -> QSize:
        # Tabs clip/overflow when the host is narrower than the content (see
        # the squeeze test) — the bar must not force the host wider than it
        # wants, so the minimum is just the chrome floor, not the content.
        return QSize(self._layout.contentsMargins().left()
                     + self._layout.contentsMargins().right() + self._style.tab_min_width(TAB_MIN_WIDTH),
                     self._scaled_tab_height())

    def _content_width(self) -> int:
        margins = self._layout.contentsMargins()
        width = margins.left() + margins.right()
        if not self._tabs:
            return max(width, self._style.tab_min_width(TAB_MIN_WIDTH))
        widths = [
            max(self._style.tab_min_width(TAB_MIN_WIDTH), tab.button.sizeHint().width())
            for tab in self._tabs
        ]
        width += sum(widths)
        if len(widths) > 1:
            width += self._layout.spacing() * (len(widths) - 1)
        return width

    def required_width(self) -> int:
        """The width this strip needs to show EVERY tab at its natural size.

        A host that can size its column uses this instead of guessing, and a host that cannot gets a scrollbar rather
        than tabs hidden behind the pane.
        """
        return self._content_width()

    def scroll_offset(self) -> int:
        return self._h_offset

    def set_scroll_offset(self, offset: int) -> None:
        maximum = max(0, self.required_width() - self.width())
        self._h_offset = max(0, min(maximum, int(offset)))
        self._place_strip()
        if self._h_scroll.value() != self._h_offset:
            self._h_scroll.blockSignals(True)
            self._h_scroll.setValue(self._h_offset)
            self._h_scroll.blockSignals(False)

    def _on_h_scroll(self, value: int) -> None:
        self._h_offset = int(value)
        self._place_strip()

    def _place_strip(self) -> None:
        tab_height = self._scaled_tab_height()
        self._strip.move(-self._h_offset, 0)

    def wheelEvent(self, event) -> None:  # noqa: N802 - Qt API
        """A wheel over the strip scrolls it while the tabs overflow, and leaves the event alone when they fit."""
        if self.required_width() > self.width():
            delta = event.angleDelta().y() or event.angleDelta().x()
            if delta:
                self.set_scroll_offset(self._h_offset - int(delta / 120) * max(24, self.width() // 4))
                event.accept()
                return
        super().wheelEvent(event)

    def _sync_strip_geometry(self) -> None:
        width = self._content_width()
        tab_height = self._scaled_tab_height()
        self._strip.setFixedSize(width, tab_height)
        # A host that wants a normal-scrollbar reservation states it: the row stays reserved, so showing the bar on hover
        # cannot reflow the strip. The default keeps a stock `QTabWidget`'s geometry.
        extra = scaled_px(self.SCROLL_STRIP_H) if self._style.reserve_scroll_row else 0
        self.setFixedHeight(tab_height + extra)
        self._place_strip()
        self._sync_h_scroll()
        self.updateGeometry()

    #: The overflow bar is a THIN strip of its own under the tabs - never an overlay on top of them.
    SCROLL_STRIP_H = 4

    def _sync_h_scroll(self) -> None:
        """A horizontal bar only while the tabs overflow AND the pointer is on the strip, in its own row under the tabs."""
        policy = self._style.scroll_policy
        if policy == Qt.ScrollBarPolicy.ScrollBarAlwaysOff:
            self._h_scroll.set_animated_visible(False)
            self._h_scroll.hide()
            self._h_offset = 0
            self._place_strip()
            if self.height() != self._scaled_tab_height():
                self.setFixedHeight(self._scaled_tab_height())
            return
        maximum = max(0, self.required_width() - self.width())
        bar_h = scaled_px(self.SCROLL_STRIP_H)
        tab_height = self._scaled_tab_height()
        hovering = bool(self._hovering or self._strip.underMouse() or self.underMouse())
        if policy != Qt.ScrollBarPolicy.ScrollBarAlwaysOn and not hovering:
            # The bar is a HOVER affordance: it appears while the pointer is over the strip and disappears otherwise.
            self._h_scroll.set_animated_visible(False)
            self._h_scroll.hide()
            self._h_offset = 0
            self._place_strip()
            return
        if maximum <= 0:
            # Not "fade it out": a bar that fits must not show a scrollbar at all. `set_animated_visible(False)` leaves the
            # widget created and mapped in some styles, which read as "always visible" on a strip that had nothing to
            # scroll.
            self._h_scroll.set_animated_visible(False)
            self._h_scroll.hide()
            self._h_offset = 0
            self._place_strip()
            if self.height() != tab_height:
                self.setFixedHeight(tab_height)
            return
        if self.height() != tab_height + bar_h:
            # The bar's own row: the widget grows by the thin strip so the tabs are never covered.
            self.setFixedHeight(tab_height + bar_h)
        self._h_scroll.setGeometry(0, tab_height, self.width(), bar_h)
        self._h_scroll.setRange(0, maximum)
        self._h_scroll.setPageStep(max(1, self.width()))
        self._h_scroll.setSingleStep(max(1, self.width() // 8))
        self._h_scroll.blockSignals(True)
        self._h_scroll.setValue(min(self._h_offset, maximum))
        self._h_scroll.blockSignals(False)
        self._h_scroll.show()
        self._h_scroll.set_animated_visible(True)

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

    def _scaled_tab_height(self) -> int:
        """Design ``tab_height`` resolved through the live ``UiScale`` factor."""
        return scaled_px(self._tab_height)

    def _scaled_close_size(self) -> int:
        """Design ``close_size`` resolved through the live ``UiScale`` factor."""
        return scaled_px(self._close_size)

    def _on_scale_changed(self, *_args: object) -> None:
        # Interface-scale resync: tab buttons were fixed at construction in
        # old design px — re-stamp heights, re-fit widths from the (now
        # scale-resolved) size hints, then re-flow the strip like a theme
        # switch does.
        tab_height = self._scaled_tab_height()
        for tab in self._tabs:
            tab.button.setFixedHeight(tab_height)
            if not self._expand_tabs:
                tab.button.setFixedWidth(tab.button.sizeHint().width())
            if tab.close_button is not None:
                try:
                    if isinstance(tab.close_button, QWidget):
                        close = self._scaled_close_size()
                        tab.close_button.setFixedSize(close, close)
                except Exception:
                    pass
        self._sync_strip_geometry()
        self.update()
