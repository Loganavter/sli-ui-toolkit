"""Opt-in right-click context menu for toolkit widgets.

Before this existed the same plumbing lived inside every widget that wanted a
menu: a ``contextMenuEvent`` override that built ``(entries, on_triggered)``
and opened a popup ``ContextMenu`` at ``globalPos()``. ``Label`` and the plain
``Text`` path share ``label_context_menu``; every other widget (Button,
ComboBox, LineEdit, list/table surfaces, ``ConsoleView``) had no menu at all,
so a host that wanted one had to wire it per widget class.

A widget opts in by mixing this in and implementing
:meth:`ContextMenuMixin.build_context_menu`; the mixin owns the event, the
placement, the fail-open guard and the "a second right-click dismisses the
first menu" rule, so no widget copies that plumbing again.

Bare mixin — fold it in BEFORE the QWidget base
(``class MyWidget(ContextMenuMixin, QWidget)``), never used standalone.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable, Literal, cast

from PySide6.QtGui import QContextMenuEvent
from PySide6.QtWidgets import QWidget

if TYPE_CHECKING:
    from sli_ui_toolkit.ui.widgets.composite.context_menu.models import (
        ContextMenuEntry,
    )

logger = logging.getLogger(__name__)

TriggeredCallback = Callable[[str, object], None]


class ContextMenuMixin:
    """Shared right-click menu plumbing for any toolkit ``QWidget``.

    Subclasses implement :meth:`build_context_menu` and inherit a themed
    popup menu at the cursor; they keep every other event and method they had.
    """

    def build_context_menu(
        self,
    ) -> tuple[tuple[ContextMenuEntry, ...], TriggeredCallback]:
        """Entries plus their trigger handler for this widget's right-click menu.

        Return an empty entry tuple when the widget has nothing to offer for
        this click: the mixin then falls through to Qt's default behaviour
        instead of showing an empty popup.
        """
        raise NotImplementedError

    def context_menu_surface(self) -> Literal["popup", "in_window"]:
        """Menu surface: ``popup`` (default) is the cursor-positioned right-click menu."""
        return "popup"

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:  # noqa: N802
        try:
            entries, on_triggered = self.build_context_menu()
        except Exception:  # noqa: BLE001 - fail-open by contract
            logger.debug(
                "%s: context menu builder failed", type(self).__name__, exc_info=True
            )
            QWidget.contextMenuEvent(cast(QWidget, self), event)
            return
        if not entries:
            QWidget.contextMenuEvent(cast(QWidget, self), event)
            return
        try:
            # Imported here: the menu package pulls the flyout stack, which
            # widgets should not load just because they mix this in.
            from sli_ui_toolkit.ui.widgets.composite.context_menu.menu import (
                ContextMenu,
            )

            self._hide_owned_context_menu()
            menu = ContextMenu(
                cast(QWidget, self),
                entries=entries,
                on_triggered=on_triggered,
                surface=self.context_menu_surface(),
            )
            self.__dict__["_owned_context_menu"] = menu
            menu.popup_at(event.globalPos())
        except Exception:  # noqa: BLE001 - fail-open by contract
            logger.debug(
                "%s: context menu failed to open", type(self).__name__, exc_info=True
            )
        event.accept()

    def _hide_owned_context_menu(self) -> None:
        """Dismiss the menu this mixin opened last (popup menus delete on hide)."""
        menu = self.__dict__.pop("_owned_context_menu", None)
        if menu is None:
            return
        try:
            menu.hide()
        except RuntimeError:
            # Already destroyed with its parent; nothing to dismiss.
            pass


__all__ = ["ContextMenuMixin", "TriggeredCallback"]
