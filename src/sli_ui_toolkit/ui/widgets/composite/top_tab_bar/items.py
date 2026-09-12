from __future__ import annotations

from typing import TYPE_CHECKING

from dataclasses import dataclass, field

from PySide6.QtCore import Qt

from sli_ui_toolkit.ui.widgets.composite.top_tab_bar.tab_button import TopTabButton

if TYPE_CHECKING:
    from sli_ui_toolkit.ui.widgets.composite.top_tab_bar.bar import TopTabBar


@dataclass(slots=True)
class TopTabItem:
    text: str
    data: object | None = None


@dataclass
class TabSpec:
    text: str
    button: TopTabButton
    data_roles: dict[int, object] = field(default_factory=dict)


class TabItem:
    """Lightweight proxy over a bar row (text / data), like IconListWidget items."""

    def __init__(self, owner: TopTabBar, index: int) -> None:
        self._owner = owner
        self._index = index

    @property
    def _spec(self) -> TabSpec | None:
        if 0 <= self._index < len(self._owner._tabs):
            return self._owner._tabs[self._index]
        return None

    def text(self) -> str:
        spec = self._spec
        return spec.text if spec is not None else ""

    def setText(self, text: str) -> None:
        spec = self._spec
        if spec is None:
            return
        spec.text = text
        spec.button.setText(text)
        spec.button.updateGeometry()

    def data(self, role: int = Qt.ItemDataRole.UserRole) -> object | None:
        spec = self._spec
        if spec is None:
            return None
        return spec.data_roles.get(int(role))

    def setData(self, role: int, value: object) -> None:
        spec = self._spec
        if spec is None:
            return
        spec.data_roles[int(role)] = value
