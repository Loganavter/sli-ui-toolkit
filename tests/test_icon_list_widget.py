from __future__ import annotations

from PySide6.QtCore import QPoint
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QSizePolicy

from sli_ui_toolkit.widgets import Button, IconListItem, IconListWidget
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.buttons.content import IconTextContent
from sli_ui_toolkit.ui.widgets.buttons.state import ButtonState


def test_icon_list_widget_button_factory_builds_custom_rows(qapp):
    built = []

    def factory(item):
        btn = Button(text=item.text, badge=3, variant="surface", size=(0, 40))
        built.append(btn)
        return btn

    widget = IconListWidget(button_factory=factory)
    widget.add_item("Alerts")
    row = widget._rows[0]

    assert row.custom is True
    assert row.button is built[0]
    assert row.button.getVariant() == "surface"


def test_icon_list_widget_button_factory_selection_still_works(qapp):
    def factory(item):
        return Button(text=item.text, variant="surface", size=(0, 40))

    widget = IconListWidget(button_factory=factory)
    widget.add_item("First")
    widget.add_item("Second")

    widget.setCurrentRow(1)

    assert widget.currentRow() == 1
    assert widget._rows[1].button.isChecked()
    assert not widget._rows[0].button.isChecked()


def test_icon_list_widget_button_factory_skips_default_icon_management(qapp):
    def factory(item):
        return Button(icon="settings", text=item.text, variant="surface", size=(0, 40))

    widget = IconListWidget(button_factory=factory, selected_icon_mode="invert")
    widget.add_item("Custom", icon="settings")
    row = widget._rows[0]

    # Default icon-swap/pixmap bookkeeping is skipped for factory-built rows —
    # the app's Button owns its own icon.
    assert row.normal_pixmap is None
    assert row.selected_pixmap is None

    widget.setCurrentRow(0)
    assert row.button.isChecked()


def test_icon_list_widget_resolves_string_icons(qapp):
    widget = IconListWidget()
    widget.add_item("Settings", icon="settings")

    row = widget._rows[0]

    assert row.normal_pixmap is not None
    assert not row.normal_pixmap.isNull()
    content = row.button._build_region_content(row.button.regions()[0])
    assert isinstance(content, IconTextContent)


def test_icon_list_widget_set_icon_updates_row_pixmap(qapp):
    widget = IconListWidget()
    item = widget.add_item("Settings")

    item.setIcon("settings")
    row = widget._rows[0]

    assert row.normal_pixmap is not None
    assert not row.normal_pixmap.isNull()


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
    qtbot.addWidget(widget)
    row.button.show()
    qtbot.waitExposed(row.button)

    image = QImage(row.button.size(), QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    # PySide6 requires targetOffset when rendering into a QPainter.
    row.button.render(painter, QPoint())
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


def test_icon_list_widget_rows_expand_without_text_minimum(qapp):
    long_text = "Very long navigation entry that should not stretch the sidebar"
    widget = IconListWidget()
    item = widget.add_item(long_text, icon="settings")
    row = widget._rows[0]

    assert row.button.minimumWidth() == 0
    assert row.button.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding
    assert row.button.toolTip() == ""

    updated_text = "Updated long navigation entry without a duplicate tooltip"
    item.setText(updated_text)

    assert row.button.toolTip() == ""


def test_nav_row_content_elides_text_to_available_width(qapp):
    long_text = "Navigation entry with text that cannot fit"
    widget = IconListWidget()
    widget.add_item(long_text, icon="settings")
    button = widget._rows[0].button
    button.setFixedSize(96, 44)

    class FakePainter:
        def __init__(self, source):
            self.source = source
            self.drawn_text = None

        def fontMetrics(self):
            return self.source.fontMetrics()

        def setFont(self, _font):
            pass

        def setPen(self, _pen):
            pass

        def drawPixmap(self, *_args):
            pass

        def drawText(self, _rect, _flags, text):
            self.drawn_text = text

    painter = FakePainter(button)
    ctx = button._make_context(painter)
    content = ctx.content
    assert isinstance(content, IconTextContent)

    content.draw(ctx, ThemeManager.get_instance())

    assert painter.drawn_text is not None
    assert painter.drawn_text != long_text
    assert "…" in painter.drawn_text


def test_scrollbar_appearance_does_not_shift_content(qapp):
    """The nav content keeps its width when the scrollbar appears (the
    floating overlay scrollbar reserves no layout space)."""
    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtWidgets import QWidget, QVBoxLayout

    host = QWidget()
    layout = QVBoxLayout(host)
    layout.setContentsMargins(0, 0, 0, 0)
    host.resize(200, 120)
    widget = IconListWidget()
    layout.addWidget(widget)
    host.show()
    qapp.processEvents()

    for i in range(10):
        widget.add_item(f"Item {i}")
    _spin_event_loop(qapp)
    assert widget._scroll.custom_v_scrollbar.isVisible()
    width_with_scrollbar = widget._host.width()
    assert width_with_scrollbar > 0

    widget.clear()
    for i in range(1):
        widget.add_item(f"Item {i}")
    _spin_event_loop(qapp)
    # The overlay bar fades out instead of disappearing instantly.
    for _ in range(40):
        if not widget._scroll.custom_v_scrollbar.isVisible():
            break
        _spin_event_loop(qapp)
    assert not widget._scroll.custom_v_scrollbar.isVisible()
    assert widget._host.width() == width_with_scrollbar


def _spin_event_loop(qapp):
    from PySide6.QtCore import QEventLoop, QTimer

    loop = QEventLoop()
    QTimer.singleShot(50, loop.quit)
    loop.exec()
    qapp.processEvents()
