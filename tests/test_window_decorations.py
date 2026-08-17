from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import QDialog, QHBoxLayout, QVBoxLayout, QWidget

from sli_ui_toolkit import (
    CustomTitleBar,
    FLUENT_DARK,
    FLUENT_LIGHT,
    ThemeManager,
    TitleBarPresets,
    WindowChrome,
    WindowChromeConfig,
    apply_frameless,
    decorate_dialog,
    remove_frameless,
)
from sli_ui_toolkit.ui.widgets.buttons import Button


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
    assert bar._controls._min_btn is None
    assert bar._controls._max_btn is None
    assert bar._controls._close_btn is not None
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


def test_custom_title_bar_recenters_after_leading_width_change(qapp):
    """Leading-zone width change must keep the title centered (balance resync)."""
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

    def _leading(label: str) -> QWidget:
        widget = QWidget(bar)
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(Button(label, variant="ghost", size=(72, 24), parent=widget))
        layout.addWidget(Button("Help", variant="ghost", size=(64, 24), parent=widget))
        return widget

    bar.set_leading(_leading("File"))
    qapp.processEvents()
    mid_en = bar._center_host.geometry().center().x()
    assert abs(mid_en - bar.width() // 2) <= 1

    # Simulate a language rebuild: swap in a wider leading widget.
    bar.set_leading(_leading("Файл"))
    # Deferred balance resync must run with the laid-out widget width.
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

    assert bar._controls._max_btn.region("_main").icon.cacheKey() == maximize_icon.cacheKey()

    window.maximized = True
    bar._controls.refresh_window_state(window)

    assert bar._controls._max_btn.region("_main").icon.cacheKey() == restore_icon.cacheKey()
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


def test_title_bar_presets_app_shell_hosts_leading_widget(qapp):
    _register_palettes(qapp)
    leading = QWidget()
    bar = TitleBarPresets.app_shell("Improve ImgSLI", leading=leading)
    assert bar._leading_host.layout().count() == 1
    assert bar._leading_host.layout().itemAt(0).widget() is leading
    bar.deleteLater()


def test_custom_title_bar_app_icon_and_leading_widget(qapp):
    from PySide6.QtGui import QIcon, QPixmap

    _register_palettes(qapp)
    pixmap = QPixmap(16, 16)
    pixmap.fill()
    icon = QIcon(pixmap)
    bar = TitleBarPresets.app_shell(
        "Improve ImgSLI",
        icon=icon,
    )
    bar.show()
    assert bar._app_icon_label is not None
    assert not bar._app_icon_label.isHidden()
    assert bar._leading_host.layout().count() == 1
    # Icon stays when the leading widget is replaced.
    first = QWidget()
    second = QWidget()
    bar.set_leading(first)
    assert not bar._app_icon_label.isHidden()
    assert bar._leading_host.layout().count() == 2
    bar.set_leading(second)
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
    assert bar._controls._close_btn is not None
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


def test_outer_resize_band_insets_chrome_and_expands_geometry(qapp):
    """The outer resize band: the window surface carries the band
    (transparent), the rounded body / title bar / layout are inset by it, and
    resize()/setGeometry() keep content-size semantics by re-expanding."""
    _register_palettes(qapp)
    dialog = QDialog()
    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(0, 0, 0, 0)
    inner = QWidget(dialog)
    layout.addWidget(inner)

    dialog.setMinimumSize(300, 200)
    dialog.resize(300, 200)
    chrome = WindowChrome.install(
        dialog,
        config=WindowChromeConfig(title="Hi", resizable=True, resize_margin=8),
    )
    try:
        # The already-set size is expanded at install: the surface carries
        # the band from the very first frame.
        assert dialog.width() == 300 + 16
        assert dialog.height() == 200 + 16
        assert dialog.property("_csd_outer_band") == 8
        # The layout margin carries the band on every side.
        margins = layout.contentsMargins()
        assert margins.left() == 8
        assert margins.right() == 8
        assert margins.bottom() == 8
        # The title bar is inset by the band.
        bar = dialog._csd_title_bar
        assert bar.geometry().left() == 8
        assert bar.geometry().top() == 8
        # The rounded body layer is inset by the band.
        bg = dialog._csd_bg_layer
        dialog.resize(300, 200)
        qapp.processEvents()
        assert bg.geometry().left() == 8
        assert bg.geometry().top() == 8
        assert bg.width() == 300 - 16
        assert bg.height() == 200 - 16
        # resize keeps content-size semantics: the surface grows by 2*band.
        dialog.resize(340, 240)
        assert dialog.width() == 340 + 16
        assert dialog.height() == 240 + 16
        # The resize filter's edge zone straddles the visible body edge.
        from sli_ui_toolkit.ui.windows.frameless import _ResizeFilter

        f = dialog.findChild(_ResizeFilter)
        assert f is not None
        assert f._resize_margin == 8 + 8
    finally:
        dialog.deleteLater()
