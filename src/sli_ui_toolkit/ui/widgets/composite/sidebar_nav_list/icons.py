"""Row icon resolution for IconListWidget — pure functions, no widget state.

Normal/selected pixmap pairs are resolved through the icon pipeline; the
selected state either tints the normal pixmap (``invert``) or swaps in an
explicit selected icon (``replace``). Every function takes its inputs
explicitly (row spec, icon size, mode) so the logic is testable without
an ``IconListWidget``; the panel only owns the ``_icon_size`` /
``_selected_icon_mode`` settings and applies the results to row buttons.
"""

from __future__ import annotations

from typing import cast

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap

from sli_ui_toolkit.icons import resolve_icon
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.managers.ui_scale import scaled_px
from sli_ui_toolkit.ui.widgets.helpers.icon_pixmap import normalized_icon_pixmap

from .rows import SelectedIconMode, _RowSpec, _SELECTED_ICON_MODES


def normalize_selected_icon_mode(mode: str) -> SelectedIconMode:
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
    return cast(SelectedIconMode, normalized)


def selected_icon_color() -> QColor:
    """Theme-resolved color for a selected row's icon/foreground."""
    theme = ThemeManager.get_instance()
    color = theme.try_get_color("list_item.icon.selected")
    if color is not None and color.isValid():
        return QColor(color)
    color = theme.try_get_color("HighlightedText")
    if color is None or not color.isValid():
        color = QColor("white")
    return color


def tinted_pixmap(base_pixmap: QPixmap, color: QColor) -> QPixmap:
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


def selected_pixmap_for(
    row: _RowSpec,
    normal_pixmap: QPixmap,
    icon_size: QSize,
    mode: SelectedIconMode,
) -> QPixmap:
    """The pixmap to show when ``row`` is selected, given its normal one."""
    if mode == "replace":
        selected_icon = row.selected_icon
        if selected_icon is None:
            return normal_pixmap
        resolved = resolve_icon(selected_icon)
        if resolved.isNull():
            return normal_pixmap
        size = icon_size if icon_size.isValid() else QSize(24, 24)
        selected_pixmap = normalized_icon_pixmap(resolved, scaled_px(size.height()))
        return selected_pixmap if not selected_pixmap.isNull() else normal_pixmap

    selected_pixmap = tinted_pixmap(normal_pixmap, selected_icon_color())
    return selected_pixmap if not selected_pixmap.isNull() else normal_pixmap


def apply_row_icon(
    row: _RowSpec, icon_size: QSize, mode: SelectedIconMode
) -> None:
    """Resolve ``row``'s normal/selected pixmap pair and apply the icon."""
    if row.custom:
        return
    row.normal_pixmap = None
    row.selected_pixmap = None
    if row.icon is not None:
        base_icon = resolve_icon(row.icon)
        if not base_icon.isNull():
            size = icon_size if icon_size.isValid() else QSize(24, 24)
            normal_pixmap = normalized_icon_pixmap(
                base_icon, scaled_px(size.height())
            )
            if not normal_pixmap.isNull():
                row.normal_pixmap = normal_pixmap
                row.selected_pixmap = selected_pixmap_for(
                    row, normal_pixmap, icon_size, mode
                )
    update_row_icon(row)


def update_row_icon(row: _RowSpec) -> None:
    if row.custom:
        return
    pixmap = row.normal_pixmap
    if row.button.isChecked() and row.selected_pixmap is not None:
        pixmap = row.selected_pixmap
    row.button.setIcon(QIcon(pixmap) if pixmap is not None else None)


def update_row_fg(row: _RowSpec) -> None:
    if row.custom:
        return
    if row.button.isChecked():
        row.button.setForegroundColor(selected_icon_color())
    else:
        row.button.setForegroundColor(None)
    row.button.update()
