"""Red-before/green-after for the px-scaling ratchet drain (kit-px-sweep).

Each offender site named in ``tests/px_scaling_allowlist.py`` is exercised at
factor 1.0 and then 1.5 **live** (build, ``set_factor``, let the appearance
bus coalesce through its zero-timer) and the geometry is asserted to grow by
exactly ``scaled_px(design)`` — not merely "it changed". Every assertion below
fails against the pre-change source (the raw design px): that is the point of
committing the tests first.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QPixmap

from sli_ui_toolkit.managers import UiScale
from sli_ui_toolkit.widgets import (
    Button,
    CalendarDayButton,
    DropZoneLabel,
    EditableListItem,
    MarkdownHelpDialog,
    MarkdownHelpSection,
)


@pytest.fixture(autouse=True)
def _reset_ui_scale():
    yield
    UiScale.get_instance().set_factor(1.0)


def _to_factor(factor: float) -> None:
    UiScale.get_instance().set_factor(factor)


def test_icon_only_button_fixed_size_re_derives_on_live_scale(qtbot):
    """style_api icon-only branch: 36×36 fixed design size must scale live."""
    pixmap = QPixmap(16, 16)
    pixmap.fill(Qt.GlobalColor.red)
    button = Button(icon=QIcon(pixmap), text="label")
    qtbot.addWidget(button)
    button.setText("")  # text -> icon-only: the 36×36 branch

    assert button.minimumWidth() == 36
    assert button.maximumWidth() == 36

    _to_factor(1.5)
    qtbot.wait(20)  # appearance bus coalesces through a zero-timer

    assert button.minimumWidth() == 54  # scaled_px(36)
    assert button.maximumWidth() == 54


def test_drop_zone_min_height_re_derives_on_live_scale(qtbot):
    """drop_zone_label: the 80 design-px floor must grow with the scale."""
    zone = DropZoneLabel("drop here")
    qtbot.addWidget(zone)

    assert zone.minimumHeight() == 80

    _to_factor(1.5)
    qtbot.wait(20)

    assert zone.minimumHeight() == 120  # scaled_px(80)


def test_calendar_day_button_geometry_re_derives_on_live_scale(qtbot):
    """day_button: sizeHint/minimumSizeHint/floor are design px, scaled live."""
    button = CalendarDayButton()
    qtbot.addWidget(button)

    assert button.sizeHint() == QSize(50, 70)
    assert button.minimumSizeHint() == QSize(28, 36)
    assert button.minimumSize() == QSize(28, 36)

    _to_factor(1.5)
    qtbot.wait(20)

    assert button.sizeHint() == QSize(75, 105)  # scaled_px((50, 70))
    assert button.minimumSizeHint() == QSize(42, 54)
    assert button.minimumSize() == QSize(42, 54)  # re-derived by the bus


def test_markdown_help_nav_row_and_default_size_re_derive_on_live_scale(qtbot):
    """markdown_help_dialog: nav row height + initial size are design px."""
    sections = (
        MarkdownHelpSection(
            order=1,
            slug="one",
            title="One",
            body_md="### First\n\ntext\n\n### Second\n\ntext\n",
        ),
    )
    dialog = MarkdownHelpDialog(sections=sections)
    qtbot.addWidget(dialog)

    assert dialog.width() == 800
    assert dialog.height() == 600
    row = dialog.nav_widget.row_button(0)
    assert row is not None
    assert row.maximumHeight() == 35  # scaled_px(35) at 1.0

    _to_factor(1.5)
    qtbot.wait(20)

    # The cached nav row re-derives at the live factor (scaled_px(35) = 52).
    row = dialog.nav_widget.row_button(0)
    assert row is not None
    assert row.maximumHeight() == 52

    # A dialog built at the live factor takes the scaled default size.
    fresh = MarkdownHelpDialog()
    qtbot.addWidget(fresh)
    assert fresh.width() == 1200  # scaled_px(800)
    assert fresh.height() == 900  # scaled_px(600)


def test_editable_list_item_checkbox_floor_re_derives_on_live_scale(qtbot):
    """editable_list_item: the checkbox 28×28 design floor must scale live."""
    item = EditableListItem("entry")
    qtbot.addWidget(item)

    assert item.checkbox.minimumSize() == QSize(28, 28)

    _to_factor(1.5)
    qtbot.wait(20)

    assert item.checkbox.minimumSize() == QSize(42, 42)  # scaled_px(28)
