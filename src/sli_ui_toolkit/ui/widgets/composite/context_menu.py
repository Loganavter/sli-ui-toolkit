from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable, Sequence

from PySide6.QtCore import QEventLoop, QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFontMetrics, QKeySequence, QPainter, QPen
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.in_window_surface import (
    clamp_surface_rect,
    surface_anchor_rect,
    surface_available_rect,
)
from sli_ui_toolkit.ui.widgets.buttons.button import Button
from sli_ui_toolkit.ui.widgets.buttons.layers import RippleLayer
from sli_ui_toolkit.ui.widgets.buttons.layers._base import Layer
from sli_ui_toolkit.ui.widgets.buttons.state import ButtonState
from sli_ui_toolkit.ui.widgets.composite.base_flyout import BaseFlyout
from sli_ui_toolkit.ui.widgets.helpers.icon_pixmap import normalized_icon_pixmap

_DANGER_COLOR = QColor("#e5484d")


@dataclass(slots=True)
class ContextMenuAction:
    action_id: str
    text: str
    icon: object | None = None
    enabled: bool = True
    visible: bool = True
    checked: bool = False
    checkable: bool = False
    danger: bool = False
    shortcut: str | QKeySequence | None = None
    tooltip: str = ""
    data: object = None
    children: tuple["ContextMenuEntry", ...] = ()


@dataclass(slots=True)
class ContextMenuSection:
    entries: tuple["ContextMenuEntry", ...] = field(default_factory=tuple)
    title: str = ""


@dataclass(slots=True)
class ContextMenuSeparator:
    visible: bool = True


ContextMenuEntry = ContextMenuAction | ContextMenuSection | ContextMenuSeparator


@dataclass(slots=True)
class _SectionTitle:
    text: str


def _entry_visible(entry: ContextMenuEntry) -> bool:
    if isinstance(entry, ContextMenuAction):
        return entry.visible
    if isinstance(entry, ContextMenuSeparator):
        return entry.visible
    if isinstance(entry, ContextMenuSection):
        return any(_entry_visible(child) for child in entry.entries)
    return False


def _trim_flat_separators(flat: list) -> list:
    while flat and isinstance(flat[0], ContextMenuSeparator):
        flat.pop(0)
    while flat and isinstance(flat[-1], ContextMenuSeparator):
        flat.pop()
    result = []
    previous_separator = False
    for item in flat:
        if isinstance(item, ContextMenuSeparator):
            if previous_separator:
                continue
            previous_separator = True
        else:
            previous_separator = False
        result.append(item)
    return result


def _shortcut_display_text(shortcut: str | QKeySequence | None) -> str:
    if not shortcut:
        return ""
    sequence = shortcut if isinstance(shortcut, QKeySequence) else QKeySequence(shortcut)
    return sequence.toString(QKeySequence.SequenceFormat.NativeText)


class _SeparatorRow(QWidget):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setFixedHeight(9)

    def paintEvent(self, event):  # noqa: N802 - Qt API
        painter = QPainter(self)
        color = ThemeManager.get_instance().get_color("separator.color")
        y = self.height() // 2
        painter.setPen(QPen(color, 1))
        painter.drawLine(6, y, self.width() - 6, y)
        painter.end()


class _SectionTitleRow(QWidget):
    def __init__(self, text: str, parent: QWidget):
        super().__init__(parent)
        self._text = text
        self.setFixedHeight(24)

    def paintEvent(self, event):  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setPen(QPen(ThemeManager.get_instance().get_color("dialog.text")))
        font = painter.font()
        font.setBold(True)
        font.setPixelSize(11)
        painter.setFont(font)
        painter.drawText(
            self.rect().adjusted(12, 0, -12, 0),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            self._text,
        )
        painter.end()


class _RowBgLayer(Layer):
    def applies(self, ctx) -> bool:
        widget = ctx.widget
        if not widget.isEnabled():
            return False
        states = ctx.effective_states
        return (
            widget._submenu_open
            or ButtonState.HOVERED in states
            or ButtonState.PRESSED in states
        )

    def draw(self, ctx, tm: ThemeManager) -> None:
        rect = ctx.rect.toRect().adjusted(2, 1, -2, -1)
        p = ctx.painter
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(tm.get_color("list_item.background.hover")))
        p.drawRoundedRect(rect, 5, 5)


class _RowContentLayer(Layer):
    def draw(self, ctx, tm: ThemeManager) -> None:
        widget = ctx.widget
        p = ctx.painter
        rect = ctx.rect.toRect()

        if not widget.isEnabled():
            text_color = tm.get_color("ButtonText")
        elif widget._danger:
            text_color = _DANGER_COLOR
        else:
            text_color = tm.get_color("dialog.text")

        x = widget._check_gutter
        if widget._check_icon is not None:
            icon_rect = QRect(10, (rect.height() - 16) // 2, 16, 16)
            p.drawPixmap(icon_rect, widget._check_icon)

        if widget._icon_pixmap is not None:
            icon_rect = QRect(x, (rect.height() - widget.ICON_SIZE) // 2, widget.ICON_SIZE, widget.ICON_SIZE)
            p.drawPixmap(icon_rect, widget._icon_pixmap)
            x += widget.ICON_SIZE + 8

        p.setPen(QPen(text_color))
        p.setFont(widget.font())
        fm = QFontMetrics(widget.font())
        text_y = rect.center().y() + 5
        available = max(0, rect.width() - x - widget._trailing_width - 12)
        elided = fm.elidedText(widget._text, Qt.TextElideMode.ElideRight, available)
        p.drawText(x, text_y, elided)

        if widget._shortcut_text:
            p.setPen(QPen(tm.get_color("ButtonText")))
            sc_width = fm.horizontalAdvance(widget._shortcut_text)
            p.drawText(rect.width() - 12 - sc_width, text_y, widget._shortcut_text)
        elif widget._has_children:
            arrow_rect = QRect(rect.width() - 20, 0, 16, rect.height())
            p.setPen(QPen(text_color))
            p.drawText(
                arrow_rect,
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                "›",
            )


class _ContextMenuRow(Button):
    ROW_HEIGHT = 32
    ICON_SIZE = 16

    def __init__(self, action: ContextMenuAction, *, check_gutter: int, parent: QWidget):
        super().__init__(
            text="",
            size=(0, self.ROW_HEIGHT),
            corner_radius=5,
            layers=[_RowBgLayer(), RippleLayer(), _RowContentLayer()],
            parent=parent,
        )
        self._text = action.text
        self._danger = action.danger
        self._has_children = bool(action.children)
        self._check_gutter = check_gutter
        self._check_icon = (
            normalized_icon_pixmap("check", 16) if action.checkable and action.checked else None
        )
        self._icon_pixmap = normalized_icon_pixmap(action.icon, self.ICON_SIZE) if action.icon else None
        self._shortcut_text = "" if action.children else _shortcut_display_text(action.shortcut)
        self._trailing_width = 0
        if self._shortcut_text:
            self._trailing_width = QFontMetrics(self.font()).horizontalAdvance(self._shortcut_text) + 8
        elif self._has_children:
            self._trailing_width = 20
        self._submenu_open = False
        self._has_text = bool(self._text)
        self.setEnabled(action.enabled)
        if action.tooltip:
            self.setToolTip(action.tooltip)

    def sizeHint(self):
        fm = QFontMetrics(self.font())
        text_w = fm.horizontalAdvance(self._text) if self._text else 0
        icon_w = self.ICON_SIZE + 8 if self._icon_pixmap is not None else 0
        w = self._check_gutter + icon_w + text_w + self._trailing_width + 12
        return QSize(w, self.ROW_HEIGHT)

    def minimumSizeHint(self):
        return self.sizeHint()

    def set_submenu_open(self, is_open: bool) -> None:
        self._submenu_open = is_open
        self.update()


class ContextMenu(BaseFlyout):
    """In-app, theme-aware context menu built from declarative entries.

    Renders as a regular in-window overlay widget (like the rest of this
    toolkit's flyouts) rather than a separate OS popup window.
    """

    actionTriggered = Signal(str, object)
    aboutToHide = Signal()

    CONTENT_RADIUS = 6

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        entries: Iterable[ContextMenuEntry] | None = None,
        on_triggered: Callable[[str, object], None] | None = None,
        _is_submenu: bool = False,
    ):
        # These must exist before BaseFlyout.__init__ runs: attaching the
        # widget to its overlay layer can call hide() on self as a side
        # effect, and hide()/_close_submenu() read these attributes.
        self._open_submenu: "ContextMenu | None" = None
        self._submenu_owner_row: _ContextMenuRow | None = None
        self._owner_menu: "ContextMenu | None" = None
        self._is_submenu = _is_submenu
        super().__init__(parent)
        self._on_triggered = on_triggered
        self._rows: list[_ContextMenuRow] = []
        if _is_submenu:
            self.flyout_manager.unregister_flyout(self)
        if entries is not None:
            self.set_entries(entries)

    # -------- entries --------

    def set_entries(self, entries: Iterable[ContextMenuEntry]) -> None:
        self._close_submenu()
        for row in self._rows:
            row.setParent(None)
            row.deleteLater()
        self._rows.clear()
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        flat = _trim_flat_separators(self._flatten(tuple(entries)))
        check_gutter = 28 if any(
            isinstance(item, ContextMenuAction) and item.checkable for item in flat
        ) else 12
        for item in flat:
            self.content_layout.addWidget(self._build_row(item, check_gutter))
        self.adjustSize()

    def _flatten(self, entries: Sequence[ContextMenuEntry]) -> list:
        flat: list = []
        for entry in entries:
            if isinstance(entry, ContextMenuSeparator):
                if entry.visible:
                    flat.append(entry)
            elif isinstance(entry, ContextMenuSection):
                visible_entries = tuple(e for e in entry.entries if _entry_visible(e))
                if not visible_entries:
                    continue
                if flat and not isinstance(flat[-1], ContextMenuSeparator):
                    flat.append(ContextMenuSeparator())
                if entry.title:
                    flat.append(_SectionTitle(entry.title))
                flat.extend(self._flatten(visible_entries))
                if not isinstance(flat[-1], ContextMenuSeparator):
                    flat.append(ContextMenuSeparator())
            elif isinstance(entry, ContextMenuAction):
                if entry.visible:
                    flat.append(entry)
        return flat

    def _build_row(self, item, check_gutter: int) -> QWidget:
        if isinstance(item, ContextMenuSeparator):
            return _SeparatorRow(self.container)
        if isinstance(item, _SectionTitle):
            return _SectionTitleRow(item.text, self.container)
        row = _ContextMenuRow(item, check_gutter=check_gutter, parent=self.container)
        row.clicked.connect(lambda checked=False, r=row, spec=item: self._on_row_clicked(r, spec))
        self._rows.append(row)
        return row

    def _on_row_clicked(self, row: _ContextMenuRow, spec: ContextMenuAction) -> None:
        if spec.children:
            self._toggle_submenu(row, spec)
            return
        self._close_submenu()
        self._root_menu().hide()
        self.actionTriggered.emit(spec.action_id, spec.data)
        if self._on_triggered is not None:
            self._on_triggered(spec.action_id, spec.data)

    def _root_menu(self) -> "ContextMenu":
        menu = self
        while menu._owner_menu is not None:
            menu = menu._owner_menu
        return menu

    # -------- submenus --------

    def _toggle_submenu(self, row: _ContextMenuRow, spec: ContextMenuAction) -> None:
        if self._open_submenu is not None and self._submenu_owner_row is row:
            self._close_submenu()
            return
        self._close_submenu()

        submenu = ContextMenu(
            self.parentWidget(),
            entries=spec.children,
            on_triggered=self._on_triggered,
            _is_submenu=True,
        )
        submenu.actionTriggered.connect(self.actionTriggered)
        submenu._owner_menu = self
        submenu._ensure_overlay_parent(row)

        self._open_submenu = submenu
        self._submenu_owner_row = row
        row.set_submenu_open(True)

        self._position_submenu(submenu, row)
        submenu.show()
        submenu.raise_()

    def _position_submenu(self, submenu: "ContextMenu", row: _ContextMenuRow) -> None:
        anchor_rect = surface_anchor_rect(submenu, row, submenu.overlay_layer)
        available = surface_available_rect(submenu, row, submenu.overlay_layer, margin=4)
        size = submenu.sizeHint()
        target = QRect(anchor_rect.right() + 2, anchor_rect.top() - self.SHADOW_RADIUS, size.width(), size.height())
        if target.right() > available.right() and anchor_rect.left() - size.width() - 2 >= available.left():
            target.moveLeft(anchor_rect.left() - size.width() - 2)
        target = clamp_surface_rect(target, available)
        submenu.setGeometry(target)

    def _close_submenu(self) -> None:
        submenu = self._open_submenu
        if submenu is None:
            return
        self._open_submenu = None
        if self._submenu_owner_row is not None:
            self._submenu_owner_row.set_submenu_open(False)
        self._submenu_owner_row = None
        submenu.hide()
        submenu.deleteLater()

    # -------- show/hide plumbing --------

    def show(self):
        if self._is_submenu:
            QWidget.show(self)
            return
        super().show()

    def hide(self):
        self._close_submenu()
        if self._is_submenu:
            QWidget.hide(self)
        else:
            super().hide()
        self.aboutToHide.emit()

    def contains_global(self, global_pos) -> bool:
        if super().contains_global(global_pos):
            return True
        if self._open_submenu is not None and self._open_submenu.isVisible():
            return self._open_submenu.contains_global(global_pos)
        return False

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape and self._open_submenu is not None:
            self._close_submenu()
            event.accept()
            return
        super().keyPressEvent(event)

    # -------- public show API --------

    def popup_at(self, global_pos: QPoint) -> None:
        self._close_submenu()
        if self.container.layout():
            self.container.layout().invalidate()
            self.container.layout().activate()
            self.container.updateGeometry()
        self.adjustSize()

        parent = self.parentWidget()
        local_pos = parent.mapFromGlobal(global_pos) if parent is not None else QPoint(0, 0)
        target = QRect(local_pos, self.size())
        if self.overlay_layer is not None and hasattr(self.overlay_layer, "clamp_rect"):
            try:
                target = self.overlay_layer.clamp_rect(target, margin=4)
            except TypeError:
                target = self.overlay_layer.clamp_rect(target)
        else:
            target = clamp_surface_rect(target, surface_available_rect(self, None, self.overlay_layer, margin=4))

        self.setGeometry(target)
        self.show()
        self.raise_()
        self.setFocus()

    def exec_at(self, global_pos: QPoint) -> str | None:
        result: dict[str, str | None] = {"id": None}
        loop = QEventLoop()

        def _on_triggered(action_id: str, _data: object) -> None:
            result["id"] = action_id

        def _on_about_to_hide() -> None:
            loop.quit()

        self.actionTriggered.connect(_on_triggered)
        self.aboutToHide.connect(_on_about_to_hide)
        self.popup_at(global_pos)
        loop.exec()
        self.actionTriggered.disconnect(_on_triggered)
        self.aboutToHide.disconnect(_on_about_to_hide)
        return result["id"]


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
    ) -> "ContextMenuBuilder":
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

    def separator(self, *, visible: bool = True) -> "ContextMenuBuilder":
        self._entries.append(ContextMenuSeparator(visible=visible))
        return self

    def section(
        self,
        entries: Iterable[ContextMenuEntry],
        *,
        title: str = "",
    ) -> "ContextMenuBuilder":
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
