"""IconListWidget — sidebar/nav-список на стеке toolkit Button-ов.

Внутри: QScrollArea с вертикальным layout-ом, каждая строка — Button (toggle,
no-indicator). Это даёт «бесплатный» ripple-эффект (overlay + автоматический
градиент при смене checked-состояния) и единый источник истины для clickable-
визуала через Button.

Совместимый публичный API (минимально достаточный набор для существующих
потребителей, см. toolkit demo, markdown_help_dialog, Improve-ImgSLI settings):

    set_items(iterable), add_item(text, icon=None, data=None, selected_icon=None),
    clear(), count(), currentRow(), setCurrentRow(int),
    item(idx) -> _ListItem (proxy с text/icon/data/sizeHint),
    row_button(idx) -> Button | None,
    setIconSize(QSize), iconSize(), setSelectedIconMode(str),
    selectedIconMode(), enable_minimal_scrollbar(),
    refresh_icons(),

    signals: currentRowChanged(int), currentItemChanged(item, prev)

Прокси `_ListItem` не наследник QListWidgetItem — это лёгкая ссылка на
конкретную строку-Button плюс dict для произвольных Qt-ролей (UserRole и др.).

Кастомизация строк (``button_factory``)
----------------------------------------
По умолчанию каждая строка — это ``Button``, собранный внутренним
``_make_nav_row_button`` (icon+text, variant="sidebar_nav", left-aligned).
Приложению, которому нужен другой внешний вид строки (бейджи, свой variant,
``regions=``, multi-row текст и т.п.), не нужно наследоваться от
``IconListWidget`` или лезть в его внутренности — достаточно передать
``button_factory=Callable[[IconListItem], Button]`` в конструктор. Строки,
собранные через кастомную фабрику, IconListWidget трогает минимально: он
по-прежнему управляет layout'ом (растягивает кнопку по ширине, лочит
``FocusPolicy.NoFocus``), кликом (подписка на ``clicked`` → выбор строки) и
CHECKED-состоянием (``setRegionChecked("_main", ...)`` при смене
``currentRow``) — но не трогает иконку/foreground-цвет строки: это styling,
специфичный для дефолтной фабрики, приложение с кастомной фабрикой отвечает
за собственную визуальную реакцию на checked само (через variant/`Button`
API, как обычно).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from sli_ui_toolkit.icons import resolve_icon
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.atomic.minimalist_scrollbar import MinimalistScrollBar
from sli_ui_toolkit.ui.widgets.buttons import Button
from sli_ui_toolkit.ui.widgets.buttons.state import ButtonState
from sli_ui_toolkit.ui.widgets.buttons.variants import VariantSpec, register_variant
from sli_ui_toolkit.ui.widgets.helpers.icon_pixmap import normalized_icon_pixmap


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
_SELECTED_ICON_MODES = {"invert", "replace"}


def _split_icon_pair(icon: object | None) -> tuple[object | None, object | None]:
    if isinstance(icon, (tuple, list)) and len(icon) >= 2:
        return icon[0], icon[1]
    return icon, None


_NAV_CONTENT_ALIGN = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
_NAV_CONTENT_PADDING = (_LEFT_PADDING, 0.0, _LEFT_PADDING, 0.0)


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
    """
    button = Button(
        icon=icon,
        text=text,
        toggle=False,
        size=(0, row_height),
        variant="sidebar_nav",
        corner_radius=6,
        icon_size=icon_size_px,
        gap=_ICON_TEXT_GAP,
        content_align=_NAV_CONTENT_ALIGN,
        content_padding=_NAV_CONTENT_PADDING,
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


class _ListItem:
    """Лёгкая прокси-обёртка над строкой-Button, повторяет нужный кусок
    QListWidgetItem-API (text/setIcon/data/setData/setSizeHint)."""

    def __init__(self, owner: "IconListWidget", row_index: int) -> None:
        self._owner = owner
        self._row_index = row_index

    @property
    def _spec(self) -> _RowSpec | None:
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
        self._owner._apply_icon(spec)

    def setSelectedIcon(self, icon: object | None) -> None:
        spec = self._spec
        if spec is None:
            return
        spec.selected_icon = icon
        self._owner._apply_icon(spec)

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


class IconListWidget(QWidget):
    currentRowChanged = Signal(int)
    currentItemChanged = Signal(object, object)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        icon_size: QSize | None = None,
        row_height: int = 44,
        selected_icon_mode: str = "invert",
        button_factory: Callable[[IconListItem], Button] | None = None,
    ) -> None:
        super().__init__(parent)
        self._row_height = int(row_height)
        self._icon_size: QSize = icon_size if isinstance(icon_size, QSize) else QSize(24, 24)
        self._selected_icon_mode = self._normalize_selected_icon_mode(selected_icon_mode)
        self._button_factory = button_factory
        self._rows: list[_RowSpec] = []
        self._current_row: int = -1

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self._host = QWidget()
        self._host_layout = QVBoxLayout(self._host)
        self._host_layout.setContentsMargins(8, 4, 8, 4)
        self._host_layout.setSpacing(8)
        self._host_layout.addStretch(1)
        self._scroll.setWidget(self._host)
        layout.addWidget(self._scroll)

        try:
            ThemeManager.get_instance().theme_changed.connect(self.refresh_icons)
        except Exception:
            pass

    # -------- public: items --------

    def set_items(
        self,
        items: Iterable[IconListItem | tuple],
    ) -> None:
        self.clear()
        for item in items:
            if isinstance(item, IconListItem):
                spec = item
            elif isinstance(item, tuple):
                spec = self._item_from_tuple(item)
            else:
                spec = IconListItem(text=str(item))
            self._append_row(spec)

    def add_item(
        self,
        text: str,
        icon: object | None = None,
        data: object | None = None,
        row_height: int | None = None,
        selected_icon: object | None = None,
    ) -> _ListItem:
        spec = IconListItem(
            text=text,
            icon=icon,
            data=data,
            row_height=row_height or self._row_height,
            selected_icon=selected_icon,
        )
        self._append_row(spec)
        return _ListItem(self, len(self._rows) - 1)

    def clear(self) -> None:
        for row in self._rows:
            row.button.setParent(None)
            row.button.deleteLater()
        self._rows.clear()
        prev_current = self._current_row
        self._current_row = -1
        if prev_current != -1:
            self.currentRowChanged.emit(-1)
            self.currentItemChanged.emit(None, None)

    def count(self) -> int:
        return len(self._rows)

    def item(self, idx: int) -> _ListItem | None:
        if 0 <= idx < len(self._rows):
            return _ListItem(self, idx)
        return None

    def row_button(self, idx: int) -> QWidget | None:
        """Nav-row Button for ``idx``, or ``None`` if out of range.

        Host Find Action reveal uses this instead of poking ``_rows`` /
        ``_ListItem._spec``.
        """
        if 0 <= idx < len(self._rows):
            return self._rows[idx].button
        return None

    # -------- public: selection --------

    def currentRow(self) -> int:
        return self._current_row

    def setCurrentRow(self, idx: int) -> None:
        if idx < 0 or idx >= len(self._rows):
            idx = -1
        if idx == self._current_row:
            return
        prev = self._current_row
        self._current_row = idx
        for i, row in enumerate(self._rows):
            row.button.setRegionChecked("_main", i == idx)
            self._update_row_icon(row)
            self._update_row_fg(row)
        prev_item = _ListItem(self, prev) if 0 <= prev < len(self._rows) else None
        curr_item = _ListItem(self, idx) if 0 <= idx < len(self._rows) else None
        self.currentRowChanged.emit(idx)
        self.currentItemChanged.emit(curr_item, prev_item)

    # -------- public: icons --------

    def iconSize(self) -> QSize:
        return QSize(self._icon_size)

    def setIconSize(self, size: QSize) -> None:
        if not isinstance(size, QSize) or not size.isValid():
            return
        self._icon_size = QSize(size)
        for row in self._rows:
            if row.custom:
                continue
            row.button.setIconSize(self._icon_size)
            self._apply_icon(row)

    def refresh_icons(self) -> None:
        for row in self._rows:
            if row.custom:
                continue
            self._apply_icon(row)
            self._update_row_fg(row)

    def selectedIconMode(self) -> str:
        return self._selected_icon_mode

    def setSelectedIconMode(self, mode: str) -> None:
        normalized = self._normalize_selected_icon_mode(mode)
        if normalized == self._selected_icon_mode:
            return
        self._selected_icon_mode = normalized
        self.refresh_icons()

    set_selected_icon_mode = setSelectedIconMode

    # -------- public: scroll appearance --------

    def enable_minimal_scrollbar(self) -> None:
        self._scroll.setVerticalScrollBar(MinimalistScrollBar())

    # -------- internals --------

    def _append_row(self, spec: IconListItem) -> None:
        icon, selected_icon_from_pair = _split_icon_pair(spec.icon)
        selected_icon = spec.selected_icon
        if selected_icon is None:
            selected_icon = selected_icon_from_pair

        custom = self._button_factory is not None
        if custom:
            button = self._button_factory(spec)
        else:
            button = _make_nav_row_button(
                text=spec.text,
                icon=None,
                row_height=spec.row_height or self._row_height,
                icon_size_px=self._icon_size.height() if isinstance(self._icon_size, QSize) else 24,
            )
        button.setMinimumWidth(0)
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        row = _RowSpec(
            text=spec.text,
            icon=icon,
            selected_icon=selected_icon,
            row_height=spec.row_height or self._row_height,
            button=button,
            custom=custom,
        )
        if spec.data is not None:
            row.data_roles[int(Qt.ItemDataRole.UserRole)] = spec.data
        self._rows.append(row)

        self._apply_icon(row)

        index = len(self._rows) - 1
        button.clicked.connect(lambda _i=index: self._on_row_clicked(_i))

        insert_at = self._host_layout.count() - 1
        if insert_at < 0:
            insert_at = 0
        self._host_layout.insertWidget(insert_at, button)

    def _on_row_clicked(self, idx: int) -> None:
        if idx == self._current_row:
            return
        self.setCurrentRow(idx)

    def _apply_icon(self, row: _RowSpec) -> None:
        if row.custom:
            return
        row.normal_pixmap = None
        row.selected_pixmap = None
        if row.icon is not None:
            base_icon = resolve_icon(row.icon)
            if not base_icon.isNull():
                size = self._icon_size if self._icon_size.isValid() else QSize(24, 24)
                normal_pixmap = normalized_icon_pixmap(base_icon, size.height())
                if not normal_pixmap.isNull():
                    row.normal_pixmap = normal_pixmap
                    row.selected_pixmap = self._selected_pixmap_for_row(row, normal_pixmap)
        self._update_row_icon(row)

    def _update_row_icon(self, row: _RowSpec) -> None:
        if row.custom:
            return
        pixmap = row.normal_pixmap
        if row.button.isChecked() and row.selected_pixmap is not None:
            pixmap = row.selected_pixmap
        row.button.setIcon(QIcon(pixmap) if pixmap is not None else None)

    def _update_row_fg(self, row: _RowSpec) -> None:
        if row.custom:
            return
        if row.button.isChecked():
            row.button.setForegroundColor(self._selected_icon_color())
        else:
            row.button.setForegroundColor(None)
        row.button.update()

    def _selected_icon_color(self) -> QColor:
        theme = ThemeManager.get_instance()
        color = theme.try_get_color("list_item.icon.selected")
        if color is not None and color.isValid():
            return QColor(color)
        color = theme.try_get_color("HighlightedText")
        if color is None or not color.isValid():
            color = QColor("white")
        return color

    def _selected_pixmap_for_row(
        self,
        row: _RowSpec,
        normal_pixmap: QPixmap,
    ) -> QPixmap:
        if self._selected_icon_mode == "replace":
            selected_icon = row.selected_icon
            if selected_icon is None:
                return normal_pixmap
            resolved = resolve_icon(selected_icon)
            if resolved.isNull():
                return normal_pixmap
            size = self._icon_size if self._icon_size.isValid() else QSize(24, 24)
            selected_pixmap = normalized_icon_pixmap(resolved, size.height())
            return selected_pixmap if not selected_pixmap.isNull() else normal_pixmap

        selected_pixmap = self._tinted_pixmap(normal_pixmap, self._selected_icon_color())
        return selected_pixmap if not selected_pixmap.isNull() else normal_pixmap

    def _normalize_selected_icon_mode(self, mode: str) -> str:
        normalized = str(mode or "").strip().lower().replace("-", "_")
        aliases = {
            "inversion": "invert",
            "inverse": "invert",
            "replace_icon": "replace",
            "replacement": "replace",
        }
        normalized = aliases.get(normalized, normalized)
        if normalized not in _SELECTED_ICON_MODES:
            raise ValueError(
                "selected_icon_mode must be 'invert' or 'replace', "
                f"got {mode!r}"
            )
        return normalized

    def _item_from_tuple(self, item: tuple) -> IconListItem:
        if len(item) <= 4:
            return IconListItem(*item)
        text, icon, data, row_height, selected_icon = item[:5]
        return IconListItem(
            text=text,
            icon=icon,
            data=data,
            row_height=row_height,
            selected_icon=selected_icon,
        )

    def _tinted_pixmap(self, base_pixmap: QPixmap, color: QColor) -> QPixmap:
        if base_pixmap.isNull():
            return QPixmap()
        result = QPixmap(base_pixmap.size())
        result.setDevicePixelRatio(base_pixmap.devicePixelRatio())
        result.fill(Qt.GlobalColor.transparent)
        painter = QPainter(result)
        painter.drawPixmap(0, 0, base_pixmap)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(result.rect(), color)
        painter.end()
        return result
