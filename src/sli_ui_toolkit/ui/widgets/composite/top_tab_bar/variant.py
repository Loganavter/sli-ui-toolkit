"""Button variant ``top_tab`` — folder/content-section tab chrome."""

from __future__ import annotations

from PySide6.QtGui import QColor

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.buttons.state import ButtonState
from sli_ui_toolkit.ui.widgets.buttons.variants import VariantSpec, register_variant

_TRANSPARENT = QColor(0, 0, 0, 0)
_REGISTERED = False


def _top_tab_resolve(states, tm: ThemeManager) -> QColor:
    if ButtonState.DISABLED in states:
        return _TRANSPARENT
    if ButtonState.CHECKED in states:
        color = tm.try_get_color("dialog.input.background")
        if color is not None:
            return QColor(color)
        return QColor(tm.try_get_color("Window") or _TRANSPARENT)
    if ButtonState.PRESSED in states or ButtonState.HOVERED in states:
        return QColor(
            tm.try_get_color("button.toggle.background.hover")
            or tm.try_get_color("list_item.background.hover")
            or _TRANSPARENT
        )
    return _TRANSPARENT


def register_top_tab_variant() -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    register_variant(VariantSpec("top_tab", "button.toggle", resolve_bg=_top_tab_resolve))
    _REGISTERED = True
