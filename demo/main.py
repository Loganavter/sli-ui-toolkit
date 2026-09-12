"""Entry point for the demo application."""

import sys
import os

# Add parent directory to path to allow imports when running as script
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon

from sli_ui_toolkit.icons import configure_icon_resolver
from sli_ui_toolkit.config import FlyoutTimingConfig, configure_toolkit
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.widgets import install_application_tooltips
from sli_ui_toolkit.palettes import FLUENT_LIGHT, FLUENT_DARK
from demo.app import MainWindow
from demo.icon_resolver import demo_icon_resolver


_NAMED_ICONS = {
    name: name
    for name in (
        "add", "add_circle", "remove", "delete", "close",
        "check", "chevron_down", "chevron_up", "chevron_left", "chevron_right",
        "divider_hidden", "line_weight", "info", "warning", "error",
        "settings", "folder", "file", "edit", "save", "search",
        "menu", "more", "play", "pause", "stop",
    )
}


def _native_qss(tm: ThemeManager) -> str:
    def hex_(key: str, fallback: str) -> str:
        c = tm.try_get_color(key)
        return c.name() if c else fallback

    tt_bg = hex_("tooltip.background", "#ffffff")
    tt_border = hex_("tooltip.border", "#c0c0c0")
    tt_text = hex_("tooltip.text", "#1f1f1f")
    item_hover = hex_("list_item.background.hover", "#f5f5f5")
    item_normal = hex_("list_item.background.normal", "#ffffff")
    item_text = hex_("list_item.text.normal", "#1f1f1f")
    highlight = hex_("Highlight", "#0078d4")
    highlight_text = hex_("HighlightedText", "#ffffff")
    return f"""
    QLabel#TooltipContentWidget {{
        background-color: {tt_bg};
        color: {tt_text};
        border: 1px solid {tt_border};
        border-radius: 5px;
        padding: 4px 8px;
    }}
    QListWidget {{
        background-color: {item_normal};
        color: {item_text};
        border: none;
        outline: 0;
    }}
    QListWidget::item {{
        padding: 4px 8px;
        border-radius: 4px;
    }}
    QListWidget::item:hover {{
        background-color: {item_hover};
    }}
    QListWidget::item:selected {{
        background-color: {highlight};
        color: {highlight_text};
    }}
    """


def main():
    app = QApplication(sys.argv)

    # Provide a glyph-based icon resolver so demo widgets get visible icons.
    configure_icon_resolver(demo_icon_resolver, named_icons=_NAMED_ICONS)

    # Configure toolkit
    configure_toolkit(
        timings=FlyoutTimingConfig(
            transient_auto_hide_delay_ms=300,
            flyout_animation_duration_ms=150,
            text_settings_flyout_animation_duration_ms=150,
        ),
        overlay_resolver=lambda widget: getattr(widget.window(), "overlay_layer", None),
    )

    # Configure theme with example palettes from sli_ui_toolkit.palettes
    theme_manager = ThemeManager.get_instance()
    theme_manager.register_palettes(light_palette=FLUENT_LIGHT, dark_palette=FLUENT_DARK)
    theme_manager.set_theme("light", app)

    # Apply native-widget QSS (QListWidget hover, tooltip bubble background)
    # — toolkit uses Qt-native widgets here and expects host app to theme them.
    app.setStyleSheet(_native_qss(theme_manager))
    theme_manager.theme_changed.connect(
        lambda *_: app.setStyleSheet(_native_qss(theme_manager))
    )

    # Install tooltips
    install_application_tooltips(app)

    # Create and show main window
    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
