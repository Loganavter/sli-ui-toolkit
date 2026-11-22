"""TopTabHost — TopTabBar + bordered page stack (tab-host API)."""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import QSizePolicy, QStackedWidget, QVBoxLayout, QWidget

from .style import TabStyle
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.composite.adaptive_tab_strip import CloseButtonPolicy
from sli_ui_toolkit.ui.widgets.composite.top_tab_bar import chrome as pane_chrome
from sli_ui_toolkit.ui.widgets.composite.top_tab_bar.bar import TopTabBar
from sli_ui_toolkit.ui.widgets.composite.top_tab_bar.constants import (
    DEFAULT_PANE_RADIUS,
    DEFAULT_TAB_RADIUS,
    content_inset_for_radii,
)
from sli_ui_toolkit.ui.widgets.composite.top_tab_bar.pane import TopTabPane


def _normalize_pane_radii(
    pane_radius: int | tuple[int, int, int, int],
) -> tuple[int, int, int, int]:
    if isinstance(pane_radius, tuple):
        values = [int(r) for r in pane_radius[:4]]
        if not values:
            values = [DEFAULT_PANE_RADIUS]
        while len(values) < 4:
            values.append(values[-1])
        return (values[0], values[1], values[2], values[3])
    r = int(pane_radius)
    return (r, r, r, r)


class TopTabHost(QWidget):
    """Folder-tab host: ``TopTabBar`` + bordered content stack."""

    currentChanged = Signal(int)
    #: emitted when a tab's close (X) region is clicked — hosts decide what
    #: to do (typically ``removeTab``); disabled by default (``NONE``).
    tabCloseRequested = Signal(int)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        tab_height: int = 32,
        pane_radius: int | tuple[int, int, int, int] = DEFAULT_PANE_RADIUS,
        expand_tabs: bool = False,
        close_policy: CloseButtonPolicy = CloseButtonPolicy.NONE,
        pane_inset: int | tuple[int, int, int, int] | None = None,
        chrome_inset: int = 1,
        tab_radius: int = DEFAULT_TAB_RADIUS,
        pane_fill_token: str | None = "surface.background",
        tab_style: "TabStyle | None" = None,
        tab_factory=None,
    ) -> None:
        super().__init__(parent)
        # `None` = the host's page paints its own body and the pane must stay transparent (see `paint_pane_chrome`).
        self._pane_fill_token = pane_fill_token
        self._tab_style = tab_style or TabStyle()
        self._bar_gap = max(0, int(self._tab_style.gap))
        self._pane_radii = _normalize_pane_radii(pane_radius)
        self._pane_radius = self._pane_radii[0]
        self._pages: list[QWidget] = []
        self._labels: list[str] = []
        # Stock-geometry answers: a host replacing a QTabWidget needs its pane to start exactly where the stock stack
        # did. PANE_CONTENT_INSET (2) and the 1 px chrome are right for a rounded pane and wrong for a flat one -
        # measured on a migrated page: with the defaults the tab bar pushed the pane 7 px down and 2 px in, and every
        # widget below shifted. `pane_inset=None` keeps the radius-derived inset.
        self._chrome_inset = max(0, int(chrome_inset))
        #: Per-side pane padding. A host replacing a stock `QStackedWidget` that carried `padding:5px 10px` in its
        #: stylesheet needs 10 px horizontally and 5 vertically - a uniform `int` cannot express that, and the gutters
        #: move every page inside the stack when the stylesheet goes (measured: pages shifted 10 px left, 5 up, and
        #: grew 20 px wide).
        if pane_inset is None:
            _inset = content_inset_for_radii(self._pane_radii)
            self._content_margins = (_inset, _inset, _inset, _inset)
        elif isinstance(pane_inset, (tuple, list)):
            _l, _t, _r, _b = (max(0, int(v)) for v in pane_inset)
            self._content_margins = (_l, _t, _r, _b)
        else:
            _v = max(0, int(pane_inset))
            self._content_margins = (_v, _v, _v, _v)
        self._content_inset = self._content_margins[0]

        root = QVBoxLayout(self)
        root.setContentsMargins(
            self._chrome_inset,
            0,
            self._chrome_inset,
            self._chrome_inset,
        )
        root.setSpacing(0)

        self.tab_bar = TopTabBar(
            self,
            tab_height=tab_height,
            expand_tabs=expand_tabs,
            show_indicator=False,
            corner_radius=self._tab_style.tab_radius(tab_radius),
            style=self._tab_style,
            close_policy=close_policy,
            tab_factory=tab_factory,
        )
        self.tab_bar.setObjectName("TopTabBar")
        # A bar that is wider than its host used to run past the pane and clip its last tabs with no affordance: the bar
        # may now shrink below its content hint (it elides its tabs to fit - see `TopTabBar._fit_tabs`).
        self.tab_bar.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        root.addWidget(self.tab_bar)
        if self._bar_gap:
            root.addSpacing(self._bar_gap)
        self.tab_bar.tabCloseRequested.connect(self.tabCloseRequested.emit)

        self._pane = TopTabPane(self)
        pane_layout = QVBoxLayout(self._pane)
        pane_layout.setContentsMargins(*self._content_margins)
        pane_layout.setSpacing(0)

        self.pages_stack = QStackedWidget(self._pane)
        self.pages_stack.setObjectName("TopTabStack")
        self.pages_stack.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        pane_chrome.clear_stack_content_clip(self.pages_stack)
        pane_chrome.apply_stack_fill(self.pages_stack)
        pane_layout.addWidget(self.pages_stack)
        root.addWidget(self._pane, 1)

        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

        # `QStackedLayout` in its default StackOne mode lays out ONLY the current page; the others keep whatever size
        # they had when they were last current. Switch to one of those and it is shown at that stale size: its content
        # clips at the old width and the strip that was never covered keeps the previous page's pixels - the host app
        # measured pages at 434x592 and 480x515 inside a 500x571 host, cut exactly at the stale width, healed only by a
        # window resize (RVE, 2026-11-22; BlinkTable documented the same mechanism and patched it per pane in
        # docs/dev/rendering/investigations/ui-inspector-csd-corner-clip.md:80-97). The guarantee belongs HERE, so no
        # consumer has to repeat the event filter.
        self.pages_stack.installEventFilter(self)
        self.tab_bar.currentChanged.connect(self._on_bar_changed)
        try:
            ThemeManager.get_instance().theme_changed.connect(self._refresh_pane)
        except Exception:
            pass

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._fit_pages()
        self._pane.update()

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt API
        if watched is self.pages_stack and event.type() == QEvent.Type.Resize:
            self._fit_pages()
        return super().eventFilter(watched, event)

    def _fit_pages(self) -> None:
        """Resize EVERY page to the stack and settle each page's own layout in the same call.

        `QStackedLayout` in its default `StackOne` mode lays out only the page it shows; the others keep whatever size
        they had when they were last current (Qt's 640x480 at creation, or the window's old width). Show one of those and
        it paints clipped at that stale rect - and the strip it does not cover keeps the previous page's pixels. The host
        app measured pages at 434x592 and 480x515 inside a 500x571 host, with its controls cut mid-word at the stale
        edge, healed only by a window resize (RVE, 2026-11-22).

        Every page, not just the current one, plus `settle_layout`, is the toolkit's existing idiom: the inspector pane
        does exactly this (`ui/inspector/view.py:108-128`) because a page whose scroll area caches a `sizeHint` would
        otherwise open one frame stale. The settled widget is the PAGE, never the stack we are filtering.
        """
        size = self.pages_stack.size()
        if size.isEmpty():
            return
        for page in self._pages:
            if page.size() != size:
                page.resize(size)
            self._settle(page)

    @staticmethod
    def _settle(page) -> None:
        """Re-run the page's layout synchronously, refreshing its scroll area's hint if it has one."""
        try:
            from sli_ui_toolkit.ui.layout_settle import settle_layout
        except Exception:                     # the helper is optional for a bare host
            return
        scroll_area = getattr(page, "scroll_area", None) or getattr(page, "_scroll", None)
        try:
            settle_layout(page, scroll_area)
        except Exception:
            pass

    def _apply_content_clip(self) -> None:
        # Masks caused neighbour-framebuffer bleed; square content is kept
        # inside the rounded fill via ``_content_inset`` instead.
        pane_chrome.clear_stack_content_clip(self.pages_stack)

    def _selected_tab_cover_in_pane(self, pane: QWidget):
        return pane_chrome.selected_tab_cover_rect(
            host=self,
            pane=pane,
            tab_bar=self.tab_bar,
            current_index=self.currentIndex(),
            content_inset=self._content_inset,
        )

    def addTab(self, widget: QWidget, label: str) -> int:
        widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        widget.setAutoFillBackground(False)
        widget.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self._labels.append(str(label))
        self._pages.append(widget)
        self.pages_stack.addWidget(widget)
        self.tab_bar.add_item(str(label))
        if self.tab_bar.currentIndex() < 0:
            self.setCurrentIndex(0)
        else:
            self._pane.update()
        return self.count() - 1

    def insertTab(self, index: int, widget: QWidget, label: str) -> int:
        index = max(0, min(int(index), self.count()))
        current = self.tab_bar.currentIndex()
        if current >= index:
            current += 1
        widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        widget.setAutoFillBackground(False)
        widget.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self._labels.insert(index, str(label))
        self._pages.insert(index, widget)
        self.pages_stack.insertWidget(index, widget)
        self._rebuild_bar(current if self.count() > 1 else 0)
        self._pane.update()
        return index

    def removeTab(self, index: int) -> None:
        if index < 0 or index >= self.count():
            return
        current = self.tab_bar.currentIndex()
        self._labels.pop(index)
        widget = self._pages.pop(index)
        self.pages_stack.removeWidget(widget)
        if not self._pages:
            self.tab_bar.clear()
            self._pane.update()
            return
        if current < 0:
            target = 0
        elif current == index:
            target = min(index, self.count() - 1)
        elif current > index:
            target = current - 1
        else:
            target = current
        self._rebuild_bar(target)
        self._pane.update()

    def count(self) -> int:
        return len(self._pages)

    def currentIndex(self) -> int:
        return self.tab_bar.currentIndex()

    def setCurrentIndex(self, index: int) -> None:
        self.tab_bar.setCurrentIndex(index)

    def currentWidget(self) -> QWidget | None:
        idx = self.currentIndex()
        if 0 <= idx < len(self._pages):
            return self._pages[idx]
        return None

    def setCurrentWidget(self, widget: QWidget | None) -> None:
        if widget is None:
            return
        idx = self.indexOf(widget)
        if idx >= 0:
            self.setCurrentIndex(idx)

    def indexOf(self, widget: QWidget | None) -> int:
        if widget is None:
            return -1
        try:
            return self._pages.index(widget)
        except ValueError:
            return -1

    def widget(self, index: int) -> QWidget | None:
        if 0 <= index < len(self._pages):
            return self._pages[index]
        return None

    def tabText(self, index: int) -> str:
        return self.tab_bar.tabText(index)

    def setTabText(self, index: int, text: str) -> None:
        if 0 <= index < len(self._labels):
            self._labels[index] = str(text)
        self.tab_bar.setTabText(index, text)

    def tabBar(self) -> TopTabBar:
        return self.tab_bar

    def _on_bar_changed(self, index: int) -> None:
        if 0 <= index < self.pages_stack.count():
            self.pages_stack.setCurrentIndex(index)
            # Before it paints: this page may never have been current since the stack last changed size. Settled
            # synchronously (a tab-change slot is not a resizeEvent), so the first frame after the switch agrees.
            self._fit_pages()
        self.pages_stack.update()
        self._pane.update()
        self.currentChanged.emit(index)

    def _rebuild_bar(self, current: int) -> None:
        self.tab_bar.clear()
        for text in self._labels:
            self.tab_bar.add_item(text)
        if self.count() <= 0:
            return
        target = max(0, min(int(current), self.count() - 1))
        self.tab_bar.setCurrentIndex(target)

    def _refresh_pane(self, *_args) -> None:
        pane_chrome.apply_stack_fill(self.pages_stack)
        self._pane.update()
