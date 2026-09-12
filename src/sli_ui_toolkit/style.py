"""Public widget style token helpers.

Hosts use `WidgetStyleTokens` together with `read_widget_style` /
`update_widget_style` to push app-specific colors and geometry into
custom-painted widgets via Qt dynamic properties.
"""

from sli_ui_toolkit.ui.widgets.style_bridge import (
    WidgetStyleTokens,
    icon_size_qsize,
    read_widget_style,
    update_widget_style,
)

__all__ = [
    "WidgetStyleTokens",
    "icon_size_qsize",
    "read_widget_style",
    "update_widget_style",
]
