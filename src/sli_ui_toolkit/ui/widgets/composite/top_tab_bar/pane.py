"""TopTabPane — frame that owns folder-tab chrome paint."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame

from sli_ui_toolkit.ui.widgets.composite.top_tab_bar import chrome as pane_chrome

if TYPE_CHECKING:
    from sli_ui_toolkit.ui.widgets.composite.top_tab_bar.host import TopTabHost


class TopTabPane(QFrame):
    """Content frame that owns folder-tab chrome (fill + stroke).

    ``paintEvent`` first clears the full rectangle with the dialog surface
    colour, then draws the rounded pane — so corner pixels never show
    neighbouring framebuffer garbage.
    """

    def __init__(self, host: TopTabHost) -> None:
        super().__init__(host)
        self._host = host
        self.setObjectName("TopTabPane")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setAutoFillBackground(False)

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        cover = pane_chrome.selected_tab_cover_rect(
            host=self._host,
            pane=self,
            tab_bar=self._host.tab_bar,
            current_index=self._host.currentIndex(),
            content_inset=self._host._content_inset,
        )
        pane_chrome.paint_pane_chrome(
            self,
            pane_radii=self._host._pane_radii,
            selected_cover=cover,
        )

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.update()
