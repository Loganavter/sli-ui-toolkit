from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from PySide6.QtCore import QEvent, QSize, Qt
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QWidget

from sli_ui_toolkit.theme import ThemeManager

from sli_ui_toolkit.ui.widgets.buttons import Button
from sli_ui_toolkit.ui.widgets.composite.context_menu import (
    ContextMenu,
    ContextMenuAction,
    ContextMenuEntry,
    ContextMenuSection,
    ContextMenuSeparator,
    entries_from_callbacks,
    popup_context_menu_for_anchor,
)
from sli_ui_toolkit.ui.windows.custom_title_bar import CustomTitleBar, resolve_titlebar_color

TitleBarMenuMode = Literal["auto", "context_menu", "flyout"]


def _estimate_menu_button_width(
    label: str,
    height: int,
    *,
    has_icon: bool = False,
    icon_size: int = 16,
    gap: int = 0,
    content_pad: int = 0,
) -> int:
    from PySide6.QtGui import QFontMetrics
    from sli_ui_toolkit.ui.managers.ui_font import ui_font

    # Small slack so AA / font swaps after first measure do not clip glyphs.
    _SLACK = 4
    fm = QFontMetrics(ui_font())
    text_w = fm.horizontalAdvance(label)
    if has_icon:
        return content_pad + icon_size + gap + text_w + content_pad + _SLACK
    # Text-only triggers: modest side padding so the hit target isn't flush.
    return max(40, text_w + 16 + _SLACK)


def _is_context_entry(entry: object) -> bool:
    return isinstance(
        entry,
        (ContextMenuAction, ContextMenuSection, ContextMenuSeparator),
    )


def _is_callback_tuple_entry(entry: object) -> bool:
    return (
        isinstance(entry, tuple)
        and len(entry) == 2
        and isinstance(entry[0], str)
    )


def _normalize_menu_entries(
    entries: Sequence[object],
    *,
    id_prefix: str,
) -> tuple[ContextMenuEntry, ...]:
    if not entries:
        return ()
    if all(_is_context_entry(entry) for entry in entries):
        return tuple(entries)  # type: ignore[return-value]
    if all(_is_callback_tuple_entry(entry) for entry in entries):
        return entries_from_callbacks(entries, id_prefix=id_prefix)  # type: ignore[arg-type]
    raise TypeError(
        "TitleBarMenu.entries must be ContextMenuEntry objects or (label, callback) tuples"
    )


@dataclass(slots=True)
class TitleBarMenu:
    label: str
    entries: Sequence[object] = field(default_factory=tuple)
    mode: TitleBarMenuMode = "auto"
    flyout_factory: Callable[[QWidget], QWidget] | None = None
    on_triggered: Callable[[str, object], None] | None = None
    # Optional leading icon drawn inside the trigger (e.g. app icon on File).
    icon: Any = None
    icon_size: int = 16


class TitleBarMenuStrip(QWidget):
    """Horizontal row of menu triggers for a title bar leading zone."""

    # Equal top/bottom inset so File/Help don't flush against the chrome edges.
    V_INSET = 4
    # Left inset from the title-bar edge to the first menu trigger.
    H_INSET = 8
    # Space between adjacent menu triggers (File | Help).
    SPACING = 8
    # Internal icon↔label spacing inside a single trigger capsule.
    GAP = 8
    # Text triggers default to radius 2 in Button — force a visible round.
    CORNER_RADIUS = 6
    # Horizontal inset inside an icon+label trigger (icon/text ↔ button edge).
    CONTENT_PAD = 6

    def __init__(
        self,
        menus: Sequence[TitleBarMenu],
        *,
        parent: QWidget | None = None,
        height: int = CustomTitleBar.HEIGHT,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("TitleBarMenuStrip")
        self._height = height
        self.setFixedHeight(height)
        self._menus = list(menus)
        self._buttons: list[Button] = []
        self._context_menus: dict[int, ContextMenu] = {}
        self._theme_manager = ThemeManager.get_instance()
        self._theme_manager.theme_changed.connect(self._on_theme_changed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(self.H_INSET, self.V_INSET, 0, self.V_INSET)
        layout.setSpacing(self.SPACING)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        for menu in self._menus:
            button = self._build_trigger(menu)
            self._buttons.append(button)
            layout.addWidget(button)

    def _resolve_mode(self, menu: TitleBarMenu) -> TitleBarMenuMode:
        if menu.mode != "auto":
            return menu.mode
        if menu.flyout_factory is not None:
            return "flyout"
        return "context_menu"

    def _build_trigger(self, menu: TitleBarMenu) -> Button:
        trigger_height = max(20, self._height - 2 * self.V_INSET)
        has_icon = menu.icon is not None
        icon_size = max(12, min(menu.icon_size, trigger_height - 4))
        gap = self.GAP if has_icon else 6
        content_pad = self.CONTENT_PAD if has_icon else 0
        width = _estimate_menu_button_width(
            menu.label,
            trigger_height,
            has_icon=has_icon,
            icon_size=icon_size,
            gap=gap if has_icon else 0,
            content_pad=content_pad,
        )
        button = Button(
            icon=menu.icon if has_icon else None,
            text=menu.label,
            variant="ghost",
            size=(width, trigger_height),
            icon_size=icon_size,
            gap=gap,
            corner_radius=self.CORNER_RADIUS,
            content_padding=(content_pad, 0, content_pad, 0) if has_icon else 0.0,
            content_align=(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                if has_icon
                else Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
            ),
            parent=self,
        )
        button.setObjectName("TitleBarMenuTrigger")
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.setCursor(Qt.CursorShape.ArrowCursor)
        button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._apply_trigger_style(button)

        mode = self._resolve_mode(menu)
        if mode == "context_menu":
            entries = _normalize_menu_entries(
                menu.entries,
                id_prefix=f"titlebar.{menu.label.lower()}",
            )
            button.clicked.connect(
                lambda *, _button=button, _entries=entries, _handler=menu.on_triggered: self._show_context_menu(
                    _button, _entries, on_triggered=_handler
                )
            )
        elif mode == "flyout" and menu.flyout_factory is not None:
            button.clicked.connect(
                lambda *, _button=button, _factory=menu.flyout_factory: self._toggle_flyout(
                    _button, _factory
                )
            )
        return button

    def _apply_trigger_style(self, button: Button) -> None:
        button.setForegroundColor(
            resolve_titlebar_color("titlebar.text", fallback="WindowText")
        )

    def remasure(self) -> None:
        """Recompute trigger widths from the current UiFont and sync title balance.

        Call after the host applies the UI face (menus are often built before
        ``FontManager`` runs). Without this, Cyrillic labels can measure near
        zero width and «Справка» paints where «Файл» belongs until FontChange.

        Does **not** schedule a deferred balance pass — a singleShot(0) resync
        after the first paint leaves a translucent ghost of «Справка» between
        File and Help.
        """
        for menu, button in zip(self._menus, self._buttons):
            trigger_height = max(20, self._height - 2 * self.V_INSET)
            has_icon = menu.icon is not None
            icon_size = max(12, min(menu.icon_size, trigger_height - 4))
            gap = self.GAP if has_icon else 6
            content_pad = self.CONTENT_PAD if has_icon else 0
            width = _estimate_menu_button_width(
                menu.label,
                trigger_height,
                has_icon=has_icon,
                icon_size=icon_size,
                gap=gap if has_icon else 0,
                content_pad=content_pad,
            )
            button.setFixedSize(width, trigger_height)
            button.update()
        self.updateGeometry()
        self.update()
        parent = self.parent()
        while parent is not None:
            sync = getattr(parent, "_sync_balance_spacer", None)
            if callable(sync):
                sync()
                # Erase translucent ghost trigger glyphs after width changes.
                parent.repaint()
                break
            parent = parent.parentWidget()

    def _on_theme_changed(self, *_args) -> None:
        for button in self._buttons:
            self._apply_trigger_style(button)
            button.update()

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() in (
            QEvent.Type.FontChange,
            QEvent.Type.ApplicationFontChange,
        ):
            self.remasure()

    def _show_context_menu(
        self,
        anchor: Button,
        entries: Iterable[ContextMenuEntry],
        *,
        on_triggered: Callable[[str, object], None] | None = None,
        force_open: bool = False,
    ) -> None:
        parent = anchor.window()
        if parent is None:
            return
        key = id(anchor)
        if getattr(anchor, "_suppress_next_context_menu", False):
            anchor._suppress_next_context_menu = False  # type: ignore[attr-defined]
            return

        menu = self._context_menus.get(key)
        if menu is not None and not self._menu_is_alive(menu):
            self._context_menus.pop(key, None)
            if getattr(anchor, "_anchor_context_menu", None) is menu:
                anchor._anchor_context_menu = None  # type: ignore[attr-defined]
            menu = None

        if not force_open and menu is not None and menu.isVisible():
            menu.hide()
            return

        wrapped = self._wrap_triggered(on_triggered)
        if menu is not None:
            menu._on_triggered = wrapped
            try:
                menu.set_entries(entries)
                menu.show_aligned(
                    anchor,
                    anchor_point="bottom-left",
                    flyout_point="top-left",
                    offset=2,
                    animation="slide",
                    animation_axis="vertical",
                )
                anchor._anchor_context_menu = menu  # type: ignore[attr-defined]
                return
            except (RuntimeError, SystemError):
                # Stale C++ shell or row-rebuild failure — drop and recreate.
                self._discard_cached_menu(anchor, key, menu)
                menu = None

        menu = popup_context_menu_for_anchor(
            parent,
            anchor,
            entries,
            on_triggered=wrapped,
            toggle=not force_open,
        )
        self._context_menus[key] = menu

    @staticmethod
    def _menu_is_alive(menu: ContextMenu) -> bool:
        try:
            from shiboken6 import isValid

            return bool(isValid(menu))
        except Exception:
            try:
                menu.objectName()
                return True
            except RuntimeError:
                return False

    def _discard_cached_menu(
        self, anchor: Button, key: int, menu: ContextMenu
    ) -> None:
        self._context_menus.pop(key, None)
        if getattr(anchor, "_anchor_context_menu", None) is menu:
            anchor._anchor_context_menu = None  # type: ignore[attr-defined]
        try:
            menu.hide()
        except RuntimeError:
            pass
        try:
            menu.setParent(None)
            menu.deleteLater()
        except RuntimeError:
            pass

    def reveal_menu_action(self, button: Button, action_id: str) -> QWidget | None:
        """Force-open the menu for ``button`` and return the row for ``action_id``."""
        try:
            index = self._buttons.index(button)
        except ValueError:
            return None
        if index < 0 or index >= len(self._menus):
            return None
        menu_spec = self._menus[index]
        if self._resolve_mode(menu_spec) != "context_menu":
            return None
        entries = _normalize_menu_entries(
            menu_spec.entries,
            id_prefix=f"titlebar.{menu_spec.label.lower()}",
        )
        self._show_context_menu(
            button,
            entries,
            on_triggered=menu_spec.on_triggered,
            force_open=True,
        )
        menu = self._context_menus.get(id(button))
        if menu is None:
            return None
        return menu.row_for_action(action_id)

    @staticmethod
    def _wrap_triggered(
        on_triggered: Callable[[str, object], None] | None,
    ) -> Callable[[str, object], None]:
        def _dispatch(action_id: str, data: object) -> None:
            if on_triggered is not None:
                on_triggered(action_id, data)
            elif callable(data):
                data()
        return _dispatch

    def _toggle_flyout(
        self,
        anchor: Button,
        factory: Callable[[QWidget], QWidget],
    ) -> None:
        panel = factory(anchor)
        show = getattr(panel, "show_aligned", None)
        if show is None:
            return
        if panel.isVisible():
            panel.hide()
            return
        show(anchor, anchor_point="bottom-left", flyout_point="top-left", offset=2)

    def set_menu_labels(self, labels: Sequence[str]) -> None:
        for button, label in zip(self._buttons, labels, strict=False):
            button.setText(label)

    def buttons(self) -> tuple[Button, ...]:
        return tuple(self._buttons)
