from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.ui.widgets.buttons import Button


@dataclass(slots=True)
class WindowControlsConfig:
    minimize_icon: Any = None
    maximize_icon: Any = None
    restore_icon: Any = None
    close_icon: Any = None
    show_minimize: bool = True
    show_maximize: bool = True
    show_close: bool = True


class WindowControlsHandle:
    """Runtime view of the window-control buttons on a title bar."""

    def __init__(
        self,
        *,
        min_btn: Button | None,
        max_btn: Button | None,
        close_btn: Button | None,
        container: QWidget,
    ) -> None:
        self._min_btn = min_btn
        self._max_btn = max_btn
        self._close_btn = close_btn
        self._container = container

    def set_minimize_visible(self, visible: bool) -> None:
        if self._min_btn is not None:
            self._min_btn.setVisible(visible)

    def set_maximize_visible(self, visible: bool) -> None:
        if self._max_btn is not None:
            self._max_btn.setVisible(visible)

    def set_close_visible(self, visible: bool) -> None:
        if self._close_btn is not None:
            self._close_btn.setVisible(visible)

    @property
    def container(self) -> QWidget:
        return self._container

    def size_hint_width(self) -> int:
        return self._container.sizeHint().width()
