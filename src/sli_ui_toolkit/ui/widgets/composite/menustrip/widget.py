"""A title-bar menu strip over the shared ``ContextMenu`` row model.

Hosts that want File/Help-style title-bar menus had to build the trigger row
themselves and then fill a dropdown with fake rows to get a label, a
right-aligned shortcut and disabled/danger states. This widget is that row:
each trigger is a toolkit ``Button`` and each dropdown is a toolkit
``ContextMenu`` filled with the existing ``ContextMenuEntry`` models, so there
is no second menu model and no host strings.

Deliberate non-goals:

- The strip never registers itself with ``NavigationManager`` — a global
  registry entry is the host's decision (``navigation_section()`` hands one
  back, the host registers it).
- No hover-to-open: a menu opens on click, Down or Enter only (native menubar
  parity minus the mode nobody asks for).
- No QSS: triggers are ``variant="ghost"`` buttons, which resolve their own
  look through the painter pipeline and the theme tokens.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Literal, Sequence

import shiboken6
from PySide6.QtCore import QCoreApplication, QEvent, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHBoxLayout, QWidget

from sli_ui_toolkit.i18n import get_current_language, translator_for
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.managers.navigation_sections import ToolbarRowsSection
from sli_ui_toolkit.ui.managers.ui_scale import scaled_px
from sli_ui_toolkit.ui.widgets.buttons.button import Button
from sli_ui_toolkit.ui.widgets.composite.context_menu.menu import ContextMenu
from sli_ui_toolkit.ui.widgets.composite.context_menu.models import (
    ContextMenuAction,
    ContextMenuEntry,
    ContextMenuSection,
)

__all__ = ["MenuStrip", "MenuStripMenu"]


@dataclass(slots=True)
class MenuStripMenu:
    """One strip trigger plus the entries its dropdown shows.

    ``title`` is a literal label; ``text_key`` (when set) wins over it and is
    re-resolved on every language change, matching the rest of the toolkit's
    declarative-key convention. ``entries`` are the SAME ``ContextMenuEntry``
    models a right-click ``ContextMenu`` takes, so actions, sections,
    separators and submenus work here without translation.
    """

    title: str = ""
    entries: tuple[ContextMenuEntry, ...] = ()
    text_key: str | None = None
    icon: object | None = None
    tooltip: str = ""
    enabled: bool = True
    on_triggered: Callable[[str, object], None] | None = None


def _action_in_entries(entries: Sequence[ContextMenuEntry], action_id: str) -> bool:
    """True when ``action_id`` is reachable in this entry tree.

    Children count: a row inside a submenu is still owned by the menu the
    submenu belongs to, which is what ``reveal`` needs to know.
    """
    for entry in entries:
        if isinstance(entry, ContextMenuAction):
            if entry.action_id == action_id:
                return True
            if entry.children and _action_in_entries(entry.children, action_id):
                return True
        elif isinstance(entry, ContextMenuSection):
            if _action_in_entries(entry.entries, action_id):
                return True
    return False


class _MenuTrigger(Button):
    """Trigger button that also owns the strip's Down/Escape semantics.

    ``ToolbarRowsSection`` gives the focused widget first refusal on Up/Down by
    dispatching a synthetic key press to it (``_widget_handles``). Handling
    Down here is therefore the only place that works both with and without a
    host-registered navigation section: with one, the section sees the key
    accepted and stops; without one, Qt delivers the key straight to the
    button. Left/Right stay untouched so the section can move between
    triggers.
    """

    def __init__(self, strip: "MenuStrip", menu_index: int, *, icon=None, **kwargs) -> None:
        super().__init__(icon, **kwargs)
        self._menu_strip = strip
        self._menu_index = menu_index

    def keyPressEvent(self, event):  # noqa: N802 - Qt API
        key = event.key()
        if key == Qt.Key.Key_Down:
            self._menu_strip._open_menu_at(self._menu_index)
            event.accept()
            return
        if key == Qt.Key.Key_Escape and self._menu_strip.current_menu() is not None:
            self._menu_strip.close_menu()
            event.accept()
            return
        super().keyPressEvent(event)


class MenuStrip(QWidget):
    """A row of menu triggers, each opening a ``ContextMenu`` below itself.

    Usage::

        strip = MenuStrip(title_bar)
        strip.add_menu("File", file_entries, on_triggered=self._on_file_action)
        strip.add_menu("Help", help_entries)
        strip.actionTriggered.connect(self._dispatch)   # or per-menu callbacks
        title_bar.set_leading(strip)
        navigation_manager.register(window, strip.navigation_section())

    ``MenuStrip`` is host-agnostic: it takes titles and entry models, never an
    application's own strings, and keeps no app-level state. Only one dropdown
    is open at a time; clicking the same trigger again, Esc, or an outside
    click closes it (the last two come from ``ContextMenu``/``FlyoutManager``).
    """

    actionTriggered = Signal(str, object)

    #: Title-bar proportions (design px); the trigger's width follows its text.
    TRIGGER_HEIGHT = 24
    #: Visible gap between the trigger's bottom edge and the dropdown.
    MENU_OFFSET = 2

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        surface: Literal["in_window", "popup"] = "in_window",
        trigger_height: int | None = None,
    ) -> None:
        super().__init__(parent)
        if surface not in ("in_window", "popup"):
            raise ValueError(
                f"MenuStrip surface must be 'in_window' or 'popup', got {surface!r}"
            )
        self._surface = surface
        self._trigger_height = (
            int(trigger_height) if trigger_height is not None else self.TRIGGER_HEIGHT
        )
        self._menus: list[MenuStripMenu] = []
        self._triggers: list[_MenuTrigger] = []
        self._open_menu: ContextMenu | None = None
        self._open_index: int | None = None
        self._translator = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(scaled_px(2))
        self._layout = layout

        # ``_MenuTrigger`` is a ``Button``: its content layer falls back to
        # ``dialog.text`` unless the strip hands it the menu family's own ink.
        # The token is resolved per theme (never cached at construction), so a
        # live theme switch re-inks the triggers with the rest of the menu.
        try:
            ThemeManager.get_instance().theme_changed.connect(self._on_theme_changed)
        except Exception:
            pass  # the manager is a process singleton; a stripped test host may lack it, and ink then stays default

    # -------- content --------

    def add_menu(
        self,
        title: str,
        entries: Iterable[ContextMenuEntry],
        *,
        text_key: str | None = None,
        icon: object | None = None,
        tooltip: str = "",
        enabled: bool = True,
        on_triggered: Callable[[str, object], None] | None = None,
    ) -> None:
        """Append one trigger + dropdown; titles are host-supplied."""
        spec = MenuStripMenu(
            title=str(title),
            entries=tuple(entries),
            text_key=text_key,
            icon=icon,
            tooltip=str(tooltip),
            enabled=bool(enabled),
            on_triggered=on_triggered,
        )
        self._install_menu(spec)

    def set_menus(
        self,
        menus: Iterable[MenuStripMenu | tuple[str, Iterable[ContextMenuEntry]]],
    ) -> None:
        """Replace every menu. Accepts ``MenuStripMenu`` or ``(title, entries)``."""
        self.clear()
        for item in menus:
            if isinstance(item, MenuStripMenu):
                self._install_menu(item)
                continue
            try:
                title, entries = item
            except (TypeError, ValueError):
                raise TypeError(
                    "MenuStrip.set_menus expects MenuStripMenu or "
                    f"(title, entries) pairs, got {item!r}"
                ) from None
            self.add_menu(title, entries)

    def clear(self) -> None:
        """Drop every trigger (and tear down the open dropdown)."""
        self._release_menu()
        for trigger in self._triggers:
            self._layout.removeWidget(trigger)
            trigger.hide()
            trigger.setParent(None)
            trigger.deleteLater()
        self._triggers.clear()
        self._menus.clear()
        # Same deferred-delete flush the ContextMenu entry reset uses: creating
        # a new trigger in the same tick as the old one is deleted races under
        # Python 3.14 / Shiboken.
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def menu_titles(self) -> list[str]:
        """Trigger labels in strip order, with translation keys resolved."""
        return [self._title_text(spec) for spec in self._menus]

    def menu_count(self) -> int:
        return len(self._menus)

    # -------- opening / closing --------

    def current_menu(self) -> ContextMenu | None:
        """The visible dropdown, or ``None`` when everything is closed."""
        menu = self._open_menu
        if menu is None:
            return None
        try:
            if not shiboken6.isValid(menu):  # type: ignore[attr-defined]
                self._open_menu = None
                self._open_index = None
                return None
            return menu if menu.isVisible() else None
        except RuntimeError:
            self._open_menu = None
            self._open_index = None
            return None

    def close_menu(self) -> None:
        """Hide the open dropdown (no-op when none is open).

        The hidden ``ContextMenu`` is torn down by its own ``aboutToHide``
        slot, so a closed menu never lingers as an overlay-layer child.
        """
        menu = self._open_menu
        if menu is None:
            return
        try:
            if not shiboken6.isValid(menu):  # type: ignore[attr-defined]
                self._open_menu = None
                self._open_index = None
                return
            menu.hide()
        except RuntimeError:
            self._open_menu = None
            self._open_index = None

    def reveal(self, action_id: str, *, pulse: bool = True) -> QWidget | None:
        """Open the menu owning ``action_id`` and surface its row.

        Returns the row widget when the action sits at the menu's top level
        (a row inside a submenu is materialized only when that submenu opens),
        ``None`` when the id is unknown or only reachable through a branch.
        ``pulse`` briefly flashes the row's hover background so a command
        palette or a host shortcut can point at it.
        """
        if not action_id:
            return None
        index = next(
            (
                i
                for i, spec in enumerate(self._menus)
                if _action_in_entries(spec.entries, action_id)
            ),
            None,
        )
        if index is None:
            return None
        menu = self.current_menu()
        if menu is None or self._open_index != index:
            self._open_menu_at(index)
            menu = self.current_menu()
        if menu is None:
            return None
        row = menu.row_for_action(action_id)
        if row is None:
            return None
        try:
            row.setFocus(Qt.FocusReason.OtherFocusReason)
        except RuntimeError:
            return None
        if pulse:
            pulse_row = getattr(row, "pulse", None)
            if callable(pulse_row):
                pulse_row()
        return row

    # -------- keyboard / navigation --------

    def navigation_section(self, *, tag: str = "menu-strip") -> ToolbarRowsSection:
        """A section over the triggers for the host to register.

        The strip is one row (Left/Right walk its triggers); an empty strip is
        not a row at all, so registration never creates a dead stop.
        """
        return ToolbarRowsSection(
            lambda: [self] if self._triggers else [],
            tag=tag,
        )

    def keyPressEvent(self, event):  # noqa: N802 - Qt API
        # Fallback for hosts that did not register ``navigation_section()``:
        # a trigger's unhandled Escape propagates here.
        if event.key() == Qt.Key.Key_Escape and self.current_menu() is not None:
            self.close_menu()
            event.accept()
            return
        super().keyPressEvent(event)

    # -------- translation --------

    def set_translator(self, tr_func, *, defer_when_hidden: bool = False) -> None:
        """Duck-typed protocol hook used by ``bind_translator``."""
        del defer_when_hidden
        self._translator = tr_func
        self._sli_translator = tr_func  # translator_for() walks for this name
        menu = self.current_menu()
        if menu is not None:
            menu.set_translator(tr_func)
            menu.retranslate(get_current_language())

    def retranslate(self, lang: str) -> None:
        """Re-resolve every keyed trigger label (and the open dropdown)."""
        for spec, trigger in zip(self._menus, self._triggers):
            try:
                trigger.setText(self._title_text(spec))
            except RuntimeError:
                continue
        menu = self.current_menu()
        if menu is not None:
            try:
                menu.retranslate(lang)
            except (RuntimeError, SystemError):
                pass

    # -------- internals --------

    def _title_text(self, spec: MenuStripMenu) -> str:
        if not spec.text_key:
            return spec.title
        tr_func = self._translator or translator_for(self)
        return str(tr_func(spec.text_key, get_current_language()))

    def _install_menu(self, spec: MenuStripMenu) -> None:
        index = len(self._menus)
        self._menus.append(spec)
        trigger = _MenuTrigger(
            self,
            index,
            icon=spec.icon,
            text=self._title_text(spec),
            variant="ghost",
            size=(0, self._trigger_height),
            parent=self,
        )
        if spec.tooltip:
            trigger.setToolTip(spec.tooltip)
        trigger.setEnabled(spec.enabled)
        self._apply_trigger_ink(trigger)
        trigger.clicked.connect(lambda _checked=False, i=index: self._on_trigger_clicked(i))
        self._layout.addWidget(trigger)
        self._triggers.append(trigger)

    def _apply_trigger_ink(self, trigger: _MenuTrigger) -> None:
        """Give a trigger the menu family's label colour (``menu.text``).

        ``None`` leaves the button's own default in place, which is what a
        palette without the menu family gets.
        """
        ink = ThemeManager.get_instance().try_get_color("menu.text")
        try:
            trigger.setForegroundColor(QColor(ink) if ink is not None else None)
            trigger.update()
        except (RuntimeError, AttributeError):
            # A trigger deleted between the theme change and this pass.
            return

    def _on_theme_changed(self, *_args) -> None:
        for trigger in self._triggers:
            self._apply_trigger_ink(trigger)

    def _on_trigger_clicked(self, index: int) -> None:
        trigger = self._triggers[index]
        # FlyoutManager set this on the press that dismissed this trigger's
        # own open menu; consuming it here is what makes a second click on an
        # open trigger close instead of close-then-reopen.
        if getattr(trigger, "_suppress_next_context_menu", False):
            trigger._suppress_next_context_menu = False  # type: ignore[attr-defined]
            return
        menu = self.current_menu()
        if menu is not None and self._open_index == index:
            self.close_menu()
            return
        self._open_menu_at(index)

    def _open_menu_at(self, index: int) -> ContextMenu | None:
        if not (0 <= index < len(self._menus)):
            return None
        self._release_menu()
        spec = self._menus[index]
        trigger = self._triggers[index]
        menu = ContextMenu(self, entries=spec.entries, surface=self._surface)
        # A later-built dropdown is reparented into the window's overlay, so
        # ``translator_for`` cannot walk back to the strip: hand it the
        # translator explicitly and resolve declarative keys before showing
        # (a keyed row would otherwise open with empty text).
        tr_func = self._translator
        if tr_func is not None:
            menu.set_translator(tr_func)
        menu.retranslate(get_current_language())
        menu.actionTriggered.connect(
            lambda action_id, data, i=index: self._dispatch(i, action_id, data)
        )
        menu.aboutToHide.connect(lambda m=menu: self._on_menu_hidden(m))
        self._open_menu = menu
        self._open_index = index
        menu.show_aligned(
            trigger,
            anchor_point="bottom-left",
            flyout_point="top-left",
            offset=self.MENU_OFFSET,
        )
        return menu

    def _release_menu(self) -> None:
        """Hide + destroy the previous dropdown before a new one is built."""
        menu = self._open_menu
        self._open_menu = None
        self._open_index = None
        if menu is None:
            return
        try:
            alive = shiboken6.isValid(menu)  # type: ignore[attr-defined]
        except RuntimeError:
            return
        if not alive:
            return
        try:
            menu.hide()
        except RuntimeError:
            pass
        try:
            menu.setParent(None)
            menu.deleteLater()
        except RuntimeError:
            pass

    def _on_menu_hidden(self, menu: ContextMenu) -> None:
        if self._open_menu is menu:
            self._open_menu = None
            self._open_index = None
        # The dropdown is reparented into the window's overlay layer, so the
        # strip cannot rely on ownership: deleting it here is what keeps a
        # closed menu from outliving its open (same teardown the popup surface
        # runs right after its own ``aboutToHide``).
        try:
            if shiboken6.isValid(menu):  # type: ignore[attr-defined]
                menu.deleteLater()
        except RuntimeError:
            pass

    def _dispatch(self, index: int, action_id: str, data: object) -> None:
        spec = self._menus[index]
        self.actionTriggered.emit(action_id, data)
        if spec.on_triggered is not None:
            spec.on_triggered(action_id, data)
