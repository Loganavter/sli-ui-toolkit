"""ListPanel stylesheet/theme application — split out of ``widget.py`` to
keep the facade thin, matching the ``appearance.py`` precedent used in
``ui/windows/custom_title_bar/``. Functions take the panel as their first
argument."""

from __future__ import annotations

from PySide6.QtGui import QColor


def apply_style(panel) -> None:
    accent = panel.theme_manager.try_get_color("accent")
    if accent is None or not accent.isValid():
        accent = panel.theme_manager.get_color("accent")
    panel.drop_overlay.set_color(accent)

    # Paint the panel surface ourselves so the widget renders correctly
    # without a host-supplied QSS sheet. Selector keyed on the widget's
    # own objectName — subclasses that keep their legacy name (e.g. the
    # flyout panel) still match their own rule.
    bg_color = panel.theme_manager.get_color("surface.background").name(
        QColor.NameFormat.HexArgb
    )
    border_color = panel.theme_manager.get_color("flyout.border").name(
        QColor.NameFormat.HexArgb
    )
    panel.setStyleSheet(
        f"#{panel.objectName()} {{"
        f"background-color: {bg_color};"
        f"border: 1px solid {border_color};"
        "border-radius: 8px;"
        "}"
    )
    try:
        panel.scroll_area.setStyleSheet(
            "background-color: transparent; border: none;"
        )
        panel.content_widget.setStyleSheet("background: transparent;")
    except Exception:
        pass
