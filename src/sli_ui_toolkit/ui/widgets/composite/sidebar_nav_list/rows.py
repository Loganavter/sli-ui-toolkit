"""Row specs, the nav-row button factory, and the selected-icon mode.

Each sidebar row is a toolkit ``Button`` (toggle, no-indicator) so ripple
and the clickable visual come from the button system for free; hosts can
swap the default factory for a custom ``button_factory``. The
"sidebar_nav" button variant (list_item-based background resolution) is
registered here.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Literal, cast

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QPixmap

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.managers.ui_scale import scaled_px
from sli_ui_toolkit.ui.widgets.buttons import Button
from sli_ui_toolkit.ui.widgets.buttons.state import ButtonState
from sli_ui_toolkit.ui.widgets.buttons.variants import VariantSpec, register_variant


_TRANSPARENT = QColor(0, 0, 0, 0)


def _sidebar_nav_resolve(states, tm: ThemeManager) -> QColor:
    if ButtonState.DISABLED in states:
        return QColor(tm.try_get_color("list_item.background.normal") or _TRANSPARENT)
    if ButtonState.CHECKED in states:
        selected_bg = tm.try_get_color("list_item.background.selected")
        if selected_bg is not None:
            return QColor(selected_bg)
        accent = tm.try_get_color("accent")
        if accent is not None:
            return QColor(accent)
        return QColor(tm.try_get_color("list_item.background.hover") or _TRANSPARENT)
    if ButtonState.PRESSED in states or ButtonState.HOVERED in states:
        return QColor(tm.try_get_color("list_item.background.hover") or _TRANSPARENT)
    return QColor(tm.try_get_color("list_item.background.normal") or _TRANSPARENT)


register_variant(
    VariantSpec("sidebar_nav", "list_item", resolve_bg=_sidebar_nav_resolve)
)


_LEFT_PADDING = 12
_ICON_TEXT_GAP = 10
SelectedIconMode = Literal["invert", "replace"]
_SELECTED_ICON_MODES = {"invert", "replace"}


def _split_icon_pair(icon: object | None) -> tuple[object | None, object | None]:
    if isinstance(icon, (tuple, list)) and len(icon) >= 2:
        return icon[0], icon[1]
    return icon, None


_NAV_CONTENT_ALIGN = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter


def _make_nav_row_button(
    text: str,
    icon: object | None,
    row_height: int,
    icon_size_px: int,
) -> Button:
    """Кнопка-строка сайдбара, целиком через публичный Button API.

    ``toggle=False`` — selected-состоянием полностью управляет IconListWidget
    (через ``setRegionChecked``), чтобы:
      * клик мгновенно фиксировал выбор без deselect-restore-flicker;
      * ripple оставался в overlay-режиме (немного темнее ховера), а не в
        авто-градиенте между unchecked-/checked-bg (тот включается только
        для ``toggle=True``).
    Focus-обводки нет — у sidebar-навигации нет своей tab-логики.

    ``content_padding`` / ``gap`` — дизайн-px: Button их НЕ масштабирует
    (в отличие от icon_size/corner_radius/sizeHint), поэтому они
    прогоняются через ``scaled_px()`` здесь, на границе композита.
    """
    button = Button(
        icon=icon,
        text=text,
        toggle=False,
        size=(0, row_height),
        variant="sidebar_nav",
        corner_radius=6,
        icon_size=icon_size_px,
        gap=scaled_px(_ICON_TEXT_GAP),
        content_align=_NAV_CONTENT_ALIGN,
        content_padding=(scaled_px(_LEFT_PADDING), 0.0, scaled_px(_LEFT_PADDING), 0.0),
    )
    button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    return button


@dataclass(slots=True)
class IconListItem:
    text: str
    icon: object | None = None
    data: object | None = None
    row_height: int = 44
    selected_icon: object | None = None
    # Extra pre-normalized search texts (e.g. translations in every UI
    # language). ``set_search_text`` matches against these + the display text;
    # precomputing keeps per-keystroke filtering allocation-free.
    search_texts: tuple[str, ...] = ()


@dataclass
class _RowSpec:
    text: str
    icon: object | None
    selected_icon: object | None
    row_height: int
    button: Button
    custom: bool = False
    data_roles: dict[int, object] = field(default_factory=dict)
    normal_pixmap: QPixmap | None = None
    selected_pixmap: QPixmap | None = None
    # Pre-normalized search texts (display text + ``search_texts``) — computed
    # once at append so per-keystroke filtering never re-normalizes.
    normalized_texts: tuple[str, ...] = ()


class _ListItem:
    """Лёгкая прокси-обёртка над строкой-Button, повторяет нужный кусок
    QListWidgetItem-API (text/setIcon/data/setData/setSizeHint)."""

    def __init__(self, owner: Any, row_index: int) -> None:
        self._owner = owner
        self._row_index = row_index

    @property
    def _spec(self) -> _RowSpec | None:
        if self._row_index < 0:
            # Visible-index -1 is the no-results placeholder row.
            return self._owner._no_results_row
        if 0 <= self._row_index < len(self._owner._rows):
            return self._owner._rows[self._row_index]
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

    def setIcon(self, icon: object) -> None:
        spec = self._spec
        if spec is None:
            return
        normal_icon, selected_icon = _split_icon_pair(icon)
        spec.icon = normal_icon
        if selected_icon is not None:
            spec.selected_icon = selected_icon
        self._owner._refresh_row_icon(spec)

    def setSelectedIcon(self, icon: object | None) -> None:
        spec = self._spec
        if spec is None:
            return
        spec.selected_icon = icon
        self._owner._refresh_row_icon(spec)

    def setSizeHint(self, size: QSize) -> None:
        spec = self._spec
        if spec is None:
            return
        h = size.height() if isinstance(size, QSize) else int(size)
        if h > 0:
            spec.row_height = h
            spec.button.setFixedHeight(h)

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
