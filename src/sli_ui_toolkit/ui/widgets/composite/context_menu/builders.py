"""Builder helpers and convenience openers for ContextMenu."""

from __future__ import annotations

from typing import Callable, Iterable, Sequence

from PySide6.QtCore import QPoint
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.ui.widgets.composite.context_menu.menu import ContextMenu
from sli_ui_toolkit.ui.widgets.composite.context_menu.models import (
    ContextMenuAction,
    ContextMenuEntry,
    ContextMenuSection,
    ContextMenuSeparator,
)


class ContextMenuBuilder:
    def __init__(self):
        self._entries: list[ContextMenuEntry] = []

    def action(
        self,
        action_id: str,
        text: str,
        *,
        icon: object | None = None,
        enabled: bool = True,
        visible: bool = True,
        checked: bool = False,
        checkable: bool = False,
        danger: bool = False,
        shortcut: str | QKeySequence | None = None,
        tooltip: str = "",
        data: object = None,
        children: Iterable[ContextMenuEntry] | None = None,
    ) -> ContextMenuBuilder:
        self._entries.append(
            ContextMenuAction(
                action_id=action_id,
                text=text,
                icon=icon,
                enabled=enabled,
                visible=visible,
                checked=checked,
                checkable=checkable,
                danger=danger,
                shortcut=shortcut,
                tooltip=tooltip,
                data=data,
                children=tuple(children or ()),
            )
        )
        return self

    def separator(self, *, visible: bool = True) -> ContextMenuBuilder:
        self._entries.append(ContextMenuSeparator(visible=visible))
        return self

    def section(
        self,
        entries: Iterable[ContextMenuEntry],
        *,
        title: str = "",
    ) -> ContextMenuBuilder:
        self._entries.append(ContextMenuSection(entries=tuple(entries), title=title))
        return self

    def entries(self) -> tuple[ContextMenuEntry, ...]:
        return tuple(self._entries)

    def build(
        self,
        parent: QWidget | None = None,
        *,
        on_triggered: Callable[[str, object], None] | None = None,
    ) -> ContextMenu:
        return ContextMenu(parent, entries=self._entries, on_triggered=on_triggered)


def entries_from_labeled_data(
    items: Sequence[tuple[str, object]],
    *,
    current: object | None = None,
    checkable: bool = True,
    id_prefix: str = "item",
) -> tuple[ContextMenuAction, ...]:
    """Build checkable picker entries from ``[(label, data), ...]`` tuples."""
    entries: list[ContextMenuAction] = []
    for index, (label, data) in enumerate(items):
        entries.append(
            ContextMenuAction(
                f"{id_prefix}.{index}",
                str(label),
                data=data,
                checkable=checkable,
                checked=current is not None and data == current,
            )
        )
    return tuple(entries)


def entries_from_callbacks(
    items: Sequence[tuple[str, object]],
    *,
    id_prefix: str = "action",
) -> tuple[ContextMenuAction, ...]:
    """Build command entries from ``[(label, callback_or_data), ...]`` tuples."""
    entries: list[ContextMenuAction] = []
    for index, (label, payload) in enumerate(items):
        entries.append(
            ContextMenuAction(
                f"{id_prefix}.{index}",
                str(label),
                data=payload,
            )
        )
    return tuple(entries)


def show_context_menu(
    parent: QWidget,
    global_pos: QPoint,
    entries: Iterable[ContextMenuEntry],
    *,
    on_triggered: Callable[[str, object], None] | None = None,
) -> ContextMenu:
    menu = ContextMenu(parent, entries=entries, on_triggered=on_triggered)
    menu.popup_at(global_pos)
    return menu


def popup_context_menu_for_anchor(
    parent: QWidget,
    anchor: QWidget,
    entries: Iterable[ContextMenuEntry],
    *,
    on_triggered: Callable[[str, object], None] | None = None,
    toggle: bool = True,
    anchor_point: str = "bottom-left",
    flyout_point: str = "top-left",
    offset: int = 2,
    animation_distance: int | None = None,
    animation_duration_ms: int | None = None,
) -> ContextMenu:
    """Open a :class:`ContextMenu` aligned to any anchor widget.

    Typical wiring: ``button.clicked.connect(lambda: popup_context_menu_for_anchor(...))``.
    The anchor is only a geometry reference — not part of the menu widget tree.
    """
    existing = getattr(anchor, "_anchor_context_menu", None)
    if getattr(anchor, "_suppress_next_context_menu", False):
        anchor._suppress_next_context_menu = False  # type: ignore[attr-defined]
        return (
            existing
            if existing is not None
            else ContextMenu(parent, entries=tuple(entries), on_triggered=on_triggered)
        )
    if toggle and existing is not None and existing.isVisible():
        existing.hide()
        return existing

    if existing is not None:
        try:
            from shiboken6 import isValid

            alive = bool(isValid(existing))
        except Exception:
            try:
                existing.objectName()
                alive = True
            except RuntimeError:
                alive = False
        if alive:
            try:
                existing.hide()
                existing.setParent(None)
                existing.deleteLater()
            except RuntimeError:
                pass
        anchor._anchor_context_menu = None  # type: ignore[attr-defined]

    menu = ContextMenu(parent, entries=tuple(entries), on_triggered=on_triggered)
    anchor._anchor_context_menu = menu  # type: ignore[attr-defined]
    menu.show_aligned(
        anchor,
        anchor_point=anchor_point,
        flyout_point=flyout_point,
        offset=offset,
        animation="slide",
        animation_axis="vertical",
        animation_distance=animation_distance,
        animation_duration_ms=animation_duration_ms,
    )
    return menu
