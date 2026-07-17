"""ToastProgressBar paints accent fill over a rounded track."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QWidget

from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.ui.widgets.composite.toast import (
    ToastNotification,
    ToastProgressBar,
)

APP = QApplication.instance() or QApplication([])


def _register_toast_palette() -> None:
    tm = ThemeManager.get_instance()
    light = {
        "accent": QColor("#0078D4"),
        "toast.background": QColor("#ffffff"),
        "toast.text": QColor("#000000"),
        "toast.border": QColor("#19000000"),
        "toast.progress.background": QColor("#24000000"),
        "toast.progress.fill": QColor("#0078D4"),
    }
    tm.register_palettes(light_palette=light, dark_palette=light)
    tm.set_theme("light", APP)


def test_toast_progress_bar_value_and_colors():
    _register_toast_palette()
    bar = ToastProgressBar()
    bar.setRange(0, 100)
    bar.resize(200, 6)
    bar.setValue(40)
    assert bar.value() == 40
    assert bar._fill_color().name() == "#0078d4"
    assert bar._track_color().alpha() > 0
    # Smoke: paint path must not raise.
    bar.grab()


def test_toast_width_does_not_shrink_on_shorter_label():
    _register_toast_palette()
    host = QWidget()
    host.resize(800, 600)
    toast = ToastNotification(host)
    toast.show_message(
        "Saving\n.../long/path/to/result.png...",
        max_width=360,
        progress=10,
        duration=0,
    )
    wide = toast.width()
    toast.update_message(
        "Saved result.png",
        max_width=360,
        success=True,
        duration=0,
        actions=[],
        progress=100,
    )
    assert toast.width() == wide
    assert toast.progress_bar.value() == 100
