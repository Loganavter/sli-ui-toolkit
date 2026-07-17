"""UiFont — toolkit single source of truth for UI typefaces."""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QVBoxLayout, QWidget

from sli_ui_toolkit import FLUENT_DARK, FLUENT_LIGHT, ThemeManager
from sli_ui_toolkit.managers import UiFont, apply_text_color, ui_font
from sli_ui_toolkit.ui.widgets.atomic.text_labels import Label


def test_ui_font_follows_pinned_family(qapp):
    manager = UiFont.get_instance()
    previous = manager._family_override
    app = QApplication.instance()
    previous_app = QFont(app.font())
    try:
        app.setFont(QFont("Sans Serif", 11))
        manager.set_family("Monospace")
        font = ui_font(pixel_size=16)
        assert font.family() == "Monospace"
        assert font.pixelSize() == 16
    finally:
        manager._family_override = previous
        app.setFont(previous_app)


def test_ui_font_sync_notifies_labels(qapp):
    manager = UiFont.get_instance()
    app = QApplication.instance()
    previous_app = QFont(app.font())
    previous_family = manager._family_override
    try:
        app.setFont(QFont("Monospace", 12))
        manager.set_family("Monospace")
        label = Label("Title", pixel_size=16)
        assert label.font().family() == "Monospace"

        app.setFont(QFont("Sans Serif", 12))
        manager.set_family("Sans Serif")
        assert label.font().family() == "Sans Serif"
        label.deleteLater()
    finally:
        manager._family_override = previous_family
        app.setFont(previous_app)


def test_apply_text_color_clears_color_stylesheet(qapp):
    label = QLabel("x")
    label.setStyleSheet("color: #ff0000;")
    apply_text_color(label, QColor("#00ff00"))
    assert not (label.styleSheet() or "").strip()
    assert (
        label.palette().color(QPalette.ColorRole.WindowText).name() == "#00ff00"
    )
    label.deleteLater()


def test_label_does_not_use_color_stylesheet(qapp):
    label = Label("Hello", pixel_size=13, color_token="dialog.text")
    assert "color:" not in (label.styleSheet() or "").lower()
    label.deleteLater()


def test_label_keeps_theme_color_after_reparent(qapp, tmp_path):
    """ParentChange must not leave Label stuck on the previous theme's text color."""
    app = QApplication.instance()
    tm = ThemeManager.get_instance()
    tm.register_palettes(FLUENT_LIGHT, FLUENT_DARK)
    qss = tmp_path / "probe.qss"
    qss.write_text("QDialog { background-color: @Window; }\n", encoding="utf-8")
    tm.register_qss_path(str(qss))
    tm.set_theme("light", app)

    dialog = QDialog()
    layout = QVBoxLayout(dialog)
    label = Label("Theme text", color_token="WindowText")
    layout.addWidget(label)
    tm.apply_theme_to_dialog(dialog)
    dialog.show()
    app.processEvents()

    tm.set_theme("dark", app)
    tm.apply_theme_to_dialog(dialog)
    app.processEvents()
    expected = tm.get_color("WindowText").name()
    assert label.palette().color(QPalette.ColorRole.WindowText).name() == expected

    host = QWidget()
    QVBoxLayout(host).addWidget(label)
    host.show()
    app.processEvents()
    assert label.palette().color(QPalette.ColorRole.WindowText).name() == expected

    label.deleteLater()
    host.deleteLater()
    dialog.deleteLater()


def test_apply_theme_to_dialog_palette_survives_qss_polish(qapp, tmp_path):
    """setPalette must run after unpolish/polish, or text stays on the old theme."""
    app = QApplication.instance()
    tm = ThemeManager.get_instance()
    tm.register_palettes(FLUENT_LIGHT, FLUENT_DARK)
    qss = tmp_path / "probe.qss"
    qss.write_text("QWidget { background-color: @Window; }\n", encoding="utf-8")
    tm.register_qss_path(str(qss))

    tm.set_theme("light", app)
    dialog = QDialog()
    plain = QLabel("plain")
    QVBoxLayout(dialog).addWidget(plain)
    tm.apply_theme_to_dialog(dialog)
    assert (
        dialog.palette().color(QPalette.ColorRole.WindowText).name()
        == QColor(FLUENT_LIGHT["WindowText"]).name()
    )

    tm.set_theme("dark", app)
    tm.apply_theme_to_dialog(dialog)
    dark_wt = QColor(FLUENT_DARK["WindowText"]).name()
    assert dialog.palette().color(QPalette.ColorRole.WindowText).name() == dark_wt
    assert dialog.palette().color(QPalette.ColorRole.Window).name() == QColor(
        FLUENT_DARK["Window"]
    ).name()

    plain.deleteLater()
    dialog.deleteLater()
