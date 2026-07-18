from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import QDialog, QVBoxLayout, QWidget

from sli_ui_toolkit import (
    CustomTitleBar,
    FLUENT_DARK,
    FLUENT_LIGHT,
    ThemeManager,
    TitleBarMenu,
    TitleBarMenuStrip,
    TitleBarPresets,
    WindowChrome,
    WindowChromeConfig,
    apply_frameless,
    decorate_dialog,
    remove_frameless,
)
from sli_ui_toolkit.ui.widgets.buttons import Button
from sli_ui_toolkit.ui.widgets.composite.context_menu import ContextMenuAction


def _solid_icon(color: str) -> QIcon:
    pixmap = QPixmap(16, 16)
    pixmap.fill(QColor(color))
    return QIcon(pixmap)


class _WindowStateProbe(QWidget):
    def __init__(self):
        super().__init__()
        self.maximized = False

    def isMaximized(self):
        return self.maximized


def _register_palettes(qapp):
    tm = ThemeManager.get_instance()
    tm.register_palettes(FLUENT_LIGHT, FLUENT_DARK)
    tm.set_theme("dark", qapp)


def test_custom_title_bar_constructs(qapp):
    _register_palettes(qapp)
    bar = CustomTitleBar(title="Test")
    assert bar.objectName() == "CustomTitleBar"
    assert bar.height() == CustomTitleBar.HEIGHT
    bar.deleteLater()


def test_custom_title_bar_hides_buttons(qapp):
    bar = CustomTitleBar(
        title="X",
        show_minimize=False,
        show_maximize=False,
        show_close=True,
    )
    assert bar._min_btn is None
    assert bar._max_btn is None
    assert bar._close_btn is not None
    bar.deleteLater()


def test_custom_title_bar_set_title(qapp):
    _register_palettes(qapp)
    bar = CustomTitleBar(title="Old")
    bar.set_title("New")
    assert bar._title_label.text() == "New"
    bar.deleteLater()


def test_custom_title_bar_centers_title_with_close_only(qapp):
    """Close-only chrome used to pad the RIGHT, shifting the title left by 46px."""
    _register_palettes(qapp)
    bar = CustomTitleBar(
        title="Помощь",
        show_minimize=False,
        show_maximize=False,
        show_close=True,
    )
    bar.resize(880, CustomTitleBar.HEIGHT)
    bar.show()
    qapp.processEvents()
    bar._sync_balance_spacer()
    qapp.processEvents()
    mid = bar._center_host.geometry().center().x()
    assert abs(mid - bar.width() // 2) <= 1
    bar.deleteLater()


def test_custom_title_bar_centers_title_with_asymmetric_leading(qapp):
    _register_palettes(qapp)
    bar = CustomTitleBar(
        title="Settings",
        show_minimize=False,
        show_maximize=False,
        show_close=True,
    )
    leading = QWidget()
    leading.setFixedWidth(120)
    bar.set_leading(leading)
    bar.resize(880, CustomTitleBar.HEIGHT)
    bar.show()
    qapp.processEvents()
    bar._sync_balance_spacer()
    qapp.processEvents()
    mid = bar._center_host.geometry().center().x()
    assert abs(mid - bar.width() // 2) <= 1
    bar.deleteLater()


def test_custom_title_bar_leading_stays_left_when_balance_grows(qapp):
    """Language/menu width changes must not shove File/Help inward via left pad."""
    _register_palettes(qapp)
    bar = CustomTitleBar(
        title="Improve ImgSLI",
        show_minimize=True,
        show_maximize=True,
        show_close=True,
    )
    narrow = QWidget()
    narrow.setFixedWidth(40)
    bar.set_leading(narrow)
    bar.resize(1000, CustomTitleBar.HEIGHT)
    bar.show()
    qapp.processEvents()
    bar._sync_balance_spacer()
    qapp.processEvents()
    assert bar._left_balance.width() > 0
    assert bar._leading_host.geometry().x() == 0

    wide = QWidget()
    wide.setFixedWidth(200)
    bar.set_leading(wide)
    qapp.processEvents()
    bar._sync_balance_spacer()
    qapp.processEvents()
    assert bar._leading_host.geometry().x() == 0
    mid = bar._center_host.geometry().center().x()
    assert abs(mid - bar.width() // 2) <= 1
    bar.deleteLater()


def test_custom_title_bar_recenters_after_menu_strip_relabel(qapp):
    """Language rebuild used to sync while leading sizeHint was still 0."""
    _register_palettes(qapp)
    bar = CustomTitleBar(
        title="Improve ImgSLI",
        show_minimize=True,
        show_maximize=True,
        show_close=True,
    )
    bar.resize(1000, CustomTitleBar.HEIGHT)
    bar.show()
    qapp.processEvents()

    bar.set_menu_strip(
        TitleBarMenuStrip(
            [
                TitleBarMenu(
                    label="File",
                    icon=_solid_icon("#00ff00"),
                    entries=[ContextMenuAction("a", "A")],
                ),
                TitleBarMenu(
                    label="Help",
                    entries=[ContextMenuAction("b", "B")],
                ),
            ]
        )
    )
    qapp.processEvents()
    mid_en = bar._center_host.geometry().center().x()
    assert abs(mid_en - bar.width() // 2) <= 1

    bar.set_menu_strip(
        TitleBarMenuStrip(
            [
                TitleBarMenu(
                    label="Файл",
                    icon=_solid_icon("#00ff00"),
                    entries=[ContextMenuAction("a", "A")],
                ),
                TitleBarMenu(
                    label="Справка",
                    entries=[ContextMenuAction("b", "B")],
                ),
            ]
        )
    )
    # Deferred balance resync must run with the laid-out strip width.
    qapp.processEvents()
    mid_ru = bar._center_host.geometry().center().x()
    assert abs(mid_ru - bar.width() // 2) <= 1
    bar.deleteLater()


def test_custom_title_bar_title_uses_titlebar_pixel_size(qapp):
    """Regression: titlebar variant must register; get_label_variant used to
    silently fall back to body (12px), so size tweaks never applied."""
    _register_palettes(qapp)
    bar = CustomTitleBar(title="Sized")
    assert bar._title_label.variant() == "titlebar"
    assert bar._title_label.font().pixelSize() == 16
    bar.deleteLater()


def test_custom_title_bar_maximize_refresh_updates_button_region_icon(qapp):
    maximize_icon = _solid_icon("#ff0000")
    restore_icon = _solid_icon("#0000ff")
    window = _WindowStateProbe()
    bar = CustomTitleBar(
        title="Test",
        maximize_icon=maximize_icon,
        restore_icon=restore_icon,
        show_minimize=False,
        show_close=False,
    )
    bar.attach_window(window)

    assert bar._max_btn.region("_main").icon.cacheKey() == maximize_icon.cacheKey()

    window.maximized = True
    bar._refresh_maximize_icon()

    assert bar._max_btn.region("_main").icon.cacheKey() == restore_icon.cacheKey()
    window.deleteLater()
    bar.deleteLater()


def test_custom_title_bar_leading_button_blocks_drag(qapp):
    _register_palettes(qapp)
    bar = CustomTitleBar(title="Test")
    button = Button(text="File", variant="ghost", size=(48, CustomTitleBar.HEIGHT))
    bar.add_button(button)
    pos = bar.mapFromGlobal(button.mapToGlobal(button.rect().center()))
    assert not bar._is_draggable_at(pos)
    bar.deleteLater()


def test_title_bar_menu_strip_builds_triggers(qapp):
    from PySide6.QtGui import QIcon, QPixmap

    _register_palettes(qapp)
    icon = QIcon(QPixmap(16, 16))
    strip = TitleBarMenuStrip(
        [
            TitleBarMenu(label="File", icon=icon, entries=[("Quit", lambda: None)]),
            TitleBarMenu(
                label="Help",
                entries=[ContextMenuAction("help", "Show Help")],
            ),
        ]
    )
    assert len(strip.buttons()) == 2
    assert strip.buttons()[0]._text == "File"
    assert strip.buttons()[0]._icon_unchecked is not None
    assert strip.buttons()[0].getGap() == TitleBarMenuStrip.GAP
    assert strip.buttons()[1]._text == "Help"
    expected_h = CustomTitleBar.HEIGHT - 2 * TitleBarMenuStrip.V_INSET
    assert strip.buttons()[0].height() == expected_h
    strip.deleteLater()


def test_title_bar_presets_app_shell_adds_menu_strip(qapp):
    _register_palettes(qapp)
    bar = TitleBarPresets.app_shell(
        "Improve ImgSLI",
        menus=[TitleBarMenu(label="File", entries=[("Quit", lambda: None)])],
    )
    assert bar._leading_host.layout().count() == 1
    bar.deleteLater()


def test_custom_title_bar_app_icon_and_menu_strip(qapp):
    from PySide6.QtGui import QIcon, QPixmap

    _register_palettes(qapp)
    pixmap = QPixmap(16, 16)
    pixmap.fill()
    icon = QIcon(pixmap)
    bar = TitleBarPresets.app_shell(
        "Improve ImgSLI",
        icon=icon,
        menus=[TitleBarMenu(label="File", entries=[("Quit", lambda: None)])],
    )
    bar.show()
    assert bar._app_icon_label is not None
    assert not bar._app_icon_label.isHidden()
    assert bar._leading_host.layout().count() == 2
    # Icon stays when menu strip is replaced.
    bar.set_menu_strip(
        TitleBarMenuStrip([TitleBarMenu(label="Help", entries=[("About", lambda: None)])])
    )
    assert not bar._app_icon_label.isHidden()
    assert bar._leading_host.layout().count() == 2
    bar.deleteLater()


def test_apply_and_remove_frameless(qapp):
    w = QWidget()
    w.resize(200, 150)
    apply_frameless(w)
    assert bool(w.windowFlags() & Qt.WindowType.FramelessWindowHint)
    remove_frameless(w)
    assert not bool(w.windowFlags() & Qt.WindowType.FramelessWindowHint)
    w.deleteLater()


def test_decorate_dialog_inserts_title_bar(qapp):
    _register_palettes(qapp)
    dialog = QDialog()
    layout = QVBoxLayout(dialog)
    inner = QWidget(dialog)
    layout.addWidget(inner)

    bar = decorate_dialog(dialog, title="Hello")
    assert isinstance(bar, CustomTitleBar)
    assert dialog._csd_title_bar is bar
    assert dialog._csd_paint_state is not None
    assert dialog._csd_bg_layer is not None
    assert bar.parent() is dialog
    assert bool(dialog.windowFlags() & Qt.WindowType.FramelessWindowHint)
    dialog.deleteLater()


def test_decorate_dialog_attaches_close(qapp):
    dialog = QDialog()
    QVBoxLayout(dialog)
    bar = decorate_dialog(dialog, title="Hi", show_close=True)
    assert bar._close_btn is not None
    dialog.deleteLater()


def test_window_chrome_theme_refresh_updates_paint_state(qapp):
    _register_palettes(qapp)
    dialog = QDialog()
    QVBoxLayout(dialog)
    chrome = WindowChrome.install(dialog, config=WindowChromeConfig(title="Hi"))
    before = QColor(dialog._csd_paint_state["color"])
    ThemeManager.get_instance().set_theme("light", qapp)
    after = QColor(dialog._csd_paint_state["color"])
    assert before != after
    chrome.title_bar().deleteLater()
    dialog.deleteLater()
