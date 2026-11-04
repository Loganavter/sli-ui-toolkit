"""The shell's opt-in footer rule: edge to edge, in the divider's colour.

Owner request 2026-11-04: the horizontal rule above the dialog's action buttons
must (a) use the same colour as the vertical section divider and (b) run from
that divider to the window edge — no content padding on its own row.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QHBoxLayout, QStackedWidget, QWidget

from sli_ui_toolkit.ui.widgets.composite.dialog_shell import (
    SidebarDialogShell,
    _DialogHairline,
)


def _shell(qapp, *, footer_separator: bool):
    return SidebarDialogShell(
        sidebar_width=200,
        content_margins=(20, 20, 20, 20),
        resizable_sidebar=True,
        footer_separator=footer_separator,
    )


def test_the_footer_rule_exists_only_when_asked(qapp):
    plain = _shell(qapp, footer_separator=False)
    with_rule = _shell(qapp, footer_separator=True)
    try:
        assert plain.footer_separator is None
        assert with_rule.footer_separator is not None
        assert isinstance(with_rule.footer_separator, _DialogHairline)
        assert with_rule.footer_layout is not None
        assert isinstance(with_rule.footer_layout, QHBoxLayout)
    finally:
        plain.deleteLater()
        with_rule.deleteLater()


def test_the_rule_row_has_no_side_padding_so_it_reaches_both_edges(qapp):
    """The column is flush; the pages and the footer carry the padding."""
    shell = _shell(qapp, footer_separator=True)
    try:
        margins = shell.content_layout.contentsMargins()
        assert (margins.left(), margins.right()) == (0, 0)
        # the pages keep the design padding
        pages = shell._pages_host_layout.contentsMargins()
        assert (pages.left(), pages.top(), pages.right(), pages.bottom()) == (
            20, 20, 20, 20,
        )
        # the footer keeps the side padding for its buttons, not for the rule,
        # and the top gap keeps them off the line (owner report 2026-11-04)
        footer = shell.footer_layout.contentsMargins()
        assert footer.left() == 20 and footer.right() == 20
        assert footer.top() == 20, "the buttons sit right against the rule"
    finally:
        shell.deleteLater()


def test_the_handle_carries_the_rule_across_to_the_divider_line(qapp):
    """The rule must MEET the divider, not stop a few px short of it.

    The rule lives in the content pane and the divider line is painted at the
    splitter handle's centre, so a flush rule leaves a gap. Qt clamps negative
    layout margins to zero, so the handle paints the connecting stub instead.
    """
    shell = _shell(qapp, footer_separator=True)
    try:
        shell.resize(900, 600)
        shell.show()
        qapp.processEvents()
        shell._sync_footer_rule_y()
        handle = shell.splitter.handle(1)
        assert handle._footer_rule_provider is not None, (
            "the handle was never told where the footer rule is"
        )
        # the provider answers at PAINT time, so it survives a late layout
        y = handle._footer_rule_provider()
        assert 0 <= y <= handle.height(), (y, handle.height())
    finally:
        shell.close()
        shell.deleteLater()


def test_the_rule_paints_one_device_column_in_the_divider_colour(qapp):
    """Same painting rule as the vertical handle: one crisp device column."""
    from PySide6.QtGui import QColor

    from sli_ui_toolkit.managers import ThemeManager

    shell = _shell(qapp, footer_separator=True)
    try:
        rule = shell.footer_separator
        theme = ThemeManager.get_instance()
        expected = theme.try_get_color("dialog.border")
        rule._refresh_color()
        assert rule._line_color.isValid()
        if expected is not None:
            assert rule._line_color == QColor(expected)
        # a 1-logical-px strip at DPR 1 is exactly one device column
        rule.resize(400, 1)
        assert rule.height() == 1
    finally:
        shell.deleteLater()


def test_the_rule_row_is_flush_so_the_rule_starts_on_the_column_edge(qapp):
    """A fresh QLayout takes the style's ~9 px margins and insets the rule."""
    shell = _shell(qapp, footer_separator=True)
    try:
        margins = shell._rule_row_layout.contentsMargins()
        assert (margins.left(), margins.top(), margins.right(), margins.bottom()) == (
            0, 0, 0, 0,
        )
    finally:
        shell.deleteLater()
