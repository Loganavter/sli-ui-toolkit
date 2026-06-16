from __future__ import annotations

from PyQt6.QtGui import QImage, QPainter

from sli_ui_toolkit.widgets import IconListItem, IconListWidget
from sli_ui_toolkit.ui.widgets.buttons.state import ButtonState
from sli_ui_toolkit.ui.widgets.composite.sidebar_nav_list import _NavRowContent


def test_icon_list_widget_resolves_string_icons(qapp):
    widget = IconListWidget()
    widget.add_item("Settings", icon="settings")

    row = widget._rows[0]

    assert row.normal_pixmap is not None
    assert not row.normal_pixmap.isNull()
    assert row.button._normal_pixmap is row.normal_pixmap
    content = row.button._build_region_content(row.button.regions()[0])
    assert isinstance(content, _NavRowContent)
    assert content.normal_pixmap is row.normal_pixmap


def test_icon_list_widget_set_icon_updates_row_pixmap(qapp):
    widget = IconListWidget()
    item = widget.add_item("Settings")

    item.setIcon("settings")
    row = widget._rows[0]

    assert row.normal_pixmap is not None
    assert not row.normal_pixmap.isNull()
    assert row.button._normal_pixmap is row.normal_pixmap


def test_icon_list_widget_set_icon_accepts_icon_pair(qapp):
    widget = IconListWidget(selected_icon_mode="replace")
    item = widget.add_item("Settings")

    item.setIcon(("settings", "help"))
    row = widget._rows[0]

    assert row.icon == "settings"
    assert row.selected_icon == "help"
    assert row.normal_pixmap is not None
    assert row.selected_pixmap is not None
    assert row.selected_pixmap.cacheKey() != row.normal_pixmap.cacheKey()


def test_icon_list_widget_selection_updates_button_region_state(qapp):
    widget = IconListWidget()
    widget.add_item("Settings", icon="settings")

    widget.setCurrentRow(0)

    row = widget._rows[0]
    assert row.button.isChecked()
    assert ButtonState.CHECKED in row.button.region_states("_main")


def test_icon_list_widget_paints_icon_pixels(qtbot):
    widget = IconListWidget()
    widget.add_item("Settings", icon="settings")
    row = widget._rows[0]
    row.button.setFixedSize(180, 44)
    qtbot.addWidget(row.button)
    row.button.show()
    qtbot.waitExposed(row.button)

    image = QImage(row.button.size(), QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    row.button.render(painter)
    painter.end()

    icon_pixels = 0
    for x in range(8, 44):
        for y in range(8, 36):
            if image.pixelColor(x, y).alpha() > 0:
                icon_pixels += 1

    assert icon_pixels > 0


def test_icon_list_widget_default_selected_icon_mode_inverts(qapp):
    widget = IconListWidget()
    widget.add_item("Settings", icon="settings")
    row = widget._rows[0]

    assert widget.selectedIconMode() == "invert"
    assert row.selected_pixmap is not None
    assert not row.selected_pixmap.isNull()
    assert row.selected_pixmap.cacheKey() != row.normal_pixmap.cacheKey()


def test_icon_list_widget_replace_mode_uses_selected_icon(qapp):
    widget = IconListWidget(selected_icon_mode="replace")
    widget.add_item("Settings", icon="settings", selected_icon="help")
    row = widget._rows[0]

    assert row.selected_icon == "help"
    assert row.selected_pixmap is not None
    assert not row.selected_pixmap.isNull()
    assert row.selected_pixmap.cacheKey() != row.normal_pixmap.cacheKey()


def test_icon_list_widget_replace_mode_accepts_icon_pair(qapp):
    widget = IconListWidget(selected_icon_mode="replace")
    widget.set_items([IconListItem(text="Settings", icon=("settings", "help"))])
    row = widget._rows[0]

    assert row.icon == "settings"
    assert row.selected_icon == "help"
    assert row.selected_pixmap is not None
    assert not row.selected_pixmap.isNull()


def test_icon_list_widget_set_selected_icon_mode_refreshes_icons(qapp):
    widget = IconListWidget(selected_icon_mode="replace")
    item = widget.add_item("Settings", icon="settings", selected_icon="help")
    row = widget._rows[0]
    replace_key = row.selected_pixmap.cacheKey()

    widget.setSelectedIconMode("invert")

    assert widget.selectedIconMode() == "invert"
    assert row.selected_pixmap is not None
    assert row.selected_pixmap.cacheKey() != replace_key

    item.setSelectedIcon("calendar")
    widget.setSelectedIconMode("replace")

    assert row.selected_icon == "calendar"
    assert row.selected_pixmap is not None
    assert row.selected_pixmap.cacheKey() != row.normal_pixmap.cacheKey()
