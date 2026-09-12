"""Ordered row accumulation for ``ToolbarRowsSection`` consumers.

Replaces the "wrap each row with a helper, then hand-reassemble a list at
the end" two-step every settings-page-shaped consumer used to write for
itself (e.g. the app's old ``as_nav_row`` + a hand-built ``rows = [...]``)
— that reassembly step is exactly where row order silently drifts from
visual layout order, since nothing enforces the two match. ``NavRowBuilder``
accumulates rows in construction order instead, so the row list is always
right by construction.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtWidgets import QLayout, QVBoxLayout, QWidget

from sli_ui_toolkit.ui.managers.navigation_sections import ToolbarRowsSection


def as_nav_row(item: QWidget | QLayout) -> QWidget:
    """Wrap *item* (a widget or an unparented layout) in a thin row widget.

    A bare widget becomes the sole child of a zero-margin ``QVBoxLayout``;
    a bare layout is adopted directly by a new ``QWidget`` — either way the
    result is a container ``ToolbarRowsSection`` can treat as one row
    (``ToolbarRowsSection._focusable`` looks at a row's *descendants*,
    never the row widget itself, so a standalone control needs wrapping
    before it can serve as one).
    """
    if isinstance(item, QWidget):
        row = QWidget()
        row_layout = QVBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.addWidget(item)
        return row
    row = QWidget()
    row.setLayout(item)
    return row


class NavRowBuilder:
    """Accumulates navigable rows in construction order for one section.

    Usage::

        builder = NavRowBuilder(tag="settings-general")
        lang_row = builder.row(lang_row_widget)      # same call site as as_nav_row() today
        theme_row = builder.row(theme_row_widget)
        section = builder.build()                     # -> ToolbarRowsSection, rows already in order

    ``extend()`` absorbs rows built elsewhere (e.g. a tab-contributed
    "extras" callback) so they participate in navigation instead of being
    silently dropped. This class only removes the order-drift risk and the
    wrap-then-reassemble step — callers still do their own registration
    (``register_navigation`` / ``NavigationManager.register``).
    """

    def __init__(self, *, tag: str = "toolbar-rows") -> None:
        self._tag = tag
        self._rows: list[QWidget] = []

    @property
    def tag(self) -> str:
        return self._tag

    def row(self, item: QWidget | QLayout) -> QWidget:
        """Wrap *item* via :func:`as_nav_row`, remember it, and return it."""
        row = as_nav_row(item)
        self._rows.append(row)
        return row

    def extend(self, rows: list[QWidget]) -> None:
        """Append already-built row widgets, preserving their order."""
        self._rows.extend(rows)

    def build(self, *, on_exit_left: Callable[..., bool] | None = None) -> ToolbarRowsSection:
        """Return a ``ToolbarRowsSection`` over the rows accumulated so far.

        Snapshots the current row list at call time — later ``row()``/
        ``extend()`` calls on this builder do not affect an already-built
        section.
        """
        rows = list(self._rows)
        return ToolbarRowsSection(lambda: list(rows), tag=self._tag, on_exit_left=on_exit_left)


__all__ = ["NavRowBuilder", "as_nav_row"]
