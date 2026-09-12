"""Entry flattening, row construction, and width sizing for ``ContextMenu``.

Split out of ``menu.py`` to separate "build the row widgets from declarative
entries" from the popup placement/animation and the ``ContextMenu`` facade
itself, mirroring the ``base_flyout/`` builder/placement/animation split.
Every function here takes the owning ``ContextMenu`` as its first argument
(except ``_flatten``, which is pure).
"""

from __future__ import annotations

from typing import Sequence

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QWidget

from sli_ui_toolkit.managers import scaled_px
from sli_ui_toolkit.ui.widgets.composite.context_menu import submenu as submenu_ops
from sli_ui_toolkit.ui.widgets.composite.context_menu.models import (
    ContextMenuAction,
    ContextMenuEntry,
    ContextMenuSection,
    ContextMenuSeparator,
    _SectionTitle,
    _entry_visible,
    _trim_flat_separators,
)
from sli_ui_toolkit.ui.widgets.composite.context_menu.rows import (
    ContextMenuRow,
    SectionTitleRow,
    SeparatorRow,
)


def set_entries(menu, entries) -> None:
    submenu_ops.close_submenu(menu)
    # Take widgets out of the layout once, then destroy. Calling
    # deleteLater on both ``_rows`` and layout items double-schedules the
    # same ContextMenuRow and races with immediate recreation under
    # Python 3.14 / Shiboken (SystemError in Button/QWidget.__init__).
    pending: list[QWidget] = []
    while menu.content_layout.count():
        item = menu.content_layout.takeAt(0)
        widget = item.widget() if item is not None else None
        if widget is not None:
            pending.append(widget)
    menu._rows.clear()
    for widget in pending:
        widget.hide()
        widget.setParent(None)
        widget.deleteLater()

    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    flat = _trim_flat_separators(_flatten(tuple(entries)))
    # No check-glyph gutter: current/checkable rows use background highlight only.
    check_gutter = scaled_px(12)
    for item in flat:
        menu.content_layout.addWidget(_build_row(menu, item, check_gutter))
    _assign_row_positions(menu)
    _relayout_widths(menu)


def _flatten(entries: Sequence[ContextMenuEntry]) -> list:
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
            flat.extend(_flatten(visible_entries))
            if not isinstance(flat[-1], ContextMenuSeparator):
                flat.append(ContextMenuSeparator())
        elif isinstance(entry, ContextMenuAction):
            if entry.visible:
                flat.append(entry)
    return flat


def _build_row(menu, item, check_gutter: int) -> QWidget:
    if isinstance(item, ContextMenuSeparator):
        return SeparatorRow(menu.container)
    if isinstance(item, _SectionTitle):
        return SectionTitleRow(item.text, menu.container)
    row = ContextMenuRow(item, check_gutter=check_gutter, parent=menu.container)
    row._spec = item
    row.clicked.connect(lambda checked=False, r=row, spec=item: menu._on_row_clicked(r, spec))
    row.installEventFilter(menu)
    menu._rows.append(row)
    return row


def _assign_row_positions(menu) -> None:
    rows = list(menu._rows)
    count = len(rows)
    for index, row in enumerate(rows):
        if count == 1:
            row.set_position("only")
        elif index == 0:
            row.set_position("first")
        elif index == count - 1:
            row.set_position("last")
        else:
            row.set_position("middle")


def _relayout_widths(menu) -> None:
    """Size the menu to the widest row using the current font metrics."""
    from sli_ui_toolkit.ui.managers.ui_font import ui_font

    app_font = ui_font()
    max_w = 0

    for index in range(menu.content_layout.count()):
        layout_item = menu.content_layout.itemAt(index)
        widget = layout_item.widget() if layout_item is not None else None
        if widget is None:
            continue
        widget.setMinimumWidth(0)
        if isinstance(widget, SectionTitleRow):
            widget.setFont(ui_font(pixel_size=11, bold=True))
        else:
            widget.setFont(app_font)

    for row in menu._rows:
        row.refresh_metrics()
        max_w = max(max_w, row.sizeHint().width())

    for index in range(menu.content_layout.count()):
        layout_item = menu.content_layout.itemAt(index)
        widget = layout_item.widget() if layout_item is not None else None
        if widget is None:
            continue
        hint = widget.sizeHint()
        if hint.isValid():
            max_w = max(max_w, hint.width())

    if max_w <= 0:
        menu.adjustSize()
        return

    for index in range(menu.content_layout.count()):
        layout_item = menu.content_layout.itemAt(index)
        widget = layout_item.widget() if layout_item is not None else None
        if widget is not None:
            widget.setMinimumWidth(max_w)

    menu.setMinimumSize(0, 0)
    container_layout = menu.container.layout()
    if container_layout is not None:
        container_layout.invalidate()
        container_layout.activate()
        menu.container.updateGeometry()
    menu.adjustSize()
