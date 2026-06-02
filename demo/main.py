"""Entry point for the demo application."""

import sys
import os

# Add parent directory to path to allow imports when running as script
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon

from sli_ui_toolkit.icons import configure_icon_resolver
from sli_ui_toolkit.config import FlyoutTimingConfig, configure_toolkit
from sli_ui_toolkit.theme import ThemeManager
from sli_ui_toolkit.widgets import install_application_tooltips
from sli_ui_toolkit.palettes import FLUENT_LIGHT, FLUENT_DARK
from demo.app import MainWindow


def main():
    app = QApplication(sys.argv)

    # Configure icon resolver (empty fallback)
    configure_icon_resolver(lambda icon: QIcon())

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

    # Install tooltips
    install_application_tooltips(app)

    # Create and show main window
    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
