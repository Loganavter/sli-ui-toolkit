"""Painted context menu for the toolkit :class:`Label`.

Selectable labels show the toolkit :class:`ContextMenu` (Copy / Select all)
so the popup obeys the painter pipeline and the active theme.

Hosts can substitute their own entry builder via
:func:`set_label_menu_builder` (e.g. to add "Copy all", translations, or
application actions); :func:`open_label_context_menu` always resolves the
current builder at call time.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable, TypeAlias

from PySide6.QtCore import QPoint
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QLabel

if TYPE_CHECKING:
    from sli_ui_toolkit.ui.widgets.composite.context_menu.models import (
        ContextMenuEntry,
    )

logger = logging.getLogger(__name__)

TriggeredCallback: TypeAlias = Callable[[str, object], None]
LabelMenuBuilder: TypeAlias = Callable[
    [QLabel], "tuple[tuple[ContextMenuEntry, ...], TriggeredCallback]"
]

COPY_ACTION_ID = "label.copy"
SELECT_ALL_ACTION_ID = "label.select_all"


def build_label_menu(
    label: QLabel,
) -> tuple[tuple[ContextMenuEntry, ...], TriggeredCallback]:
    """Build the default Copy / Select-all entries for ``label``.

    Returns the entry tuple plus the matching ``on_triggered`` callback.
    Plain English defaults only -- the toolkit ships no app translations.
    """
    # Imported here, not at module scope: the context-menu package pulls in
    # base_flyout -> builder -> text_labels, which imports this module.
    from sli_ui_toolkit.ui.widgets.composite.context_menu.models import (
        ContextMenuAction,
    )

    def on_triggered(action_id: str, _data: object) -> None:
        if action_id == COPY_ACTION_ID:
            selected = label.selectedText()
            if selected:
                QGuiApplication.clipboard().setText(selected)
                # Copy ends the selection gesture (one rule for every
                # selectable text surface — see Text.copy_selection).
                label.setSelection(0, 0)
        elif action_id == SELECT_ALL_ACTION_ID:
            label.setSelection(0, len(label.text()))

    entries: tuple[ContextMenuEntry, ...] = (
        ContextMenuAction(
            COPY_ACTION_ID,
            "Copy",
            enabled=label.hasSelectedText(),
        ),
        ContextMenuAction(
            SELECT_ALL_ACTION_ID,
            "Select all",
            enabled=bool(label.text()),
        ),
    )
    return entries, on_triggered


_DEFAULT_BUILDER: LabelMenuBuilder = build_label_menu
_builder: LabelMenuBuilder = _DEFAULT_BUILDER


def set_label_menu_builder(builder: LabelMenuBuilder | None) -> None:
    """Install a host entry builder; ``None`` restores the built-in one."""
    global _builder
    _builder = builder if builder is not None else _DEFAULT_BUILDER


def get_label_menu_builder() -> LabelMenuBuilder:
    """Return the currently active label-menu builder."""
    return _builder


def open_label_context_menu(label: QLabel, global_pos: QPoint) -> None:
    """Pop the toolkit context menu for ``label`` at ``global_pos``.

    Fail-open: any failure to build or show the menu is logged and
    swallowed so a stray right-click can never crash the host.
    """
    try:
        # Imported here to avoid the text_labels <-> base_flyout cycle.
        from sli_ui_toolkit.ui.widgets.composite.context_menu.menu import (
            ContextMenu,
        )

        entries, on_triggered = get_label_menu_builder()(label)
        menu = ContextMenu(
            label,
            entries=entries,
            on_triggered=on_triggered,
            surface="popup",
        )
        menu.popup_at(global_pos)
    except Exception:  # noqa: BLE001 - fail-open by contract
        logger.debug("label context menu failed to open", exc_info=True)
