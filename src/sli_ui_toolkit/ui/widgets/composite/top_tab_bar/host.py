"""TopTabHost — TopTabBar + bordered page stack (QTabWidget-ish API)."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QSizePolicy, QStackedWidget, QVBoxLayout, QWidget

from sli_ui_toolkit.theme import ThemeManager
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
    """Folder-tab host: ``TopTabBar`` + bordered content stack (QTabWidget-ish)."""

    currentChanged = Signal(int)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        tab_height: int = 32,
        pane_radius: int | tuple[int, int, int, int] = DEFAULT_PANE_RADIUS,
        expand_tabs: bool = False,
    ) -> None:
        super().__init__(parent)
        self._pane_radii = _normalize_pane_radii(pane_radius)
        self._pane_radius = self._pane_radii[0]
        self._pages: list[QWidget] = []
        self._labels: list[str] = []
        self._chrome_inset = 1
        self._content_inset = content_inset_for_radii(self._pane_radii)

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
            corner_radius=DEFAULT_TAB_RADIUS,
        )
        self.tab_bar.setObjectName("TopTabBar")
        root.addWidget(self.tab_bar)

        self._pane = TopTabPane(self)
        pane_layout = QVBoxLayout(self._pane)
        pane_layout.setContentsMargins(
            self._content_inset,
            self._content_inset,
            self._content_inset,
            self._content_inset,
        )
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

        self.tab_bar.currentChanged.connect(self._on_bar_changed)
        try:
            ThemeManager.get_instance().theme_changed.connect(self._refresh_pane)
        except Exception:
            pass

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._pane.update()

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
